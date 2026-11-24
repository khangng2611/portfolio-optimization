import { expect, test, type Browser, type Page, type TestInfo } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import { submitLogin } from './login-form';

// This gate deliberately avoids localhost:3000, which belongs to the user's SSH tunnel.
const origin = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3100';
const generated = resolve('../../infra/local/.generated');
const directory = resolve(generated, 'user-selection');
const receiptPath = resolve(directory, 'browser-receipt.json');
const verifyOnly = process.env.USER_SELECTION_VERIFY_RECEIPT === '1';
const requirePositive = process.env.USER_SELECTION_REQUIRE_POSITIVE === '1';
const legacyPath = process.env.USER_SELECTION_LEGACY_RECEIPT ?? resolve(generated, 'phase1-browser-receipt.json');
type Value = Record<string, any>;

test.use({ baseURL: origin });
test.beforeAll(() => {
  const url = new URL(origin);
  if (process.env.E2E_DISPOSABLE_STACK !== '1' || !['localhost', '127.0.0.1'].includes(url.hostname) || url.port === '3000') throw new Error('Use the disposable localhost stack on port3100; port3000 is reserved');
});
test.afterEach(async ({ browser }) => {
  for (const context of browser.contexts()) await context.close();
});
function phase(info: TestInfo, value: string) { info.annotations.push({ type: 'safe-phase', description: value }); console.log(`BROWSER_PHASE: ${value}`); }
async function login(browser: Browser, username: string) {
  const accounts = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  const account = accounts.users.find((user: { username: string }) => user.username === username);
  if (!account?.password) throw new Error('Disposable account unavailable');
  const page = await browser.newPage({ baseURL: origin });
  await page.goto('/login'); await submitLogin(page, account); return page;
}
async function get(page: Page, path: string): Promise<any> { const response = await page.request.get(path); expect(response.status()).toBe(200); return response.json(); }
async function save(value: Value) { await mkdir(directory, { recursive: true, mode: 0o700 }); await writeFile(receiptPath, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 }); }
async function postUI(page: Page, path: string, action: () => Promise<unknown>, status: number) {
  const pending = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === path);
  await action(); const response = await pending; expect(response.status()).toBe(status);
  expect(Boolean(response.request().headers()['x-csrf-token'])).toBe(true);
  return { result: await response.json(), body: response.request().postDataJSON(), headers: response.request().headers() };
}
async function create(page: Page, ids: string[]) {
  await page.goto('/#create');
  await page.getByLabel(/^Tên danh mục/).fill(`User selection ${Date.now()}`);
  await page.getByLabel(/^Vốn kế hoạch \(VND\)/).fill('100000000');
  await page.getByLabel('Thời gian đầu tư (tháng)').fill('36');
  await page.getByRole('button', { name: 'Chọn tài sản', exact: true }).click();
  await page.getByRole('button', { name: /^Xem tất cả \d+ mã$/ }).click();
  for (const asset of ids) await page.getByTestId('available-assets').getByRole('button', { name: `Thêm ${asset} vào rổ tài sản`, exact: true }).click();
  if (!ids.includes('VFF')) await expect(page.getByTestId('selected-assets').locator('[data-asset-id="VFF"]')).toHaveCount(0);
  await expect(page.getByText('Mã đã chọn vẫn có thể nhận tỷ trọng 0%.', { exact: false }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  await page.getByRole('radio', { name: 'Vừa · Từ 5% đến dưới 15%', exact: true }).check();
  await page.getByRole('radio', { name: 'Tối đa 10%', exact: true }).check();
  await page.getByRole('radio', { name: 'Từ 6 tháng trở lên', exact: true }).check();
  await page.getByRole('button', { name: 'Xem lại hồ sơ', exact: true }).click();
  const sent = await postUI(page, '/api/v1/onboarding/portfolios', () => page.getByTestId('create-portfolio-submit').click(), 201);
  expect(sent.body.asset_ids).toEqual(ids); expect(sent.body).not.toHaveProperty('universe_id');
  expect(sent.result.asset_selection.candidate_asset_ids).toEqual(ids);
  expect(sent.result.constraints).toMatchObject({ defensive_asset_ids: ['VFF'], min_defensive_weight: .15, max_non_defensive_weight: .7, max_position_weight: .5 });
  return sent.result;
}
async function blocked(page: Page, portfolio: Value, code: string) {
  const ready = await get(page, `/api/v1/portfolios/${portfolio.id}/readiness`);
  expect(ready.readiness_kind).toBe('user-selection-v1'); expect(ready.reason_code).toBe(code);
  await page.goto(`/#proposal?portfolio=${portfolio.id}`);
  await page.getByTestId('strategy-BL_ML').check();
  const fallback = page.getByRole('checkbox', { name: /Cho phép phương án EW/ });
  await fallback.uncheck(); await expect(fallback).not.toBeChecked(); await expect(page.getByTestId('propose-portfolio')).toBeDisabled();
  await fallback.check(); await expect(page.getByTestId('propose-portfolio')).toBeDisabled();
  expect(await get(page, `/api/v1/portfolios/${portfolio.id}/recommendations`)).toEqual([]);
  if (code === 'VFF_STALE') {
    await expect(page.getByText(/NAV VFF đủ điều kiện đã quá 7 ngày/).first()).toBeVisible();
    const rejected = await mutate(page, `/api/v1/portfolios/${portfolio.id}/recommendations`, { strategy: 'BL_ML', fallback_strategy: 'EW' }, randomUUID(), portfolio.version, 409);
    expect(rejected.error.code).toBe('VFF_STALE');
    expect(rejected.error.details).toMatchObject({ asset_id: 'VFF', max_age_days: 7 });
    expect(rejected.error.details.age_days).toBeGreaterThan(7);
    expect(await get(page, `/api/v1/portfolios/${portfolio.id}/recommendations`)).toEqual([]);
  }
  return ready;
}
async function optionalReviewPublication(browser: Browser, snapshotOverride?: string) {
  const modelId = process.env.USER_SELECTION_MODEL_ID, snapshotId = snapshotOverride ?? process.env.USER_SELECTION_SNAPSHOT_ID;
  if (!modelId || !snapshotId) return null;
  const reviewer = await login(browser, 'model-reviewer');
  await reviewer.goto(`/#model-review?model=${modelId}`);
  const model = await get(reviewer, `/api/v1/ml/models/${modelId}`);
  expect(model.metadata.schema_version).toBe(5); expect(model.metadata.native_member_count).toBe(model.metadata.covered_asset_ids.length * 5);
  expect(model.metadata.target_native_member_count).toBe(150);
  if (model.status === 'CANDIDATE') {
    await reviewer.getByTestId('model-review-reason').fill('Verified asset-wise native ensemble coverage, purged labels, fit epoch, source and booster hashes.');
    await reviewer.getByTestId('model-review-preview').click();
    const review = await postUI(reviewer, `/api/v1/ml/models/${modelId}/reviews`, () => reviewer.getByTestId('model-review-submit').click(), 200);
    expect(review.headers['if-match']).toBe(`"${model.version}"`);
  }
  await expect(reviewer.getByTestId('model-detail')).toHaveAttribute('data-artifact-ready', 'true', { timeout: 90_000 });
  const operator = await login(browser, 'data-operator');
  await operator.goto(`/#market-publications?snapshot=${snapshotId}&model=${modelId}`);
  await operator.getByTestId('publication-universe').fill('VN_USER_SELECTION');
  await operator.getByTestId('publication-model').selectOption(modelId);
  await expect(operator.getByTestId('publication-max-age')).toHaveValue('7');
  const publication = await postUI(operator, '/api/v1/market/publications', () => operator.getByTestId('market-publication-submit').click(), 202);
  await expect.poll(async () => (await get(operator, `/api/v1/market/publications/${publication.result.job_id}`)).status, { timeout: 90_000 }).toBe('SUCCEEDED');
  return { model_id: modelId, model: await get(reviewer, `/api/v1/ml/models/${modelId}`), publication: await get(operator, `/api/v1/market/publications/${publication.result.job_id}`) };
}

test('Asset basket moves individual and filtered bulk choices without creating a portfolio', async ({ browser }) => {
  const page = await login(browser, 'alice');
  await page.goto('/#create');
  await page.getByLabel('Tên danh mục').fill('Kiểm tra rổ tài sản');
  await page.getByRole('button', { name: 'Chọn tài sản', exact: true }).click();
  await page.getByRole('button', { name: /^Xem tất cả \d+ mã$/ }).click();
  const available = page.getByTestId('available-assets'), basket = page.getByTestId('selected-assets');
  await expect(available.locator('[data-asset-id]')).toHaveCount(32);
  await available.getByRole('button', { name: 'Thêm FPT vào rổ tài sản', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(available.locator('[data-asset-id="FPT"]')).toHaveCount(0);
  await expect(basket.locator('[data-asset-id="FPT"]')).toHaveCount(1);
  await expect(available.getByRole('button', { name: 'Thêm GAS vào rổ tài sản', exact: true })).toBeFocused();
  await page.getByRole('searchbox', { name: 'Tìm tài sản để thêm', exact: true }).fill('VFF');
  await available.getByRole('button', { name: 'Thêm tất cả kết quả', exact: true }).click();
  await expect(basket.locator('[data-asset-id]')).toHaveCount(2);
  await basket.getByRole('button', { name: 'Bỏ FPT khỏi rổ tài sản', exact: true }).click();
  await expect(basket.locator('[data-asset-id]')).toHaveCount(1);
  await basket.getByRole('button', { name: 'Bỏ tất cả', exact: true }).click();
  await expect(basket.getByText('Rổ tài sản đang trống', { exact: true })).toBeVisible();
  await page.getByRole('searchbox', { name: 'Tìm tài sản để thêm', exact: true }).fill('');
  await expect(available.locator('[data-asset-id]')).toHaveCount(32);
  await expect(page.getByRole('button', { name: 'Tiếp tục', exact: true })).toBeDisabled();
  await page.getByRole('combobox', { name: 'Loại tài sản', exact: true }).selectOption('gold');
  await expect(available.locator('[data-asset-id]')).toHaveCount(1);
  await expect(available.locator('[data-asset-id="GOLD"]')).toHaveCount(1);
  await page.getByRole('combobox', { name: 'Loại tài sản', exact: true }).selectOption('');
  const search = page.getByRole('searchbox', { name: 'Tìm tài sản để thêm', exact: true });
  await search.fill('chuyển đổi số');
  await expect(available.locator('[data-asset-id]')).toHaveCount(1);
  await expect(available.locator('[data-asset-id="FPT"]')).toHaveCount(1);
  await search.fill('asset-does-not-exist');
  await expect(available.getByText('Không có tài sản khớp bộ lọc.', { exact: true })).toBeVisible();
  await search.fill('');
  const captures = resolve('../../output/playwright/asset-transfer-v26-real');
  await mkdir(captures, { recursive: true });
  await available.getByRole('button', { name: 'Thêm FPT vào rổ tài sản', exact: true }).click();
  await page.getByRole('button', { name: 'Xem danh sách đơn', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Bỏ FPT khỏi rổ tài sản' })).toBeVisible();
  await page.getByRole('button', { name: /^Xem tất cả \d+ mã$/ }).click();
  await expect(basket.locator('[data-asset-id="FPT"]')).toHaveCount(1);
  await available.getByRole('region', { name: 'Danh sách tài sản hỗ trợ', exact: true }).evaluate(element => { element.scrollTop = 0; });
  for (const [name, width] of [['desktop', 1440], ['tablet-wide', 1024], ['mobile', 375]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width > 800) {
      const left = (await available.boundingBox())!, right = (await basket.boundingBox())!;
      expect(right.x).toBeGreaterThanOrEqual(left.x + left.width);
      expect(right.y).toBeCloseTo(left.y, 0);
    } else {
      await expect(basket).toBeHidden();
      await page.getByRole('button', { name: 'Rổ của bạn · 1', exact: true }).click();
      await expect(available).toBeHidden();
      await expect(basket.getByRole('button', { name: 'Bỏ FPT khỏi rổ tài sản' })).toBeVisible();
    }
    await page.screenshot({ path: resolve(captures, `${name}.png`), fullPage: true, mask: [page.locator('.account-name')] });
  }
  await page.close();
});

test('User selection basket preserves newer search focus after clearing selections', async ({ browser }, info) => {
  phase(info, 'asset-basket-focus');
  const page = await login(browser, 'alice');
  await page.goto('/#create');
  await page.getByLabel('Tên danh mục').fill('Kiểm tra rổ tài sản');
  await page.getByRole('button', { name: 'Chọn tài sản', exact: true }).click();
  await page.getByRole('button', { name: /^Xem tất cả \d+ mã$/ }).click();
  await page.getByTestId('available-assets').getByRole('button', { name: 'Thêm FPT vào rổ tài sản', exact: true }).click();
  await page.evaluate(() => {
    document.querySelector<HTMLButtonElement>('[data-testid="selected-assets"] .asset-transfer-header button')!.click();
    document.querySelector<HTMLInputElement>('input[type="search"]')!.focus();
  });
  await page.evaluate(() => new Promise<void>(done => requestAnimationFrame(() => done())));
  await expect(page.getByRole('searchbox', { name: 'Tìm tài sản để thêm', exact: true })).toBeFocused();
  await expect(page.getByTestId('selected-assets').locator('[data-asset-id]')).toHaveCount(0);
  await page.close();
});

test('User selection catalog and drafts preserve policy while stale VFF blocks submission', async ({ browser }, info) => {
  test.skip(verifyOnly, 'Persistence mode'); test.setTimeout(300_000); phase(info, 'user-selection-drafts');
  const operations = await optionalReviewPublication(browser);
  const page = await login(browser, 'alice');
  const catalog = await get(page, '/api/v1/assets/catalog');
  expect(catalog.selection_enabled).toBe(true); expect(catalog.assets).toHaveLength(32);
  expect(new Set(catalog.assets.map((asset: Value) => asset.asset_id)).size).toBe(32);
  expect(catalog.assets.map((asset: Value) => asset.asset_id)).not.toContain('DEMO_STOCK');
  const legacy = JSON.parse(await readFile(legacyPath, 'utf8'));
  expect(await get(page, `/api/v1/recommendations/${legacy.proposal.id}`)).toEqual(legacy.proposal);
  const one = await create(page, ['FPT']); await blocked(page, one, 'INSUFFICIENT_ASSETS');
  const stocks = await create(page, ['FPT', 'MWG', 'VCB']); await blocked(page, stocks, 'DEFENSIVE_ASSET_REQUIRED');
  const cases = [];
  for (const ids of [['FPT', 'MWG', 'VCB', 'VFF'], ['ACB', 'BID', 'CTG', 'DGC', 'FPT', 'GAS', 'GVR', 'HDB', 'GOLD', 'VFF']]) {
    const portfolio = await create(page, ids);
    const readiness = await get(page, `/api/v1/portfolios/${portfolio.id}/readiness`);
    if (readiness.reason_code === 'VFF_STALE') await blocked(page, portfolio, 'VFF_STALE');
    cases.push({ portfolio, draft_readiness: readiness, readiness, proposal: null, positive_status: 'NOT_RUN' });
  }
  if (process.env.USER_SELECTION_EXPECT_VFF_STALE !== '0') expect(cases.some(item => item.readiness.reason_code === 'VFF_STALE')).toBe(true);
  await save({ schema_version: 1, checked_at: new Date().toISOString(), origin, catalog, operations, one, stocks, cases, legacy });
});

test('User selection explicit BL_ML succeeds only with actual eligible data', async ({ browser }, info) => {
  test.skip(verifyOnly, 'Persistence mode'); test.setTimeout(300_000); phase(info, 'user-selection-positive-check');
  const saved = JSON.parse(await readFile(receiptPath, 'utf8'));
  if (process.env.USER_SELECTION_FRESH_SNAPSHOT_ID) {
    saved.stale_operations = saved.operations;
    saved.operations = await optionalReviewPublication(browser, process.env.USER_SELECTION_FRESH_SNAPSHOT_ID);
    expect(saved.operations).not.toBeNull();
    await save(saved);
  }
  const page = await login(browser, 'alice');
  const operator = await login(browser, 'data-operator'), reviewer = await login(browser, 'model-reviewer');
  let succeeded = 0;
  for (const entry of saved.cases) {
    const p = entry.portfolio;
    const readiness = await get(page, `/api/v1/portfolios/${p.id}/readiness`);
    entry.readiness = readiness;
    if (!readiness.strategies.find((strategy: Value) => strategy.strategy === 'BL_ML')?.can_submit) { entry.positive_status = 'BLOCKED'; continue; }
    await page.goto(`/#proposal?portfolio=${p.id}`); await page.getByTestId('strategy-BL_ML').check();
    const fallback = page.getByRole('checkbox', { name: /Cho phép phương án EW/ }); await expect(fallback).not.toBeChecked();
    await page.getByTestId('propose-portfolio').click();
    const sent = await postUI(page, `/api/v1/portfolios/${p.id}/recommendations`, () => page.getByTestId('confirm-proposal').click(), 202);
    expect(sent.body).toEqual({ strategy: 'BL_ML' }); expect(sent.headers['if-match']).toBe(`"${p.version}"`);
    await expect(page.getByTestId('accept-proposal')).toBeEnabled({ timeout: 90_000 });
    const job = await get(page, `/api/v1/jobs/portfolio/${sent.result.job_id}`); expect(job.status).toBe('SUCCEEDED');
    const proposal = await get(page, `/api/v1/recommendations/${job.recommendation_id}`);
    const candidates = p.asset_selection.candidate_asset_ids, proof = proposal.selection_proof, c = proposal.constraints;
    expect(proposal.asset_ids).toEqual(candidates); expect(proposal.strategy).toBe('BL_ML'); expect(proposal.fallback_reason).toBeNull();
    expect(proposal.selection_context.revision_id).toBe(p.asset_selection.revision_id); expect(proof.candidate_hash).toBe(p.asset_selection.candidate_hash);
    expect(proof.selection_hash).toMatch(/^[a-f0-9]{64}$/); expect(proof.active_asset_ids.every((asset: string) => candidates.includes(asset))).toBe(true);
    const equityCount = candidates.filter((asset: string) => !['GOLD', 'VFF'].includes(asset)).length;
    expect(proof.selected_equity_ids).toHaveLength(Math.min(5, equityCount));
    expect(proof.active_asset_ids).toEqual(candidates.filter((asset: string) => ['GOLD', 'VFF'].includes(asset) || proof.selected_equity_ids.includes(asset)));
    expect(proof.rejected_equity_ids).toHaveLength(Math.max(0, equityCount - 5));
    for (const asset of candidates) { const status = readiness.asset_status.find((item: Value) => item.asset_id === asset); expect(status).toBeDefined(); expect(status.age_days).toBeGreaterThanOrEqual(0); expect(status.age_days).toBeLessThanOrEqual(7); }
    expect(proposal.inputs_provenance.data_origin).toBe('real');
    const weights = proposal.weights.map(Number); expect(weights.reduce((a: number, b: number) => a + b, 0)).toBeCloseTo(1, 7);
    weights.forEach((w: number, i: number) => { expect(w).toBeGreaterThanOrEqual(0); expect(w).toBeLessThanOrEqual(c.max_position_weight + 1e-7); if (!proof.active_asset_ids.includes(candidates[i])) expect(w).toBe(0); });
    const defensive = weights[candidates.indexOf('VFF')]; expect(defensive + 1e-7).toBeGreaterThanOrEqual(c.min_defensive_weight); expect(1 - defensive).toBeLessThanOrEqual(c.max_non_defensive_weight + 1e-7);
    expect(proposal.input_hash).toBe(proof.input_hash);
    expect(proposal.data_snapshot_id).toBe(readiness.inputs.snapshot_id);
    expect(proposal.bundle_hash).toBe(readiness.inputs.bundle_hash);
    expect(proposal.model_bundle_id).toBe(readiness.inputs.model_bundle_id);
    expect(proof.snapshot_hash).toBe(readiness.inputs.provenance.snapshot_hash);
    expect(proof.panel_hash).toBe(readiness.inputs.provenance.panel_hash);
    const inference = proposal.diagnostics.inference;
    expect(inference.manifest_hash).toBe(readiness.inputs.model_bundle_id);
    const snapshot = await get(operator, `/api/v1/market/snapshots/${proposal.data_snapshot_id}`);
    expect(snapshot.content_hash).toBe(proof.snapshot_hash);
    const model = await get(reviewer, `/api/v1/ml/models/${inference.model_id}`);
    expect(model.status).toBe('APPROVED'); expect(model.artifact_ready).toBe(true);
    expect(model.metadata.schema_version).toBe(5); expect(model.metadata.fit_epoch).toBe(inference.fit_epoch);
    if (saved.operations) {
      expect(inference.model_id).toBe(saved.operations.model_id);
      expect(proposal.bundle_hash).toBe(saved.operations.publication.result.sha256);
      expect(proposal.data_snapshot_id).toBe(saved.operations.publication.request.snapshot_id);
    }
    entry.snapshot = snapshot; entry.model = model;
    entry.proposal = proposal; entry.job = job; entry.positive_status = 'SUCCEEDED'; succeeded++;
  }
  await save(saved);
  if (requirePositive) expect(succeeded).toBe(saved.cases.length);
  test.skip(!succeeded, 'Actual selected data/model blocked every positive case; private receipt records the reasons');
});

test('User selection basket saves all 32 assets, edits, reloads and accepts a real MVO target', async ({ browser }, info) => {
  test.skip(verifyOnly, 'Persistence mode'); test.setTimeout(300_000); phase(info, 'asset-basket-save-edit-accept');
  const page = await login(browser, 'alice');
  const catalog = await get(page, '/api/v1/assets/catalog');
  const ids: string[] = catalog.assets.map((asset: Value) => asset.asset_id);
  expect(ids).toHaveLength(32);
  expect(catalog.assets.every((asset: Value) => asset.description === null && asset.display_name === asset.asset_id)).toBe(true);
  const metadata = await get(page, '/api/v1/market/assets');
  const supportedMetadata = metadata.filter((asset: Value) => ids.includes(asset.asset_id));
  expect(supportedMetadata).toHaveLength(32);
  expect(supportedMetadata.every((asset: Value) => asset.description && asset.metadata_source)).toBe(true);
  expect(metadata.find((asset: Value) => asset.asset_id === 'VFF')).toMatchObject({ metadata_source: 'fmarket:vff:21', metadata_source_symbol: 'VFF' });
  expect(metadata.find((asset: Value) => asset.asset_id === 'GOLD')).toMatchObject({ metadata_source: 'giavang:sjc-sell-hcm', metadata_source_symbol: 'GOLD' });
  await page.goto('/#create');
  await page.getByLabel(/^Tên danh mục/).fill(`Asset basket V2.6 real ${Date.now()}`);
  await page.getByRole('button', { name: 'Chọn tài sản', exact: true }).click();
  await page.getByRole('button', { name: /^Xem tất cả \d+ mã$/ }).click();
  await expect(page.getByTestId('available-assets').getByText(metadata.find((asset: Value) => asset.asset_id === 'FPT').display_name, { exact: true })).toBeVisible();
  const available = page.getByTestId('available-assets'), basket = page.getByTestId('selected-assets');
  await available.getByRole('button', { name: 'Thêm tất cả', exact: true }).click();
  await expect(basket.locator('[data-asset-id]')).toHaveCount(32);
  await expect(available.locator('[data-asset-id]')).toHaveCount(0);
  await basket.getByRole('button', { name: 'Bỏ tất cả', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Tiếp tục', exact: true })).toBeDisabled();
  await page.getByRole('searchbox', { name: 'Tìm tài sản để thêm', exact: true }).fill('FPT');
  await available.getByRole('button', { name: 'Thêm tất cả kết quả', exact: true }).click();
  await page.getByRole('searchbox', { name: 'Tìm tài sản để thêm', exact: true }).fill('');
  await available.getByRole('button', { name: 'Thêm tất cả', exact: true }).click();
  await expect(basket.locator('[data-asset-id]')).toHaveCount(32);
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  for (const name of ['Vừa · Từ 5% đến dưới 15%', 'Tối đa 10%', 'Từ 6 tháng trở lên']) await page.getByRole('radio', { name, exact: true }).check();
  await page.getByRole('button', { name: 'Xem lại hồ sơ', exact: true }).click();
  const created = await postUI(page, '/api/v1/onboarding/portfolios', () => page.getByTestId('create-portfolio-submit').click(), 201);
  expect(created.body.asset_ids).toEqual(ids);
  expect(created.body).not.toHaveProperty('universe_id');
  const base = `/api/v1/portfolios/${created.result.id}`;
  expect((await get(page, base)).asset_selection.candidate_asset_ids).toEqual(ids);

  await page.goto(`/#edit?portfolio=${created.result.id}`);
  const editor = page.locator('section.panel').filter({ has: page.getByRole('heading', { name: 'Lựa chọn tài sản của danh mục', exact: true }) });
  await expect(editor.getByTestId('selected-assets').locator('[data-asset-id]')).toHaveCount(32);
  await editor.getByRole('button', { name: 'Bỏ ACB khỏi rổ tài sản', exact: true }).click();
  const edited = await postUI(page, base + '/asset-selections', () => editor.getByRole('button', { name: 'Lưu lựa chọn tài sản', exact: true }).click(), 201);
  expect(edited.headers['if-match']).toBe('"1"');
  const remaining = ids.filter(asset => asset !== 'ACB');
  expect(edited.body.candidate_asset_ids).toEqual(remaining);
  await page.reload();
  await expect(editor.getByTestId('selected-assets').locator('[data-asset-id]')).toHaveCount(31);
  await editor.getByRole('button', { name: 'Thêm ACB vào rổ tài sản', exact: true }).click();
  const restored = await postUI(page, base + '/asset-selections', () => editor.getByRole('button', { name: 'Lưu lựa chọn tài sản', exact: true }).click(), 201);
  expect(restored.headers['if-match']).toBe('"2"');
  expect(restored.body.candidate_asset_ids).toEqual(ids);
  expect(await get(page, base + '/asset-selections')).toHaveLength(3);

  const readiness = await get(page, base + '/readiness');
  expect(readiness.strategies.find((item: Value) => item.strategy === 'MVO')?.can_submit).toBe(true);
  await page.goto(`/#proposal?portfolio=${created.result.id}`);
  await page.getByTestId('strategy-MVO').check();
  await page.getByTestId('propose-portfolio').click();
  const submitted = await postUI(page, base + '/recommendations', () => page.getByTestId('confirm-proposal').click(), 202);
  expect(submitted.headers['if-match']).toBe('"3"');
  const job = await succeededJob(page, submitted.result.job_id);
  const proposal = await get(page, `/api/v1/recommendations/${job.recommendation_id}`);
  expect(proposal.asset_ids).toEqual(ids);
  expect(proposal.selection_context.revision_id).toBe(restored.result.revision_id);
  expect(proposal.weights.map(Number).reduce((a: number, b: number) => a + b, 0)).toBeCloseTo(1, 7);
  const table = page.locator('.allocation-view').first().locator('table');
  await expect(table.locator('tbody tr')).toHaveCount(proposal.weights.filter((weight: string | number) => Number(weight) !== 0).length);
  await table.getByRole('button', { name: 'Tài sản: sắp xếp tăng dần', exact: true }).click();
  const displayed = await table.locator('tbody th').allTextContents();
  expect(displayed).toEqual([...displayed].sort((a, b) => a.localeCompare(b, 'vi')));
  await expect(page.getByTestId('accept-proposal')).toBeEnabled();
  const accepted = await postUI(page, `/api/v1/recommendations/${proposal.id}/accept`, () => page.getByTestId('accept-proposal').click(), 200);
  expect(accepted.headers['if-match']).toBe('"3"');
  const dashboard = await get(page, base + '/dashboard');
  expect(dashboard.accepted_target.id).toBe(accepted.result.id);
  expect(dashboard.accepted_target.recommendation_id).toBe(proposal.id);
  await page.reload();
  await expect(page.getByTestId('accept-proposal')).toBeDisabled();
  expect((await get(page, base + '/dashboard')).accepted_target).toEqual(dashboard.accepted_target);
  const bob = await login(browser, 'bob');
  expect((await bob.request.get(base)).status()).toBe(404);
  expect((await bob.request.get(`/api/v1/recommendations/${proposal.id}`)).status()).toBe(404);
  await writeFile(resolve(directory, 'browser-ui-v26-receipt.json'), JSON.stringify({ checked_at: new Date().toISOString(), origin, portfolio_id: created.result.id, candidate_asset_ids: ids, edited_candidate_asset_ids: remaining, restored_revision: restored.result, metadata: supportedMetadata, job, proposal, target: dashboard.accepted_target, owner_isolation: true }, null, 2) + '\n', { mode: 0o600 });
  await bob.close(); await page.close();
});

async function mutate(page: Page, path: string, body: Value, key: string, version: number, status: number) {
  const session = await get(page, '/auth/session');
  const response = await page.request.post(path, {
    headers: { Origin: origin, 'X-CSRF-Token': session.csrfToken, 'Idempotency-Key': key, 'If-Match': `"${version}"` }, data: body,
  });
  expect(response.status()).toBe(status); return response.json();
}
async function succeededJob(page: Page, id: string) {
  let job: Value = {};
  await expect.poll(async () => { job = await get(page, `/api/v1/jobs/portfolio/${id}`); return job.status; }, { timeout: 90_000 }).toBe('SUCCEEDED');
  return job;
}

test('User selection GOLD and VFF use a real fifty-fifty job and preserve revision replay', async ({ browser }, info) => {
  test.skip(verifyOnly, 'Persistence mode'); test.setTimeout(300_000); phase(info, 'user-selection-two-assets');
  const saved = JSON.parse(await readFile(receiptPath, 'utf8'));
  const page = await login(browser, 'alice');
  const portfolio = await create(page, ['GOLD', 'VFF']);
  const path = `/api/v1/portfolios/${portfolio.id}/recommendations`;
  const readiness = await get(page, `/api/v1/portfolios/${portfolio.id}/readiness`);
  saved.two_asset_case = { portfolio, readiness, positive_status: 'BLOCKED' };
  await save(saved);
  const mvo = readiness.strategies.find((item: Value) => item.strategy === 'MVO');
  if (requirePositive) expect(mvo?.can_submit).toBe(true);
  test.skip(!mvo?.can_submit, 'Actual GOLD/VFF inputs not eligible; receipt records the blocker');
  expect(readiness.strategies.find((item: Value) => item.strategy === 'EW')?.can_submit).toBe(true);
  expect(readiness.strategies.find((item: Value) => item.strategy === 'BL_ML')).toMatchObject({ can_submit: false, reason_code: 'NO_VALID_ML_VIEWS' });
  await page.goto(`/#proposal?portfolio=${portfolio.id}`); await page.getByTestId('strategy-MVO').check();
  await page.getByTestId('propose-portfolio').click();
  const sent = await postUI(page, path, () => page.getByTestId('confirm-proposal').click(), 202);
  expect(sent.body).toEqual({ strategy: 'MVO' }); expect(sent.headers['if-match']).toBe('"1"');
  const firstJob = await succeededJob(page, sent.result.job_id);
  const first = await get(page, `/api/v1/recommendations/${firstJob.recommendation_id}`);
  expect(first.asset_ids).toEqual(['GOLD', 'VFF']);
  first.weights.map(Number).forEach((weight: number) => expect(weight).toBeCloseTo(.5, 7));
  expect(first.selection_proof.active_asset_ids).toEqual(['GOLD', 'VFF']);
  expect(first.selection_proof.selected_equity_ids).toEqual([]);
  expect(first.bundle_hash).toBe(readiness.inputs.bundle_hash); expect(first.data_snapshot_id).toBe(readiness.inputs.snapshot_id);
  expect(first.model_bundle_id).toBe(readiness.inputs.model_bundle_id); expect(first.strategy).toBe('MVO');
  const bob = await login(browser, 'bob');
  for (const route of [`/api/v1/portfolios/${portfolio.id}`, `/api/v1/portfolios/${portfolio.id}/asset-selections`, `/api/v1/recommendations/${first.id}`]) expect((await bob.request.get(route)).status()).toBe(404);

  // Use a second real job so revision edits and replay do not replace the first receipt.
  const key = randomUUID();
  const secondAccepted = await mutate(page, path, { strategy: 'MVO' }, key, 1, 202);
  const beforeEdit = await get(page, `/api/v1/jobs/portfolio/${secondAccepted.job_id}`);
  const editKey = randomUUID(), editBody = { candidate_asset_ids: ['FPT', 'VFF'] };
  const editPath = `/api/v1/portfolios/${portfolio.id}/asset-selections`;
  const revision = await mutate(page, editPath, editBody, editKey, 1, 201);
  expect(revision.portfolio_version).toBe(2);
  expect(await mutate(page, editPath, editBody, editKey, 1, 201)).toEqual(revision);
  expect(await mutate(page, path, { strategy: 'MVO' }, key, 1, 202)).toEqual(secondAccepted);
  await mutate(page, path, { strategy: 'MVO' }, key, 2, 409);
  const secondJob = await succeededJob(page, secondAccepted.job_id);
  const second = await get(page, `/api/v1/recommendations/${secondJob.recommendation_id}`);
  expect(second.asset_ids).toEqual(['GOLD', 'VFF']); expect(second.selection_context.revision_id).toBe(portfolio.asset_selection.revision_id);
  second.weights.map(Number).forEach((weight: number) => expect(weight).toBeCloseTo(.5, 7));
  expect(await get(page, `/api/v1/recommendations/${first.id}`)).toEqual(first);
  await mutate(page, `/api/v1/recommendations/${second.id}/accept`, {}, randomUUID(), 2, 409);
  const current = await get(page, `/api/v1/portfolios/${portfolio.id}`);
  expect(current.asset_selection).toEqual(revision);
  saved.additional_proposals = [
    { portfolio: current, creation_portfolio: portfolio, job: firstJob, proposal: first },
    { portfolio: current, creation_portfolio: portfolio, job: secondJob, proposal: second },
  ];
  saved.two_asset_case = { portfolio, current_portfolio: current, readiness, positive_status: 'SUCCEEDED', pending_observed_before_edit: beforeEdit.status === 'QUEUED', status_observed_before_edit: beforeEdit.status, revision, replay_job_id: secondJob.job_id, foreign_owner_denials: 3 };
  await save(saved);
});

test('User selection keeps pending risk revision jobs pinned to their confirmed policy', async ({ browser }, info) => {
  test.skip(verifyOnly, 'Persistence mode'); test.setTimeout(300_000); phase(info, 'user-selection-risk-revision');
  const saved = JSON.parse(await readFile(receiptPath, 'utf8'));
  const page = await login(browser, 'alice');
  const portfolio = await create(page, ['FPT', 'VFF']);
  const base = `/api/v1/portfolios/${portfolio.id}`;
  const readiness = await get(page, base + '/readiness');
  const available = readiness.strategies.find((item: Value) => item.strategy === 'MVO')?.can_submit;
  saved.risk_revision_case = { portfolio, readiness, status: 'BLOCKED' }; await save(saved);
  if (requirePositive) expect(available).toBe(true);
  test.skip(!available, 'Actual selected inputs block MVO; receipt records the reason');
  const answers = { ...portfolio.risk_profile.answers, horizon_months: 6 };
  const preview = await mutate(page, base + '/risk-assessments/preview', { answers }, randomUUID(), 1, 200);
  expect(preview.before.constraints).toEqual(portfolio.constraints); expect(preview.after.constraints.risk_aversion).toBe(6);
  const key = randomUUID(), assessmentKey = randomUUID();
  const accepted = await mutate(page, base + '/recommendations', { strategy: 'MVO' }, key, 1, 202);
  const beforeRevision = await get(page, `/api/v1/jobs/portfolio/${accepted.job_id}`);
  // Require an observed pending job: a fast completed job is not mid-flight evidence.
  expect(beforeRevision.status).toBe('QUEUED');
  const revision = await mutate(page, base + '/risk-assessments', { answers }, assessmentKey, 1, 201);
  expect(revision.portfolio_version).toBe(2); expect(revision.constraints.risk_aversion).toBe(6);
  const afterRevision = await get(page, `/api/v1/jobs/portfolio/${accepted.job_id}`);
  expect(await mutate(page, base + '/risk-assessments', { answers }, assessmentKey, 1, 201)).toEqual(revision);
  const oldJob = await succeededJob(page, accepted.job_id);
  const oldProposal = await get(page, `/api/v1/recommendations/${oldJob.recommendation_id}`);
  expect(oldProposal.portfolio_version).toBe(1); expect(oldProposal.risk_profile).toEqual(portfolio.risk_profile);
  expect(oldProposal.policy_version_id).toBe(portfolio.policy_version_id);
  expect(oldProposal.requested_constraints).toEqual(portfolio.constraints);
  expect(oldProposal.constraints).toEqual(readiness.effective_constraints);
  expect(oldProposal.selection_context.revision_id).toBe(portfolio.asset_selection.revision_id);
  expect(oldProposal.asset_ids).toEqual(['FPT', 'VFF']);
  oldProposal.weights.map(Number).forEach((weight: number) => expect(weight).toBeCloseTo(.5, 7));
  expect(await mutate(page, base + '/recommendations', { strategy: 'MVO' }, key, 1, 202)).toEqual(accepted);
  await mutate(page, base + '/recommendations', { strategy: 'MVO' }, key, 2, 409);
  await mutate(page, `/api/v1/recommendations/${oldProposal.id}/accept`, {}, randomUUID(), 2, 409);
  const current = await get(page, base);
  expect(current.version).toBe(2); expect(current.policy_version_id).toBe(revision.policy_version_id);
  expect(current.asset_selection).toEqual(portfolio.asset_selection);
  const nextReady = await get(page, base + '/readiness');
  expect(nextReady.strategies.find((item: Value) => item.strategy === 'MVO')?.can_submit).toBe(true);
  const nextAccepted = await mutate(page, base + '/recommendations', { strategy: 'MVO' }, randomUUID(), 2, 202);
  const nextJob = await succeededJob(page, nextAccepted.job_id);
  const nextProposal = await get(page, `/api/v1/recommendations/${nextJob.recommendation_id}`);
  expect(nextProposal.portfolio_version).toBe(2); expect(nextProposal.risk_profile).toEqual(current.risk_profile);
  expect(nextProposal.policy_version_id).toBe(current.policy_version_id);
  expect(nextProposal.requested_constraints).toEqual(current.constraints);
  expect(nextProposal.constraints).toEqual(nextReady.effective_constraints);
  expect(nextProposal.constraints.risk_aversion).toBe(6);
  expect(nextProposal.asset_ids).toEqual(['FPT', 'VFF']);
  nextProposal.weights.map(Number).forEach((weight: number) => expect(weight).toBeCloseTo(.5, 7));
  expect(nextProposal.selection_context.revision_id).toBe(portfolio.asset_selection.revision_id);
  expect(await get(page, `/api/v1/recommendations/${oldProposal.id}`)).toEqual(oldProposal);
  const history = await get(page, base + '/risk-assessments');
  expect(history).toHaveLength(2); expect(history[0].id).toBe(revision.id);
  expect(history[1].risk_profile).toEqual(portfolio.risk_profile);
  saved.additional_proposals = [...(saved.additional_proposals ?? []),
    { portfolio: current, creation_portfolio: portfolio, job: oldJob, proposal: oldProposal },
    { portfolio: current, creation_portfolio: portfolio, job: nextJob, proposal: nextProposal },
  ];
  saved.risk_revision_case = { portfolio, current_portfolio: current, readiness, next_readiness: nextReady, status: 'SUCCEEDED', observed_pending_status: beforeRevision.status, job_status_after_revision: afterRevision.status, revision, history, old_job_id: oldJob.job_id, new_job_id: nextJob.job_id, old_proposal_id: oldProposal.id, new_proposal_id: nextProposal.id };
  await save(saved);
});

test('User selection reopens identical old and new proposals after restart', async ({ browser }, info) => {
  test.skip(!verifyOnly, 'Requires the same private receipt and a real process restart'); phase(info, 'user-selection-persistence');
  const saved = JSON.parse(await readFile(receiptPath, 'utf8')); const page = await login(browser, 'alice');
  for (const entry of [...saved.cases, ...(saved.additional_proposals ?? [])]) {
    const p = await get(page, `/api/v1/portfolios/${entry.portfolio.id}`); expect(p).toEqual(entry.portfolio);
    const history = await get(page, `/api/v1/portfolios/${p.id}/asset-selections`); expect(history[0]).toEqual(p.asset_selection);
  }
  if (saved.risk_revision_case?.status === 'SUCCEEDED') expect(await get(page, `/api/v1/portfolios/${saved.risk_revision_case.portfolio.id}/risk-assessments`)).toEqual(saved.risk_revision_case.history);
  const operator = await login(browser, 'data-operator'), reviewer = await login(browser, 'model-reviewer');
  for (const entry of saved.cases.filter((item: Value) => item.proposal)) {
    expect(await get(operator, `/api/v1/market/snapshots/${entry.snapshot.id}`)).toEqual(entry.snapshot);
    expect(await get(reviewer, `/api/v1/ml/models/${entry.model.model_id}`)).toEqual(entry.model);
  }
  const proposals = [saved.legacy, ...[...saved.cases, ...(saved.additional_proposals ?? [])].filter((entry: Value) => entry.proposal).map((entry: Value) => ({ portfolio_id: entry.portfolio.id, proposal: entry.proposal, job_id: entry.job.job_id }))];
  const basket = JSON.parse(await readFile(resolve(directory, 'browser-ui-v26-receipt.json'), 'utf8'));
  const metadata = await get(page, '/api/v1/market/assets');
  expect(metadata.filter((asset: Value) => basket.candidate_asset_ids.includes(asset.asset_id))).toEqual(basket.metadata);
  const basketPortfolio = await get(page, `/api/v1/portfolios/${basket.portfolio_id}`);
  expect(basketPortfolio.asset_selection).toEqual(basket.restored_revision);
  expect(await get(page, `/api/v1/portfolios/${basket.portfolio_id}/asset-selections`)).toHaveLength(3);
  expect((await get(page, `/api/v1/portfolios/${basket.portfolio_id}/dashboard`)).accepted_target).toEqual(basket.target);
  proposals.push({ portfolio_id: basket.portfolio_id, proposal: basket.proposal, job_id: basket.job.job_id });
  for (const entry of proposals) {
    const actual = await get(page, `/api/v1/recommendations/${entry.proposal.id}`); expect(actual).toEqual(entry.proposal);
    await page.goto(`/#proposal?portfolio=${entry.portfolio_id}&proposal=${entry.proposal.id}`);
    await expect(page.locator('.allocation-tags').getByText('Giá thị trường', { exact: true })).toBeVisible();
    const rows = page.locator('.allocation-view').first().locator('tbody');
    await expect(rows.locator('tr')).toHaveCount(entry.proposal.weights.filter((weight: string | number) => Number(weight) !== 0).length);
    for (const [index, asset] of entry.proposal.asset_ids.entries()) {
      const row = rows.getByRole('rowheader', { name: asset, exact: true });
      if (Number(entry.proposal.weights[index]) === 0) await expect(row).toHaveCount(0);
      else await expect(row).toBeVisible();
    }
    if (entry.proposal.id === basket.proposal.id) {
      const allocation = entry.proposal.asset_ids.map((asset: string, index: number) => ({ asset, weight: Number(entry.proposal.weights[index]), capital: Number(entry.proposal.capital_vnd) * Number(entry.proposal.weights[index]) })).filter((row: Value) => row.weight !== 0);
      for (const [key, label] of [['asset', 'Tài sản'], ['weight', 'Tỷ trọng mục tiêu'], ['capital', 'Vốn mục tiêu (VND)']] as const) {
        for (const direction of ['tăng', 'giảm'] as const) {
          await page.locator('.allocation-view').first().getByRole('button', { name: `${label}: sắp xếp ${direction} dần`, exact: true }).click();
          const expected = [...allocation].sort((a, b) => (direction === 'tăng' ? 1 : -1) * (key === 'asset' ? a.asset.localeCompare(b.asset, 'vi') : a[key] - b[key]));
          await expect(rows.getByRole('rowheader')).toHaveText(expected.map(row => row.asset));
        }
      }
    }
    const current = await get(page, `/api/v1/portfolios/${entry.portfolio_id}`);
    if (entry.proposal.id === basket.proposal.id) await expect(page.getByTestId('accept-proposal')).toBeDisabled();
    else if (Date.parse(entry.proposal.valid_until) <= Date.now() || entry.proposal.portfolio_version !== current.version) { await expect(page.getByTestId('accept-proposal')).toBeDisabled(); await expect(page.getByTestId('stale-proposal-notice')).toBeVisible(); }
    else await expect(page.getByTestId('accept-proposal')).toBeEnabled();
    const job = await get(page, `/api/v1/jobs/portfolio/${entry.job_id}`); expect(job.status).toBe('SUCCEEDED'); expect(job.recommendation_id).toBe(entry.proposal.id);
  }
  await writeFile(resolve(directory, 'browser-persistence-receipt.json'), JSON.stringify({ checked_at: new Date().toISOString(), old_proposal_verified: saved.legacy.proposal.id, new_proposals_verified: proposals.slice(1).map(entry => entry.proposal.id), bl_ml_proposals_verified: saved.cases.filter((entry: Value) => entry.proposal).map((entry: Value) => entry.proposal.id), positive_persistence: proposals.length > 1 ? 'VERIFIED' : 'BLOCKED_NO_POSITIVE_PROPOSAL' }, null, 2) + '\n', { mode: 0o600 });
  if (requirePositive) expect(proposals.length).toBeGreaterThan(1);
});

test('Quantified survey persists confirmed bands and reassesses only the test portfolio', async ({ browser }) => {
  const page = await login(browser, 'alice');
  const previous = await get(page, '/api/v1/portfolios?limit=100');
  const legacy = previous.find((p: any) => p.risk_profile?.answers?.questionnaire_version === 'risk-v1');
  if (legacy) {
    await page.goto('/#risk-assessment?portfolio=' + legacy.id);
    await expect(page.getByTestId('risk-horizon')).toHaveValue(String(legacy.risk_profile.answers.horizon_months));
    await expect(page.locator('.risk-questions input:checked')).toHaveCount(0);
    expect((await get(page, '/api/v1/portfolios/' + legacy.id)).risk_profile).toEqual(legacy.risk_profile);
  }

  const p = await create(page, ['FPT', 'MWG', 'VCB', 'VFF']);
  const path = '/api/v1/portfolios/' + p.id;
  expect(p.risk_profile.answers.questionnaire_version).toBe('risk-v2');
  expect(p.risk_profile.answers).not.toHaveProperty('experience');
  expect(p.risk_profile.profile).toBe('balanced');
  await page.goto('/#risk-assessment?portfolio=' + p.id);
  const form = page.getByTestId('risk-reassessment');
  await expect(form.getByText('5% = 5.000.000 ₫ · 15% = 15.000.000 ₫', { exact: true })).toBeVisible();
  const reserve = form.getByRole('group', { name: /Nếu thu nhập tạm dừng/ });
  await reserve.getByRole('button', { name: 'Tôi chưa chắc' }).click();
  await expect(reserve.getByRole('status')).toContainText('4 tháng');
  await page.getByTestId('risk-preview').click();
  await expect(page.getByTestId('risk-confirm')).toHaveCount(0);
  await reserve.getByRole('radio', { name: 'Từ 6 tháng trở lên' }).check();
  await page.getByTestId('risk-horizon').fill('60');
  await page.getByRole('radio', { name: 'Cao · Từ 15% trở lên' }).check();
  await page.getByRole('radio', { name: 'Trên 30%', exact: true }).check();
  await form.getByLabel('Kinh nghiệm đầu tư (tùy chọn)').selectOption('beginner');
  const preview = await postUI(page, path + '/risk-assessments/preview', () => page.getByTestId('risk-preview').click(), 200);
  expect(preview.result.after.risk_profile.determining_factors).toEqual(['liquidity_need']);
  await expect(page.getByText(/Hồ sơ được xác định theo dự kiến rút trên 30%/)).toBeVisible();
  expect((await get(page, path)).risk_profile).toEqual(p.risk_profile);
  const confirmed = await postUI(page, path + '/risk-assessments', () => page.getByTestId('risk-confirm').click(), 201);
  expect(confirmed.result.constraints.risk_aversion).toBe(6);
  expect(confirmed.headers['if-match']).toBe('"1"');
  expect(confirmed.headers['idempotency-key']).toBeTruthy();
  await page.goto('/#profile?portfolio=' + p.id);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Thận trọng', exact: true })).toBeVisible();
  await expect(page.getByText(/Hồ sơ được xác định theo dự kiến rút trên 30%/)).toBeVisible();
  const history = await get(page, path + '/risk-assessments');
  expect(history.map((r: any) => r.risk_profile.profile)).toEqual(['conservative', 'balanced']);
  expect(history[1].risk_profile).toEqual(p.risk_profile);
  expect((await get(page, path)).asset_selection.revision_id).toBe(p.asset_selection.revision_id);
});
