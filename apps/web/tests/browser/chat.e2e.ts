import { test, expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

// Real localhost browser/PKCE/BFF/Chat/PostgreSQL/Portfolio/RabbitMQ/Quant.
// No HTTP routing/interception, synthetic result SQL, provider mocks or browser tokens.
const root = resolve('../..');
const generated = resolve(root, 'infra/local/.generated');
const origin = 'http://localhost:3000';
const persistence = process.env.CHAT_VERIFY_RECEIPT === '1';
const outage = process.env.CHAT_PROVIDER_OUTAGE === '1';
const llmLive = process.env.CHAT_LLM_LIVE === '1';
const receiptFile = resolve(generated, outage ? 'chat-browser-outage-receipt.json' : 'chat-browser-receipt.json');
type Value = Record<string, any>;
const digest = (v: unknown) => createHash('sha256').update(JSON.stringify(v)).digest('hex');
function phase(info: TestInfo, name: string) {
  info.annotations = info.annotations.filter(a => a.type !== 'safe-phase');
  info.annotations.push({ type: 'safe-phase', description: name });
  console.log(`BROWSER_PHASE: ${name}`);
}
async function get(context: BrowserContext, path: string): Promise<any> {
  const r = await context.request.get(path);
  expect(r.status(), 'Authenticated owner BFF read').toBe(200);
  return r.json();
}
async function authenticate(page: Page, destination: string) {
  const accounts = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  const account = accounts.users.find((a: Value) => a.username === 'alice');
  if (!account?.password) throw new Error('Disposable Chat investor missing');
  await page.goto(destination);
  const authorize = page.waitForRequest(r => new URL(r.url()).pathname === '/realms/portfolio/protocol/openid-connect/auth');
  await page.getByRole('link', { name: 'Đăng nhập qua Identity', exact: true }).click();
  const auth = new URL((await authorize).url());
  expect(auth.searchParams.get('response_type')).toBe('code');
  expect(auth.searchParams.get('client_id')).toBe('portfolio-web');
  expect(auth.searchParams.get('code_challenge_method')).toBe('S256');
  expect(Boolean(auth.searchParams.get('code_challenge'))).toBe(true);
  const form = await page.locator('#username').waitFor({ state: 'visible', timeout: 3000 }).then(() => true).catch(() => false);
  if (form) {
    await page.locator('#username').fill(account.username);
    await page.locator('#password').fill(account.password);
    await page.locator('#kc-login').click();
  }
  await page.waitForURL(url => url.origin === origin && url.pathname === '/');
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
  expect((await get(page.context(), '/auth/session')).authenticated).toBe(true);
  await page.goto(destination);
}
async function capture(page: Page, name: string) {
  expect(new URL(page.url()).origin).toBe(origin);
  const folder = resolve(root, 'output/playwright/sanitized');
  await mkdir(folder, { recursive: true });
  await page.locator('#main-content').screenshot({ path: resolve(folder, name + '.png'), mask: [page.locator('.account-name')] });
}
async function uiPost(page: Page, path: string, action: () => Promise<unknown>, status: number) {
  const pending = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path);
  await action();
  const response = await pending;
  expect(response.status(), 'UI POST uses the real BFF').toBe(status);
  const request = response.request();
  expect(Boolean(request.headers()['x-csrf-token'])).toBe(true);
  expect(request.headers().authorization).toBeUndefined();
  return { value: await response.json(), body: request.postDataJSON(), key: request.headers()['idempotency-key'] };
}
function worker(action: 'stop' | 'restart') {
  const result = spawnSync('docker', ['compose', '--env-file', resolve(generated, '.env'), '-f', resolve(root, 'infra/local/compose.yaml'), '-f', resolve(root, 'infra/local/compose.tracing.yaml'), action, 'chat-worker'], { cwd: root, encoding: 'utf8', timeout: 30_000 });
  expect(result.status, 'Real disposable Chat worker operation').toBe(0);
}
async function waitJob(context: BrowserContext, jid: string) {
  let job: Value = {};
  await expect.poll(async () => { job = await get(context, `/api/v1/jobs/chat/${jid}`); return job.status; }, { timeout: 90_000, intervals: [300, 600, 1000] }).toBe('SUCCEEDED');
  return job;
}
async function replay(context: BrowserContext, cid: string, intent: Value) {
  const session = await get(context, '/auth/session');
  const r = await context.request.post(`/api/v1/conversations/${cid}/messages`, { data: intent.body, headers: { Origin: origin, 'X-CSRF-Token': session.csrfToken, 'Idempotency-Key': intent.key } });
  expect(r.status()).toBe(202);
  expect((await r.json()).job_id).toBe(intent.value.job_id);
}
async function verify(page: Page, saved: Value) {
  const context = page.context();
  const path = `/api/v1/conversations/${saved.conversation_id}`;
  const conversation = await get(context, path);
  expect(conversation.id).toBe(saved.conversation_id);
  const messages = await get(context, path + '/messages?limit=100&offset=0');
  expect(digest(messages)).toBe(saved.messages_hash);
  const facts = await get(context, `/api/v1/recommendations/${saved.recommendation_id}`);
  expect(digest(facts)).toBe(saved.facts_hash);
  expect(facts.input_hash).toBe(saved.input_hash);
  const dashboard = await get(context, `/api/v1/portfolios/${saved.portfolio_id}/dashboard`);
  expect(dashboard.accepted_target.id).toBe(saved.target_id);
  expect(digest(dashboard.accepted_target.allocation)).toBe(saved.target_allocation_hash);
  for (const intent of saved.intents) await replay(context, saved.conversation_id, intent);
  expect(digest(await get(context, path + '/messages?limit=100&offset=0'))).toBe(saved.messages_hash);
  await page.goto(`/#chat?conversation=${saved.conversation_id}&job=${saved.job_id}`);
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
  await expect(page.getByTestId('chat-result').last()).toContainText(facts.asset_ids[0]);
  await page.reload();
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
}

