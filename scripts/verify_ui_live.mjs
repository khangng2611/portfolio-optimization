/** Real browser/BFF/Keycloak/DB/broker gate. Local disposable stack only.
 * No mocks/interception. Reads ignored local credentials without logging them.
 * PORTFOLIO_PLAYWRIGHT_MODULE may point to an existing Playwright package entry.
 */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';

const origin = 'http://localhost:3000';
const output = resolve('output/playwright/ui-live');
const verifyOnly = process.argv.includes('--verify-receipt');
const receiptPath = resolve('infra/local/.generated/ui-live-receipt.json');
const check = (condition, message) => { if (!condition) throw new Error(message); };
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const { chromium } = await import(process.env.PORTFOLIO_PLAYWRIGHT_MODULE ?? 'playwright');
const accounts = JSON.parse(await readFile('infra/local/.generated/accounts.json', 'utf8'));
const account = accounts.users.find(user => user.username === 'alice');
check(account?.password, 'Disposable investor account unavailable');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(20000);
const evidence = { started_at: new Date().toISOString(), origin, mode: 'real-browser-no-mocks', auth: {}, requests: [], runtime_errors: [] };
let receipt;
page.on('pageerror', error => evidence.runtime_errors.push(error.name));
page.on('response', response => {
  const url = new URL(response.url());
  if (url.origin !== origin || !/^\/(auth|api\/v1)\//.test(url.pathname)) return;
  const request = response.request();
  const headers = request.headers();
  evidence.requests.push({ method: request.method(), path: url.pathname, status: response.status(),
    ...(request.method() === 'POST' ? { csrf_present: !!headers['x-csrf-token'], idempotency_present: !!headers['idempotency-key'], version_precondition_present: !!headers['if-match'] } : {}) });
});
const screenshot = async name => { await page.evaluate(() => document.fonts.ready); await page.evaluate(() => window.scrollTo(0, 0)); await page.screenshot({ path: resolve(output, name + '.png'), fullPage: true }); };
const readAPI = async path => {
  const response = await context.request.get(origin + path);
  check(response.status() === 200, `Authenticated BFF read failed (${response.status()}): ${path}`);
  return response.json();
};
async function openPortfolio(name) {
  await page.locator('.sidebar a[href="#portfolios"]').click();
  const button = page.getByRole('button', { name: `Mở danh mục ${name}`, exact: true });
  // The list has an accessible search field when records exist.
  await page.getByLabel('Tìm trong danh sách').fill(name);
  await button.click();
  await page.getByRole('heading', { level: 1, name, exact: true }).waitFor();
}
try {
  await page.goto(origin, { waitUntil: 'domcontentloaded' });
  check(await page.getByRole('heading', { name: 'Đầu tư có kế hoạch. Quyết định có cơ sở.', exact: true }).count() === 1, 'Port 3000 does not serve the updated UI');
  await page.getByRole('link', { name: 'Đăng nhập qua Identity', exact: true }).click();
  await page.waitForURL(url => url.hostname === 'localhost' && url.port === '8080');
  const authURL = new URL(page.url());
  check(authURL.searchParams.get('client_id') === 'portfolio-web', 'Unexpected OIDC browser client');
  check(authURL.searchParams.get('code_challenge_method') === 'S256' && !!authURL.searchParams.get('code_challenge'), 'PKCE S256 challenge missing');
  check(authURL.searchParams.get('response_type') === 'code', 'Authorization code flow missing');
  evidence.auth = { client: 'portfolio-web', authorization_code: true, pkce_s256: true, issuer_origin: 'http://localhost:8080' };
  await page.locator('#username').fill(account.username);
  await page.locator('#password').fill(account.password);
  await Promise.all([
    page.waitForURL(url => url.origin === origin && url.pathname === '/', { timeout: 45000 }),
    page.locator('#kc-login').click(),
  ]);
  await page.getByRole('button', { name: 'Đăng xuất', exact: true }).waitFor();
  const sessionResponse = await context.request.get(origin + '/auth/session');
  const session = await sessionResponse.json();
  check(sessionResponse.status() === 200 && session.authenticated === true, 'Authenticated browser session missing');
  evidence.auth.session = 'passed';

  if (verifyOnly) {
    receipt = JSON.parse(await readFile(receiptPath, 'utf8'));
    const dashboard = await readAPI(`/api/v1/portfolios/${receipt.portfolio_id}/dashboard`);
    check(dashboard.accepted_target?.id === receipt.target_id, 'Persisted target changed after restart');
    check(hash(dashboard.accepted_target.allocation) === receipt.allocation_hash, 'Persisted allocation changed after restart');
    const history = await readAPI(`/api/v1/portfolios/${receipt.portfolio_id}/targets`);
    check(history.some(target => target.id === receipt.target_id), 'Persisted target history missing');
    await openPortfolio(receipt.portfolio_name);
    await page.locator('.dashboard').filter({ hasText: 'Đã lưu mục tiêu' }).waitFor();
    await screenshot('dashboard-after-restart');
    evidence.persistence = { passed: true, portfolio_id: receipt.portfolio_id, target_id: receipt.target_id, allocation_hash: receipt.allocation_hash };
  } else {
    const localStamp = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', dateStyle: 'short', timeStyle: 'medium' }).format(new Date());
    const name = `UI live · ${localStamp}`;
    await page.locator('.sidebar a[href="#portfolios"]').click();
    await page.getByRole('link', { name: 'Tạo danh mục', exact: true }).click();
    await page.getByLabel('Tên danh mục').fill(name);
    await page.getByLabel('Vốn kế hoạch (VND)').fill('100000000');
    await page.getByLabel('Thời gian đầu tư (tháng)').fill('36');
    await page.getByLabel('Bộ tài sản').selectOption('VN_EQUITY_REAL');
    await screenshot('onboarding-real');
    await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
    await page.getByLabel('Kinh nghiệm đầu tư').selectOption('experienced');
    await page.getByRole('button', { name: 'Xem lại hồ sơ', exact: true }).click();
    check(await page.locator('.wizard-review').innerText().then(text => text.includes(name) && text.includes('VN_EQUITY_REAL')), 'Review does not reflect the entered portfolio');
    const createdResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/onboarding/portfolios');
    await page.getByRole('button', { name: 'Xác nhận & tạo danh mục', exact: true }).click();
    const createdHTTP = await createdResponse;
    check(createdHTTP.status() === 201, `Onboarding failed (${createdHTTP.status()})`);
    const created = await createdHTTP.json();
    receipt = { portfolio_id: created.id, portfolio_name: name, created_at: new Date().toISOString(), universe_id: created.universe_id, portfolio_initial_version: created.version };
    await writeFile(receiptPath, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
    await page.getByRole('heading', { level: 1, name, exact: true }).waitFor();
    await page.getByRole('link', { name: 'Lập phương án phân bổ', exact: true }).click();
    await page.getByLabel('Chiến lược được cho phép').selectOption('MVO');
    const queuedResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === `/api/v1/portfolios/${created.id}/recommendations`);
    await page.getByRole('button', { name: 'Tạo đề xuất', exact: true }).click();
    const queuedHTTP = await queuedResponse;
    check(queuedHTTP.status() === 202, `Proposal enqueue failed (${queuedHTTP.status()})`);
    const queued = await queuedHTTP.json();
    receipt.job_id = queued.job_id;
    await writeFile(receiptPath, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
    await page.getByRole('button', { name: 'Chấp nhận làm mục tiêu', exact: true }).waitFor({ timeout: 90000 });
    const job = await readAPI(`/api/v1/jobs/portfolio/${queued.job_id}`);
    check(job.status === 'SUCCEEDED' && job.recommendation_id, 'Asynchronous job did not succeed');
    const allocation = await readAPI(`/api/v1/recommendations/${job.recommendation_id}`);
    check(allocation.portfolio_id === created.id && allocation.portfolio_version === created.version, 'Proposal portfolio/version mismatch');
    check(allocation.demo === false && allocation.inputs_provenance?.data_origin === 'real', 'Requested real-price provenance missing');
    check(allocation.strategy === 'MVO' && Date.parse(allocation.valid_until) > Date.now(), 'Proposal strategy/freshness invalid');
    const weights = allocation.weights.map(Number);
    check(weights.length === allocation.asset_ids.length && weights.length > 0, 'Asset/weight dimension mismatch');
    check(Math.abs(weights.reduce((sum, weight) => sum + weight, 0) - 1) < 1e-7, 'Weights do not sum to one');
    check(weights.every(weight => weight >= -1e-8 && weight <= created.constraints.max_position_weight + 1e-7), 'Allocation violates position policy');
    await screenshot('proposal-real');
    const acceptedResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === `/api/v1/recommendations/${allocation.id}/accept`);
    await page.getByRole('button', { name: 'Chấp nhận làm mục tiêu', exact: true }).click();
    const acceptedHTTP = await acceptedResponse;
    check(acceptedHTTP.status() === 200, `Target acceptance failed (${acceptedHTTP.status()})`);
    const target = await acceptedHTTP.json();
    await page.getByRole('button', { name: 'Đã lưu mục tiêu ✓', exact: true }).waitFor();
    check(await page.getByRole('button', { name: 'Đã lưu mục tiêu ✓', exact: true }).isDisabled(), 'Saved target remains actionable');
    const dashboard = await readAPI(`/api/v1/portfolios/${created.id}/dashboard`);
    check(dashboard.accepted_target?.id === target.id && dashboard.accepted_target.recommendation_id === allocation.id, 'Dashboard did not persist the accepted target');
    check(dashboard.holdings_status === 'NOT_TRACKED', 'Target acceptance changed holdings semantics');
    const history = await readAPI(`/api/v1/portfolios/${created.id}/targets`);
    check(history.some(item => item.id === target.id), 'Target history missing');
    receipt = { ...receipt, recommendation_id: allocation.id, target_id: target.id, allocation_hash: hash(dashboard.accepted_target.allocation),
      strategy: allocation.strategy, asset_ids: allocation.asset_ids, weights: allocation.weights, capital_vnd: allocation.capital_vnd,
      as_of_date: allocation.as_of_date, valid_until: allocation.valid_until, policy_version_id: allocation.policy_version_id,
      data_snapshot_id: allocation.data_snapshot_id, core_version: allocation.core_version, inputs_provenance: allocation.inputs_provenance,
      portfolio_accepted_version: dashboard.portfolio.version, holdings_status: dashboard.holdings_status };
    await writeFile(receiptPath, JSON.stringify(receipt, null, 2) + '\n', { mode: 0o600 });
    await page.getByRole('link', { name: 'Xem tổng quan danh mục', exact: true }).click();
    await screenshot('dashboard-real');
    await page.reload();
    await openPortfolio(name);
    await page.locator('.dashboard').filter({ hasText: 'Đã lưu mục tiêu' }).waitFor();
    await screenshot('dashboard-after-reload');
    evidence.workflow = { passed: true, receipt, dashboard_reload: 'passed', history: 'passed' };
    const mutations = evidence.requests.filter(item => item.method === 'POST' && item.path.startsWith('/api/v1/'));
    check(mutations.every(item => item.csrf_present), 'Mutation missing CSRF protection');
    check(mutations.some(item => item.path.endsWith('/recommendations') && item.idempotency_present), 'Proposal missing idempotency key');
    check(mutations.some(item => item.path.endsWith('/accept') && item.version_precondition_present), 'Acceptance missing If-Match precondition');
  }
  check(evidence.runtime_errors.length === 0, 'Browser runtime error occurred');
  await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click();
  await page.getByRole('link', { name: 'Đăng nhập qua Identity', exact: true }).waitFor();
  evidence.auth.logout = 'passed';
  evidence.passed = true;
  evidence.finished_at = new Date().toISOString();
  await writeFile(resolve(output, verifyOnly ? 'persistence.json' : 'browser-live.json'), JSON.stringify(evidence, null, 2) + '\n');
  console.log(JSON.stringify({ passed: true, mode: evidence.mode, persistence: verifyOnly, portfolio_id: receipt.portfolio_id, job_id: receipt.job_id, recommendation_id: receipt.recommendation_id, target_id: receipt.target_id, strategy: receipt.strategy, universe_id: receipt.universe_id, assets: receipt.asset_ids, weights: receipt.weights, output }, null, 2));
} catch (error) {
  // Never serialize credentials, cookies, authorization URLs or browser storage.
  evidence.passed = false;
  evidence.failure = { name: error.name, message: String(error.message).split('\n')[0].replace(/https?:\/\/\S+/g, '[URL redacted]') };
  await writeFile(resolve(output, 'failure.json'), JSON.stringify(evidence, null, 2) + '\n');
  console.error(`FAIL: ${evidence.failure.message}`);
  process.exitCode = 1;
} finally { await browser.close(); }
