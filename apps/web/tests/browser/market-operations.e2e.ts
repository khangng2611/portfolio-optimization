import { test, expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

// Real localhost Identity/BFF/Market/Quant/Portfolio only. No route interception.
const root = resolve('../..');
const generated = resolve(root, 'infra/local/.generated');
const receiptFile = resolve(generated, 'market-operations-browser-receipt.json');
const origin = 'http://localhost:3000';
const persistence = process.env.MARKET_OPS_VERIFY_RECEIPT === '1';
const retryOutage = process.env.MARKET_OPS_RETRY_OUTAGE === '1';
type Value = Record<string, any>;
type Source = { dataset_id: string; sha256: string; asset_id: string; row_count?: number };
type Fixture = { sources: Source[]; invalid: Source; asset_ids: string[]; start_date: string;
  end_date: string; as_of_date: string; max_age_days: number; universe_id: string };
type Intent = { path: string; body: Value; key: string; job_id?: string };
type Receipt = { sources: Source[]; ingestion_ids: string[]; quarantine_id: string;
  snapshot_id: string; snapshot_hash: string; publication_id: string; publication_result: Value;
  publication_attempts: number; publication: Intent; ingestions: Intent[];
  portfolio_id: string; proposal_id: string; target_id: string; input_hash: string; allocation_hash: string };
const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');

function phase(info: TestInfo, name: string) {
  info.annotations = info.annotations.filter(item => item.type !== 'safe-phase');
  info.annotations.push({ type: 'safe-phase', description: name });
  console.log(`BROWSER_PHASE: ${name}`);
}

async function authenticate(page: Page, username: 'alice' | 'data-operator', destination = '/') {
  const accounts = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  const account = accounts.users.find((item: { username: string }) => item.username === username);
  if (!account?.password) throw new Error('Disposable browser account unavailable');
  await page.goto(destination);
  await page.getByRole('link', { name: 'Đăng nhập qua Identity', exact: true }).click();
  await page.waitForURL(url => url.origin === 'http://localhost:8080');
  // One-time authorization state and credentials remain only in browser memory.
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

async function get(context: BrowserContext, path: string): Promise<any> {
  const response = await context.request.get(path);
  expect(response.status(), 'Real authenticated BFF read').toBe(200);
  return response.json();
}

async function mutate(context: BrowserContext, intent: Intent, status: number) {
  const session = await get(context, '/auth/session');
  const response = await context.request.post(intent.path, {
    data: intent.body,
    headers: { Origin: origin, 'X-CSRF-Token': session.csrfToken, 'Idempotency-Key': intent.key },
  });
  expect(response.status(), 'Real CSRF-protected BFF mutation').toBe(status);
  return response.json();
}

async function uiMutation(page: Page, path: string, action: () => Promise<unknown>, status: number) {
  const pending = page.waitForResponse(response => response.request().method() === 'POST'
    && new URL(response.url()).pathname === path);
  await action();
  const response = await pending;
  expect(response.status(), 'UI submits to real BFF').toBe(status);
  const request = response.request();
  expect(Boolean(request.headers()['x-csrf-token'])).toBe(true);
  const intent: Intent = { path, body: request.postDataJSON(), key: request.headers()['idempotency-key'] ?? '' };
  if (['/api/v1/market/datasets', '/api/v1/market/ingestions', '/api/v1/market/publications'].includes(path)
    || /^\/api\/v1\/portfolios\/[^/]+\/recommendations$/.test(path)) {
    expect(Boolean(intent.key), 'Durable operation has explicit idempotency key').toBe(true);
  }
  return { result: await response.json(), intent };
}

async function ingestion(context: BrowserContext, intent: Intent) {
  const result = await mutate(context, intent, 202);
  intent.job_id = result.job_id;
  return result.job_id as string;
}

async function waitIngestion(context: BrowserContext, id: string, status: 'SUCCEEDED' | 'FAILED') {
  await expect.poll(async () => (await get(context, `/api/v1/jobs/market/${id}`)).status,
    { timeout: 90_000, intervals: [300, 700, 1500] }).toBe(status);
  return get(context, `/api/v1/market/ingestions/${id}/quality`);
}

async function capture(page: Page, name: string) {
  expect(new URL(page.url()).origin).toBe(origin);
  const directory = resolve(root, 'output/playwright/sanitized');
  await mkdir(directory, { recursive: true });
  await page.locator('#main-content').screenshot({ path: resolve(directory, `${name}.png`),
    mask: [page.locator('.account-name')] });
}

async function verifyOperator(page: Page, receipt: Receipt) {
  for (const id of receipt.ingestion_ids) {
    expect((await get(page.context(), `/api/v1/jobs/market/${id}`)).status).toBe('SUCCEEDED');
    expect((await get(page.context(), `/api/v1/market/ingestions/${id}/quality`)).status).toBe('PASS');
  }
  const quarantine = await get(page.context(), `/api/v1/market/ingestions/${receipt.quarantine_id}/quality`);
  expect(quarantine.status).toBe('QUARANTINED');
  expect(quarantine.findings.some((item: Value) => item.code === 'INVALID_ROW')).toBe(true);
  const snapshot = await get(page.context(), `/api/v1/market/snapshots/${receipt.snapshot_id}`);
  expect(snapshot.content_hash).toBe(receipt.snapshot_hash);
  expect(snapshot.data_origin).toBe('real');
  const publication = await get(page.context(), `/api/v1/market/publications/${receipt.publication_id}`);
  expect(publication.status).toBe('SUCCEEDED');
  expect(publication.result).toEqual(receipt.publication_result);
  expect(publication.attempts).toBe(receipt.publication_attempts);
  expect(publication.request.snapshot_hash).toBe(receipt.snapshot_hash);
  await page.goto(`/#market-quality?job=${receipt.quarantine_id}`);
  await expect(page.getByTestId('market-quality-report')).toHaveAttribute('data-status', 'QUARANTINED');
  await page.reload();
  await expect(page.getByTestId('market-quality-report')).toContainText('INVALID_ROW');
  await page.goto(`/#market-publications?job=${receipt.publication_id}`);
  await expect(page.getByTestId(`market-publication-${receipt.publication_id}`)).toHaveAttribute('data-status', 'SUCCEEDED');
  await page.reload();
  await expect(page.getByTestId(`market-publication-${receipt.publication_id}`)).toHaveAttribute('data-status', 'SUCCEEDED');
}

async function verifyInvestor(page: Page, receipt: Receipt) {
  const proposal = await get(page.context(), `/api/v1/recommendations/${receipt.proposal_id}`);
  expect(proposal.demo).toBe(false);
  expect(proposal.input_hash).toBe(receipt.input_hash);
  expect(proposal.inputs_provenance.snapshot_hash).toBe(receipt.snapshot_hash);
  const dashboard = await get(page.context(), `/api/v1/portfolios/${receipt.portfolio_id}/dashboard`);
  expect(dashboard.accepted_target.id).toBe(receipt.target_id);
  expect(dashboard.accepted_target.recommendation_id).toBe(receipt.proposal_id);
  expect(digest(dashboard.accepted_target.allocation)).toBe(receipt.allocation_hash);
  expect(dashboard.holdings_status).toBe('NOT_TRACKED');
  await page.goto(`/#history?portfolio=${receipt.portfolio_id}`);
  await expect(page.getByTestId(`target-row-${receipt.target_id}`)).toBeVisible();
  await page.reload();
  await expect(page.getByTestId(`target-row-${receipt.target_id}`)).toBeVisible();
}

test.beforeEach(() => {
  if (process.env.E2E_DISPOSABLE_STACK !== '1') throw new Error('Set E2E_DISPOSABLE_STACK=1 for the explicit localhost-only gate');
});

test('real operator source to publication to investor accepted target', async ({ page, browser }, info) => {
  test.skip(persistence || retryOutage, 'Dedicated receipt/outage modes preserve the existing lifecycle records');
  test.setTimeout(300_000);
  phase(info, 'market-prepare-real-source-aliases');
  const prepared = spawnSync('python3', ['scripts/market_operations_fixture.py', 'prepare', '--disposable'],
    { cwd: root, encoding: 'utf8', timeout: 30_000 });
  if (prepared.status !== 0) throw new Error('Disposable Market Operations source preparation failed');
  const fixture: Fixture = JSON.parse(await readFile(resolve(generated, 'market-operations-fixture.json'), 'utf8'));
  phase(info, 'market-operator-pkce');
  await authenticate(page, 'data-operator', '/#market');
  await page.goto('/#market');

  phase(info, 'market-register-ingest-quality');
  const first = fixture.sources[0];
  const registered = await uiMutation(page, '/api/v1/market/datasets',
    () => page.getByTestId(`market-register-${first.dataset_id}`).click(), 201);
  expect(registered.result.sha256).toBe(first.sha256);
  expect(registered.result.data_origin).toBe('real');
  expect(registered.result.price_basis).toBe('provider_adjusted');
  expect((await mutate(page.context(), registered.intent, 201)).dataset_id).toBe(first.dataset_id);
  const firstJob = await uiMutation(page, '/api/v1/market/ingestions',
    () => page.getByTestId(`market-ingest-${first.dataset_id}`).click(), 202);
  firstJob.intent.job_id = firstJob.result.job_id;
  const intents = [firstJob.intent];
  const ids: string[] = [firstJob.result.job_id];
  for (const source of fixture.sources.slice(1)) {
    await mutate(page.context(), { path: '/api/v1/market/datasets',
      body: { dataset_id: source.dataset_id, expected_sha256: source.sha256 }, key: randomUUID() }, 201);
    const intent = { path: '/api/v1/market/ingestions', body: { dataset_id: source.dataset_id }, key: randomUUID() };
    ids.push(await ingestion(page.context(), intent));
    intents.push(intent);
  }
  for (const id of ids) {
    const quality = await waitIngestion(page.context(), id, 'SUCCEEDED');
    expect(quality.status).toBe('PASS');
    expect(quality.row_count).toBeGreaterThanOrEqual(61);
  }
  await page.goto(`/#market-quality?job=${ids[0]}`);
  await expect(page.getByTestId('market-quality-report')).toHaveAttribute('data-status', 'PASS');
  await capture(page, 'market-quality-pass');
  // Replaying a durable ingestion intent must return the same job, never a new write.
  expect((await mutate(page.context(), intents[0], 202)).job_id).toBe(ids[0]);
  const conflict = { ...intents[0], body: { dataset_id: fixture.sources[1].dataset_id } };
  await mutate(page.context(), conflict, 409);

  phase(info, 'market-quarantine-real-validator');
  await mutate(page.context(), { path: '/api/v1/market/datasets', key: randomUUID(),
    body: { dataset_id: fixture.invalid.dataset_id, expected_sha256: fixture.invalid.sha256 } }, 201);
  const badIntent = { path: '/api/v1/market/ingestions', body: { dataset_id: fixture.invalid.dataset_id }, key: randomUUID() };
  const badId = await ingestion(page.context(), badIntent);
  const quality = await waitIngestion(page.context(), badId, 'FAILED');
  expect(quality.status).toBe('QUARANTINED');
  expect(quality.findings.some((finding: Value) => finding.code === 'INVALID_ROW' && finding.action)).toBe(true);
  await page.goto(`/#market-quality?job=${badId}`);
  await expect(page.getByTestId('market-quality-report')).toHaveAttribute('data-status', 'QUARANTINED');
  await capture(page, 'market-quality-quarantine');

  phase(info, 'market-create-hash-pinned-snapshot');
  await page.goto('/#market-snapshots');
  await page.getByTestId('snapshot-assets').fill(fixture.asset_ids.join(','));
  await page.getByTestId('snapshot-start').fill(fixture.start_date);
  await page.getByTestId('snapshot-end').fill(fixture.end_date);
  await page.getByTestId('snapshot-asof').fill(fixture.as_of_date);
  await page.getByTestId('snapshot-max-age').fill(String(fixture.max_age_days));
  const snapshot = (await uiMutation(page, '/api/v1/market/snapshots',
    () => page.getByTestId('market-snapshot-submit').click(), 201)).result;
  expect(snapshot.data_origin).toBe('real');
  expect(snapshot.asset_ids).toEqual(fixture.asset_ids);
  expect(snapshot.content_hash).toMatch(/^[a-f0-9]{64}$/);
  await page.getByTestId(`market-snapshot-${snapshot.id}`).getByRole('button', { name: 'Phát hành', exact: true }).click();

  phase(info, 'market-durable-publication-worker');
  await page.getByTestId('publication-universe').fill(fixture.universe_id);
  await page.getByTestId('publication-max-age').fill(String(fixture.max_age_days));
  const submitted = await uiMutation(page, '/api/v1/market/publications',
    () => page.getByTestId('market-publication-submit').click(), 202);
  const publicationId = submitted.result.job_id;
  expect(submitted.intent.body.snapshot_id).toBe(snapshot.id);
  expect(submitted.intent.body.snapshot_hash).toBe(snapshot.content_hash);
  await expect(page.getByTestId(`market-publication-${publicationId}`)).toHaveAttribute('data-status', 'SUCCEEDED', { timeout: 90_000 });
  const publication = await get(page.context(), `/api/v1/market/publications/${publicationId}`);
  expect(publication.result.bundle_id).toBeTruthy();
  expect(publication.result.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect((await mutate(page.context(), submitted.intent, 202)).job_id).toBe(publicationId);
  await mutate(page.context(), { ...submitted.intent, body: { ...submitted.intent.body, snapshot_hash: '0'.repeat(64) } }, 409);
  await capture(page, 'market-publication-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, 'market-publication-mobile');

  phase(info, 'market-investor-ready-proposal-accept');
  const investor = await browser.newContext({ baseURL: origin });
  try {
    const alice = await investor.newPage();
    await authenticate(alice, 'alice');
    // Backend and BFF enforce operator boundaries for an actual investor cookie.
    expect((await investor.request.get('/api/v1/market/dataset-inventory')).status()).toBe(403);
    const investorSession = await get(investor, '/auth/session');
    expect((await investor.request.post('/api/v1/market/publications', { data: submitted.intent.body,
      headers: { Origin: origin, 'X-CSRF-Token': investorSession.csrfToken, 'Idempotency-Key': randomUUID() } })).status()).toBe(403);
    await alice.goto('/#create');
    await alice.getByLabel(/^Tên danh mục/).fill(`Market operations real ${Date.now()}`);
    await alice.getByLabel(/^Vốn kế hoạch \(VND\)/).fill('100000000');
    await alice.getByLabel('Thời gian đầu tư (tháng)').fill('36');
    await alice.getByLabel('Bộ tài sản').selectOption(fixture.universe_id);
    await alice.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
    await alice.getByLabel('Kinh nghiệm đầu tư').selectOption('experienced');
    await alice.getByRole('button', { name: 'Xem lại hồ sơ', exact: true }).click();
    const portfolio = (await uiMutation(alice, '/api/v1/onboarding/portfolios',
      () => alice.getByTestId('create-portfolio-submit').click(), 201)).result;
    await alice.goto(`/#proposal?portfolio=${portfolio.id}`);
    await alice.getByLabel('Chiến lược được cho phép').selectOption('EW');
    const job = (await uiMutation(alice, `/api/v1/portfolios/${portfolio.id}/recommendations`,
      () => alice.getByTestId('propose-portfolio').click(), 202)).result;
    await expect(alice.getByTestId('accept-proposal')).toBeEnabled({ timeout: 90_000 });
    const completed = await get(investor, `/api/v1/jobs/portfolio/${job.job_id}`);
    expect(completed.status).toBe('SUCCEEDED');
    const proposal = await get(investor, `/api/v1/recommendations/${completed.recommendation_id}`);
    expect(proposal.demo).toBe(false);
    expect(proposal.inputs_provenance.data_origin).toBe('real');
    expect(proposal.inputs_provenance.snapshot_hash).toBe(snapshot.content_hash);
    expect(proposal.asset_ids).toEqual(fixture.asset_ids);
    expect(proposal.weights.map(Number).reduce((sum: number, value: number) => sum + value, 0)).toBeCloseTo(1, 7);
    const target = (await uiMutation(alice, `/api/v1/recommendations/${proposal.id}/accept`,
      () => alice.getByTestId('accept-proposal').click(), 200)).result;
    const dashboard = await get(investor, `/api/v1/portfolios/${portfolio.id}/dashboard`);
    const receipt: Receipt = { sources: fixture.sources, ingestion_ids: ids, quarantine_id: badId,
      snapshot_id: snapshot.id, snapshot_hash: snapshot.content_hash, publication_id: publicationId,
      publication_result: publication.result, publication_attempts: publication.attempts,
      publication: submitted.intent, ingestions: intents, portfolio_id: portfolio.id,
      proposal_id: proposal.id, target_id: target.id, input_hash: proposal.input_hash,
      allocation_hash: digest(dashboard.accepted_target.allocation) };
    await writeFile(receiptFile, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
    await verifyInvestor(alice, receipt);
    await capture(alice, 'market-investor-target');
    await verifyOperator(page, receipt);
  } finally { await investor.close(); }
  phase(info, 'market-complete');
});

test('same market operations and accepted target receipt after process restart', async ({ page, browser }, info) => {
  test.skip(!persistence || retryOutage, 'Run explicitly after actual Compose process restart');
  phase(info, 'market-restart-operator-pkce');
  const receipt: Receipt = JSON.parse(await readFile(receiptFile, 'utf8'));
  await authenticate(page, 'data-operator', '/#market');
  phase(info, 'market-restart-same-durable-records');
  await verifyOperator(page, receipt);
  // Identical explicit retries recover the persisted intent, without new jobs.
  expect((await mutate(page.context(), receipt.publication, 202)).job_id).toBe(receipt.publication_id);
  for (const intent of receipt.ingestions) {
    expect((await mutate(page.context(), intent, 202)).job_id).toBe(intent.job_id);
  }
  const investor = await browser.newContext({ baseURL: origin });
  try {
    const alice = await investor.newPage();
    await authenticate(alice, 'alice');
    await verifyInvestor(alice, receipt);
    await capture(alice, 'market-target-after-restart');
  } finally { await investor.close(); }
  phase(info, 'market-complete');
});

test('real transient Market outage retries one durable publication to identical output', async ({ page }, info) => {
  test.skip(!retryOutage || persistence, 'Explicit optional outage gate; stops only the disposable market-api service');
  test.setTimeout(240_000);
  phase(info, 'market-outage-operator-pkce');
  const originalReceipt = await readFile(receiptFile, 'utf8');
  const receipt: Receipt = JSON.parse(originalReceipt);
  await authenticate(page, 'data-operator', '/#market-publications');
  const snapshot = await get(page.context(), `/api/v1/market/snapshots/${receipt.snapshot_id}`);
  expect(snapshot.content_hash).toBe(receipt.snapshot_hash);
  expect(snapshot.data_origin).toBe('real');
  const universe = `VN_OPS_RETRY_${randomUUID().replaceAll('-', '').slice(0, 16).toUpperCase()}`;
  const intent: Intent = { path: '/api/v1/market/publications', key: randomUUID(),
    body: { ...receipt.publication.body, snapshot_id: receipt.snapshot_id,
      snapshot_hash: receipt.snapshot_hash, universe_id: universe } };
  const marketService = (action: 'stop' | 'start') => {
    // Fixed service, fixed local files, no shell interpolation or expanded config.
    // Recovery is scoped to market-api; never restart dependency migration jobs.
    const command = ['compose', '--env-file', resolve(generated, '.env'),
      '-f', resolve(root, 'infra/local/compose.yaml'),
      ...(action === 'stop' ? ['stop', '--timeout', '5'] : ['up', '-d', '--no-deps']), 'market-api'];
    const result = spawnSync('docker', command, { cwd: root, stdio: 'ignore', timeout: 45_000 });
    if (result.status !== 0) throw new Error('Disposable market-api stop/start failed; raw diagnostics withheld');
  };
  let retryState: Value | undefined;
  let publicationId = '';
  try {
    phase(info, 'market-outage-stop-reader');
    marketService('stop');
    // The Quant API/BFF and publication worker remain live while their real
    // Market dependency is unavailable. No HTTP interception or SQL edits.
    const queued = await mutate(page.context(), intent, 202);
    publicationId = queued.job_id;
    intent.job_id = publicationId;
    phase(info, 'market-outage-observe-worker-retry');
    await expect.poll(async () => {
      const state = await get(page.context(), `/api/v1/market/publications/${publicationId}`);
      retryState = state;
      return state.status;
    }, { timeout: 60_000, intervals: [250, 500, 1000] }).toBe('RETRY');
    expect(retryState!.attempts).toBeGreaterThanOrEqual(1);
    const safeError = typeof retryState!.safe_error === 'string'
      ? retryState!.safe_error : retryState!.safe_error?.code;
    expect(safeError).toBe('MARKET_UNAVAILABLE');
    expect(retryState!.result).toBeNull();
    expect(Date.parse(retryState!.next_attempt_at)).toBeGreaterThan(Date.parse(retryState!.updated_at));
    await page.goto(`/#market-publications?job=${publicationId}`);
    const row = page.getByTestId(`market-publication-${publicationId}`);
    await expect(row).toHaveAttribute('data-status', 'RETRY');
    await expect(row).toContainText('Dịch vụ tạm thời chưa khả dụng; worker sẽ thử lại.');
    await capture(page, 'market-publication-transient-retry');
  } finally {
    // Also run if stop times out or any queue/assertion fails: recovery is never
    // dependent on a successful test assertion or the lifecycle receipt writer.
    phase(info, 'market-outage-restore-reader');
    marketService('start');
  }
  await expect.poll(async () => (await page.context().request.get('/api/v1/market/datasets?limit=1&offset=0')).status(),
    { timeout: 45_000, intervals: [500, 1000, 2000] }).toBe(200);
  phase(info, 'market-outage-recover-same-job');
  // Backoff is 30 seconds after the first failure, then 60 seconds; wait for
  // the worker's real due time rather than modifying its persistent schedule.
  await expect.poll(async () => (await get(page.context(), `/api/v1/market/publications/${publicationId}`)).status,
    { timeout: 120_000, intervals: [500, 1000, 2000] }).toBe('SUCCEEDED');
  const finalState = await get(page.context(), `/api/v1/market/publications/${publicationId}`);
  expect(finalState.attempts).toBeGreaterThanOrEqual(2);
  expect(finalState.request.snapshot_id).toBe(receipt.snapshot_id);
  expect(finalState.request.snapshot_hash).toBe(receipt.snapshot_hash);
  expect(finalState.request.universe_id).toBe(universe);
  expect(finalState.safe_error).toBeNull();
  expect(finalState.result.bundle_id).toBeTruthy();
  expect(finalState.result.sha256).toMatch(/^[a-f0-9]{64}$/);
  expect((await mutate(page.context(), intent, 202)).job_id).toBe(publicationId);
  const reread = await get(page.context(), `/api/v1/market/publications/${publicationId}`);
  expect(reread.result).toEqual(finalState.result);
  expect(reread.attempts).toBe(finalState.attempts);
  const catalog = JSON.parse(await readFile(resolve(generated, 'bundles/catalog.json'), 'utf8'));
  const artifacts = catalog.bundles.filter((entry: Value) => entry.bundle_id === finalState.result.bundle_id);
  expect(artifacts).toHaveLength(1);
  expect(artifacts[0].sha256).toBe(finalState.result.sha256);
  expect(artifacts[0].file).toMatch(/^[A-Za-z0-9._-]+$/);
  const bytes = await readFile(resolve(generated, 'bundles', artifacts[0].file));
  expect(createHash('sha256').update(bytes).digest('hex')).toBe(finalState.result.sha256);
  await page.reload();
  await expect(page.getByTestId(`market-publication-${publicationId}`)).toHaveAttribute('data-status', 'SUCCEEDED');
  await capture(page, 'market-publication-after-retry');
  expect(await readFile(receiptFile, 'utf8')).toBe(originalReceipt);
  await writeFile(resolve(generated, 'market-outage-receipt.json'), JSON.stringify({
    schema_version: 1, verified_at: new Date().toISOString(), snapshot_id: receipt.snapshot_id,
    snapshot_hash: receipt.snapshot_hash, universe_id: universe, publication_id: publicationId,
    intent, retry: { status: retryState!.status, attempts: retryState!.attempts,
      safe_error: retryState!.safe_error, next_attempt_at: retryState!.next_attempt_at },
    final: { status: finalState.status, attempts: finalState.attempts, result: finalState.result },
    artifact_sha256_verified: true,
  }, null, 2) + '\n', { mode: 0o600 });
  phase(info, 'market-outage-complete');
});
