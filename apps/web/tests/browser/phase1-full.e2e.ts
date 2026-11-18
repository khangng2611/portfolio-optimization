import { expect, test, type Browser, type Page } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { submitLogin } from './login-form';

const generated = resolve('../../infra/local/.generated');
const receiptPath = resolve(generated, 'phase1-full-browser-receipt.json');
const snapshotReceiptPath = process.env.PHASE1_FULL_SNAPSHOT_RECEIPT ?? resolve(generated, 'phase1-full-snapshot-receipt.json');
const stale = process.env.PHASE1_FULL_EXPECT === 'vff-stale';
const verifyOnly = process.env.PHASE1_FULL_VERIFY_RECEIPT === '1';
const universe = 'VN_PHASE1_FULL';
const assets: string[] = JSON.parse(await readFile(resolve('../../assets_1.json'), 'utf8')).default_selection;
const reviewReason = 'Checked full Phase 1 selection and fit epochs, purged label boundaries, 25 native booster hashes, availability and active-asset pins.';

async function login(browser: Browser, username: string) {
  const { users } = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  const account = users.find((user: { username: string }) => user.username === username);
  if (!account) throw new Error('Local browser account unavailable');
  const page = await browser.newPage({ baseURL: 'http://localhost:3000' });
  await page.goto('/login');
  await submitLogin(page, account);
  return page;
}

async function get(page: Page, path: string) {
  const response = await page.request.get(path);
  expect(response.status()).toBe(200);
  return response.json();
}

async function submit(page: Page, path: string, action: () => Promise<void>, status: number) {
  const pending = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path);
  await action();
  const response = await pending;
  expect(response.status()).toBe(status);
  const request = response.request();
  expect(!!request.headers()['x-csrf-token']).toBe(true);
  if (status !== 201) expect(request.headers()['idempotency-key']).toMatch(/^[0-9a-f-]{36}$/);
  return { result: await response.json(), body: request.postDataJSON(), ifMatch: request.headers()['if-match'] };
}

test.beforeAll(() => {
  if (process.env.E2E_DISPOSABLE_STACK !== '1') throw new Error('Set E2E_DISPOSABLE_STACK=1 for the localhost-only gate');
});

