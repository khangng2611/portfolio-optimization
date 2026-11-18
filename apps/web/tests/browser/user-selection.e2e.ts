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
  for (const asset of ids) await page.locator(`.risk-wizard input[type="checkbox"][value="${asset}"]`).check();
  if (!ids.includes('VFF')) await expect(page.locator('.risk-wizard input[type="checkbox"][value="VFF"]')).not.toBeChecked();
  await expect(page.getByText('Hệ thống có thể phân bổ 0% vào tài sản đã chọn.', { exact: false }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  await page.getByRole('radio', { name: 'Vừa — chấp nhận dao động', exact: true }).check();
  await page.getByRole('radio', { name: 'Thấp — có nguồn dự phòng riêng', exact: true }).check();
  await page.getByRole('radio', { name: 'Đã có kinh nghiệm', exact: true }).check();
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
  for (const entry of proposals) {
    const actual = await get(page, `/api/v1/recommendations/${entry.proposal.id}`); expect(actual).toEqual(entry.proposal);
    await page.goto(`/#proposal?portfolio=${entry.portfolio_id}&proposal=${entry.proposal.id}`);
    await expect(page.locator('.allocation-tags').getByText(entry.proposal.strategy === 'BL_ML' ? 'BL + ML' : entry.proposal.strategy, { exact: true })).toBeVisible();
    for (const asset of entry.proposal.asset_ids) await expect(page.locator('.allocation-view').first().locator('tbody th').filter({ hasText: asset })).toBeVisible();
    const current = await get(page, `/api/v1/portfolios/${entry.portfolio_id}`);
    if (Date.parse(entry.proposal.valid_until) <= Date.now() || entry.proposal.portfolio_version !== current.version) { await expect(page.getByTestId('accept-proposal')).toBeDisabled(); await expect(page.getByTestId('stale-proposal-notice')).toBeVisible(); }
    else await expect(page.getByTestId('accept-proposal')).toBeEnabled();
    const job = await get(page, `/api/v1/jobs/portfolio/${entry.job_id}`); expect(job.status).toBe('SUCCEEDED'); expect(job.recommendation_id).toBe(entry.proposal.id);
  }
  await writeFile(resolve(directory, 'browser-persistence-receipt.json'), JSON.stringify({ checked_at: new Date().toISOString(), old_proposal_verified: saved.legacy.proposal.id, new_proposals_verified: proposals.slice(1).map(entry => entry.proposal.id), bl_ml_proposals_verified: saved.cases.filter((entry: Value) => entry.proposal).map((entry: Value) => entry.proposal.id), positive_persistence: proposals.length > 1 ? 'VERIFIED' : 'BLOCKED_NO_POSITIVE_PROPOSAL' }, null, 2) + '\n', { mode: 0o600 });
  if (requirePositive) expect(proposals.length).toBeGreaterThan(1);
});