test.beforeEach(() => {
  if (process.env.E2E_DISPOSABLE_STACK !== '1') throw new Error('Requires explicit E2E_DISPOSABLE_STACK=1 local gate');
});

test('real Chat LLM dialogue clarification grounded result and explicit accept', async ({ page }, info) => {
  test.skip(!llmLive, 'Paid provider gate is opt-in; ordinary tests spend no credits');
  test.setTimeout(180_000);
  const llmReceipt = resolve(generated, 'chat-llm-browser-receipt.json');
  if (persistence) {
    phase(info, 'chat-llm-restart');
    const saved = JSON.parse(await readFile(llmReceipt, 'utf8'));
    await authenticate(page, `/#chat?conversation=${saved.conversation_id}&job=${saved.job_id}`);
    await verify(page, saved);
    const jobs = await Promise.all(saved.intents.map((intent: Value) => get(page.context(), intent.value.status_url)));
    const usage = jobs.flatMap((job: Value) => job.provider_usage).filter((p: Value) => p?.reason === 'VERIFIED');
    expect(usage.length).toBe(saved.provider_calls);
    expect(usage.reduce((n: number, p: Value) => n + p.input_tokens, 0)).toBe(saved.input_tokens);
    expect(usage.reduce((n: number, p: Value) => n + p.output_tokens, 0)).toBe(saved.output_tokens);
    return;
  }
  phase(info, 'chat-llm-pkce');
  const input = JSON.parse(await readFile(resolve(generated, 'chat-real-input-receipt.json'), 'utf8'));
  await authenticate(page, '/#chat');
  const session = await get(page.context(), '/auth/session');
  const onboarded = await page.context().request.post('/api/v1/onboarding/portfolios', { data: { name: `LLM Chat ${Date.now()}`, capital_vnd: '100000000', universe_id: input.universe_id, answers: { questionnaire_version: 'risk-v1', horizon_months: 60, liquidity_need: 'low', loss_tolerance: 'high', experience: 'experienced' } }, headers: { Origin: origin, 'X-CSRF-Token': session.csrfToken } });
  expect(onboarded.status()).toBe(201);
  const pid = (await onboarded.json()).id;
  await page.goto(`/#chat?portfolio=${pid}`);
  await page.getByTestId('chat-title').fill('LLM hỗ trợ làm rõ kế hoạch');
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id, path = `/api/v1/conversations/${cid}`;
  await expect(page.getByTestId('chat-llm-consent')).not.toBeChecked();
  await uiPost(page, path + '/preferences', () => page.getByTestId('chat-llm-consent').click(), 200);
  await expect(page.getByTestId('chat-llm-consent')).toBeChecked();
  async function natural(content: string, expectedStatus: string) {
    await page.getByTestId('chat-input').fill(content);
    const receipt = await uiPost(page, path + '/messages', () => page.getByTestId('chat-send').click(), 202);
    let state: Value = {};
    await expect.poll(async () => { state = await get(page.context(), receipt.value.status_url); return state.status; }, { timeout: 60_000 }).toBe(expectedStatus);
    const rows = await get(page.context(), path + '/messages?limit=100&offset=0');
    return { receipt, state, message: rows.find((m: Value) => m.id === state.result_message_id) };
  }
  phase(info, 'chat-llm-clarify');
  const first = await natural('Tôi muốn bạn giúp tôi chia vốn cho kế hoạch này.', 'WAITING_INPUT');
  expect(first.message.structured.fields).toEqual(['strategy']);
  expect(first.message.structured.dialogue.reason).toBe('VERIFIED');
  expect((await get(page.context(), `/api/v1/portfolios/${pid}/recommendations`)).length).toBe(0);
  const second = await natural('Dùng mean variance (MVO) nhé.', 'WAITING_INPUT');
  expect(second.message.structured.type).toBe('confirmation');
  expect(second.message.structured.input.strategy).toBe('MVO');
  expect(second.message.structured.dialogue.reason).toBe('VERIFIED');
  await expect(page.getByTestId('chat-confirm').last()).toBeEnabled();
  phase(info, 'chat-llm-confirm');
  const confirmed = await uiPost(page, path + '/messages', () => page.getByTestId('chat-confirm').last().click(), 202);
  const allocation = await waitJob(page.context(), confirmed.value.job_id);
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
  const facts = await get(page.context(), `/api/v1/recommendations/${allocation.recommendation_id}`);
  expect(facts.inputs_provenance.data_origin).toBe('real');
  let rows = await get(page.context(), path + '/messages?limit=100&offset=0');
  const explanation = rows.find((m: Value) => m.id === allocation.result_message_id);
  expect(explanation.structured.provider.provider).toBe('openai');
  expect(explanation.structured.provider.reason).toBe('VERIFIED');
  expect(explanation.structured.facts).toEqual(facts);
  phase(info, 'chat-llm-followup');
  const followup = await natural('Nói rõ thêm kết quả vừa rồi giúp tôi.', 'SUCCEEDED');
  expect(followup.state.recommendation_id).toBe(facts.id);
  expect(followup.message.structured.provider.reason).toBe('VERIFIED');
  expect(followup.message.structured.facts).toEqual(facts);
  expect((await get(page.context(), `/api/v1/portfolios/${pid}/recommendations`)).length).toBe(1);
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
  await capture(page, 'chat-llm-grounded-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await capture(page, 'chat-llm-grounded-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  phase(info, 'chat-llm-consent-revoke');
  await uiPost(page, path + '/preferences', () => page.getByTestId('chat-llm-consent').click(), 200);
  await expect(page.getByTestId('chat-llm-consent')).not.toBeChecked();
  const noConsent = await natural('Xin chào', 'SUCCEEDED');
  expect(noConsent.message.structured.dialogue.reason).toBe('CONSENT_REQUIRED');
  await page.getByTestId('chat-open-recommendation').last().click();
  const accepted = await uiPost(page, `/api/v1/recommendations/${facts.id}/accept`, () => page.getByTestId('accept-proposal').click(), 200);
  rows = await get(page.context(), path + '/messages?limit=100&offset=0');
  const jobs = await Promise.all([first.receipt, second.receipt, confirmed, followup.receipt, noConsent.receipt].map(intent => get(page.context(), intent.value.status_url)));
  const usage = jobs.flatMap((job: Value) => job.provider_usage).filter((p: Value) => p?.reason === 'VERIFIED' && p.provider === 'openai');
  expect(usage.length).toBe(5);
  const saved = {
    schema_version: 1, conversation_id: cid, portfolio_id: pid, job_id: noConsent.state.job_id,
    recommendation_id: facts.id, target_id: accepted.value.id, input_hash: facts.input_hash,
    facts_hash: digest(facts), messages_hash: digest(rows), target_allocation_hash: digest(accepted.value.allocation),
    intents: [first.receipt, second.receipt, confirmed, followup.receipt, noConsent.receipt],
    provider_calls: usage.length, input_tokens: usage.reduce((n: number, p: Value) => n + p.input_tokens, 0),
    output_tokens: usage.reduce((n: number, p: Value) => n + p.output_tokens, 0),
    estimated_cost_usd: usage.reduce((n: number, p: Value) => n + p.estimated_cost_usd, 0),
  };
  await verify(page, saved);
  await writeFile(llmReceipt, JSON.stringify(saved, null, 2) + '\n', { mode: 0o600 });
  phase(info, 'chat-llm-complete');
});

test('real Chat PKCE confirmation allocation explanation accept and reconnect', async ({ page }, info) => {
  test.skip(persistence, 'Receipt mode reads the original Chat resources after restart');
  test.setTimeout(240_000);
  phase(info, 'chat-pkce');
  const baseline = JSON.parse(await readFile(resolve(generated, 'chat-api-receipt.json'), 'utf8'));
  await authenticate(page, '/#chat');
  const session = await get(page.context(), '/auth/session');
  const sourcePortfolio = await get(page.context(), `/api/v1/portfolios/${baseline.portfolio_id}`);
  // Actual onboarding API creates a separate fixture portfolio. Browser acceptance
  // must not mutate the independently recorded API-gate portfolio/version.
  const onboarded = await page.context().request.post('/api/v1/onboarding/portfolios', { data: { name: `Browser Chat ${Date.now()}`, capital_vnd: '100000000', universe_id: sourcePortfolio.universe_id, answers: { questionnaire_version: 'risk-v1', horizon_months: 60, liquidity_need: 'low', loss_tolerance: 'high', experience: 'experienced' } }, headers: { Origin: origin, 'X-CSRF-Token': session.csrfToken } });
  expect(onboarded.status()).toBe(201);
  const pid = (await onboarded.json()).id;
  await page.goto(`/#chat?portfolio=${pid}`);
  phase(info, 'chat-create-conversation');
  await page.getByTestId('chat-title').fill(`Kế hoạch Chat ${Date.now()}`);
  await page.getByTestId('chat-portfolio').selectOption(pid);
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id;
  await expect(page).toHaveURL(new RegExp(`conversation=${cid}`));
  const before = await get(page.context(), `/api/v1/portfolios/${pid}/recommendations`);
  const sendPath = `/api/v1/conversations/${cid}/messages`;
  await page.getByLabel('Tùy chọn hội thoại', { exact: true }).click();
  await page.getByTestId('chat-strategy-MVO').check();
  await page.getByTestId('chat-input').fill('Tôi muốn tạo phân bổ danh mục theo hồ sơ đã xác nhận.');
  let first: Awaited<ReturnType<typeof uiPost>>;
  worker('stop');
  try {
    const stream = page.waitForResponse(r => new URL(r.url()).pathname.startsWith('/api/v1/jobs/chat/') && new URL(r.url()).pathname.endsWith('/events'));
    first = await uiPost(page, sendPath, () => page.getByTestId('chat-send').click(), 202);
    expect(first.key).toBe(first.body.client_message_id);
    const response = await stream;
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('text/event-stream');
    expect(response.request().headers()['last-event-id']).toMatch(/^\d+$/);
    await expect.poll(() => page.evaluate(jid => Object.keys(sessionStorage).some(key => key.startsWith('portfolio.chat.sequence.') && key.endsWith('.' + jid) && Number(sessionStorage.getItem(key)) >= 1), first.value.job_id)).toBe(true);
    await page.context().setOffline(true);
    worker('restart');
    await expect.poll(async () => (await get(page.context(), first.value.status_url)).status, { timeout: 30_000 }).toBe('WAITING_INPUT');
    await page.context().setOffline(false);
  } finally { worker('restart'); await page.context().setOffline(false); }
  await expect(page.getByTestId('chat-confirm').last()).toBeVisible();
  expect((await get(page.context(), `/api/v1/portfolios/${pid}/recommendations`)).length).toBe(before.length);
  const initialHistory = await get(page.context(), `/api/v1/conversations/${cid}/messages?limit=100&offset=0`);
  await page.reload();
  await expect(page.getByTestId('chat-confirm').last()).toBeVisible();
  expect(await get(page.context(), `/api/v1/conversations/${cid}/messages?limit=100&offset=0`)).toEqual(initialHistory);
  await capture(page, 'chat-confirmation-desktop');
  phase(info, 'chat-confirm-and-disconnect');
  const confirmed = await uiPost(page, sendPath, () => page.getByTestId('chat-confirm').last().click(), 202);
  expect(confirmed.body.confirmation.message_id).toBeTruthy();
  expect(confirmed.body.confirmation.facts_hash).toMatch(/^[a-f0-9]{64}$/);
  await page.context().setOffline(true);
  const job = await waitJob(page.context(), confirmed.value.job_id);
  await page.context().setOffline(false);
  await expect(page.getByTestId('chat-result').last()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.chat-workspace .error')).toHaveCount(0);
  const rid = job.recommendation_id;
  const facts = await get(page.context(), `/api/v1/recommendations/${rid}`);
  expect(facts.inputs_provenance.data_origin).toBe('real');
  const messages = await get(page.context(), `/api/v1/conversations/${cid}/messages?limit=100&offset=0`);
  const result = messages.find((m: Value) => m.id === job.result_message_id);
  expect(result.structured.facts).toEqual(facts);
  expect(result.structured.explanation_status).toBe('TEMPLATE');
  if (outage) expect(['PROVIDER_UNAVAILABLE', 'TIMEOUT']).toContain(result.structured.provider.reason);
  await capture(page, outage ? 'chat-provider-outage' : 'chat-canonical-result-desktop');
  phase(info, 'chat-mobile-and-reload');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await capture(page, 'chat-canonical-result-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  phase(info, 'chat-explicit-accept-ui');
  await page.getByTestId('chat-open-recommendation').last().click();
  await expect(page.getByTestId('accept-proposal')).toBeEnabled();
  const accepted = await uiPost(page, `/api/v1/recommendations/${rid}/accept`, () => page.getByTestId('accept-proposal').click(), 200);
  await expect(page.getByTestId('accept-proposal')).toHaveText('Đã lưu mục tiêu');
  const saved = {
    schema_version: 1, created_at: new Date().toISOString(), portfolio_id: pid,
    conversation_id: cid, job_id: job.job_id, recommendation_id: rid,
    target_id: accepted.value.id, facts_hash: digest(facts), input_hash: facts.input_hash,
    target_allocation_hash: digest(accepted.value.allocation), messages_hash: digest(messages),
    intents: [first, confirmed],
  };
  await verify(page, saved);
  await writeFile(receiptFile, JSON.stringify(saved, null, 2) + '\n', { mode: 0o600 });
  phase(info, 'chat-complete');
});

test('real Chat saved conversation recommendation target and histories after restart', async ({ page }, info) => {
  test.skip(!persistence, 'Requires receipt produced before an external restart');
  phase(info, 'chat-restart-pkce');
  const receipt = JSON.parse(await readFile(receiptFile, 'utf8'));
  await authenticate(page, `/#chat?conversation=${receipt.conversation_id}&job=${receipt.job_id}`);
  await verify(page, receipt);
  await capture(page, 'chat-restart-persisted-history');
  phase(info, 'chat-restart-complete');
});

test('real Chat session expiry requires explicit reconfirmation before retry', async ({ page }, info) => {
  test.skip(persistence, 'Session recovery creates a separate disposable conversation');
  test.setTimeout(180_000);
  phase(info, 'chat-session-pkce');
  const baseline = JSON.parse(await readFile(resolve(generated, 'chat-browser-receipt.json'), 'utf8'));
  const pid = baseline.portfolio_id;
  await authenticate(page, `/#chat?portfolio=${pid}`);
  await page.getByTestId('chat-title').fill(`Kiểm tra phiên Chat ${Date.now()}`);
  await page.getByTestId('chat-portfolio').selectOption(pid);
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id, path = `/api/v1/conversations/${cid}/messages`;
  await page.getByLabel('Tùy chọn hội thoại', { exact: true }).click();
  await page.getByTestId('chat-strategy-MVO').check();
  await page.getByTestId('chat-input').fill('Tôi muốn tạo phân bổ danh mục theo hồ sơ đã xác nhận.');
  await uiPost(page, path, () => page.getByTestId('chat-send').click(), 202);
  await expect(page.getByTestId('chat-confirm').last()).toBeVisible();
  const history = await get(page.context(), path + '?limit=100&offset=0');
  const proposals = await get(page.context(), `/api/v1/portfolios/${pid}/recommendations`);
  const cookie = (await page.context().cookies(origin)).find(c => c.name === 'portfolio_session');
  expect(Boolean(cookie)).toBe(true);
  const expired = spawnSync('python3', ['scripts/browser_fixture.py', 'expire-session', '--disposable'], { cwd: root, input: cookie!.value, encoding: 'utf8', timeout: 30_000 });
  expect(expired.status, 'Expired one real Redis BFF session').toBe(0);
  phase(info, 'chat-session-denied-confirmation');
  const denied = await uiPost(page, path, () => page.getByTestId('chat-confirm').last().click(), 401);
  await expect(page.getByTestId('session-expired-notice')).toBeVisible();
  phase(info, 'chat-session-fresh-pkce');
  await authenticate(page, `/#chat?conversation=${cid}`);
  await expect(page.getByTestId('chat-retry')).toBeVisible();
  expect(await get(page.context(), path + '?limit=100&offset=0')).toEqual(history);
  expect((await get(page.context(), `/api/v1/portfolios/${pid}/recommendations`)).length).toBe(proposals.length);
  phase(info, 'chat-session-explicit-retry');
  const retried = await uiPost(page, path, () => page.getByTestId('chat-retry').click(), 202);
  expect(retried.body).toEqual(denied.body);
  expect(retried.key).toBe(denied.key);
  const job = await waitJob(page.context(), retried.value.job_id);
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
  expect(job.recommendation_id).toBeTruthy();
  await capture(page, 'chat-session-reconfirmed');
  phase(info, 'chat-session-complete');
});

test('real Chat late refresh cannot hide a newer accepted turn', async ({ page }, info) => {
  test.skip(persistence, 'Creates one extra read-only Chat turn against real APIs');
  phase(info, 'chat-race-pkce');
  const saved = JSON.parse(await readFile(receiptFile, 'utf8'));
  await authenticate(page, `/#chat?conversation=${saved.conversation_id}&job=${saved.job_id}`);
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  const canonicalPath = `/api/v1/recommendations/${saved.recommendation_id}`;
  const content = `Hướng dẫn sử dụng danh mục ${Date.now()}`;
  if (await page.locator('.chat-advanced').getAttribute('open') === null) await page.getByLabel('Tùy chọn hội thoại', { exact: true }).click();
  await page.getByRole('group', { name: 'Mục đích', exact: true }).getByRole('radio', { name: 'Trợ giúp', exact: true }).check();
  await page.getByTestId('chat-input').fill(content);
  // Delay the genuine network response; no interception, altered body or SQL.
  await cdp.send('Network.emulateNetworkConditionsByRule', { matchedNetworkConditions: [{ urlPattern: origin + canonicalPath, latency: 3000, downloadThroughput: -1, uploadThroughput: -1 }] });
  try {
    const slowRead = page.waitForRequest(r => new URL(r.url()).pathname === canonicalPath);
    const lateResponse = page.waitForResponse(r => new URL(r.url()).pathname === canonicalPath);
    await page.getByRole('button', { name: 'Tải lại trạng thái', exact: true }).click();
    await slowRead;
    phase(info, 'chat-race-new-turn');
    const sent = await uiPost(page, `/api/v1/conversations/${saved.conversation_id}/messages`, () => page.getByTestId('chat-send').click(), 202);
    await waitJob(page.context(), sent.value.job_id);
    await lateResponse;
    await expect(page.getByText(content, { exact: true })).toBeVisible({ timeout: 15_000 });
    expect(new URL(page.url()).hash).toContain('job=' + sent.value.job_id);
    saved.messages_hash = digest(await get(page.context(), `/api/v1/conversations/${saved.conversation_id}/messages?limit=100&offset=0`));
    saved.intents.push(sent); saved.recovery_job_id = sent.value.job_id;
    await writeFile(receiptFile, JSON.stringify(saved, null, 2) + '\n', { mode: 0o600 });
    phase(info, 'chat-race-complete');
  } finally {
    await cdp.send('Network.emulateNetworkConditionsByRule', { matchedNetworkConditions: [] });
    await cdp.detach();
  }
});

test('real Chat late conversation creation preserves subsequent navigation', async ({ page }, info) => {
  test.skip(persistence, 'Creates a separate empty disposable conversation');
  phase(info, 'chat-create-race-pkce');
  await authenticate(page, '/#chat');
  const existing = page.getByRole('link', { name: /Tiếp tục hội thoại/ }).first();
  await expect(existing).toBeVisible();
  const href = await existing.getAttribute('href');
  expect(href).toContain('conversation=');
  await page.getByTestId('chat-title').fill(`Hội thoại kết nối chậm ${Date.now()}`);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.emulateNetworkConditionsByRule', { matchedNetworkConditions: [{ urlPattern: origin + '/api/v1/conversations', latency: 3000, downloadThroughput: -1, uploadThroughput: -1 }] });
  try {
    const created = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/v1/conversations');
    await page.getByTestId('chat-create').click();
    await existing.click();
    await expect(page).toHaveURL(origin + '/' + href);
    expect((await created).status()).toBe(201);
    await page.waitForTimeout(350); // allow the fulfilled UI promise to settle
    await expect(page).toHaveURL(origin + '/' + href);
    phase(info, 'chat-create-race-complete');
  } finally {
    await cdp.send('Network.emulateNetworkConditionsByRule', { matchedNetworkConditions: [] });
    await cdp.detach();
  }
});
