import { submitLogin } from './login-form';
import { test, expect, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

// Real localhost browser/Auth/BFF/Chat/PostgreSQL/Portfolio/RabbitMQ/Quant.
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
  await page.getByRole('link', { name: 'Đăng nhập', exact: true }).click();
  await submitLogin(page, account);
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
  await page.locator('.chat-context-results').getByRole('button', { name: /Xem phân bổ/ }).first().click();
  await expect(page.locator('.chat-detail-panel')).toContainText('Phân bổ chính');
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
  phase(info, 'chat-llm-login');
  const input = JSON.parse(await readFile(resolve(generated, 'chat-real-input-receipt.json'), 'utf8'));
  await authenticate(page, '/#chat');
  const session = await get(page.context(), '/auth/session');
  const onboarded = await page.context().request.post('/api/v1/onboarding/portfolios', { data: { name: `LLM Chat ${Date.now()}`, capital_vnd: '100000000', universe_id: input.universe_id, answers: { questionnaire_version: 'risk-v1', horizon_months: 60, liquidity_need: 'low', loss_tolerance: 'high', experience: 'experienced' } }, headers: { Origin: origin, 'X-CSRF-Token': session.csrfToken } });
  expect(onboarded.status()).toBe(201);
  const pid = (await onboarded.json()).id;
  await page.goto(`/#chat?portfolio=${pid}`);
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill('LLM hỗ trợ làm rõ kế hoạch');
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id, path = `/api/v1/conversations/${cid}`;
  await expect(page.getByTestId('chat-llm-consent')).toHaveCount(0);
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
  phase(info, 'chat-llm-developer-policy');
  await expect(page.getByTestId('chat-llm-consent')).toHaveCount(0);
  await page.locator('.chat-context-results').getByRole('button', { name: /Xem phân bổ/ }).first().click();
  await page.locator('.chat-detail-panel').getByTestId('chat-open-recommendation').click();
  const accepted = await uiPost(page, `/api/v1/recommendations/${facts.id}/accept`, () => page.getByTestId('accept-proposal').click(), 200);
  rows = await get(page.context(), path + '/messages?limit=100&offset=0');
  const jobs = await Promise.all([first.receipt, second.receipt, confirmed, followup.receipt].map(intent => get(page.context(), intent.value.status_url)));
  const usage = jobs.flatMap((job: Value) => job.provider_usage).filter((p: Value) => p?.reason === 'VERIFIED' && p.provider === 'openai');
  expect(usage.length).toBe(5);
  const saved = {
    schema_version: 1, conversation_id: cid, portfolio_id: pid, job_id: followup.state.job_id,
    recommendation_id: facts.id, target_id: accepted.value.id, input_hash: facts.input_hash,
    facts_hash: digest(facts), messages_hash: digest(rows), target_allocation_hash: digest(accepted.value.allocation),
    intents: [first.receipt, second.receipt, confirmed, followup.receipt],
    provider_calls: usage.length, input_tokens: usage.reduce((n: number, p: Value) => n + p.input_tokens, 0),
    output_tokens: usage.reduce((n: number, p: Value) => n + p.output_tokens, 0),
    estimated_cost_usd: usage.reduce((n: number, p: Value) => n + p.estimated_cost_usd, 0),
  };
  await verify(page, saved);
  await writeFile(llmReceipt, JSON.stringify(saved, null, 2) + '\n', { mode: 0o600 });
  phase(info, 'chat-llm-complete');
});

test('real Chat login confirmation allocation explanation accept and reconnect', async ({ page }, info) => {
  test.skip(persistence, 'Receipt mode reads the original Chat resources after restart');
  test.setTimeout(240_000);
  phase(info, 'chat-login');
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
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill(`Kế hoạch Chat ${Date.now()}`);
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id;
  await expect(page).toHaveURL(new RegExp(`conversation=${cid}`));
  const before = await get(page.context(), `/api/v1/portfolios/${pid}/recommendations`);
  const sendPath = `/api/v1/conversations/${cid}/messages`;
  await page.getByTestId('chat-input').fill('Tạo đề xuất phân bổ');
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
  await page.locator('.chat-context-results').getByRole('button', { name: /Xem phân bổ/ }).first().click();
  await page.locator('.chat-detail-panel').getByTestId('chat-open-recommendation').click();
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
  phase(info, 'chat-restart-login');
  const receipt = JSON.parse(await readFile(receiptFile, 'utf8'));
  await authenticate(page, `/#chat?conversation=${receipt.conversation_id}&job=${receipt.job_id}`);
  await verify(page, receipt);
  await capture(page, 'chat-restart-persisted-history');
  phase(info, 'chat-restart-complete');
});