test('Phase 1 full review, publication and investor BL_ML proposal', async ({ browser }) => {
  test.skip(verifyOnly || (stale && !process.env.PHASE1_FULL_MODEL_ID), 'Persistence or stale inspection without a model to publish');
  const modelId = process.env.PHASE1_FULL_MODEL_ID;
  expect(modelId).toMatch(/^[0-9a-f-]{36}$/);
  const { snapshot } = JSON.parse(await readFile(snapshotReceiptPath, 'utf8'));
  expect(snapshot.status).toBe('READY');
  expect(snapshot.quality_status).toBe('PASS');
  expect(snapshot.asset_ids).toEqual(assets);
  const modelPath = `/api/v1/ml/models/${modelId}`;
  const modelLink = `/#model-review?model=${modelId}`;

  const reviewer = await login(browser, 'model-reviewer');
  await reviewer.goto(modelLink);
  const candidate = await get(reviewer, modelPath);
  expect(candidate.metadata.modelled_asset_ids).toHaveLength(5);
  expect(candidate.metadata.active_asset_ids).toHaveLength(7);
  expect(candidate.metadata.active_asset_ids.slice(-2)).toEqual(['GOLD', 'VFF']);
  expect(new Set(candidate.metadata.active_asset_ids).size).toBe(7);
  expect(candidate.metadata.selection_id).toMatch(/^[a-f0-9]{64}$/);
  expect(candidate.metadata.selection_epoch).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  expect(candidate.metadata.fit_epoch).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  expect(candidate.metadata.validation.train_label_end < candidate.metadata.validation.validation_start).toBe(true);
  await expect(reviewer.getByText('Selection K5 / epoch', { exact: true })).toBeVisible();
  await expect(reviewer.getByText('Modelled / active assets', { exact: true })).toBeVisible();
  expect(candidate.metadata.horizon_sessions).toBe(5);
  await expect(reviewer.getByText('5 phiên quan sát', { exact: true })).toBeVisible();
  if (candidate.status === 'CANDIDATE') {
    await reviewer.getByTestId('model-review-decision').selectOption('APPROVED');
    await reviewer.getByTestId('model-review-reason').fill(reviewReason);
    await reviewer.getByTestId('model-review-preview').click();
    const reviewed = await submit(reviewer, modelPath + '/reviews', () => reviewer.getByTestId('model-review-submit').click(), 200);
    expect(reviewed.ifMatch).toBe(`"${candidate.version}"`);
    expect(reviewed.result.status).toBe('APPROVED');
  }
  await expect(reviewer.getByTestId('model-detail')).toHaveAttribute('data-artifact-ready', 'true');
  const approved = await get(reviewer, modelPath);
  expect(approved.status).toBe('APPROVED');
  expect(approved.reviews.some((review: { decision: string }) => review.decision === 'APPROVED')).toBe(true);

  const operator = await login(browser, 'data-operator');
  await operator.goto(`/#market-publications?snapshot=${snapshot.id}&model=${modelId}`);
  await operator.getByTestId('publication-universe').fill(universe);
  await operator.getByTestId('publication-model').selectOption(modelId!);
  await expect(operator.getByTestId('publication-max-age')).toHaveValue('7');
  const path = '/api/v1/market/publications';
  const published = await submit(operator, path, () => operator.getByTestId('market-publication-submit').click(), 202);
  expect(published.body).toMatchObject({
    snapshot_id: snapshot.id, snapshot_hash: snapshot.content_hash,
    universe_id: universe, approved_model_id: modelId, max_age_days: 7,
  });
  const publicationPath = `${path}/${published.result.job_id}`;
  await expect(operator.getByTestId(`market-publication-${published.result.job_id}`))
    .toHaveAttribute('data-status', 'SUCCEEDED', { timeout: 90_000 });
  const publication = await get(operator, publicationPath);

  const investor = await login(browser, 'alice');
  const readiness = (await get(investor, '/api/v1/universes/readiness')).find(
    (row: { universe_id: string }) => row.universe_id === universe
  );
  if (stale) {
    expect(readiness).toMatchObject({ reason_code: 'VFF_STALE', asset_ids: assets, snapshot_id: snapshot.id });
    expect(readiness.strategies.every((item: { available: boolean }) => !item.available)).toBe(true);
    expect(readiness.provenance.phase1_full.availability.VFF.age_days).toBeGreaterThan(7);
    await writeFile(resolve(generated, 'phase1-full-stale-publication-browser-receipt.json'), JSON.stringify({
      checked_at: new Date().toISOString(), model_id: modelId, model_metadata: approved.metadata,
      review_ids: approved.reviews.map((review: { review_id: string }) => review.review_id),
      publication, readiness,
    }, null, 2) + '\n');
    return;
  }
  expect(readiness).toMatchObject({
    status: 'READY', asset_ids: assets, snapshot_id: snapshot.id,
    approved_model_id: modelId, bundle_hash: publication.result.sha256,
  });
  expect(readiness.strategies).toContainEqual({ strategy: 'BL_ML', available: true, reason_code: 'READY' });

  await investor.goto('/#create');
  await investor.getByLabel(/^Tên danh mục/).fill(`Phase 1 full BL + ML ${new Date().toISOString()}`);
  await investor.getByLabel(/^Vốn kế hoạch \(VND\)/).fill('100000000');
  await investor.getByLabel('Thời gian đầu tư (tháng)').fill('36');
  await investor.getByLabel('Bộ tài sản').selectOption(universe);
  await investor.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  await investor.getByRole('radio', { name: 'Vừa — chấp nhận dao động', exact: true }).check();
  await investor.getByRole('radio', { name: 'Thấp — có nguồn dự phòng riêng', exact: true }).check();
  await investor.getByRole('radio', { name: 'Đã có kinh nghiệm', exact: true }).check();
  await investor.getByRole('button', { name: 'Xem lại hồ sơ', exact: true }).click();
  const { result: portfolio } = await submit(investor, '/api/v1/onboarding/portfolios',
    () => investor.getByTestId('create-portfolio-submit').click(), 201);

  await investor.goto(`/#proposal?portfolio=${portfolio.id}`);
  await investor.getByTestId('strategy-BL_ML').check();
  const ew = investor.getByRole('checkbox', { name: /Cho phép phương án EW/ });
  await ew.uncheck();
  await expect(ew).not.toBeChecked();
  await investor.getByTestId('propose-portfolio').click();
  await expect(investor.getByText('Chưa cho phép', { exact: true })).toBeVisible();
  const sent = await submit(investor, `/api/v1/portfolios/${portfolio.id}/recommendations`,
    () => investor.getByTestId('confirm-proposal').click(), 202);
  expect(sent.body).toEqual({ strategy: 'BL_ML' });
  await expect(investor.getByTestId('accept-proposal')).toBeEnabled({ timeout: 90_000 });
  const job = await get(investor, `/api/v1/jobs/portfolio/${sent.result.job_id}`);
  expect(job.status).toBe('SUCCEEDED');
  const proposal = await get(investor, `/api/v1/recommendations/${job.recommendation_id}`);
  expect(proposal).toMatchObject({
    strategy: 'BL_ML', requested_strategy: 'BL_ML', fallback_reason: null,
    demo: false, asset_ids: assets, data_snapshot_id: snapshot.id,
    model_bundle_id: readiness.model_manifest_hash, bundle_hash: readiness.bundle_hash,
    inputs_provenance: { data_origin: 'real', snapshot_hash: snapshot.content_hash },
    diagnostics: { inference: { model_id: modelId, model_manifest_hash: readiness.model_manifest_hash, horizon_sessions: 5 } },
  });
  const full = readiness.provenance.phase1_full;
  expect(full.active_asset_ids).toHaveLength(7);
  expect(full.selected_equity_ids).toHaveLength(5);
  expect(full.active_asset_ids).toEqual([...full.selected_equity_ids, 'GOLD', 'VFF']);
  expect(proposal.inputs_provenance.phase1_full).toEqual(full);
  expect(proposal.diagnostics.inference).toMatchObject({
    selection_id: full.selection_id, selection_epoch: full.selection_epoch,
    fit_epoch: full.fit_epoch, active_asset_ids: full.active_asset_ids,
  });
  // A reselect between fit epochs may keep the prior model for the K5 intersection.
  expect(full.selection_epoch >= candidate.metadata.selection_epoch).toBe(true);
  expect(full.fit_epoch).toBe(candidate.metadata.fit_epoch);
  expect(proposal.requested_constraints).toEqual(portfolio.constraints);
  expect(proposal.constraints).toEqual({
    ...portfolio.constraints, defensive_asset_ids: ['VFF'],
    risk_aversion: Math.max(portfolio.constraints.risk_aversion, full.regime.regime === 'crisis' ? 5 : 1.5),
    max_position_weight: Math.min(portfolio.constraints.max_position_weight, .5),
    min_defensive_weight: Math.max(portfolio.constraints.min_defensive_weight, .15),
    max_non_defensive_weight: Math.min(portfolio.constraints.max_non_defensive_weight, .7),
  });
  for (const asset of ['GOLD', 'VFF']) {
    expect(full.availability[asset].age_days).toBeLessThanOrEqual(7);
    expect(Date.parse(full.availability[asset].policy_available_at)).not.toBeNaN();
    expect(full.availability[asset].observation_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  }
  await expect(investor.getByText(/Tài sản ngoài K5 có tỷ trọng 0%/).first()).toBeVisible();
  const weights: number[] = proposal.weights.map(Number);
  const total = weights.reduce((sum, w) => sum + w, 0);
  expect(total).toBeCloseTo(1, 7);
  expect(weights).toHaveLength(32);
  expect(weights.every(w => w >= 0 && w <= proposal.constraints.max_position_weight + 1e-8)).toBe(true);
  const inactive = assets.filter(asset => !full.active_asset_ids.includes(asset));
  expect(inactive).toHaveLength(25);
  for (const asset of inactive) expect(weights[assets.indexOf(asset)]).toBe(0);
  const defensive = weights.reduce((sum, w, i) => sum + (proposal.constraints.defensive_asset_ids.includes(assets[i]) ? w : 0), 0);
  expect(defensive + 1e-8).toBeGreaterThanOrEqual(proposal.constraints.min_defensive_weight);
  expect(total - defensive).toBeLessThanOrEqual(proposal.constraints.max_non_defensive_weight + 1e-8);

  await writeFile(receiptPath, JSON.stringify({
    created_at: new Date().toISOString(), review_ids: approved.reviews.map((review: { review_id: string }) => review.review_id),
    publication_id: publication.job_id, snapshot_id: snapshot.id, model_metadata: approved.metadata,
    portfolio_id: portfolio.id, job_id: sent.result.job_id, model_id: modelId, proposal,
  }, null, 2) + '\n');
});

test('Phase 1 full investor reopens the same proposal after stack restart', async ({ browser }) => {
  test.skip(!verifyOnly, 'Requires a completed receipt and a stack restart');
  const saved = JSON.parse(await readFile(receiptPath, 'utf8'));
  const investor = await login(browser, 'alice');
  await investor.goto(`/#proposal?portfolio=${saved.portfolio_id}&proposal=${saved.proposal.id}`);
  if (Date.parse(saved.proposal.valid_until) <= Date.now()) {
    await expect(investor.getByTestId('accept-proposal')).toBeDisabled();
    await expect(investor.getByTestId('stale-proposal-notice')).toBeVisible();
  } else {
    await expect(investor.getByTestId('accept-proposal')).toBeEnabled();
  }
  await expect(investor.locator('.allocation-tags').getByText('BL + ML', { exact: true })).toBeVisible();
  const job = await get(investor, `/api/v1/jobs/portfolio/${saved.job_id}`);
  expect(job.status).toBe('SUCCEEDED');
  expect(job.recommendation_id).toBe(saved.proposal.id);
  expect(await get(investor, `/api/v1/recommendations/${saved.proposal.id}`)).toEqual(saved.proposal);
  const operator = await login(browser, 'data-operator');
  const publication = await get(operator, `/api/v1/market/publications/${saved.publication_id}`);
  expect(publication.result.sha256).toBe(saved.proposal.bundle_hash);
  expect(publication.status).toBe('SUCCEEDED');
  const reviewer = await login(browser, 'model-reviewer');
  const model = await get(reviewer, `/api/v1/ml/models/${saved.model_id}`);
  expect(model.status).toBe('APPROVED');
  expect(model.artifact_ready).toBe(true);
  expect(model.metadata).toEqual(saved.model_metadata);
  expect(model.metadata.fit_epoch).toBe(saved.proposal.inputs_provenance.phase1_full.fit_epoch);
  expect(saved.proposal.inputs_provenance.phase1_full.active_asset_ids).toHaveLength(7);
  expect(model.reviews.map((row: { review_id: string }) => row.review_id)).toEqual(saved.review_ids);
});


test('Phase 1 full stale VFF explains seven-day NAV limit and prevents submission', async ({ browser }) => {
  test.skip(verifyOnly || !stale, 'Requires a real VFF_STALE full-universe catalog state');
  const investor = await login(browser, 'alice');
  const readiness = (await get(investor, '/api/v1/universes/readiness')).find(
    (row: { universe_id: string }) => row.universe_id === universe
  );
  expect(readiness).toBeDefined();
  expect(readiness.reason_code).toBe('VFF_STALE');
  expect(readiness.strategies.find((row: { strategy: string }) => row.strategy === 'BL_ML'))
    .toMatchObject({ available: false, reason_code: 'VFF_STALE' });
  if (readiness.provenance?.phase1_full?.availability?.VFF) {
    expect(readiness.provenance.phase1_full.availability.VFF.age_days).toBeGreaterThan(7);
  }
  const session = await get(investor, '/auth/session');
  // A stale universe is deliberately excluded from the ready-universe wizard.
  // Create only this test's own portfolio through the real authorized BFF.
  const onboard = await investor.request.post('/api/v1/onboarding/portfolios', {
    headers: { Origin: 'http://localhost:3000', 'X-CSRF-Token': session.csrfToken },
    data: { name: `Phase 1 full stale ${new Date().toISOString()}`, capital_vnd: '100000000', universe_id: universe,
      answers: { questionnaire_version: 'risk-v1', horizon_months: 36, liquidity_need: 'low', loss_tolerance: 'medium', experience: 'experienced' } },
  });
  expect(onboard.status()).toBe(201);
  const portfolio = await onboard.json();
  const recommendationsPath = `/api/v1/portfolios/${portfolio.id}/recommendations`;
  let submissions = 0;
  investor.on('request', request => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === recommendationsPath) submissions++;
  });
  await investor.goto(`/#proposal?portfolio=${portfolio.id}`);
  await expect(investor.getByText('NAV VFF đủ điều kiện đã quá 7 ngày; cần dữ liệu khả dụng mới.', { exact: true })).toBeVisible();
  await investor.getByTestId('strategy-BL_ML').check();
  const fallback = investor.getByRole('checkbox', { name: /Cho phép phương án EW/ });
  await expect(fallback).not.toBeChecked();
  await expect(investor.getByTestId('propose-portfolio')).toBeDisabled();
  await fallback.check();
  await expect(investor.getByTestId('propose-portfolio')).toBeDisabled();
  expect(await get(investor, recommendationsPath)).toEqual([]);
  expect(submissions).toBe(0);
  await writeFile(resolve(generated, 'phase1-full-stale-browser-receipt.json'), JSON.stringify({
    checked_at: new Date().toISOString(), universe_id: universe, portfolio_id: portfolio.id,
    readiness, recommendation_submissions: submissions,
  }, null, 2) + '\n');
});
