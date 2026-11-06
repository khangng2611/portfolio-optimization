import { test, expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const root = resolve('../..');
const generated = resolve(root, 'infra/local/.generated');
const receiptFile = resolve(generated, 'browser-receipt.json');
const screenshots = resolve(root, 'output/playwright/sanitized');
const origin = 'http://localhost:3000';
const persistence = process.env.BROWSER_VERIFY_RECEIPT === '1';
type RecordValue = Record<string, any>;
type Receipt = { portfolio_id: string; proposal_id: string; target_id: string; allocation_hash: string; portfolio_name: string };
const digest = (value: unknown) => createHash('sha256').update(JSON.stringify(value)).digest('hex');

function phase(info: TestInfo, name: string) {
  info.annotations = info.annotations.filter(item => item.type !== 'safe-phase');
  info.annotations.push({ type: 'safe-phase', description: name });
  console.log(`BROWSER_PHASE: ${name}`);
}
function fixture(action: 'ready' | 'expired' | 'expire-session', input?: string) {
  const result = spawnSync('python3', ['scripts/browser_fixture.py', action, '--disposable'], {
    cwd: root, input, encoding: 'utf8', timeout: 30_000,
  });
  if (result.status !== 0) throw new Error('Disposable server fixture operation failed');
}
async function get(context: BrowserContext, path: string): Promise<RecordValue> {
  const response = await context.request.get(path);
  expect(response.status(), 'Owner-scoped BFF read').toBe(200);
  return response.json();
}
async function authenticate(page: Page, destination = '/') {
  const accounts = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  const account = accounts.users.find((item: { username: string }) => item.username === 'alice');
  if (!account?.password) throw new Error('Disposable investor unavailable');
  await page.goto(destination);
  await page.getByRole('link', { name: 'Đăng nhập qua Identity', exact: true }).click();
  await page.waitForURL(url => url.origin === 'http://localhost:8080');
  // Inspect in memory only: the authorization URL carries one-time state.
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
async function screenshot(page: Page, name: string) {
  // Only known post-login product content, never identity pages/navigation/user details.
  expect(new URL(page.url()).origin).toBe(origin);
  await mkdir(screenshots, { recursive: true });
  await page.locator('#main-content').screenshot({ path: resolve(screenshots, name + '.png'), mask: [page.locator('.account-name')] });
}
async function propose(page: Page, pid: string, strategy: 'EW' | 'MVO', expected?: { name: string; capital: RegExp }) {
  await page.goto(`/#proposal?portfolio=${pid}`);
  if (expected) {
    await expect(page.locator('.plan-context')).toContainText(expected.name);
    await expect(page.locator('.plan-context')).toContainText(expected.capital);
  }
  await page.getByTestId(`strategy-${strategy}`).check();
  const queued = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === `/api/v1/portfolios/${pid}/recommendations`);
  await page.getByTestId('propose-portfolio').click();
  await page.getByTestId('confirm-proposal').click();
  const response = await queued;
  expect(response.status()).toBe(202);
  expect(Boolean(response.request().headers()['idempotency-key'])).toBe(true);
  expect(Boolean(response.request().headers()['x-csrf-token'])).toBe(true);
  const job = await response.json();
  await expect(page.getByTestId('accept-proposal')).toBeEnabled({ timeout: 90_000 });
  const state = await get(page.context(), `/api/v1/jobs/portfolio/${job.job_id}`);
  expect(state.status).toBe('SUCCEEDED');
  const proposal = await get(page.context(), `/api/v1/recommendations/${state.recommendation_id}`);
  expect(proposal.demo).toBe(true);
  expect(proposal.strategy).toBe(strategy);
  expect(proposal.asset_ids).toEqual(['AAA', 'BBB', 'VFF']);
  expect(proposal.weights.map(Number).reduce((sum: number, item: number) => sum + item, 0)).toBeCloseTo(1, 7);
  return proposal;
}
async function verifyReceipt(page: Page, receipt: Receipt) {
  const dashboard = await get(page.context(), `/api/v1/portfolios/${receipt.portfolio_id}/dashboard`);
  expect(dashboard.accepted_target.id).toBe(receipt.target_id);
  expect(dashboard.accepted_target.recommendation_id).toBe(receipt.proposal_id);
  expect(digest(dashboard.accepted_target.allocation)).toBe(receipt.allocation_hash);
  expect(dashboard.holdings_status).toBe('NOT_TRACKED');
  const history = await get(page.context(), `/api/v1/portfolios/${receipt.portfolio_id}/targets`);
  expect((history as unknown as RecordValue[]).some(item => item.id === receipt.target_id)).toBe(true);
  await page.goto(`/#history?portfolio=${receipt.portfolio_id}`);
  await expect(page.getByTestId('target-row-' + receipt.target_id)).toBeVisible();
  await page.getByTestId('target-row-' + receipt.target_id).getByRole('button', { name: 'Xem mục tiêu', exact: true }).click();
  await expect(page.getByTestId('target-history')).toContainText('AAA');
  await page.reload();
  await expect(page.getByTestId('target-row-' + receipt.target_id)).toBeVisible();
}

test.beforeEach(() => {
  if (process.env.E2E_DISPOSABLE_STACK !== '1') throw new Error('Set E2E_DISPOSABLE_STACK=1 for this explicit localhost-only gate');
});

test('real PKCE lifecycle, conflict, expiry and reauthentication', async ({ page, browser }, info) => {
  test.skip(persistence, 'Only receipt verification runs after process restart');
  phase(info, 'register-demo');
  fixture('ready');
  try {
    phase(info, 'oidc-pkce');
    await authenticate(page);
    phase(info, 'create');
    const name = `Browser DEMO ${Date.now()}`;
    await page.goto('/#create');
    await page.getByLabel(/^Tên danh mục/).fill(name);
    await page.getByLabel(/^Vốn kế hoạch \(VND\)/).fill('100000000');
    await page.getByLabel('Thời gian đầu tư (tháng)').fill('36');
    await page.getByLabel('Bộ tài sản').selectOption('DEMO');
    await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
    await page.getByRole('radio', { name: 'Vừa — chấp nhận dao động', exact: true }).check();
    await page.getByRole('radio', { name: 'Thấp — có nguồn dự phòng riêng', exact: true }).check();
    await page.getByRole('radio', { name: 'Đã có kinh nghiệm', exact: true }).check();
    await page.getByRole('button', { name: 'Xem lại hồ sơ', exact: true }).click();
    const createdResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/onboarding/portfolios');
    await page.getByTestId('create-portfolio-submit').click();
    const createdHTTP = await createdResponse;
    expect(createdHTTP.status()).toBe(201);
    const portfolio = await createdHTTP.json();
    const pid = portfolio.id;
    await expect(page.getByRole('heading', { level: 1, name, exact: true })).toBeVisible();

    phase(info, 'broker-proposal-accept');
    const first = await propose(page, pid, 'EW');
    for (const weight of first.weights) expect(Number(weight)).toBeCloseTo(1 / 3, 7);
    const acceptedResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === `/api/v1/recommendations/${first.id}/accept`);
    await page.getByTestId('accept-proposal').click();
    const acceptedHTTP = await acceptedResponse;
    expect(acceptedHTTP.status()).toBe(200);
    expect(Boolean(acceptedHTTP.request().headers()['if-match'])).toBe(true);
    const target = await acceptedHTTP.json();
    await expect(page.getByTestId('accept-proposal')).toBeDisabled();
    const dashboard = await get(page.context(), `/api/v1/portfolios/${pid}/dashboard`);
    const receipt: Receipt = { portfolio_id: pid, proposal_id: first.id, target_id: target.id,
      allocation_hash: digest(dashboard.accepted_target.allocation), portfolio_name: name };
    await writeFile(receiptFile, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
    await verifyReceipt(page, receipt);

    phase(info, 'anonymous-deep-link-login-resume');
    const anonymous = await browser.newContext({ baseURL: origin });
    try {
      const deepPage = await anonymous.newPage();
      await authenticate(deepPage, `/#proposal?portfolio=${pid}&proposal=${first.id}`);
      await expect(deepPage).toHaveURL(`${origin}/#proposal?portfolio=${pid}&proposal=${first.id}`);
      await expect(deepPage.getByTestId('accept-proposal')).toBeDisabled();
      expect((await get(anonymous, `/api/v1/portfolios/${pid}/dashboard`)).accepted_target.id).toBe(target.id);
    } finally { await anonymous.close(); }

    phase(info, 'edit-and-412');
    await page.goto(`/#edit?portfolio=${pid}`);
    await expect(page.getByTestId('portfolio-name-input')).toHaveValue(name);
    const other = await page.context().newPage();
    await other.goto(`/#edit?portfolio=${pid}`);
    await expect(other.getByTestId('portfolio-name-input')).toHaveValue(name);
    const updatedName = name + ' updated';
    await other.getByTestId('portfolio-name-input').fill(updatedName);
    await other.getByTestId('portfolio-capital-input').fill('120000000');
    const update = other.waitForResponse(response => response.request().method() === 'PATCH' && new URL(response.url()).pathname === `/api/v1/portfolios/${pid}`);
    await other.getByTestId('edit-portfolio-submit').click();
    expect((await update).status()).toBe(200);
    await page.getByTestId('portfolio-name-input').fill(name + ' stale');
    const conflict = page.waitForResponse(response => response.request().method() === 'PATCH' && new URL(response.url()).pathname === `/api/v1/portfolios/${pid}`);
    await page.getByTestId('edit-portfolio-submit').click();
    expect((await conflict).status()).toBe(412);
    await expect(page.getByTestId('conflict-notice')).toBeVisible();
    await page.getByRole('button', { name: 'Tải phiên bản mới', exact: true }).click();
    await expect(page.getByTestId('portfolio-name-input')).toHaveValue(updatedName);
    await other.close();

    phase(info, 'compare-deep-link-reload');
    const second = await propose(page, pid, 'MVO', { name: updatedName, capital: /120[.,]000[.,]000/ });
    const comparison = `/#compare?portfolio=${pid}&a=${first.id}&b=${second.id}`;
    await page.goto(comparison);
    await expect(page.getByTestId('comparison')).toContainText('EW');
    await expect(page.getByTestId('comparison')).toContainText('MVO');
    await expect(page.getByTestId('comparison')).toContainText('AAA');
    await expect(page.getByTestId('comparison')).toContainText('Các phương án khác cơ sở đầu vào');
    await page.getByText('Đối chiếu dữ liệu & phiên bản', { exact: true }).click();
    for (const label of ['Ngày dữ liệu', 'Policy', 'Snapshot dữ liệu', 'Core', 'Vốn kế hoạch', 'Phiên bản danh mục']) {
      await expect(page.getByTestId('comparison')).toContainText(label);
    }
    await page.reload();
    await expect(page.getByTestId('comparison')).toContainText('MVO');
    await screenshot(page, 'comparison-desktop');
    await page.setViewportSize({ width: 390, height: 844 });
    await screenshot(page, 'comparison-mobile');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`/#proposal?portfolio=${pid}&proposal=${first.id}`);
    await expect(page.getByTestId('accept-proposal')).toBeDisabled();
    await page.reload();
    await expect(page.getByTestId('accept-proposal')).toBeDisabled();

    phase(info, 'expired-input');
    fixture('expired');
    await page.goto(`/#proposal?portfolio=${pid}`);
    await page.getByRole('button', { name: 'Kiểm tra lại', exact: true }).click();
    await expect(page.getByTestId('expired-input-notice')).toBeVisible();
    const readiness = await get(page.context(), `/api/v1/portfolios/${pid}/readiness`);
    expect(readiness.status).toBe('EXPIRED');
    await page.goto(`/#proposal?portfolio=${pid}`);
    await expect(page.getByTestId('propose-portfolio')).toBeDisabled();
    await verifyReceipt(page, receipt);
    fixture('ready');

    phase(info, '401-no-replay');
    await page.goto(`/#edit?portfolio=${pid}`);
    await expect(page.getByTestId('portfolio-name-input')).toHaveValue(updatedName);
    await page.getByTestId('portfolio-name-input').fill(name + ' must not replay');
    const cookie = (await page.context().cookies()).find(item => item.name === 'portfolio_session');
    if (!cookie) throw new Error('Local BFF session unavailable');
    fixture('expire-session', cookie.value);
    const unauthorized = page.waitForResponse(response => response.request().method() === 'PATCH' && new URL(response.url()).pathname === `/api/v1/portfolios/${pid}`);
    await page.getByTestId('edit-portfolio-submit').click();
    expect((await unauthorized).status()).toBe(401);
    await expect(page.getByTestId('session-expired-notice')).toBeVisible();
    // Keycloak's real SSO cookie reauthenticates; no product mutation is replayed.
    const callback = page.waitForResponse(response => new URL(response.url()).pathname === '/auth/callback');
    await page.getByRole('link', { name: 'Đăng nhập lại', exact: true }).click();
    expect((await callback).status()).toBe(303);
    await expect(page).toHaveURL(new RegExp(`#edit\\?portfolio=${pid}$`));
    await expect(page.getByTestId('portfolio-name-input')).toHaveValue(updatedName);
    expect((await get(page.context(), `/api/v1/portfolios/${pid}`)).name).toBe(updatedName);
    await verifyReceipt(page, receipt);
    phase(info, 'complete');
  } finally {
    fixture('ready');
  }
});

test('same persisted target receipt after service process restart', async ({ page }, info) => {
  test.skip(!persistence, 'Run separately after actual Compose process restart');
  phase(info, 'oidc-after-restart');
  await authenticate(page);
  const receipt: Receipt = JSON.parse(await readFile(receiptFile, 'utf8'));
  phase(info, 'same-receipt-after-restart');
  await verifyReceipt(page, receipt);
  await screenshot(page, 'history-after-restart');
  const proposals = await get(page.context(), `/api/v1/portfolios/${receipt.portfolio_id}/recommendations?limit=100&offset=0`);
  const comparison = (proposals as unknown as RecordValue[]).find(item => item.id !== receipt.proposal_id && item.strategy === 'MVO');
  expect(Boolean(comparison), 'Persisted second proposal available for comparison').toBe(true);
  await page.goto(`/#compare?portfolio=${receipt.portfolio_id}&a=${receipt.proposal_id}&b=${comparison!.id}`);
  await expect(page.getByTestId('comparison')).toContainText('MVO');
  await screenshot(page, 'comparison-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await screenshot(page, 'comparison-mobile');
  phase(info, 'complete');
});