test('real Chat session expiry requires explicit reconfirmation before retry', async ({ page }, info) => {
  test.skip(persistence, 'Session recovery creates a separate disposable conversation');
  test.setTimeout(180_000);
  phase(info, 'chat-session-login');
  const baseline = JSON.parse(await readFile(resolve(generated, 'chat-browser-receipt.json'), 'utf8'));
  const pid = baseline.portfolio_id;
  await authenticate(page, `/#chat?portfolio=${pid}`);
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill(`Kiểm tra phiên Chat ${Date.now()}`);
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id, path = `/api/v1/conversations/${cid}/messages`;
  await page.getByTestId('chat-input').fill('Tạo đề xuất phân bổ');
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
  phase(info, 'chat-session-fresh-login');
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
  phase(info, 'chat-race-login');
  const saved = JSON.parse(await readFile(receiptFile, 'utf8'));
  await authenticate(page, `/#chat?conversation=${saved.conversation_id}&job=${saved.job_id}`);
  await expect(page.getByTestId('chat-result').last()).toBeVisible();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  const canonicalPath = `/api/v1/recommendations/${saved.recommendation_id}`;
  const content = `Tóm tắt danh mục của tôi (${Date.now()})`;
  await page.getByTestId('chat-input').fill(content);
  // Delay the genuine network response; no interception, altered body or SQL.
  await cdp.send('Network.emulateNetworkConditionsByRule', { matchedNetworkConditions: [{ urlPattern: origin + canonicalPath, latency: 3000, downloadThroughput: -1, uploadThroughput: -1 }] });
  try {
    const slowRead = page.waitForRequest(r => new URL(r.url()).pathname === canonicalPath);
    const lateResponse = page.waitForResponse(r => new URL(r.url()).pathname === canonicalPath);
    await page.locator('.chat-context-summary').click();
    await page.getByRole('button', { name: 'Tải lại trạng thái', exact: true }).click();
    await page.locator('.chat-context-summary').click();
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
  phase(info, 'chat-create-race-login');
  await authenticate(page, '/#chat');
  const existing = page.getByRole('link', { name: /Tiếp tục hội thoại/ }).first();
  await expect(existing).toBeVisible();
  const href = await existing.getAttribute('href');
  expect(href).toContain('conversation=');
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
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

test('real Chat paused followups portfolio switch knowledge and pinned proposal', async ({ page, browser }, info) => {
  const mode = process.env.RAG_STATUS_MODE;
  test.skip(!['baseline', 'exercise', 'verify'].includes(mode ?? ''), 'Requires the RAG status acceptance run');
  expect(process.env.PLAYWRIGHT_BASE_URL).toBe('http://127.0.0.1:3100');
  const directory = process.env.RAG_STATUS_OUTPUT;
  if (!directory) throw new Error('Set RAG_STATUS_OUTPUT to a fresh run directory');
  const file = (name: string) => resolve(directory, name + '.json');
  const store = (name: string, record: Value) => writeFile(file(name), JSON.stringify(record, null, 2) + '\n', { mode: 0o600, flag: 'wx' });
  const load = async (name: string) => JSON.parse(await readFile(file(name), 'utf8'));
  await mkdir(directory, { recursive: true });
  const accounts = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8'));
  await page.goto('/login');
  await submitLogin(page, accounts.users.find((a: Value) => a.username === 'alice'));
  const context = page.context();
  const ref = JSON.parse(await readFile(resolve(root, 'output/concise-explanation/paid-final-receipt.json'), 'utf8'));
  const pid = ref.portfolio_id, rid = ref.recommendation_id;
  const factsPath = '/api/v1/recommendations/' + rid;
  const messages = (id: string) => get(context, '/api/v1/conversations/' + id + '/messages?limit=100&offset=0');
  async function oldPins() {
    const [facts, evidence, history] = await Promise.all([get(context, factsPath), get(context, factsPath + '/evidence'), messages(ref.conversation_id)]);
    expect(facts).toMatchObject({ id: rid, portfolio_id: pid, weights: ref.facts.weights, input_hash: ref.facts.input_hash });
    expect(evidence).toMatchObject({ recommendation_id: rid, facts_hash: ref.facts_hash, evidence_hash: ref.evidence_hash });
    expect(history.some((m: Value) => m.structured?.facts_hash === ref.facts_hash)).toBe(true);
    return { portfolio_id: pid, recommendation_id: rid, old_conversation_id: ref.conversation_id, input_hash: facts.input_hash, run_id: evidence.run_id, facts_hash: evidence.facts_hash, evidence_hash: evidence.evidence_hash, weights_hash: digest(facts.weights), old_messages_hash: digest(history) };
  }
  async function openProposal() {
    await page.goto('/#proposal?portfolio=' + pid + '&proposal=' + rid);
    await expect(page.locator('.proposal-review .allocation-primary')).toBeVisible();
    await page.reload();
    await expect(page.locator('.proposal-review .allocation-primary')).toBeVisible();
  }
  if (mode === 'baseline') {
    phase(info, 'status-freeze-old-proposal');
    await openProposal();
    await store('pinned-baseline', await oldPins());
    return;
  }
  const pins = await load('pinned-baseline');
  expect(await oldPins()).toEqual(pins);
  if (mode === 'verify') {
    phase(info, 'status-restart-persistence');
    const saved = await load('browser-exercise');
    await page.goto('/#chat?conversation=' + saved.conversation_id + '&portfolio=' + saved.switched_portfolio_id);
    await expect(page.getByTestId('allocation-status')).toHaveCount(3);
    await expect(page.getByRole('button', { name: 'Xem nguồn tham khảo' })).toBeVisible();
    expect(digest(await messages(saved.conversation_id))).toBe(saved.messages_hash);
    await page.goto('/#chat?conversation=' + ref.conversation_id + '&portfolio=' + pid);
    await expect(page.getByTestId('chat-result').last()).toBeVisible();
    await openProposal();
    await store('browser-persistence', { ...pins, conversation_id: saved.conversation_id, messages_hash: saved.messages_hash });
    return;
  }

  // This dedicated acceptance run uses a single local worker without paid calls.
  const workers = spawnSync('docker', ['ps', '--filter', 'label=com.docker.compose.project=portfolio-auth-demo', '--filter', 'label=com.docker.compose.service=chat-worker', '--format', '{{.Names}}'], { encoding: 'utf8' });
  expect(workers.status).toBe(0);
  const names = workers.stdout.trim().split('\n');
  expect(names).toHaveLength(1);
  const offline = spawnSync('docker', ['exec', names[0], 'python', '-c', 'import os, sys; sys.exit(int(os.getenv("CHAT_LLM_ENABLED") == "1" or bool(os.getenv("CHAT_PROVIDER_URL"))))']);
  expect(offline.status, 'Acceptance worker disables all provider transports').toBe(0);
  expect((await get(context, '/api/v1/portfolios/' + pid + '/readiness')).reason_code).toBe('SYSTEM_PAUSED');

  function sql(db: string, query: string) {
    const run = spawnSync('docker', ['exec', 'portfolio-auth-demo-postgres-1', 'sh', '-c', 'exec psql -XAtq -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "$2"', 'sh', db, query], { encoding: 'utf8' });
    expect(run.status).toBe(0);
    return run.stdout.trim();
  }
  const counts = () => ({ allocation_jobs: Number(sql('portfolio_db', 'select count(*) from job')), proposals: Number(sql('portfolio_db', 'select count(*) from recommendation')), quant_runs: Number(sql('quant_db', 'select count(*) from numerical_run')) });
  const before = counts();
  phase(info, 'status-legacy-paused');
  expect(ref.conversation_id).toMatch(/^[0-9a-f-]{36}$/);
  const legacy = sql('chat_db', `select conversation_id || ',' || id from chat_job where owner_key=(select owner_key from conversation where id='${ref.conversation_id}') and status='FAILED' and error='SYSTEM_PAUSED' and result_message_id is null order by created_at desc limit 1`).split(',');
  if (legacy.length === 2) {
    await page.goto('/#chat?conversation=' + legacy[0] + '&job=' + legacy[1]);
    const legacyStatus = page.getByTestId('chat-job');
    await expect(legacyStatus).toHaveText('Tính năng tạo đề xuất mới đang tạm dừng. Bạn vẫn có thể xem các đề xuất đã lưu.');
    await expect(legacyStatus.getByRole('link')).toHaveCount(0);
  }
  phase(info, 'status-paused');
  await page.goto('/#chat?portfolio=' + pid);
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill('Kiểm tra trạng thái tạo đề xuất');
  const created = await uiPost(page, '/api/v1/conversations', () => page.getByTestId('chat-create').click(), 201);
  const cid = created.value.id, durations: number[] = [], jobIds: string[] = [];
  async function ask(content: string, portfolioId: string) {
    const nextAnswer = page.locator('.chat-assistant').nth(await page.locator('.chat-assistant').count());
    await page.getByTestId('chat-input').fill(content);
    const started = performance.now();
    const sent = await uiPost(page, '/api/v1/conversations/' + cid + '/messages', () => page.getByTestId('chat-send').click(), 202);
    await nextAnswer.waitFor({ state: 'visible' });
    durations.push(Math.round(performance.now() - started));
    expect(sent.body.portfolio_id).toBe(portfolioId);
    const job = await waitJob(context, sent.value.job_id);
    expect(job.recommendation_id).toBeNull();
    expect(job.provider_usage).toEqual([]);
    const message = (await messages(cid)).find((m: Value) => m.id === job.result_message_id);
    const visible = page.locator('[data-message-id="' + message.id + '"]');
    await expect(visible).toContainText(message.content);
    jobIds.push(job.job_id);
    return { card: message.structured, visible, content: message.content };
  }
  const paused = await ask('Tạo đề xuất phân bổ', pid);
  expect(paused.card).toMatchObject({ type: 'allocation_status', status: 'BLOCKED', reason_code: 'SYSTEM_PAUSED', scope: 'system', portfolio_id: pid });
  await expect(paused.visible).toContainText('Tính năng tạo đề xuất mới đang tạm dừng.');
  await expect(paused.visible.getByRole('link', { name: 'Xem đề xuất đã lưu' })).toHaveAttribute('href', '#proposal?focus=history&portfolio=' + pid);
  await page.reload();
  await expect(paused.visible).toContainText(paused.content);
  phase(info, 'status-why-and-now');
  const why = await ask('Vì sao vậy?', pid);
  expect(why.card).toMatchObject({ type: 'allocation_status', reason_code: 'SYSTEM_PAUSED', checked_at: paused.card.checked_at, portfolio_id: pid });
  expect(why.content).toMatch(/chưa (cung cấp|có).*lý do/i);
  const now = await ask('Bây giờ tạo được chưa?', pid);
  expect(now.card).toMatchObject({ type: 'allocation_status', status: 'BLOCKED', reason_code: 'SYSTEM_PAUSED', portfolio_id: pid });
  expect(Date.parse(now.card.checked_at)).toBeGreaterThan(Date.parse(paused.card.checked_at));
  await expect(now.visible.locator('time[datetime="' + now.card.checked_at + '"]')).toBeVisible();

  await now.visible.screenshot({ path: resolve(directory, 'status-current.png') });

  phase(info, 'status-switch-and-knowledge');
  await page.locator('.chat-context-summary').click();
  const select = page.getByTestId('chat-portfolio');
  const other = await select.locator('option').evaluateAll(options => options.map(o => (o as HTMLOptionElement).value)).then(ids => ids.find(id => id && id !== pid));
  if (!other) throw new Error('Expected a second portfolio owned by the signed-in investor');
  await select.selectOption(other);
  await expect(page).toHaveURL(new RegExp('portfolio=' + other));
  await expect(paused.visible.getByRole('link')).toHaveCount(0);
  const knowledge = await ask('Black–Litterman là gì?', other);
  expect(knowledge.card.type).toBe('knowledge');
  const evidence = knowledge.card.knowledge;
  expect(evidence.mode).toBe('LEXICAL');
  expect(evidence.citations.length).toBeGreaterThan(0);
  await knowledge.visible.getByRole('button', { name: 'Xem nguồn tham khảo' }).click();
  await expect(page.getByTestId('chat-knowledge')).toContainText(evidence.citations[0].text);
  for (const id of jobIds) expect(id).toMatch(/^[0-9a-f-]{36}$/);
  const statusIds = jobIds.slice(0, 3).map(id => "'" + id + "'").join(',');
  expect(sql('chat_db', 'select count(*) from knowledge_evidence where job_id in (' + statusIds + ')')).toBe('0');
  expect(sql('chat_db', 'select count(*) from chat_job where dependency_id is not null and id in (' + statusIds + ')')).toBe('0');
  const tools = sql('chat_db', 'select tool from tool_call where job_id in (' + statusIds + ') order by tool').split('\n').filter(Boolean);
  expect(tools).not.toContain('retrieve_knowledge');
  expect(counts()).toEqual(before);
  phase(info, 'status-reopen-pinned-proposal');
  await openProposal();
  expect(await oldPins()).toEqual(pins);
  phase(info, 'status-second-owner');
  const otherOwner = await browser.newContext({ baseURL: process.env.PLAYWRIGHT_BASE_URL });
  try {
    const viewer = await otherOwner.newPage();
    await viewer.goto('/login');
    await submitLogin(viewer, accounts.users.find((a: Value) => a.username === 'bob'));
    for (const path of [factsPath, factsPath + '/evidence', '/api/v1/conversations/' + cid, '/api/v1/jobs/chat/' + jobIds[0]]) {
      expect((await otherOwner.request.get(path)).status()).toBe(404);
    }
  } finally { await otherOwner.close(); }
  await store('browser-exercise', { other_owner_denied_reads: 4, ...pins, conversation_id: cid, switched_portfolio_id: other, job_ids: jobIds, legacy_job_id: legacy[1] ?? null, status_checked_at: [paused.card.checked_at, now.card.checked_at], provider_calls: 0, status_tools: tools, job_counts_before_and_after: before, turn_duration_ms: durations, knowledge_evidence_hash: evidence.evidence_hash, messages_hash: digest(await messages(cid)) });
});
