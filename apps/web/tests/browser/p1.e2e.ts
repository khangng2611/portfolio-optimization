import { test, expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

// Real localhost Identity/BFF/Market/ML/Quant/Portfolio only. No HTTP interception,
// fixture aliases, direct database writes, synthetic prices or model artifacts.
const root = resolve('../..');
const generated = resolve(root, 'infra/local/.generated');
const receiptFile = resolve(generated, 'p1-browser-receipt.json');
const origin = 'http://localhost:3000';
const persistence = process.env.P1_VERIFY_RECEIPT === '1';
type Value = Record<string, any>;
type Intent = { path: string; body: Value; key: string; if_match?: string; method?: 'PATCH' };
type Receipt = {
  schema_version: 1; created_at: string; asset_ids: string[]; universe_id: string;
  schedule_id: string; schedule: Intent; schedule_result: Value;
  refresh_id: string; refresh: Intent; refresh_result: Value;
  auto_refresh_id: string; auto_refresh_result: Value; auto_snapshot_id: string; auto_snapshot_hash: string;
  auto_schedule_id: string; auto_schedule: Intent; auto_schedule_result: Value;
  auto_schedule_disable: Intent; auto_schedule_final_version: number;
  snapshot_id: string; snapshot_hash: string; ingestion_ids: string[];
  training_id: string; training: Intent; training_result: Value;
  model_id: string; model_metadata_hash: string; model_provenance_hash: string; model_sha256: string;
  review: Intent; review_id: string; review_result_hash: string;
  publication_id: string; publication: Intent; publication_result: Value; publication_attempts: number;
  portfolio_id: string; old_proposal_id: string; pending_proposal_id: string;
  old_target_id: string; old_allocation_hash: string; old_risk_profile_id: string;
  assessment_id: string; assessment: Intent; assessment_result: Value;
  proposal_id: string; proposal: Intent; input_hash: string; model_manifest_hash: string;
  target_id: string; target_allocation_hash: string;
};
const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const dayBefore = (value: string, days: number) => new Date(Date.parse(`${value}T00:00:00Z`) - days * 86_400_000).toISOString().slice(0, 10);
const investorPath = (id: string) => `/api/v1/portfolios/${id}`;

function phase(info: TestInfo, name: string) {
  info.annotations = info.annotations.filter(item => item.type !== 'safe-phase');
  info.annotations.push({ type: 'safe-phase', description: name });
  console.log(`BROWSER_PHASE: ${name}`);
}

async function get(context: BrowserContext, path: string): Promise<any> {
  const response = await context.request.get(path);
  expect(response.status(), 'Authenticated real BFF read').toBe(200);
  return response.json();
}

async function authenticate(page: Page, username: 'alice' | 'data-operator' | 'model-reviewer', destination = '/') {
  const accounts = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  const account = accounts.users.find((item: { username: string }) => item.username === username);
  if (!account?.password) throw new Error('Disposable P1 browser account unavailable');
  await page.goto(destination);
  await page.getByRole('link', { name: 'Đăng nhập qua Identity', exact: true }).click();
  await page.waitForURL(url => url.origin === 'http://localhost:8080');
  // Authorization state and account credentials stay exclusively in memory.
  const authorization = new URL(page.url());
  expect(authorization.searchParams.get('client_id')).toBe('portfolio-web');
  expect(authorization.searchParams.get('response_type')).toBe('code');
  expect(authorization.searchParams.get('code_challenge_method')).toBe('S256');
  expect(Boolean(authorization.searchParams.get('code_challenge'))).toBe(true);
  await page.locator('#username').fill(account.username);
  await page.locator('#password').fill(account.password);
  await Promise.all([
    page.waitForURL(url => url.origin === origin && url.pathname === '/'),
    page.locator('#kc-login').click(),
  ]);
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
  expect((await get(page.context(), '/auth/session')).authenticated).toBe(true);
}

async function mutate(context: BrowserContext, intent: Intent, status: number) {
  const session = await get(context, '/auth/session');
  const response = await context.request.fetch(intent.path, {
    method: intent.method ?? 'POST', data: intent.body,
    headers: {
      Origin: origin, 'X-CSRF-Token': session.csrfToken,
      ...(intent.key ? { 'Idempotency-Key': intent.key } : {}),
      ...(intent.if_match ? { 'If-Match': intent.if_match } : {}),
    },
  });
  expect(response.status(), 'Real CSRF-protected BFF mutation').toBe(status);
  return { result: await response.json(), etag: response.headers().etag };
}

async function uiMutation(page: Page, path: string, action: () => Promise<unknown>, status: number, durable = true, method: 'POST' | 'PATCH' = 'POST') {
  const pending = page.waitForResponse(response => response.request().method() === method
    && new URL(response.url()).pathname === path);
  await action();
  const response = await pending;
  expect(response.status(), 'UI submits to real BFF').toBe(status);
  const request = response.request();
  expect(Boolean(request.headers()['x-csrf-token'])).toBe(true);
  const intent: Intent = {
    path, body: request.postDataJSON(), key: request.headers()['idempotency-key'] ?? '',
    ...(method === 'PATCH' ? { method } : {}),
    ...(request.headers()['if-match'] ? { if_match: request.headers()['if-match'] } : {}),
  };
  if (durable) expect(Boolean(intent.key), 'Durable UI intent has an explicit idempotency key').toBe(true);
  return { result: await response.json(), intent, etag: response.headers().etag };
}

async function uiPatch(page: Page, path: string, action: () => Promise<unknown>) {
  const result = await uiMutation(page, path, action, 200, true, 'PATCH');
  expect(result.intent.if_match, 'Schedule UI uses an explicit quoted version').toMatch(/^"[1-9][0-9]*"$/);
  return result;
}

async function automaticScheduler(page: Page, manualSchedule: Value, manualId: string, assets: string[]) {
  const name = `P1 automatic KBS ${randomUUID()}`;
  let scheduleId = '';
  try {
    await page.goto('/#market-refresh');
    await page.getByTestId('refresh-name').fill(name);
    await page.getByTestId('refresh-assets').fill(assets.join(','));
    await page.getByTestId('refresh-start').fill(manualSchedule.initial_start_date);
    await page.getByTestId('refresh-interval').fill('10080');
    await page.getByTestId('refresh-overlap').fill('7');
    await page.getByTestId('refresh-max-age').fill('14');
    await page.getByTestId('refresh-enabled').check();
    await page.getByTestId('refresh-review').click();
    const schedule = await uiMutation(page, '/api/v1/market/refresh-schedules',
      () => page.getByTestId('refresh-save').click(), 201);
    scheduleId = schedule.result.id;
    expect(scheduleId).not.toBe(manualSchedule.id);
    expect(schedule.result.enabled).toBe(true);
    expect(schedule.result.version).toBe(1);
    expect(schedule.result.provider).toBe('kbs-direct-v1');
    let automaticId = '';
    // Only GETs follow this initially-enabled schedule creation. A distinct job
    // proves the real timer tick enqueued it, with no manual trigger for this
    // schedule and no synthetic time or database edits.
    await expect.poll(async () => {
      const jobs = await get(page.context(), '/api/v1/market/refresh-jobs?limit=100&offset=0');
      const job = jobs.find((item: Value) => item.schedule_id === scheduleId);
      automaticId = job?.id ?? '';
      return Boolean(automaticId);
    }, { timeout: 60_000, intervals: [500, 1000, 2000] }).toBe(true);
    const automatic = await waitJob(page.context(), `/api/v1/market/refresh-jobs/${automaticId}`, 180_000);
    expect(automatic.id).not.toBe(manualId);
    expect(automatic.schedule_id).toBe(scheduleId);
    expect(automatic.schedule_version).toBe(schedule.result.version);
    expect(automatic.provider).toBe('kbs-direct-v1');
    expect(automatic.ingestion_job_ids).toHaveLength(assets.length);
    for (const id of automatic.ingestion_job_ids) {
      const quality = await get(page.context(), `/api/v1/market/ingestions/${id}/quality`);
      expect(quality.status).toBe('PASS');
      expect(quality.source_manifest_sha256).toMatch(/^[a-f0-9]{64}$/);
    }
    const snapshot = await get(page.context(), `/api/v1/market/snapshots/${automatic.snapshot_id}`);
    expect(snapshot.asset_ids).toEqual(assets);
    expect(snapshot.provider).toBe('kbs-direct-v1');
    expect(snapshot.data_origin).toBe('real');
    expect(snapshot.content_hash).toMatch(/^[a-f0-9]{64}$/);
    await page.reload();
    const row = page.getByTestId(`refresh-schedule-${scheduleId}`);
    const disabled = await uiPatch(page, `/api/v1/market/refresh-schedules/${scheduleId}`,
      () => row.getByRole('button', { name: 'Tắt lịch', exact: true }).click());
    expect(disabled.intent.body).toEqual({ enabled: false });
    expect(disabled.result.enabled).toBe(false);
    expect(disabled.result.version).toBe(2);
    await expect(row.getByRole('button', { name: 'Bật lịch', exact: true })).toBeEnabled();
    return { automatic, snapshot, schedule, disabled };
  } finally {
    // Recover the unique schedule even if its create committed but the browser
    // response was uncertain. This cleanup never enqueues another source job.
    const schedules = await get(page.context(), '/api/v1/market/refresh-schedules?limit=100&offset=0');
    const known = schedules.find((item: Value) => scheduleId ? item.id === scheduleId : item.name === name);
    if (known) {
      const current = await get(page.context(), `/api/v1/market/refresh-schedules/${known.id}`);
      if (current.enabled) {
        await mutate(page.context(), { path: `/api/v1/market/refresh-schedules/${current.id}`,
          method: 'PATCH', body: { enabled: false }, key: randomUUID(),
          if_match: `"${current.version}"` }, 200);
      }
    }
  }
}

async function waitJob(context: BrowserContext, path: string, timeout = 120_000) {
  await expect.poll(async () => (await get(context, path)).status,
    { timeout, intervals: [500, 1000, 2000] }).toBe('SUCCEEDED');
  return get(context, path);
}

async function capture(page: Page, name: string) {
  expect(new URL(page.url()).origin).toBe(origin);
  const directory = resolve(root, 'output/playwright/sanitized');
  await mkdir(directory, { recursive: true });
  await page.locator('#main-content').screenshot({
    path: resolve(directory, `${name}.png`), mask: [page.locator('.account-name')],
  });
}

async function propose(page: Page, pid: string, strategy: 'EW' | 'BL_ML') {
  await page.goto(`/#proposal?portfolio=${pid}`);
  await page.getByTestId(`strategy-${strategy}`).check();
  const submitted = await uiMutation(page, `${investorPath(pid)}/recommendations`,
    async () => { await page.getByTestId('propose-portfolio').click(); await page.getByTestId('confirm-proposal').click(); }, 202);
  await expect(page.getByTestId('accept-proposal')).toBeEnabled({ timeout: 90_000 });
  const job = await get(page.context(), `/api/v1/jobs/portfolio/${submitted.result.job_id}`);
  expect(job.status).toBe('SUCCEEDED');
  const result = await get(page.context(), `/api/v1/recommendations/${job.recommendation_id}`);
  expect(result.strategy).toBe(strategy);
  expect(result.requested_strategy).toBe(strategy);
  expect(result.fallback_reason).toBeNull();
  expect(result.demo).toBe(false);
  expect(result.inputs_provenance.data_origin).toBe('real');
  expect(result.weights.map(Number).reduce((sum: number, weight: number) => sum + weight, 0)).toBeCloseTo(1, 7);
  return { ...submitted, result };
}

async function verifyOperator(page: Page, receipt: Receipt) {
  const schedules = await get(page.context(), '/api/v1/market/refresh-schedules?limit=100&offset=0');
  const schedule = schedules.find((item: Value) => item.id === receipt.schedule_id);
  expect(schedule).toBeTruthy();
  expect(schedule.provider).toBe('kbs-direct-v1');
  expect(schedule.enabled).toBe(false);
  expect(schedule.version).toBe(receipt.schedule_result.version);
  expect(schedule.asset_ids).toEqual(receipt.asset_ids);
  expect(schedule.last_successful_cutoff).toBe(receipt.refresh_result.cutoff_date);
  const refresh = await get(page.context(), `/api/v1/market/refresh-jobs/${receipt.refresh_id}`);
  expect(refresh).toEqual(receipt.refresh_result);
  expect(refresh.provider).toBe('kbs-direct-v1');
  expect(refresh.calendar_verified).toBe(false);
  expect(refresh.availability_basis).toBe('ingestion');
  const automatic = await get(page.context(), `/api/v1/market/refresh-jobs/${receipt.auto_refresh_id}`);
  expect(automatic).toEqual(receipt.auto_refresh_result);
  expect(automatic.id).not.toBe(receipt.refresh_id);
  expect(automatic.status).toBe('SUCCEEDED');
  expect(automatic.schedule_version).toBe(receipt.auto_schedule_result.version);
  expect(automatic.schedule_id).toBe(receipt.auto_schedule_id);
  const autoSchedule = await get(page.context(), `/api/v1/market/refresh-schedules/${receipt.auto_schedule_id}`);
  expect(autoSchedule.enabled).toBe(false);
  expect(autoSchedule.version).toBe(receipt.auto_schedule_final_version);
  expect(autoSchedule.asset_ids).toEqual(receipt.asset_ids);
  expect(autoSchedule.last_successful_cutoff).toBe(automatic.cutoff_date);
  const automaticSnapshot = await get(page.context(), `/api/v1/market/snapshots/${receipt.auto_snapshot_id}`);
  expect(automatic.snapshot_id).toBe(receipt.auto_snapshot_id);
  expect(automaticSnapshot.content_hash).toBe(receipt.auto_snapshot_hash);
  expect(automaticSnapshot.provider).toBe('kbs-direct-v1');
  expect(automaticSnapshot.data_origin).toBe('real');
  for (const id of [...receipt.ingestion_ids, ...automatic.ingestion_job_ids]) {
    expect((await get(page.context(), `/api/v1/jobs/market/${id}`)).status).toBe('SUCCEEDED');
    expect((await get(page.context(), `/api/v1/market/ingestions/${id}/quality`)).status).toBe('PASS');
  }
  const snapshot = await get(page.context(), `/api/v1/market/snapshots/${receipt.snapshot_id}`);
  expect(snapshot.content_hash).toBe(receipt.snapshot_hash);
  expect(snapshot.provider).toBe('kbs-direct-v1');
  expect(snapshot.data_origin).toBe('real');
  expect(snapshot.asset_ids).toEqual(receipt.asset_ids);
  const training = await get(page.context(), `/api/v1/ml/training-jobs/${receipt.training_id}`);
  expect(training).toEqual(receipt.training_result);
  const model = await get(page.context(), `/api/v1/ml/models/${receipt.model_id}`);
  expect(model.status).toBe('APPROVED');
  expect(model.artifact_ready).toBe(true);
  expect(digest(model.metadata)).toBe(receipt.model_metadata_hash);
  expect(digest(model.provenance)).toBe(receipt.model_provenance_hash);
  expect(model.reviews.map((item: Value) => item.review_id)).toEqual([receipt.review_id]);
  const publication = await get(page.context(), `/api/v1/market/publications/${receipt.publication_id}`);
  expect(publication.status).toBe('SUCCEEDED');
  expect(publication.result).toEqual(receipt.publication_result);
  expect(publication.attempts).toBe(receipt.publication_attempts);
  expect(publication.request.approved_model_id).toBe(receipt.model_id);
  expect(publication.request.snapshot_hash).toBe(receipt.snapshot_hash);
  await page.goto('/#market-refresh');
  await expect(page.getByTestId(`refresh-schedule-${receipt.schedule_id}`)).toBeVisible();
  await expect(page.getByTestId(`refresh-schedule-${receipt.auto_schedule_id}`)).toBeVisible();
  await expect(page.getByTestId(`refresh-job-${receipt.refresh_id}`)).toHaveAttribute('data-status', 'SUCCEEDED');
  await expect(page.getByTestId(`refresh-job-${receipt.auto_refresh_id}`)).toHaveAttribute('data-status', 'SUCCEEDED');
  await page.goto(`/#model-review?model=${receipt.model_id}`);
  await expect(page.getByTestId('model-detail')).toHaveAttribute('data-status', 'APPROVED');
  await expect(page.getByTestId('model-detail')).toHaveAttribute('data-artifact-ready', 'true');
  await page.reload();
  await expect(page.getByTestId('model-detail')).toHaveAttribute('data-status', 'APPROVED');
  const readiness = await get(page.context(), '/api/v1/universes/readiness');
  const serving = readiness.find((item: Value) => item.universe_id === receipt.universe_id);
  expect(serving.approved_model_id).toBe(receipt.model_id);
  expect(serving.model_manifest_hash).toBe(receipt.model_manifest_hash);
  expect(serving.snapshot_id).toBe(receipt.snapshot_id);
  expect(serving.strategies.find((item: Value) => item.strategy === 'BL_ML')?.available).toBe(true);
  await expect(page.getByTestId(`model-serving-${receipt.universe_id}`)).toHaveAttribute('data-ready', 'true');
}

async function verifyInvestor(page: Page, receipt: Receipt) {
  const portfolio = await get(page.context(), investorPath(receipt.portfolio_id));
  expect(portfolio.risk_profile.version_id).toBe(receipt.assessment_id);
  expect(portfolio.policy_version_id).toBe(receipt.assessment_result.policy_version_id);
  const history = await get(page.context(), `${investorPath(receipt.portfolio_id)}/risk-assessments`);
  expect(history.find((item: Value) => item.id === receipt.assessment_id)).toEqual({ ...receipt.assessment_result, is_active: true });
  expect(history.find((item: Value) => item.id === receipt.old_risk_profile_id)?.is_active).toBe(false);
  const proposal = await get(page.context(), `/api/v1/recommendations/${receipt.proposal_id}`);
  expect(proposal.input_hash).toBe(receipt.input_hash);
  expect(proposal.risk_profile.version_id).toBe(receipt.assessment_id);
  expect(proposal.inputs_provenance.snapshot_hash).toBe(receipt.snapshot_hash);
  expect(proposal.diagnostics.inference.model_id).toBe(receipt.model_id);
  expect(proposal.diagnostics.inference.model_sha256).toBe(receipt.model_sha256);
  expect(proposal.diagnostics.inference.model_manifest_hash).toBe(receipt.model_manifest_hash);
  expect(proposal.model_bundle_id).toBe(receipt.model_manifest_hash);
  const targets = await get(page.context(), `${investorPath(receipt.portfolio_id)}/targets`);
  const old = targets.find((item: Value) => item.id === receipt.old_target_id);
  expect(old.recommendation_id).toBe(receipt.old_proposal_id);
  expect(old.allocation.risk_profile.version_id).toBe(receipt.old_risk_profile_id);
  expect(digest(old.allocation)).toBe(receipt.old_allocation_hash);
  const dashboard = await get(page.context(), `${investorPath(receipt.portfolio_id)}/dashboard`);
  expect(dashboard.accepted_target.id).toBe(receipt.target_id);
  expect(dashboard.accepted_target.recommendation_id).toBe(receipt.proposal_id);
  expect(digest(dashboard.accepted_target.allocation)).toBe(receipt.target_allocation_hash);
  expect(dashboard.holdings_status).toBe('NOT_TRACKED');
  await mutate(page.context(), { path: `/api/v1/recommendations/${receipt.pending_proposal_id}/accept`,
    body: {}, key: '', if_match: `"${portfolio.version}"` }, 409);
  await page.goto(`/#risk-assessment?portfolio=${receipt.portfolio_id}`);
  await expect(page.getByTestId(`risk-history-${receipt.assessment_id}`)).toBeVisible();
  await page.reload();
  await expect(page.getByTestId(`risk-history-${receipt.assessment_id}`)).toBeVisible();
  await page.goto(`/#history?portfolio=${receipt.portfolio_id}`);
  await expect(page.getByTestId(`target-row-${receipt.old_target_id}`)).toBeVisible();
  await expect(page.getByTestId(`target-row-${receipt.target_id}`)).toBeVisible();
}

test.beforeEach(() => {
  if (process.env.E2E_DISPOSABLE_STACK !== '1') throw new Error('Set E2E_DISPOSABLE_STACK=1 for the explicit localhost-only gate');
});

test('real P1 provider refresh model review publication and risk reassessment lifecycle', async ({ page, browser }, info) => {
  test.skip(persistence, 'Dedicated receipt mode verifies existing records after actual process restart');
  test.setTimeout(540_000);
  phase(info, 'p1-operator-pkce');
  await authenticate(page, 'data-operator', '/#market-refresh');
  const assets = ['FPT', 'MWG', 'VCB'];
  const today = new Date().toISOString().slice(0, 10);
  phase(info, 'p1-create-real-provider-schedule');
  await page.goto('/#market-refresh');
  await page.getByTestId('refresh-name').fill(`P1 live KBS ${Date.now()}`);
  await page.getByTestId('refresh-assets').fill(assets.join(','));
  await page.getByTestId('refresh-start').fill(dayBefore(today, 730));
  await page.getByTestId('refresh-interval').fill('10080');
  await page.getByTestId('refresh-overlap').fill('7');
  await page.getByTestId('refresh-max-age').fill('14');
  // Keep this manual schedule disabled. A second initially-enabled schedule
  // below must produce its own timer-owned job, then is disabled for cleanup.
  await page.getByTestId('refresh-enabled').uncheck();
  await page.getByTestId('refresh-review').click();
  const schedule = await uiMutation(page, '/api/v1/market/refresh-schedules',
    () => page.getByTestId('refresh-save').click(), 201);
  expect(schedule.result.provider).toBe('kbs-direct-v1');
  expect(schedule.result.asset_ids).toEqual(assets);
  expect((await mutate(page.context(), schedule.intent, 201)).result).toEqual(schedule.result);
  await mutate(page.context(), { ...schedule.intent, body: { ...schedule.intent.body, name: 'Different P1 schedule' } }, 409);
  await expect(page.getByTestId(`refresh-schedule-${schedule.result.id}`)).toBeVisible();

  phase(info, 'p1-real-provider-refresh-quality-snapshot');
  const refresh = await uiMutation(page, '/api/v1/market/refresh-jobs',
    () => page.getByTestId(`refresh-run-${schedule.result.id}`).click(), 202);
  const refreshId = refresh.result.id;
  const refreshed = await waitJob(page.context(), `/api/v1/market/refresh-jobs/${refreshId}`, 180_000);
  expect(refreshed.provider).toBe('kbs-direct-v1');
  expect(refreshed.artifacts).toHaveLength(assets.length + 1);
  expect(refreshed.artifacts[0].role).toBe('observed-calendar');
  for (const artifact of refreshed.artifacts) {
    expect(artifact.raw.sha256).toMatch(/^[a-f0-9]{64}$/);
    if (artifact.role === 'prices') expect(artifact.normalized.sha256).toMatch(/^[a-f0-9]{64}$/);
  }
  expect(refreshed.ingestion_job_ids).toHaveLength(assets.length);
  for (const id of refreshed.ingestion_job_ids) {
    const quality = await get(page.context(), `/api/v1/market/ingestions/${id}/quality`);
    expect(quality.status).toBe('PASS');
    expect(quality.row_count).toBeGreaterThan(252);
    expect(quality.calendar_verified).toBe(false);
    expect(quality.source_manifest_sha256).toMatch(/^[a-f0-9]{64}$/);
  }
  expect((await mutate(page.context(), refresh.intent, 202)).result.id).toBe(refreshId);
  await mutate(page.context(), { ...refresh.intent, body: { schedule_id: randomUUID() } }, 409);
  const snapshot = await get(page.context(), `/api/v1/market/snapshots/${refreshed.snapshot_id}`);
  expect(snapshot.data_origin).toBe('real');
  expect(snapshot.provider).toBe('kbs-direct-v1');
  expect(snapshot.content_hash).toMatch(/^[a-f0-9]{64}$/);
  expect(snapshot.asset_ids).toEqual(assets);
  await page.reload();
  await expect(page.getByTestId(`refresh-job-${refreshId}`)).toHaveAttribute('data-status', 'SUCCEEDED');
  await capture(page, 'p1-refresh-real-provider');

  phase(info, 'p1-automatic-scheduler');
  const automatic = await automaticScheduler(page, schedule.result, refreshId, assets);

  phase(info, 'p1-manual-training-candidate');
  await page.goto('/#model-training');
  await page.getByTestId('training-snapshot').selectOption(snapshot.id);
  await page.getByTestId('training-cutoff').fill(dayBefore(snapshot.end_date, 30));
  await page.getByTestId('training-lookback').fill('252');
  await page.getByTestId('training-min-returns').fill('60');
  await page.getByTestId('training-max-age').fill('14');
  await page.getByTestId('training-review').click();
  const training = await uiMutation(page, '/api/v1/ml/training-jobs',
    () => page.getByTestId('training-submit').click(), 202);
  const trained = await waitJob(page.context(), `/api/v1/ml/training-jobs/${training.result.job_id}`, 180_000);
  expect(trained.request.snapshot_hash).toBe(snapshot.content_hash);
  expect((await mutate(page.context(), training.intent, 202)).result.job_id).toBe(trained.job_id);
  await mutate(page.context(), { ...training.intent, body: { ...training.intent.body, lookback: 251 } }, 409);
  const modelId = trained.result.model_id;
  const candidate = await get(page.context(), `/api/v1/ml/models/${modelId}`);
  expect(candidate.status).toBe('CANDIDATE');
  expect(candidate.artifact_ready).toBe(false);
  expect(candidate.metadata.training_snapshot_hash).toBe(snapshot.content_hash);
  expect(candidate.metadata.demo).toBe(false);
  expect(candidate.metadata.validation.method).toBe('chronological-80-20-label-embargo-v1');
  expect(candidate.metadata.validation.train_label_end < candidate.metadata.validation.validation_start).toBe(true);
  const reviewPath = `/api/v1/ml/models/${modelId}/reviews`;
  await mutate(page.context(), { path: reviewPath, body: { decision: 'APPROVED', reason: 'Operator cannot review models' },
    key: randomUUID(), if_match: `"${candidate.version}"` }, 403);
  await page.goto('/#models');
  await expect(page.getByTestId(`model-${modelId}`)).toHaveAttribute('data-status', 'CANDIDATE');

  const reviewerContext = await browser.newContext({ baseURL: origin });
  const investorContext = await browser.newContext({ baseURL: origin });
  try {
    phase(info, 'p1-independent-reviewer-approval');
    const reviewer = await reviewerContext.newPage();
    await authenticate(reviewer, 'model-reviewer', `/#model-review?model=${modelId}`);
    await mutate(reviewerContext, { ...training.intent, key: randomUUID() }, 403);
    await reviewer.goto(`/#model-review?model=${modelId}`);
    await expect(reviewer.getByTestId('model-detail')).toHaveAttribute('data-status', 'CANDIDATE');
    await reviewer.getByTestId('model-review-decision').selectOption('APPROVED');
    await reviewer.getByTestId('model-review-reason').fill('P1 real source provenance, chronological validation and immutable model pins reviewed.');
    await reviewer.getByTestId('model-review-preview').click();
    const review = await uiMutation(reviewer, reviewPath,
      () => reviewer.getByTestId('model-review-submit').click(), 200);
    expect(review.intent.if_match).toBe(`"${candidate.version}"`);
    expect(review.result.status).toBe('APPROVED');
    const replayedReview = await mutate(reviewerContext, review.intent, 200);
    expect(replayedReview.result.reviews).toEqual(review.result.reviews);
    await mutate(reviewerContext, { ...review.intent, body: { ...review.intent.body, decision: 'REJECTED' } }, 409);
    await expect.poll(async () => (await get(reviewerContext, `/api/v1/ml/models/${modelId}`)).artifact_ready,
      { timeout: 90_000, intervals: [500, 1000, 2000] }).toBe(true);
    const approved = await get(reviewerContext, `/api/v1/ml/models/${modelId}`);
    expect(approved.reviews).toHaveLength(1);
    await reviewer.reload();
    await expect(reviewer.getByTestId('model-detail')).toHaveAttribute('data-artifact-ready', 'true');
    await capture(reviewer, 'p1-model-reviewed-approved');

    phase(info, 'p1-publish-approved-model-id');
    await page.goto('/#market-snapshots');
    await page.getByTestId(`market-snapshot-${snapshot.id}`).getByRole('button', { name: 'Phát hành', exact: true }).click();
    const universe = `P1_${Date.now()}`;
    await page.getByTestId('publication-universe').fill(universe);
    await page.getByTestId('publication-max-age').fill('14');
    await page.getByTestId('publication-model').selectOption(modelId);
    const publication = await uiMutation(page, '/api/v1/market/publications',
      () => page.getByTestId('market-publication-submit').click(), 202);
    expect(publication.intent.body.approved_model_id).toBe(modelId);
    expect(publication.intent.body.snapshot_hash).toBe(snapshot.content_hash);
    const published = await waitJob(page.context(), `/api/v1/market/publications/${publication.result.job_id}`, 120_000);
    expect(published.result.sha256).toMatch(/^[a-f0-9]{64}$/);
    expect((await mutate(page.context(), publication.intent, 202)).result.job_id).toBe(published.job_id);
    await mutate(page.context(), { ...publication.intent, body: { ...publication.intent.body, approved_model_id: randomUUID() } }, 409);
    await expect(page.getByTestId(`market-publication-${published.job_id}`)).toHaveAttribute('data-status', 'SUCCEEDED');

    phase(info, 'p1-investor-owner-and-role-boundaries');
    const alice = await investorContext.newPage();
    await authenticate(alice, 'alice');
    expect((await investorContext.request.get('/api/v1/market/refresh-schedules')).status()).toBe(403);
    expect((await investorContext.request.get('/api/v1/ml/models')).status()).toBe(403);
    await mutate(investorContext, { ...refresh.intent, key: randomUUID() }, 403);
    await mutate(investorContext, { ...training.intent, key: randomUUID() }, 403);
    await mutate(investorContext, { ...publication.intent, key: randomUUID() }, 403);
    await mutate(investorContext, { ...review.intent, key: randomUUID() }, 403);
    const readiness = await get(investorContext, '/api/v1/universes/readiness');
    expect(readiness.find((item: Value) => item.universe_id === universe)?.strategies.find((item: Value) => item.strategy === 'BL_ML')?.available).toBe(true);

    phase(info, 'p1-initial-target-and-pending-proposal');
    await alice.goto('/#create');
    await alice.getByLabel(/^Tên danh mục/).fill(`P1 live model risk ${Date.now()}`);
    await alice.getByLabel(/^Vốn kế hoạch \(VND\)/).fill('100000000');
    await alice.getByLabel('Thời gian đầu tư (tháng)').fill('36');
    await alice.getByLabel('Bộ tài sản').selectOption(universe);
    await alice.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
    await alice.getByRole('radio', { name: 'Vừa — chấp nhận dao động', exact: true }).check();
    await alice.getByRole('radio', { name: 'Thấp — có nguồn dự phòng riêng', exact: true }).check();
    await alice.getByRole('radio', { name: 'Đã có kinh nghiệm', exact: true }).check();
    await alice.getByRole('button', { name: 'Xem lại hồ sơ', exact: true }).click();
    const created = await uiMutation(alice, '/api/v1/onboarding/portfolios',
      () => alice.getByTestId('create-portfolio-submit').click(), 201, false);
    const pid = created.result.id;
    const first = await propose(alice, pid, 'EW');
    const oldTarget = await uiMutation(alice, `/api/v1/recommendations/${first.result.id}/accept`,
      () => alice.getByTestId('accept-proposal').click(), 200, false);
    const oldHash = digest(oldTarget.result.allocation);
    const pending = await propose(alice, pid, 'EW');
    const before = await get(investorContext, investorPath(pid));
    expect(before.version).toBe(2);

    phase(info, 'p1-risk-preview-confirm-and-stale-conflicts');
    await alice.goto(`/#risk-assessment?portfolio=${pid}`);
    await alice.getByTestId('risk-horizon').fill('120');
    await alice.getByTestId('risk-liquidity').selectOption('low');
    await alice.getByTestId('risk-loss').selectOption('high');
    await alice.getByTestId('risk-experience').selectOption('experienced');
    const preview = await uiMutation(alice, `${investorPath(pid)}/risk-assessments/preview`,
      () => alice.getByTestId('risk-preview').click(), 200, false);
    expect(preview.result.portfolio_version).toBe(before.version);
    expect(preview.result.before.risk_profile).toEqual(before.risk_profile);
    expect(preview.result.after.risk_profile.profile).toBe('growth');
    expect(preview.result.after.constraints.risk_aversion).toBe(1.5);
    expect(await get(investorContext, investorPath(pid))).toEqual(before);
    const assessment = await uiMutation(alice, `${investorPath(pid)}/risk-assessments`,
      () => alice.getByTestId('risk-confirm').click(), 201);
    expect(assessment.intent.if_match).toBe(`"${before.version}"`);
    expect(assessment.result.portfolio_version).toBe(3);
    expect(assessment.result.risk_profile.version_id).toBe(assessment.result.id);
    expect(assessment.result.policy_version_id).toBe(`risk-policy-v1:growth:${assessment.result.id}`);
    expect((await mutate(investorContext, assessment.intent, 201)).result).toEqual(assessment.result);
    await mutate(investorContext, { ...assessment.intent, key: randomUUID() }, 412);
    await mutate(investorContext, { ...assessment.intent, body: { answers: { ...assessment.intent.body.answers, horizon_months: 6 } } }, 409);
    await mutate(investorContext, { path: `/api/v1/recommendations/${pending.result.id}/accept`,
      body: {}, key: '', if_match: '"3"' }, 409);
    const unchangedTargets = await get(investorContext, `${investorPath(pid)}/targets`);
    expect(unchangedTargets).toHaveLength(1);
    expect(digest(unchangedTargets[0].allocation)).toBe(oldHash);
    await alice.reload();
    await expect(alice.getByTestId(`risk-history-${assessment.result.id}`)).toBeVisible();
    await capture(alice, 'p1-risk-assessment-history');

    phase(info, 'p1-fresh-bl-ml-pins-and-accepted-target');
    const fresh = await propose(alice, pid, 'BL_ML');
    expect(fresh.result.asset_ids).toEqual(assets);
    expect(fresh.result.risk_profile.version_id).toBe(assessment.result.id);
    expect(fresh.result.policy_version_id).toBe(assessment.result.policy_version_id);
    expect(fresh.result.inputs_provenance.snapshot_hash).toBe(snapshot.content_hash);
    expect(fresh.result.diagnostics.inference.model_id).toBe(modelId);
    expect(fresh.result.diagnostics.inference.training_snapshot_hash).toBe(snapshot.content_hash);
    expect(fresh.result.model_bundle_id).toBe(fresh.result.diagnostics.inference.model_manifest_hash);
    expect(fresh.result.diagnostics.inference.model_sha256).toMatch(/^[a-f0-9]{64}$/);
    const target = await uiMutation(alice, `/api/v1/recommendations/${fresh.result.id}/accept`,
      () => alice.getByTestId('accept-proposal').click(), 200, false);
    expect(target.result.portfolio_version).toBe(4);
    const stableRiskReplay = await mutate(investorContext, assessment.intent, 201);
    expect(stableRiskReplay.result).toEqual(assessment.result);
    expect(stableRiskReplay.etag).toBe(assessment.etag);
    const receipt: Receipt = {
      schema_version: 1, created_at: new Date().toISOString(), asset_ids: assets, universe_id: universe,
      schedule_id: schedule.result.id, schedule: schedule.intent, schedule_result: schedule.result,
      refresh_id: refreshId, refresh: refresh.intent, refresh_result: refreshed,
      auto_refresh_id: automatic.automatic.id, auto_refresh_result: automatic.automatic,
      auto_snapshot_id: automatic.snapshot.id, auto_snapshot_hash: automatic.snapshot.content_hash,
      auto_schedule_id: automatic.schedule.result.id, auto_schedule: automatic.schedule.intent,
      auto_schedule_result: automatic.schedule.result, auto_schedule_disable: automatic.disabled.intent,
      auto_schedule_final_version: automatic.disabled.result.version,
      snapshot_id: snapshot.id, snapshot_hash: snapshot.content_hash, ingestion_ids: refreshed.ingestion_job_ids,
      training_id: trained.job_id, training: training.intent, training_result: trained,
      model_id: modelId, model_metadata_hash: digest(approved.metadata), model_provenance_hash: digest(approved.provenance),
      model_sha256: fresh.result.diagnostics.inference.model_sha256,
      review: review.intent, review_id: approved.reviews[0].review_id, review_result_hash: digest(approved.reviews),
      publication_id: published.job_id, publication: publication.intent,
      publication_result: published.result, publication_attempts: published.attempts,
      portfolio_id: pid, old_proposal_id: first.result.id, pending_proposal_id: pending.result.id,
      old_target_id: oldTarget.result.id, old_allocation_hash: oldHash,
      old_risk_profile_id: created.result.risk_profile.version_id,
      assessment_id: assessment.result.id, assessment: assessment.intent, assessment_result: assessment.result,
      proposal_id: fresh.result.id, proposal: fresh.intent, input_hash: fresh.result.input_hash,
      model_manifest_hash: fresh.result.model_bundle_id,
      target_id: target.result.id, target_allocation_hash: digest(target.result.allocation),
    };
    await mkdir(generated, { recursive: true });
    await writeFile(receiptFile, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
    await verifyInvestor(alice, receipt);
    await capture(alice, 'p1-investor-target-history');
    await verifyOperator(page, receipt);
    await page.setViewportSize({ width: 390, height: 844 });
    await capture(page, 'p1-model-review-mobile');
  } finally {
    await reviewerContext.close();
    await investorContext.close();
  }
  phase(info, 'p1-complete');
});

test('same P1 durable model risk and target receipts after process restart', async ({ page, browser }, info) => {
  test.skip(!persistence, 'Run explicitly after root performs the actual service process restart');
  test.setTimeout(180_000);
  const receipt: Receipt = JSON.parse(await readFile(receiptFile, 'utf8'));
  expect(receipt.schema_version).toBe(1);
  phase(info, 'p1-restart-operator-pkce');
  await authenticate(page, 'data-operator', '/#market-refresh');
  await verifyOperator(page, receipt);
  await capture(page, 'p1-model-serving-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await capture(page, 'p1-model-serving-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  expect((await mutate(page.context(), receipt.schedule, 201)).result).toEqual(receipt.schedule_result);
  // Create replay returns the original enabled receipt without re-enabling
  // the current disabled schedule or enqueuing a second automatic job.
  expect((await mutate(page.context(), receipt.auto_schedule, 201)).result).toEqual(receipt.auto_schedule_result);
  expect((await mutate(page.context(), receipt.auto_schedule_disable, 200)).result.enabled).toBe(false);
  const automaticSchedule = await get(page.context(), `/api/v1/market/refresh-schedules/${receipt.auto_schedule_id}`);
  expect(automaticSchedule.enabled).toBe(false);
  const automaticJobs = await get(page.context(), '/api/v1/market/refresh-jobs?limit=100&offset=0');
  expect(automaticJobs.filter((item: Value) => item.schedule_id === receipt.auto_schedule_id).map((item: Value) => item.id)).toEqual([receipt.auto_refresh_id]);
  expect((await mutate(page.context(), receipt.refresh, 202)).result.id).toBe(receipt.refresh_id);
  expect((await mutate(page.context(), receipt.training, 202)).result.job_id).toBe(receipt.training_id);
  expect((await mutate(page.context(), receipt.publication, 202)).result.job_id).toBe(receipt.publication_id);
  const reviewerContext = await browser.newContext({ baseURL: origin });
  const investorContext = await browser.newContext({ baseURL: origin });
  try {
    phase(info, 'p1-restart-reviewer-same-approval');
    const reviewer = await reviewerContext.newPage();
    await authenticate(reviewer, 'model-reviewer', `/#model-review?model=${receipt.model_id}`);
    const review = await mutate(reviewerContext, receipt.review, 200);
    expect(digest(review.result.reviews)).toBe(receipt.review_result_hash);
    expect(review.result.artifact_ready).toBe(true);
    phase(info, 'p1-restart-investor-same-pins-and-targets');
    const alice = await investorContext.newPage();
    await authenticate(alice, 'alice');
    await verifyInvestor(alice, receipt);
    const risk = await mutate(investorContext, receipt.assessment, 201);
    expect(risk.result).toEqual(receipt.assessment_result);
    expect(risk.etag).toBe(`"${receipt.assessment_result.portfolio_version}"`);
    expect((await mutate(investorContext, receipt.proposal, 202)).result.job_id).toBe(receipt.proposal_id);
    await capture(alice, 'p1-targets-after-restart');
  } finally {
    await reviewerContext.close();
    await investorContext.close();
  }
  phase(info, 'p1-complete');
});
