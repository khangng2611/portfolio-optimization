// Run with the local Web dependencies. Reads only the saved HYBRID pilot after login.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const requireWeb = createRequire(new URL('../apps/web/package.json', import.meta.url));
const { chromium, expect } = requireWeb('@playwright/test');
const root = new URL('../', import.meta.url);
const json = async path => JSON.parse(await readFile(new URL(path, root), 'utf8'));
const pilot = 'output/hybrid-20261122/';
const original = (await json(pilot + 'chat-result.json')).recommendation;
const conversation = (await json(pilot + 'chat-start.json')).created.result.id;
const { portfolio_id: portfolio, id } = original;
assert.equal(original.strategy, 'HYBRID');
const login = (await json('infra/local/.generated/accounts.json')).users.find(user => user.username === 'alice');
const origin = 'http://127.0.0.1:3100';
const history = `/#proposal?focus=history&portfolio=${portfolio}`;
const proposal = `/#proposal?portfolio=${portfolio}&proposal=${id}`;
const chat = `/#chat?conversation=${conversation}&portfolio=${portfolio}`;
const dir = new URL('output/playwright/sanitized/saved-hybrid-demo/', root);
await mkdir(dir, { recursive: true });
const browser = await chromium.launch();
const widths = [];
try {
  const context = await browser.newContext({ baseURL: origin });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const writes = [];
  await page.route('**/*', async route => {
    const request = route.request();
    const { pathname, origin: destination } = new URL(request.url());
    if (destination !== origin || (!['GET', 'HEAD'].includes(request.method()) && pathname !== '/auth/login')) {
      writes.push(request.method() + ' ' + pathname);
      return route.abort();
    }
    return route.continue();
  });
  const read = async path => {
    const response = await page.request.get(path, { maxRedirects: 0 });
    assert.equal(response.status(), 200, path);
    return response.json();
  };
  const snapshot = async (width, label) => page.screenshot({
    path: fileURLToPath(new URL(`${width}-${label}.png`, dir)),
    mask: [page.locator('.account-name')], maskColor: '#f1f2eb',
  });
  await page.goto('/login');
  await page.getByLabel('Tên đăng nhập', { exact: true }).fill(login.username);
  await page.getByLabel('Mật khẩu', { exact: true }).fill(login.password);
  const authenticated = page.waitForResponse(r => new URL(r.url()).pathname === '/auth/login' && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  assert.equal((await authenticated).status(), 204);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    const portfolioApi = '/api/v1/portfolios/' + portfolio;
    const readiness = await read(portfolioApi + '/readiness');
    assert.equal(readiness.reason_code, 'SYSTEM_PAUSED');
    assert.equal(readiness.can_submit, false);
    const stored = await read('/api/v1/recommendations/' + id);
    for (const key of ['id', 'portfolio_id', 'strategy', 'weights', 'asset_ids', 'run_id', 'input_hash', 'bundle_hash', 'policy_version_id', 'data_snapshot_id', 'diagnostics']) {
      assert.deepEqual(stored[key], original[key], key);
    }
    const messagesUrl = '/api/v1/conversations/' + conversation + '/messages';
    const messages = await read(messagesUrl);
    const recommendationMessage = messages.find(message => message.structured?.recommendation_id === id && message.structured.explanation_requested)
      ?? messages.find(message => message.structured?.recommendation_id === id);
    assert.ok(recommendationMessage, 'historical conversation references the same proposal');
    assert.deepEqual(recommendationMessage.structured.facts.weights, stored.weights);

    await page.goto(`/#proposal?portfolio=${portfolio}&focus=request`);
    const pauseNotice = page.getByTestId('paused-input-notice');
    await expect(pauseNotice).toContainText('Tính năng tạo đề xuất mới đang tạm dừng.');
    await expect(page.getByTestId('propose-portfolio')).toHaveCount(0);
    await snapshot(width, 'paused');
    await pauseNotice.getByRole('link', { name: 'Xem đề xuất đã lưu' }).click();
    const historyRow = page.getByTestId('proposal-row-' + id);
    await expect(historyRow).toBeVisible();
    await snapshot(width, 'history');
    await historyRow.getByRole('link').click();
    const review = page.locator('.proposal-review');
    await expect(review.getByTestId('accept-proposal')).toBeDisabled();
    const references = review.getByTestId('allocation-references');
    await references.locator('summary').click();
    for (const [index, asset] of stored.asset_ids.entries()) {
      const row = references.getByRole('row').filter({ has: page.getByRole('rowheader', { name: asset, exact: true }) });
      const percent = (Number(stored.weights[index]) * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + '%';
      await expect(row.getByRole('cell').first()).toHaveText(percent);
    }
    await review.getByRole('heading', { name: 'Phân bổ của lần tính cũ' }).scrollIntoViewIfNeeded();
    await snapshot(width, 'allocation');
    await page.goto(chat);
    await page.locator('[data-message-id="' + recommendationMessage.id + '"]').getByRole('button', { name: 'Xem dữ kiện và nguồn', exact: true }).click();
    const basis = page.locator('.chat-verified-basis');
    await expect(basis).toContainText('10 tài sản dùng khi tính, 6 tài sản có tỷ trọng trên 0%');
    await expect(page.locator('.chat-result-limits')).toContainText('Tối đa 50,0% mỗi tài sản.');
    const link = page.getByTestId('chat-open-recommendation');
    await expect(link).toHaveAttribute('href', proposal.slice(1));
    await basis.scrollIntoViewIfNeeded();
    await snapshot(width, 'explanation');
    await link.click();
    await page.reload();
    await expect(review.getByTestId('accept-proposal')).toBeDisabled();
    assert.deepEqual(await read('/api/v1/recommendations/' + id), stored);
    assert.deepEqual(await read(messagesUrl), messages);
    assert.equal((await read(portfolioApi + '/readiness')).reason_code, 'SYSTEM_PAUSED');
    assert.deepEqual(writes, []);
    widths.push({ width, ui_weights_matched: stored.weights.length, explanation_matches_proposal: true, history_contains_proposal: true, unchanged_after_reload: true, business_mutations: 0 });
  }
  await context.close();
  const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
  const receipt = { checked_at: new Date().toISOString(), strategy: original.strategy, reason_code: 'SYSTEM_PAUSED',
    portfolio, proposal: id, conversation, run_id: original.run_id, input_hash: original.input_hash,
    bundle_hash: original.bundle_hash, snapshot: original.data_snapshot_id, policy_version: original.policy_version_id,
    weights_sha256: digest(original.weights), routes: { proposal, chat, history }, widths };
  await writeFile(new URL('verification.json', dir), JSON.stringify(receipt, null, 2) + '\n');
  console.log('Saved HYBRID demo verified at both widths.');
} finally {
  await browser.close();
}
