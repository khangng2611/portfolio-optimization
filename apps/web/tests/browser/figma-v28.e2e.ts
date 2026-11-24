import { expect, test, type Locator, type Page, type Request } from '@playwright/test';
import { mkdir, readFile, realpath } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { resolve } from 'node:path';
import type { Dashboard, Portfolio, Recommendation, Target } from '../../src/lib/portfolio-types';
import { submitLogin } from './login-form';

const origin = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3100';
const captures = resolve('../../output/playwright/sanitized/v28');
const generated = resolve('../../infra/local/.generated');

test.use({ baseURL: origin });
test.beforeEach(async () => {
  test.skip(process.env.E2E_DISPOSABLE_STACK !== '1' || origin !== 'http://127.0.0.1:3100', 'Uses the dedicated local stack on port 3100');
  await mkdir(captures, { recursive: true });
});

async function account(name: string) {
  const { users } = JSON.parse(await readFile(resolve(generated, 'accounts.json'), 'utf8')) as { users: { username: string; password: string }[] };
  const user = users.find(user => user.username === name);
  if (!user) throw new Error('Disposable account unavailable');
  return user;
}

async function signIn(page: Page, name: string) {
  await page.goto('/login');
  await submitLogin(page, await account(name));
}

async function saveImage(page: Page, name: string) {
  await page.screenshot({ path: resolve(captures, name + '.png'), mask: [page.locator('.account-name')], maskColor: '#f1f2eb' });
}

async function checkWidth(page: Page, width: number, height = 844) {
  await page.setViewportSize({ width, height });
  const layout = await page.evaluate(() => {
    const root = document.documentElement;
    return { viewport: innerWidth, content: root.getBoundingClientRect().width, scroll: root.scrollWidth };
  });
  expect(layout.viewport).toBe(width);
  expect(layout.scroll).toBe(Math.round(layout.content));
}

async function checkCentered(region: Locator, limit: number) {
  const size = await region.evaluate(node => {
    const panel = node.getBoundingClientRect(), outer = node.closest('main')!.getBoundingClientRect();
    return { width: panel.width, offset: Math.abs(panel.left - outer.left - (outer.right - panel.right)) };
  });
  expect(size.width).toBeLessThanOrEqual(limit);
  expect(size.offset).toBeLessThanOrEqual(2);
}

async function checkPlanStatusLayout(overview: Locator, width: number) {
  const card = overview.locator('.plan-status');
  await expect(card).toBeVisible();
  const action = card.locator('.button').first();
  await expect(action).toBeInViewport();
  if (width <= 390) {
    const bounds = await action.boundingBox();
    const bottom = await overview.page().locator('.bottom-nav').boundingBox();
    expect(bounds && bottom && bounds.y + bounds.height <= bottom.y).toBe(true);
  }
}

async function checkSavedAllocation(region: Locator, { asset_ids: assets, weights }: Pick<Recommendation, 'asset_ids' | 'weights'>, capture?: string) {
  await expect(region).toBeVisible();
  const summary = region.locator('.result-allocation');
  if (await summary.count()) {
    const rows = summary.locator('.result-assets tbody tr');
    await expect(rows).toHaveCount(assets.length);
    const reported = await rows.evaluateAll(nodes => nodes.map(node => ({
      asset: node.querySelector('strong')?.textContent,
      weight: node.querySelector('td')?.textContent,
    })));
    for (const {asset, weight} of reported) {
      expect(assets).toContain(asset);
      const expected = Number(weights[assets.indexOf(asset!)]) * 100;
      if (weight?.startsWith('<')) expect(expected).toBeLessThan(.01);
      else expect(Math.abs(Number(weight?.replace(',', '.').replace('%', '')) - expected)).toBeLessThanOrEqual(.051);
    }
    if (capture) await saveImage(region.page(), capture);
    return;
  }
  await expect(region.locator('.weight-chart-axis span')).toHaveText(['0%', '25%', '50%', '75%', '100%']);
  const chart = region.getByRole('list', { name: 'Biểu đồ tỷ trọng theo tài sản' });
  await expect(chart).toBeVisible();
  const nonzero = assets.flatMap((asset, index) => Number(weights[index]) === 0 ? [] : [{ asset, width: Number(weights[index]) * 100 }]);
  const bars = await chart.getByRole('listitem').evaluateAll(items => items.map(item => ({
    asset: item.querySelector('.allocation-bar-label > div > strong')?.textContent,
    width: parseFloat(item.querySelector<HTMLElement>('.allocation-bar-track > span')?.style.width ?? ''),
  })));
  expect(bars).toHaveLength(nonzero.length);
  for (const bar of bars) expect(bar.width).toBeCloseTo(nonzero.find(row => row.asset === bar.asset)?.width ?? NaN, 4);
  if (capture) {
    await chart.evaluate(node => node.scrollIntoView({ block: 'start' }));
    await saveImage(region.page(), capture);
  }

  const showTable = region.getByRole('button', { name: 'Xem bảng số liệu' });
  await showTable.press('Enter');
  await expect(showTable).toBeFocused();
  const table = region.getByRole('table', { name: /Phân bổ mục tiêu/ });
  await expect(table).toBeVisible();
  const zeroes = assets.length - nonzero.length;
  if (zeroes) {
    const showZero = region.getByRole('button', { name: `Xem ${zeroes} mã có tỷ trọng 0%` });
    if (await showZero.isVisible()) await showZero.click();
    await expect(region.getByRole('button', { name: 'Ẩn mã có tỷ trọng 0%' })).toHaveAttribute('aria-pressed', 'true');
  }
  await expect(table.locator('tbody tr')).toHaveCount(assets.length);
  expect(await table.evaluate(node => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1);
  await region.getByRole('button', { name: 'Xem biểu đồ phân bổ' }).click();
  await expect(chart).toBeVisible();
}

test('guest routes share one reading rail, title size and accessible guide', async ({ page }) => {
  for (const width of [2560, 1440, 390, 375]) {
    await page.setViewportSize({ width, height: width < 600 ? 844 : 1000 });
    let reference: number[] | undefined;
    for (const view of ['overview', 'portfolios', 'chat', 'profile']) {
      await page.goto('/#' + view);
      const main = page.locator('.workspace-welcome');
      const card = main.locator('.welcome-card');
      await expect(card).toBeVisible();
      await page.evaluate(() => document.fonts.ready);
      const box = (await card.boundingBox())!;
      const title = main.getByRole('heading', { level: 1 });
      expect((await title.boundingBox())!.x).toBeCloseTo(box.x);
      await expect(title).toHaveCSS('font-size', width < 600 ? '26px' : '32px');
      if (reference) expect([box.x, box.width]).toEqual(reference);
      reference = [box.x, box.width];
      await card.getByRole('link', { name: 'Xem cách hoạt động' }).click();
      await expect(main.locator('#methodology > summary')).toBeFocused();
      await expect(page).toHaveURL(new RegExp('#' + view + '$'));
      if (width >= 1200) {
        const trigger = page.locator('.sidebar').getByRole('button', { name: 'Dữ liệu và cách tính' });
        await trigger.click();
        const guide = page.locator('#sidebar-guide');
        await expect(guide).toBeVisible();
        await guide.getByRole('button', { name: 'Đóng' }).click();
        await expect(guide).toBeHidden();
      }
    }
  }
});

test('separate portfolio and basket writes, version conflict, paused state and draft-only suggestions', async ({ page }) => {
  const user = { username: 'v28-' + randomUUID().slice(0, 8), password: randomUUID() + '!' };
  await page.goto('/register');
  await page.getByLabel('Tên hiển thị').fill('Fixture V2.8');
  await page.getByLabel('Tên đăng nhập').fill(user.username);
  await page.getByLabel('Mật khẩu').fill(user.password);
  await page.getByRole('button', { name: 'Đăng ký', exact: true }).click();
  await page.waitForURL('**/login');
  await submitLogin(page, user);
  await page.goto('/#create');
  await checkWidth(page, 390);
  const openBasket = page.getByRole('button', { name: 'Chọn tài sản', exact: true });
  await openBasket.click();
  await expect(page.getByText('Nhập tên danh mục để tiếp tục.')).toBeVisible();
  await expect(page.locator('input[name=name]')).toBeFocused();
  await page.getByLabel('Tên danh mục').fill('Danh mục kiểm thử V2.8');
  const capital = page.getByRole('textbox', { name: 'Vốn kế hoạch (VND)', exact: true });
  await capital.fill('');
  await capital.pressSequentially('1000000');
  await capital.evaluate(input => (input as HTMLInputElement).setSelectionRange(1, 1));
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin });
  await page.evaluate(() => navigator.clipboard.writeText('00'));
  await capital.press('ControlOrMeta+v');
  await expect(capital).toHaveValue('100.000.000');
  await page.getByLabel('Thời gian đầu tư (tháng)').fill('36');
  const currentStep = page.locator('.wizard-progress-label');
  await expect(currentStep).toHaveText('Bước 1/4 · Mục tiêu');
  await saveImage(page, 'v29-onboarding-plan-390');
  await openBasket.press('Enter');
  await expect(currentStep).toHaveText('Bước 2/4 · Rổ tài sản');
  await expect(page.getByRole('heading', { name: 'Chọn rổ tài sản', exact: true })).toBeFocused();
  const next = page.getByRole('button', { name: 'Tiếp tục', exact: true });
  await expect(next).toBeDisabled();
  const search = page.getByRole('searchbox', { name: 'Tìm tài sản', exact: true });
  for (const asset of ['FPT', 'VCB', 'VFF']) {
    await search.fill(asset);
    await page.getByRole('button', { name: `Thêm ${asset} vào rổ tài sản` }).click();
    await expect(next).toBeEnabled();
  }
  await search.fill('');
  await expect(page.locator('.wizard-asset-toggle[aria-pressed=true]')).toHaveCount(3);
  await saveImage(page, 'v29-onboarding-basket-390');
  await page.getByRole('button', { name: 'Quay lại', exact: true }).press('Enter');
  await expect(page.getByLabel('Tên danh mục')).toHaveValue('Danh mục kiểm thử V2.8');
  await expect(page.getByLabel(/Vốn kế hoạch \(VND\)/)).toHaveValue('100.000.000');
  await expect(page.getByLabel('Thời gian đầu tư (tháng)')).toHaveValue('36');
  await expect(currentStep).toHaveText('Bước 1/4 · Mục tiêu');
  await checkWidth(page, 1440, 1000);
  await saveImage(page, 'v29-onboarding-plan-1440');
  await openBasket.click();
  await expect(page.locator('.wizard-asset-toggle[aria-pressed=true]')).toHaveCount(3);
  await checkWidth(page, 390);
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  await page.getByRole('radio', { name: 'Vừa · Từ 5% đến dưới 15%', exact: true }).check();
  await page.getByRole('radio', { name: 'Tối đa 10%', exact: true }).check();
  await page.getByRole('radio', { name: 'Từ 6 tháng trở lên', exact: true }).check();
  await page.getByRole('button', { name: 'Xem lại hồ sơ' }).click();
  const creating = page.waitForResponse(response => response.url().endsWith('/api/v1/onboarding/portfolios') && response.request().method() === 'POST');
  await page.getByTestId('create-portfolio-submit').click();
  const created = await creating;
  expect(created.status()).toBe(201);
  const { id } = await created.json() as { id: string };
  const portfolioPath = `/api/v1/portfolios/${id}`;
  await page.waitForURL(`**/#overview?portfolio=${id}`);
  await expect(page.getByRole('heading', { name: /Sẵn sàng tạo đề xuất|Tạm dừng tạo đề xuất|Chưa thể tạo đề xuất/ })).toBeVisible();
  const overview = page.locator('.plan-overview');
  await expect(page.locator('.plan-heading')).toContainText('Vốn hiện tại 100 triệu');
  await expect(overview.locator('.plan-details')).toContainText('3 tài sản trong rổ');
  await expect(overview.locator('.allocation-chart-view')).toHaveCount(0);
  for (const width of [375, 390, 768, 1024, 1440]) {
    await checkWidth(page, width, 900);
    await checkPlanStatusLayout(overview, width);
    if ([390, 768, 1440].includes(width)) await saveImage(page, `overview-no-target-${width}`);
  }
  await checkWidth(page, 390);

  const stale = await page.context().newPage();
  await stale.goto(`/#edit?portfolio=${id}`);
  await expect(stale.getByTestId('portfolio-name-input')).toHaveValue('Danh mục kiểm thử V2.8');
  await page.goto(`/#edit?portfolio=${id}`);
  await page.getByTestId('portfolio-name-input').fill('Nháp không được lưu theo rổ');
  await page.getByTestId('available-assets').getByRole('button', { name: 'Thêm MWG vào rổ tài sản' }).click();
  const saving = page.waitForResponse(response => response.url().endsWith(portfolioPath + '/asset-selections') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Lưu lựa chọn tài sản', exact: true }).click();
  const saved = await saving;
  expect(saved.status()).toBe(201);
  expect(saved.request().headers()).toHaveProperty('if-match');
  expect(saved.request().headers()).toHaveProperty('idempotency-key');
  const updated = await (await page.request.get(portfolioPath)).json();
  expect(updated.name).toBe('Danh mục kiểm thử V2.8');
  expect(updated.asset_selection.candidate_asset_ids).toContain('MWG');

  await stale.getByTestId('portfolio-name-input').fill('Thay đổi xung đột V2.8');
  const conflict = stale.waitForResponse(response => response.url().endsWith(portfolioPath) && response.request().method() === 'PATCH');
  await stale.getByTestId('edit-portfolio-submit').click();
  expect((await conflict).status()).toBe(412);
  await expect(stale.getByTestId('conflict-notice')).toBeVisible();
  await saveImage(stale, 'plan-conflict-1440');
  await stale.close();

  await page.goto(`/#edit?portfolio=${id}`);
  await page.getByTestId('available-assets').getByRole('button', { name: 'Thêm ACB vào rổ tài sản' }).click();
  await page.getByTestId('portfolio-capital-input').fill('120000000');
  const savingPlan = page.waitForResponse(response => response.url().endsWith(portfolioPath) && response.request().method() === 'PATCH');
  await page.getByTestId('edit-portfolio-submit').click();
  expect((await savingPlan).status()).toBe(200);
  await page.reload();
  const dashboard = await (await page.request.get(portfolioPath + '/dashboard')).json();
  expect(Number(dashboard.portfolio.capital_vnd)).toBe(120000000);
  expect(dashboard.portfolio.asset_selection.candidate_asset_ids).toEqual(updated.asset_selection.candidate_asset_ids);
  expect(dashboard).toMatchObject({ accepted_target: null, holdings_status: 'NOT_TRACKED' });

  const readiness = await (await page.request.get(portfolioPath + '/readiness')).json();
  if (readiness.reason_code === 'SYSTEM_PAUSED') {
    await page.goto(`/#proposal?portfolio=${id}`);
    await expect(page.getByTestId('paused-input-notice')).toBeVisible();
    await expect(page.getByTestId('paused-input-notice').getByRole('link', { name: 'Hỏi về kế hoạch' })).toHaveAttribute('href', `#chat?portfolio=${id}`);
    const { csrfToken } = await (await page.request.get('/auth/session')).json();
    const paused = await page.request.post(portfolioPath + '/recommendations', {
      headers: { Origin: origin, 'X-CSRF-Token': csrfToken, 'If-Match': `"${dashboard.portfolio.version}"`, 'Idempotency-Key': randomUUID() },
      data: { mode: 'system' },
    });
    expect(paused.status()).toBe(409);
    expect((await paused.json()).error.code).toBe('SYSTEM_PAUSED');
    await saveImage(page, 'system-paused-390');
  }

  await page.goto(`/#chat?portfolio=${id}`);
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-create').click();
  await page.waitForURL(/#chat\?conversation=/);
  const composer = page.getByTestId('chat-input');
  await expect(composer).toBeEnabled();
  await expect(page.locator('.bottom-nav a[aria-current="page"]')).toHaveText('Hội thoại');
  let sent = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().includes('/messages')) sent++; });
  await page.getByRole('button', { name: 'Tóm tắt kế hoạch' }).click();
  await expect(composer).toHaveValue('Tóm tắt kế hoạch');
  await expect(composer).toBeFocused();
  await expect(page.getByText('Đã điền gợi ý vào bản nháp.')).toBeVisible();
  await page.getByRole('button', { name: 'Lịch sử', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Lịch sử hội thoại' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Lịch sử', exact: true })).toBeFocused();
  await expect(composer).toHaveValue('Tóm tắt kế hoạch');
  await saveImage(page, 'chat-draft-390');
  await composer.focus();
  await page.evaluate(() => {
    Object.defineProperty(visualViewport, 'height', { configurable: true, value: 458 });
    visualViewport?.dispatchEvent(new Event('resize'));
  });
  await expect(page.locator('.workspace-chat')).toHaveAttribute('data-chat-keyboard', '');
  const box = await composer.boundingBox();
  expect(box && box.y + box.height < 458).toBe(true);
  await expect(page.locator('.bottom-nav')).toBeHidden();
  await page.evaluate(() => {
    if (visualViewport) Reflect.deleteProperty(visualViewport, 'height');
    visualViewport?.dispatchEvent(new Event('resize'));
  });
  expect(sent).toBe(0);
  if (readiness.reason_code === 'SYSTEM_PAUSED') {
    await page.getByTestId('chat-input').fill('Tạo đề xuất phân bổ');
    await composer.press('Enter');
    const pausedReply = page.getByTestId('allocation-status').or(page.getByTestId('chat-job')).filter({ hasText: 'Tính năng tạo đề xuất mới đang tạm dừng' });
    await expect(pausedReply).toBeVisible();
    expect(sent).toBe(1);
    await page.reload();
    await expect(pausedReply).toBeVisible();
  }
  await page.goto(`/#chat?portfolio=${id}`);
  await page.getByRole('button', { name: 'Tóm tắt kế hoạch', exact: true }).click();
  const firstQuestion = page.getByTestId('chat-input');
  await expect(firstQuestion).toHaveValue('Tóm tắt kế hoạch');
  await expect(firstQuestion).toBeFocused();
  await expect(page.getByText('Đã điền gợi ý vào bản nháp.')).toBeVisible();
  await expect(page).not.toHaveURL(/conversation=/);
  await checkWidth(page, 390);
  await saveImage(page, 'v29-chat-first-draft-390');
  await checkWidth(page, 768);
  await checkWidth(page, 1440, 1000);
  await saveImage(page, 'v29-chat-first-draft-1440');
  const firstSent = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/messages'));
  let firstPosts = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().includes('/messages')) firstPosts++; });
  await firstQuestion.press('Enter');
  const sentResponse = await firstSent;
  expect(sentResponse.status()).toBe(202);
  expect(sentResponse.request().postDataJSON()).toMatchObject({ portfolio_id: id, intent: 'portfolio', content: 'Tóm tắt kế hoạch' });
  await expect(page.locator('.chat-user')).toContainText('Tóm tắt kế hoạch');
  expect(firstPosts).toBe(1);
  await checkWidth(page, 390);
  const sourcePanel = page.locator('.chat-assistant .chat-turn-facts');
  const portfolioSource = sourcePanel.locator('summary');
  await portfolioSource.click();
  await expect(sourcePanel.getByRole('heading', { name: 'Tóm tắt danh mục' })).toBeVisible();
  await expect(sourcePanel).toContainText('Danh mục kiểm thử V2.8');
  await portfolioSource.press('Enter');
  await expect(portfolioSource).toBeFocused();
  const knowledgeComposer = page.getByTestId('chat-input');
  await expect(knowledgeComposer).toBeEnabled();
  await knowledgeComposer.fill('EW là gì?');
  const knowledgeSent = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/messages'));
  await knowledgeComposer.press('Enter');
  const knowledgeResponse = await knowledgeSent;
  expect(knowledgeResponse.status()).toBe(202);
  const { conversation_id: conversationId, job_id: jobId } = await knowledgeResponse.json();
  await expect.poll(async () => (await (await page.request.get(`/api/v1/jobs/chat/${jobId}`)).json()).status).toBe('SUCCEEDED');
  const messages = await (await page.request.get(`/api/v1/conversations/${conversationId}/messages`)).json();
  const savedKnowledge = messages.find((message: { structured?: { type?: string } }) => message.structured?.type === 'knowledge');
  expect(savedKnowledge).toBeTruthy();
  const reply = page.locator(`[data-message-id="${savedKnowledge.id}"]`);
  const [citation] = savedKnowledge.structured.knowledge.citations;
  if (citation) {
    const sources = reply.getByRole('button', { name: 'Xem nguồn tham khảo' });
    await sources.click();
    await expect(sourcePanel.getByText(citation.source_title).first()).toBeVisible();
    await expect(sourcePanel.locator('blockquote').first()).toHaveText(citation.text);
    await saveImage(page, 'v29-chat-knowledge-390');
    await sourcePanel.getByRole('button', { name: 'Trở lại hội thoại', exact: true }).click();
    await expect(sources).toBeFocused();
  } else {
    await expect(reply.getByText('Chưa tìm thấy nguồn phù hợp cho câu hỏi này.')).toBeVisible();
  }
});

test('V2.11 expired proposal keeps saved facts and opens preview only when readiness allows it', async ({ page }) => {
  await signIn(page, 'alice');
  const portfolios = await (await page.request.get('/api/v1/portfolios?limit=100')).json() as Portfolio[];
  let saved: { portfolio: Portfolio; proposal: Recommendation } | undefined;
  for (const portfolio of portfolios.filter(value => value.asset_selection)) {
    const response = await page.request.get(`/api/v1/portfolios/${portfolio.id}/recommendations?limit=30`);
    expect(response.ok()).toBe(true);
    const results = await response.json() as Recommendation[];
    const proposal = results.find(value => value.portfolio_version === portfolio.version && value.valid_until && Date.parse(value.valid_until) <= Date.now());
    if (proposal) { saved = { portfolio, proposal }; break; }
  }
  if (!saved) throw new Error('Expected a real unaccepted expired proposal from the local fixture');
  const { portfolio, proposal } = saved;
  const id = portfolio.id, path = `/api/v1/portfolios/${id}/readiness`;
  const url = `/#proposal?portfolio=${id}&proposal=${proposal.id}`;
  const live = await (await page.request.get(path)).json();
  const captureDir = resolve('../../output/playwright/v211');
  await mkdir(captureDir, { recursive: true });
  const capture = async (name: string) => page.screenshot({ path: resolve(captureDir, name + '.png'), mask: [page.locator('.account-name')], maskColor: '#f2f7f5' });
  const matcher = (requestUrl: URL) => requestUrl.pathname === path;
  await page.route(matcher, route => route.fulfill({ json: { ...live, can_submit: false, reason_code: 'SYSTEM_PAUSED', strategies: [] } }));
  await page.goto(url);
  const notice = page.getByTestId('stale-proposal-notice');
  await expect(notice).toContainText(/đã hết hạn|Hết hạn/);
  await expect(page.getByTestId('accept-proposal')).toBeDisabled();
  await expect(notice).toContainText('Tính mới tạm dừng');
  await expect(notice.getByRole('link', { name: 'Xem lại đầu vào' })).toHaveCount(0);
  const heading = page.locator('.plan-heading');
  await expect(heading.getByRole('heading')).toHaveText('Đề xuất ' + proposal.id.slice(0, 8));
  await expect(heading.locator('time')).toHaveAttribute('datetime', proposal.as_of_date!);
  for (const width of [390, 1440]) {
    await checkWidth(page, width, width === 390 ? 844 : 1000);
    await checkPlanStatusLayout(page.locator('.proposal-review'), width);
    await capture('expired-paused-' + width);
  }
  await page.locator('.plan-evidence > summary').press('Enter');
  await expect(page.getByText('Căn cứ, giới hạn và nguồn', { exact: true })).toBeVisible();
  await expect(page.getByTestId('recommendation-evidence')).toBeVisible();
  for (const width of [390, 1440]) {
    await checkWidth(page, width, width === 390 ? 844 : 1000);
    await page.locator('.plan-evidence').evaluate(node => node.scrollIntoView({ block: 'start' }));
    await capture('expired-evidence-' + width);
  }
  await expect(page.getByText('Dữ liệu dùng để tính', { exact: true })).toBeVisible();
  await checkSavedAllocation(page.locator('.proposal-review'), proposal);
  await notice.getByRole('link', { name: 'Xem lịch sử đề xuất' }).click();
  await expect(page.locator('.proposal-history').getByTestId('proposal-row-' + proposal.id)).toBeVisible();
  await page.goto('/#overview?portfolio=' + id);
  await expect(page.getByTestId('paused-input-notice').getByRole('link', { name: 'Xem lịch sử đề xuất' })).toBeVisible();
  await page.unroute(matcher);
  const readinessMatcher = (requestUrl: URL) => requestUrl.pathname === path;
  let finishReadiness!: () => void;
  const waitingForReadiness = new Promise<void>(resolve => { finishReadiness = resolve; });
  await page.route(readinessMatcher, async route => {
    await waitingForReadiness;
    await route.fulfill({ status: 503, json: { error: { message: 'Fixture dữ liệu chưa xác định' } } });
  });
  await page.goto(url);
  await page.reload();
  try {
    await expect(notice).toContainText('Đang kiểm tra dữ liệu để tính mới');
    await expect(page.locator('.result-assets')).toBeVisible();
  } finally { finishReadiness(); }
  await expect(notice).toContainText('Chưa xác định được tình trạng dữ liệu');
  await expect(notice.getByRole('link', { name: 'Xem lại đầu vào' })).toHaveCount(0);
  await page.unroute(readinessMatcher);
  await page.route(readinessMatcher, route => route.fulfill({ json: {
    ...live, readiness_kind: 'user-selection-v1', candidate_asset_ids: portfolio.asset_selection!.candidate_asset_ids, reason_code: 'READY', can_submit: true,
    strategies: [{ strategy: 'HYBRID', can_submit: true, reason_code: 'READY' }], decision_session: '2026-11-17', selection_valid_until: new Date(Date.now() + 86_400_000).toISOString(), asset_status: [],
  } }));
  await notice.getByRole('button', { name: 'Kiểm tra lại' }).click();
  await expect(notice.getByRole('link', { name: 'Xem lại đầu vào' })).toBeVisible();
  await checkWidth(page, 1440, 1000);
  await capture('expired-ready-1440');
  await checkWidth(page, 390);
  await capture('expired-ready-390');
  let newJobs = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith(`/portfolios/${id}/recommendations`)) newJobs++; });
  await notice.getByRole('link', { name: 'Xem lại đầu vào' }).press('Enter');
  await expect(page.getByRole('heading', { name: 'Xem lại đầu vào', exact: true })).toBeVisible();
  await expect(page.getByTestId('confirm-proposal')).toBeEnabled();
  expect(newJobs).toBe(0);

  await page.unrouteAll({ behavior: 'wait' });
  const catalog = await (await page.request.get('/api/v1/assets/catalog')).json();
  await page.route('**/api/v1/assets/catalog', route => route.fulfill({ json: { ...catalog, selection_enabled: false } }));
  await page.route('**/api/v1/universes', route => route.fulfill({ json: [{ universe_id: 'DEMO', asset_ids: ['AAA', 'BBB', 'VFF'], as_of_date: '2026-11-17', demo: true }] }));
  await page.goto('/#create');
  await page.reload();
  await checkWidth(page, 768, 900);
  await expect(page.getByLabel('Bộ tài sản')).toHaveValue('DEMO');
  await expect(page.getByRole('button', { name: 'Chọn tài sản', exact: true })).toHaveCount(0);
  await page.getByLabel('Tên danh mục').fill('Kế hoạch legacy thử nghiệm');
  await page.getByRole('button', { name: 'Tiếp tục', exact: true }).click();
  await expect(page.getByRole('radio', { name: 'Vừa · Từ 5% đến dưới 15%', exact: true })).toBeVisible();
  await page.unrouteAll({ behavior: 'wait' });
});

test('V2.11 overview fixture keeps plan, saved and pending decisions distinct', async ({ page }) => {
  const account = { username: 'v211-' + randomUUID().slice(0,8), password: randomUUID() + '!' };
  expect((await page.request.post('/auth/register', { headers: { origin }, data: { ...account, name: 'Nhà đầu tư mẫu' } })).status()).toBe(201);
  await page.goto('/login');
  await submitLogin(page, account);
  const empty: Portfolio = { id: randomUUID(), name: 'Tích lũy dài hạn', capital_vnd: '100000000', version: 1,
    universe_id: 'USER_SELECTED', policy_version_id: 'fixture', constraints: { risk_aversion: 3, max_position_weight: .5 },
    risk_profile: { profile: 'balanced', answers: { questionnaire_version: 'risk-v1', horizon_months: 36, liquidity_need: 'low', loss_tolerance: 'medium', experience: 'experienced' } } };
  const withPending = { ...empty, id: randomUUID(), version: 2, capital_vnd: '120000000' };
  const withTarget = { ...withPending, id: randomUUID() };
  const pending: Recommendation = { id: randomUUID(), portfolio_id: withPending.id, portfolio_version: 2,
    strategy: 'HYBRID', asset_ids: ['VFF','FPT','GOLD'], weights: [.5,.35,.15], capital_vnd: withPending.capital_vnd,
    as_of_date: '2026-11-20', valid_until: '2099-01-01T00:00:00Z' };
  const older = { ...pending, id: randomUUID(), portfolio_id: withTarget.id, portfolio_version: 1, capital_vnd: empty.capital_vnd, as_of_date: '2026-11-17' };
  const saved = { proposal: { ...pending, id: randomUUID(), portfolio_id: withTarget.id },
    target: { id: randomUUID(), recommendation_id: older.id, allocation: older, accepted_at: '2026-11-18T00:00:00Z', portfolio_version: 1 } };
  const live = { readiness_kind: 'user-selection-v1', can_submit: false, reason_code: 'VFF_STALE', strategies: [], candidate_asset_ids: pending.asset_ids, asset_status: [] };
  await page.route('**/api/v1/assets/catalog', route => route.fulfill({ json: {
    selection_enabled: true, catalog_version: 'fixture', assets: pending.asset_ids.map((asset_id, index) => ({
      asset_id, kind: ['fund','stock','gold'][index], display_name: asset_id, unit: 'VND', currency: 'VND',
      catalog_version: 'fixture', data_status: 'FRESH', ml_status: 'UNKNOWN',
    })),
  } }));
  for (const portfolio of [empty, withPending, withTarget]) {
    const prefix = '**/api/v1/portfolios/' + portfolio.id;
    const item = portfolio === withPending ? pending : saved.proposal;
    await page.route(prefix + '/dashboard', route => route.fulfill({ json: {
      portfolio, proposal_count: portfolio === empty ? 0 : portfolio === withTarget ? 2 : 1,
      accepted_target: portfolio === withTarget ? saved.target : null, target_matches_portfolio: false,
    } }));
    await page.route(prefix + '/readiness', route => route.fulfill({json: live}));
    await page.route(prefix + '/recommendations?*', route => route.fulfill({json: portfolio === empty ? [] : [item]}));
    await page.route('**/api/v1/recommendations/' + item.id, route => route.fulfill({json: item}));
  }
  const output = resolve('../../output/playwright/v211');
  await mkdir(output, {recursive:true});
  const capture = async (name: string) => page.screenshot({ path: resolve(output, name + '.png'), mask: [page.locator('.account-name')], maskColor: '#f2f7f5' });
  const path = '/api/v1/portfolios/' + empty.id + '/readiness';
  const readiness = (url: URL) => url.pathname === path;
  let release!: () => void;
  const waiting = new Promise<void>(done => { release = done; });
  await page.route(readiness, async route => {
    await waiting;
    await route.fulfill({ json: { ...live, can_submit: false, reason_code: 'SYSTEM_PAUSED', strategies: [] } });
  });
  await page.goto('/#overview?portfolio=' + empty.id);
  await page.reload();
  const overview = page.locator('.plan-overview');
  try {
    await expect(overview.getByRole('heading', { name: 'Đang kiểm tra điều kiện tính' })).toBeVisible();
    await expect(overview.getByRole('link', { name: 'Hỏi về kế hoạch' })).toHaveAttribute('href', '#chat?portfolio=' + empty.id);
    await checkWidth(page, 390);
    await capture('verifying-390');
  } finally { release(); }
  const paused = page.getByTestId('paused-input-notice');
  await expect(paused.getByRole('link', { name: 'Hỏi về kế hoạch' })).toHaveAttribute('href', '#chat?portfolio=' + empty.id);
  for (const width of [375, 390, 768, 1440]) {
    await checkWidth(page, width, width >= 768 ? 1000 : 844);
    await checkPlanStatusLayout(overview, width);
    await capture('paused-empty-' + width);
  }
  await overview.locator('.plan-details > details > summary').press('Enter');
  await expect(overview.getByRole('heading', {name:'Rổ tài sản hiện tại'})).toBeVisible();
  await page.unroute(readiness);
  for (const item of [pending, saved.proposal]) {
    await page.goto('/#overview?portfolio=' + item.portfolio_id);
    const action = overview.getByRole('link', { name: 'Xem đề xuất ' + item.id.slice(0,8) });
    await expect(action).toHaveAttribute('href', `#proposal?portfolio=${item.portfolio_id}&proposal=${item.id}`);
    if (item.id === saved.proposal.id) {
      await expect(overview.getByRole('heading', { name: 'Có đề xuất mới chờ xem' })).toBeVisible();
      await checkSavedAllocation(overview, saved.target.allocation);
      const savedFpt = overview.locator('.result-assets tbody tr').filter({ hasText: 'FPT' });
      await expect(savedFpt).toContainText('35.000.000');
      await expect(savedFpt).toContainText('Cổ phiếu');
    } else {
      await expect(overview.getByRole('heading', { name: 'Có đề xuất chờ xem' })).toBeVisible();
      await expect(overview.locator('.result-allocation')).toHaveCount(0);
    }
    await checkWidth(page, 390);
    await capture(item.id === saved.proposal.id ? 'pending-with-target-390' : 'pending-390');
    await action.click();
    await expect(page.getByTestId('accept-proposal')).toBeEnabled();
    await checkSavedAllocation(page.locator('.proposal-review'), item);
    await expect(page.locator('.proposal-review .result-assets tbody tr').filter({ hasText: 'FPT' })).toContainText('42.000.000');
  }
  await page.route('**/api/v1/portfolios?*', route => route.fulfill({ json: [withTarget], headers: { 'X-Total-Count': '1' } }));
  await page.goto('/#portfolios');
  const plans = page.getByRole('region', {name: 'Danh sách danh mục'});
  await expect(plans.getByRole('link', {name: 'Mở danh mục ' + withTarget.name})).toBeVisible();
  for (const width of [390, 1440]) {
    await checkWidth(page, width, width === 390 ? 844 : 1000);
    await capture('portfolio-list-' + width);
  }
});

test('chat composer sends with Enter and edits with Cmd+Enter', async ({ page }) => {
  await signIn(page, 'bob');
  await page.goto('/#chat');
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill('Kiểm tra bàn phím Chat');
  await page.getByTestId('chat-create').click();
  await page.waitForURL(/#chat\?conversation=/);
  const composer = page.getByTestId('chat-input');
  await expect(composer).toBeEnabled();
  await expect(page.getByLabel('Tùy chọn hội thoại')).toHaveCount(0);

  const isSend = (request: Request) => request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/messages');
  const sent: unknown[] = [];
  page.on('request', request => { if (isSend(request)) sent.push(request.postDataJSON()); });
  await composer.fill('Dòng đầu Dòng sau');
  await composer.evaluate((area: HTMLTextAreaElement) => area.setSelectionRange(8, 9));
  await composer.press('Meta+Enter');
  await expect(composer).toHaveValue('Dòng đầu\nDòng sau');
  expect(await composer.evaluate((area: HTMLTextAreaElement) => area.selectionStart)).toBe(9);
  await composer.dispatchEvent('keydown', { key: 'Enter', isComposing: true });
  await composer.evaluate(area => {
    const legacyImeEnter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true });
    Object.defineProperty(legacyImeEnter, 'keyCode', { value: 229 });
    area.dispatchEvent(legacyImeEnter);
  });
  await expect(composer).toHaveValue('Dòng đầu\nDòng sau');
  expect(sent).toHaveLength(0);

  await page.getByRole('button', { name: 'Giá vàng hôm nay là bao nhiêu?', exact: true }).click();
  const submitted = page.waitForResponse(r => isSend(r.request()));
  await composer.press('Enter');
  const response = await submitted;
  expect(response.status()).toBe(202);
  await expect(composer).toHaveValue('');
  expect(sent).toEqual([expect.objectContaining({ content: 'Giá vàng hôm nay là bao nhiêu?', intent: 'market' })]);
  const { job_id } = await response.json();
  await expect.poll(async () => {
    const result = await page.request.get(`/api/v1/jobs/chat/${job_id}`);
    const { provider_usage, status } = await result.json();
    return { provider_usage, status };
  }).toEqual({ provider_usage: [], status: 'SUCCEEDED' });
  await checkWidth(page, 390);
  await expect(composer).toBeVisible();
  await expect(page.getByTestId('chat-send')).toBeVisible();
});

test('saved target, chart, pinned versions, investor price series and role denial', async ({ page }) => {
  await signIn(page, 'alice');
  const rows = await (await page.request.get('/api/v1/portfolios?limit=100')).json() as { id: string }[];
  let target: { portfolio: { id: string }; accepted_target: { recommendation_id: string; allocation: { asset_ids: string[]; weights: string[] } } } | undefined;
  for (const row of rows) {
    const value = await (await page.request.get(`/api/v1/portfolios/${row.id}/dashboard`)).json();
    if (value.accepted_target) { target = value; break; }
  }
  if (!target) throw new Error('No saved target exists for the read-only fixture');
  const portfolio = target.portfolio.id, proposal = target.accepted_target.recommendation_id;
  const canonical = target.accepted_target.allocation;
  await page.goto(`/#overview?portfolio=${portfolio}`);
  const overview = page.locator('.plan-overview');
  for (const width of [375, 390, 768, 1024, 1440]) {
    await checkWidth(page, width);
    await checkSavedAllocation(overview, canonical);
    if ([390, 1440].includes(width)) await saveImage(page, `overview-${width}`);
  }
  await page.locator('.plan-details > details > summary').click();
  await page.locator('summary').filter({ hasText: /^Dữ liệu và cách tính$/ }).click();
  const table = page.locator('.allocation-table');
  await expect(table).toBeVisible();
  const sort = table.getByRole('button', { name: /Tài sản: sắp xếp/ });
  await sort.focus(); await page.keyboard.press('Enter');
  await expect(sort).toBeFocused();
  await expect(table.locator('th[aria-sort="ascending"]')).toContainText('Tài sản');
  const zeroes = canonical.weights.filter(value => Number(value) === 0).length;
  if (zeroes) {
    await page.getByRole('button', { name: `Xem ${zeroes} mã có tỷ trọng 0%` }).click();
    await expect(table.locator('tbody tr')).toHaveCount(canonical.asset_ids.length);
  }
  await page.getByRole('link', { name: 'Xem mục tiêu đã lưu' }).click();
  await page.waitForURL(`**/#proposal?portfolio=${portfolio}&proposal=${proposal}`);
  await expect(page.getByTestId('accept-proposal')).toBeDisabled();
  await page.locator('.plan-evidence > summary').click();
  await expect(page.getByText('Dữ liệu dùng để tính', { exact: true })).toBeVisible();
  await page.getByText('Dữ liệu dùng để tính', { exact: true }).click();
  await expect(page.getByText('Loại dữ liệu', { exact: true })).toBeVisible();
  await expect(page.getByText('Snapshot ID', { exact: true })).toHaveCount(0);
  await saveImage(page, 'proposal-review-1440');
  await page.goto('/#asset-prices?asset=FPT');
  await expect(page.getByRole('figure')).toBeVisible();
  await page.getByText('Xem bảng giá theo ngày', { exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Ngày quan sát' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Revision' })).toHaveCount(0);
  await checkWidth(page, 375);
  await expect(page.getByRole('figure')).toBeVisible();
  await saveImage(page, 'asset-price-375');
  await page.goto('/#knowledge');
  await expect(page.getByRole('heading', { name: 'Cần quyền vận hành dữ liệu' })).toBeVisible();
  expect((await page.request.get('/api/v1/knowledge/corpora')).status()).toBe(403);
  await page.context().setOffline(true);
  await expect(page.getByText('Bạn đang ngoại tuyến', { exact: true })).toBeVisible();
  await page.context().setOffline(false);
  await expect(page.getByText('Bạn đang ngoại tuyến', { exact: true })).toBeHidden();
  let pair: { portfolioId: string; a: string; b: string } | undefined;
  for (const row of rows) {
    const proposals = await (await page.request.get(`/api/v1/portfolios/${row.id}/recommendations?limit=2`)).json() as { id: string }[];
    if (proposals.length === 2) { pair = { portfolioId: row.id, a: proposals[0].id, b: proposals[1].id }; break; }
  }
  if (!pair) throw new Error('No proposals to compare in the read-only fixture');
  await page.goto('/#compare?' + new URLSearchParams({ portfolio: pair.portfolioId, a: pair.a, b: pair.b }));
  await expect(page.getByRole('heading', { name: 'Thay đổi tỷ trọng · B trừ A' })).toBeVisible();
  await checkWidth(page, 390);
  await page.getByText('Xem hồ sơ và ngày dữ liệu', { exact: true }).click();
  await expect(page.getByRole('rowheader', { name: 'Hồ sơ rủi ro', exact: true })).toBeVisible();
  await page.getByRole('heading', { name: 'Thay đổi tỷ trọng · B trừ A' }).scrollIntoViewIfNeeded();
  await saveImage(page, 'compare-390');
});

test('desktop chat aligns both routes and opens turn sources with room to read', async ({ page }) => {
  await signIn(page, 'bob');
  const conversations: { id: string; portfolio_id?: string }[] = await (await page.request.get('/api/v1/conversations?limit=100')).json();
  let savedUrl = '';
  for (const conversation of conversations) {
    if (!conversation.portfolio_id) continue;
    const messages: { structured?: { type: string } }[] = await (await page.request.get(`/api/v1/conversations/${conversation.id}/messages?limit=50`)).json();
    if (messages.some(message => message.structured?.type === 'market')) {
      savedUrl = '/#chat?' + new URLSearchParams({ conversation: conversation.id, portfolio: conversation.portfolio_id });
      break;
    }
  }
  expect(savedUrl, 'Dedicated account needs a saved reply with facts').toBeTruthy();
  for (const width of [1280, 1440, 1920, 2560]) {
    await checkWidth(page, width, 900);
    for (const route of ['/#chat', savedUrl]) {
      await page.goto(route);
      const start = route === '/#chat';
      const source = page.locator('.chat-turn-source').last();
      if (!start) await expect(source).toBeVisible();
      const historyToggle = page.locator('.chat-navigation > details > summary');
      for (const expanded of [true, false]) {
        if (!expanded) await historyToggle.click();
        const geometry = await page.locator('.chat-thread').evaluate(node => {
          const rect = (selector: string) => node.querySelector(selector)!.getBoundingClientRect();
          const history = node.parentElement!.querySelector('.chat-navigation')!.getBoundingClientRect();
          const sidebar = document.querySelector('.sidebar')!.getBoundingClientRect();
          const header = rect('.chat-topline'), context = rect('.chat-context'), form = rect('.chat-composer'), transcript = rect('.chat-transcript');
          return { alignment: Math.max(...[header, context, transcript].map(box => Math.abs(box.left - form.left))),
            sidebarWidth: sidebar.width, historyGap: history.left - form.right, historyWidth: history.width, threadWidth: node.getBoundingClientRect().width,
            starterGap: node.querySelector('.chat-starters') ? form.top - rect('.chat-starters').bottom : null };
        });
        expect(geometry.alignment).toBeLessThanOrEqual(1);
        expect(geometry.sidebarWidth).toBe(208);
        expect(geometry.historyGap).toBeGreaterThanOrEqual(16);
        expect(geometry.historyWidth).toBeCloseTo(expanded ? Math.min(width * .193, 278) : 88, 0);
        expect(geometry.threadWidth).toBeGreaterThanOrEqual(540);
        await expect(page.getByTestId('chat-input')).toBeInViewport({ ratio: 1 });
        if (start) {
          expect(geometry.starterGap).toBeGreaterThanOrEqual(12);
          const suggestion = page.locator('.chat-starters button').first();
          await suggestion.click();
          await expect(page.getByTestId('chat-input')).toHaveValue((await suggestion.innerText()).trim());
          await expect(page).toHaveURL(/#chat$/);
          await page.getByTestId('chat-input').fill('');
        } else {
          await source.scrollIntoViewIfNeeded();
          await source.focus();
          const transcript = page.locator('.chat-transcript');
          const before = await transcript.evaluate(node => node.scrollTop);
          await source.press('Enter');
          const panel = page.locator('.chat-detail-panel');
          await expect(panel).toBeVisible();
          await expect(panel.getByRole('heading', { name: 'Dữ kiện và nguồn' })).toBeVisible();
          expect(await panel.locator('.chat-detail-header button').evaluate(button => {
            const rect = button.getBoundingClientRect();
            return button.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
          })).toBe(true);
          const inline = await panel.evaluate(node => node.tagName === 'ASIDE');
          expect(await panel.evaluate(node => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1);
          if (width === 1920) {
            expect(inline).toBe(true);
            expect((await panel.boundingBox())!.width).toBeGreaterThanOrEqual(380);
          }
          if (width === 1280 && expanded) expect(inline).toBe(false);
          if (inline) expect((await page.locator('.chat-thread').boundingBox())!.width).toBeGreaterThanOrEqual(540);
          if (expanded) await saveImage(page, 'chat-sources-desktop-' + width);
          if (expanded && width === 1920) {
            const replyTime = await panel.locator('time').first().getAttribute('datetime');
            await checkWidth(page, 1280, 900);
            await expect(page.getByRole('dialog', { name: 'Dữ kiện và nguồn' })).toBeVisible();
            await expect(panel.locator('time').first()).toHaveAttribute('datetime', replyTime!);
            await checkWidth(page, width, 900);
            await expect(page.getByRole('complementary', { name: 'Dữ kiện và nguồn' })).toBeVisible();
          }
          await page.keyboard.press('Escape');
          await expect(panel).toHaveCount(0);
          await expect(source).toBeFocused();
          await expect.poll(() => transcript.evaluate(node => node.scrollTop)).toBeCloseTo(before, 0);
        }
        if (expanded) await saveImage(page, `chat-${start ? 'start' : 'thread'}-desktop-${width}`);
        if (!start && expanded) {
          await page.locator('.chat-context-summary').click();
          const picker = page.locator('.chat-context-body');
          await expect(picker.getByRole('combobox')).toBeVisible();
          await expect(picker.getByText('Vốn kế hoạch', { exact: true })).toBeVisible();
          await expect(picker.getByText('Tỷ trọng tối đa / tài sản', { exact: true })).toBeHidden();
          await picker.getByText('Xem chi tiết danh mục', { exact: true }).click();
          await expect(picker.getByText('Tỷ trọng tối đa / tài sản', { exact: true })).toBeVisible();
          await expect(picker.getByRole('link', { name: 'Mở danh mục' })).toBeInViewport();
          await page.keyboard.press('Escape');
          await expect(page.locator('.chat-context-summary')).toBeFocused();
        }
      }
    }
  }
});

test('real saved chat loads compact results and opens history and sources separately', async ({ page }) => {
  await signIn(page, 'alice');
  const conversations = await (await page.request.get('/api/v1/conversations?limit=100')).json() as { id: string; portfolio_id?: string }[];
  let saved: (typeof conversations)[number] | undefined;
  let rsiAnswer: { id: string; content: string } | undefined;
  for (const entry of conversations) {
    const messages = await (await page.request.get(`/api/v1/conversations/${entry.id}/messages?limit=50`)).json() as { id: string; content: string; structured?: { type: string; renderer_version?: string } }[];
    if (messages.some(message => message.structured?.type === 'recommendation') && !messages.some(message => message.structured && 'focus' in message.structured)) {
      saved = entry;
      rsiAnswer = messages.find(message => message.structured?.renderer_version === 'allocation-explanation-v2' && /CTG.+RSI14|RSI14.+CTG/i.test(message.content));
      if (messages.some(message => message.structured?.renderer_version === 'allocation-explanation-v2')) break;
    }
  }
  if (!saved) throw new Error('No saved chat result exists for the read-only fixture');
  await page.goto('/#chat');
  const chatHome = page.getByTestId('chat-workspace');
  for (const width of [375, 768, 1280, 2560]) {
    await checkWidth(page, width, 1000);
    await expect(chatHome).toBeInViewport();
    const sidebar = chatHome.locator('.chat-navigation');
    if (width >= 1280) {
      const start = (await chatHome.locator('.chat-thread').boundingBox())!;
      const savedList = (await sidebar.boundingBox())!;
      expect(savedList.x).toBeGreaterThan(start.x + start.width);
    } else {
      await expect(sidebar).toBeHidden();
      await expect(chatHome.getByRole('button', { name: 'Lịch sử', exact: true })).toBeVisible();
    }
  }
  await saveImage(page, 'responsive-chat-home-2560');
  await checkWidth(page, 1440, 1000);
  const query = new URLSearchParams({ conversation: saved.id, ...(saved.portfolio_id ? { portfolio: saved.portfolio_id } : {}) });
  await page.goto('/#chat?' + query);
  const last = page.getByTestId('chat-result').last();
  await expect(last).toBeVisible();
  await expect(last.locator('.allocation-bars, .allocation-table')).toHaveCount(0);
  const navigation = page.getByRole('navigation', { name: 'Điều hướng chính' });
  const savedChatUrl = page.url();
  await navigation.getByRole('link', { name: 'Giá tài sản' }).click();
  await expect(page).toHaveURL(/#asset-prices/);
  await page.goBack();
  await expect(page).toHaveURL(savedChatUrl);
  await expect(last).toBeVisible();
  await page.locator('.chat-navigation > details > summary').click();
  await expect(page.locator('.chat-navigation > details')).not.toHaveAttribute('open', '');
  await expect(last.getByRole('button', { name: /Xem phân bổ/ })).toHaveCount(0);
  const openAllocation = page.locator('.chat-context-results').getByRole('button', { name: /Xem phân bổ/ }).first();
  await openAllocation.click();
  const desktopPanel = page.getByRole('complementary', { name: 'Đề xuất đang trao đổi' });
  await expect(desktopPanel).toBeVisible();
  await expect(navigation.getByRole('link', { name: 'Hội thoại' })).toHaveAttribute('aria-current', 'page');
  await expect(navigation.getByRole('link', { name: 'Giá tài sản' })).toBeInViewport();
  const proposal = new URLSearchParams((await desktopPanel.getByRole('link', { name: 'Xem đề xuất và quyết định' }).getAttribute('href'))?.split('?')[1]).get('proposal');
  expect(proposal).toBeTruthy();
  const stored = await page.request.get(`/api/v1/recommendations/${proposal}`);
  expect(stored.ok()).toBe(true);
  const allocation = await stored.json() as Recommendation;
  await saveImage(page, 'chat-result-1440');
  for (const width of [1280, 1440, 1920, 2560]) {
    await checkWidth(page, width, 1000);
    await expect(page.locator('.chat-conversation')).toBeInViewport();
    const resultPanel = page.locator('.chat-detail-panel');
    await expect(resultPanel).toBeVisible();
    const thread = (await page.locator('.chat-thread').boundingBox())!;
    if (await desktopPanel.count()) {
      expect(thread.width).toBeGreaterThanOrEqual(540);
      expect((await desktopPanel.boundingBox())!.x).toBeGreaterThan(thread.x + thread.width);
    }
    expect(await resultPanel.evaluate(node => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1);
    await expect(page.getByTestId('chat-input')).toBeInViewport({ ratio: 1 });
    if ([1280, 2560].includes(width)) await checkSavedAllocation(resultPanel, allocation);
  }
  await desktopPanel.evaluate(node => node.scrollTo(0, 0));
  await saveImage(page, 'responsive-chat-result-2560');
  await page.getByRole('button', { name: 'Thu gọn', exact: true }).click();
  for (const width of [375, 390, 768, 1024, 1200]) await checkWidth(page, width);
  await checkWidth(page, 768, 900);
  const openHistory = page.getByRole('button', { name: 'Lịch sử', exact: true });
  await openHistory.click();
  const history = page.getByRole('dialog', { name: 'Lịch sử hội thoại' });
  await expect(history.getByRole('navigation', { name: 'Hội thoại đã lưu' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(history).toHaveCount(0);
  await expect(openHistory).toBeFocused();
  await openAllocation.click();
  const allocationPanel = page.getByRole('dialog', { name: 'Đề xuất đang trao đổi' });
  await checkSavedAllocation(allocationPanel, allocation, 'responsive-chat-result-768');
  await expect(allocationPanel.getByRole('button', { name: 'Trở lại hội thoại' })).toBeInViewport({ ratio: 1 });
  await page.keyboard.press('Escape');
  await expect(allocationPanel).toHaveCount(0);
  await checkWidth(page, 390);
  if (rsiAnswer) {
    const answer = page.locator(`[data-message-id="${rsiAnswer.id}"] .chat-concise-answer`);
    await expect(answer).toHaveText(rsiAnswer.content);
    await expect(answer).toContainText(/\d{4}-\d{2}-\d{2}/);
    await answer.scrollIntoViewIfNeeded();
    await saveImage(page, 'chat-rsi-390');
  }
  const sources = last.getByRole('button', { name: 'Xem dữ kiện và nguồn' });
  await sources.scrollIntoViewIfNeeded();
  await sources.focus();
  await sources.evaluate(button => button.addEventListener('click', () => {
    const transcript = button.closest<HTMLElement>('.chat-transcript')!;
    transcript.dataset.readingPositionAtActivation = String(transcript.scrollTop);
  }, { once: true }));
  await sources.press('Enter');
  const transcript = page.locator('.chat-transcript');
  const atActivation = await transcript.getAttribute('data-reading-position-at-activation');
  expect(atActivation).not.toBeNull();
  const panel = page.getByRole('dialog', { name: 'Dữ kiện và nguồn' });
  await expect(panel).toBeVisible();
  await expect(panel.getByText('Căn cứ của đề xuất')).toBeVisible();
  await expect(panel.getByText(/Mã đối chiếu|Facts hash/)).toHaveCount(0);
  await saveImage(page, 'chat-sources-390');
  await page.keyboard.press('Escape');
  await expect(panel).toHaveCount(0);
  await expect(sources).toBeFocused();
  await expect.poll(() => transcript.evaluate((node, top) => Math.abs(node.scrollTop - Math.min(top, node.scrollHeight - node.clientHeight)), Number(atActivation))).toBeLessThanOrEqual(1);
  if (rsiAnswer) {
    const answerSources = page.locator(`[data-message-id="${rsiAnswer.id}"]`).getByRole('button', { name: 'Xem dữ kiện và nguồn' });
    await answerSources.click();
    await expect(panel.locator('.chat-concise-answer')).toHaveText(rsiAnswer.content);
    await page.keyboard.press('Escape');
    await expect(answerSources).toBeFocused();
  }
  await page.reload();
  await expect(last).toBeVisible();

  await checkWidth(page, 375);
  await openAllocation.click();
  const reviewLink = allocationPanel.getByRole('link', { name: 'Xem đề xuất và quyết định' });
  await checkSavedAllocation(allocationPanel, allocation, 'chat-allocation-375');
  expect(await allocationPanel.evaluate(node => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(1);
  await expect(allocationPanel.getByRole('button', { name: 'Trở lại hội thoại' })).toBeInViewport({ ratio: 1 });
  await page.keyboard.press('Escape');
  await expect(allocationPanel).toHaveCount(0);
  await expect(openAllocation).toBeFocused();
  await checkWidth(page, 390);
  await openAllocation.click();
  await reviewLink.click();
  await expect(allocationPanel).toHaveCount(0);
  await checkSavedAllocation(page.locator('.proposal-review'), allocation, 'proposal-allocation-390');
  await checkWidth(page, 390);
});

test('responsive history charts use each stored proposal and target allocation', async ({ page }) => {
  await signIn(page, 'alice');
  const portfolios = await (await page.request.get('/api/v1/portfolios?limit=100')).json() as { id: string }[];
  const targets: { portfolioId: string; target: Target }[] = [];
  let proposals: Recommendation[] = [];
  for (const { id } of portfolios) {
    const path = `/api/v1/portfolios/${id}`;
    if (targets.length < 2) {
      const response = await page.request.get(path + '/targets?limit=10');
      expect(response.ok()).toBe(true);
      for (const target of await response.json() as Target[]) targets.push({ portfolioId: id, target });
    }
    if (proposals.length < 2) {
      const response = await page.request.get(path + '/recommendations?limit=10');
      expect(response.ok()).toBe(true);
      const saved = await response.json() as Recommendation[];
      const other = saved.find(item => item.asset_ids.join() !== saved[0].asset_ids.join() || item.weights.map(Number).join() !== saved[0].weights.map(Number).join());
      if (other) proposals = [saved[0], other];
    }
    if (targets.length >= 2 && proposals.length === 2) break;
  }
  if (!targets.length || proposals.length !== 2) throw new Error('Saved targets and differing proposals are required for the read-only check');

  const [newer, older] = proposals;
  await page.goto(`/#proposal?portfolio=${newer.portfolio_id}&focus=history`);
  const proposalHistory = page.locator('.proposal-history');
  const olderRow = proposalHistory.getByTestId('proposal-row-' + older.id), newerRow = proposalHistory.getByTestId('proposal-row-' + newer.id);
  await checkWidth(page, 375);
  await olderRow.getByRole('checkbox').check();
  await newerRow.getByRole('checkbox').check();
  await expect(proposalHistory.getByRole('link', { name: 'So sánh đề xuất' })).toHaveAttribute('href', `#compare?portfolio=${newer.portfolio_id}&a=${older.id}&b=${newer.id}`);
  for (const width of [375, 390, 768, 1024, 1200, 1440, 1920, 2560]) {
    await checkWidth(page, width, width >= 768 ? 1000 : 844);
    const listBounds = await proposalHistory.boundingBox(), headingBounds = await page.locator('.plan-heading').boundingBox();
    expect(listBounds!.width).toBeLessThanOrEqual(736);
    expect(Math.abs(listBounds!.x - headingBounds!.x)).toBeLessThan(2);
    await expect(olderRow.getByRole('checkbox')).toBeChecked();
    await expect(newerRow.getByRole('checkbox')).toBeChecked();
    const box = (await newerRow.boundingBox())!, date = (await newerRow.getByRole('heading').boundingBox())!, action = (await newerRow.getByRole('link').boundingBox())!;
    expect(action.x + action.width).toBeLessThanOrEqual(box.x + box.width + 1);
    expect(action.y).toBeGreaterThan(date.y + date.height);
    if ([375, 768, 2560].includes(width)) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await saveImage(page, `responsive-proposal-history-${width}`);
    }
  }

  await checkWidth(page, 390);
  for (const proposal of [older, newer]) {
    await page.goto(`/#proposal?portfolio=${proposal.portfolio_id}&focus=history`);
    await page.getByTestId('proposal-row-' + proposal.id).getByRole('link', { name: /^(Xem đề xuất|Mở phân bổ cũ)$/ }).click();
    await page.waitForURL(`**/#proposal?portfolio=${proposal.portfolio_id}&proposal=${proposal.id}`);
    await checkSavedAllocation(page.locator('.proposal-review'), proposal, proposal === older ? 'proposal-history-allocation-390' : undefined);
    await checkWidth(page, 390);
  }

  await checkWidth(page, 375);
  let lastPortfolio: string | undefined;
  for (const [index, { portfolioId, target }] of targets.slice(0, 2).entries()) {
    if (lastPortfolio !== portfolioId) await page.goto(`/#history?portfolio=${portfolioId}`);
    lastPortfolio = portfolioId;
    const row = page.getByTestId('target-row-' + target.id);
    await row.getByRole('button', { name: 'Xem mục tiêu', exact: true }).press('Enter');
    await expect(row.getByRole('button', { name: 'Thu gọn mục tiêu', exact: true })).toHaveAttribute('aria-expanded', 'true');
    await checkSavedAllocation(row, target.allocation);
    if (index === 0) {
      for (const width of [375, 390, 768, 1024, 1200, 1440, 1920, 2560]) {
        await checkWidth(page, width, width >= 768 ? 1000 : 844);
        await checkCentered(page.getByTestId('target-history'), 1344);
        const details = (await row.locator('.target-timeline-row').boundingBox())!, chart = (await row.locator('.historical-allocation').boundingBox())!;
        if (width >= 1440) expect(details.x).toBeGreaterThan(chart.x + chart.width);
        else expect(chart.y).toBeGreaterThan(details.y + details.height);
        if ([768, 2560].includes(width)) {
          await page.evaluate(() => window.scrollTo(0, 0));
          await saveImage(page, `responsive-target-history-${width}`);
        }
      }
      await checkSavedAllocation(row, target.allocation);
      await checkWidth(page, 375);
      await row.evaluate(node => node.scrollIntoView({ block: 'start' }));
      await saveImage(page, 'target-history-allocation-375');
    }
    await expect(page.getByRole('list', { name: 'Biểu đồ tỷ trọng theo tài sản' })).toHaveCount(1);
    await checkWidth(page, 375);
  }
  await page.reload();
  const savedRow = page.getByTestId('target-row-' + targets[Math.min(1, targets.length - 1)].target.id);
  await expect(savedRow.getByRole('button', { name: 'Xem mục tiêu', exact: true })).toHaveAttribute('aria-expanded', 'false');
});

test('operator opens the real market and knowledge consoles', async ({ page }) => {
  await signIn(page, 'data-operator');
  await page.goto('/#market');
  await expect(page.getByRole('searchbox').or(page.getByPlaceholder('Tìm theo tên hoặc mã…')).first()).toBeVisible();
  await expect((await page.request.get('/api/v1/market/dataset-inventory')).status()).toBe(200);
  await page.goto('/#market-revisions');
  await page.getByLabel('Mã tài sản', { exact: true }).fill('FPT');
  await page.getByRole('button', { name: 'Tìm phiên bản giá' }).click();
  await expect(page.getByRole('table', { name: 'Lịch sử sửa đổi theo từng ngày, nguồn và loại giá' })).toBeVisible();
  await saveImage(page, 'market-revisions-1440');
  await page.goto('/#knowledge');
  await expect(page.getByRole('heading', { name: 'Phiên bản corpus' })).toBeVisible();
  await expect((await page.request.get('/api/v1/knowledge/corpora')).status()).toBe(200);
  await expect(page.getByRole('textbox', { name: 'Manifest JSON' })).toBeVisible();
  await checkWidth(page, 390);
  await saveImage(page, 'knowledge-operator-390');
});

test('reviewer reads the registry and cannot open the data operator console', async ({ page }) => {
  await signIn(page, 'model-reviewer');
  await page.goto('/#models');
  await expect(page.getByRole('heading', { name: 'Model đang được chọn cho phục vụ' })).toBeVisible();
  expect((await page.request.get('/api/v1/ml/models')).status()).toBe(200);
  await checkWidth(page, 390);
  await saveImage(page, 'model-registry-390');
  await page.goto('/#market');
  await expect(page.getByRole('heading', { name: 'Cần quyền data operator' })).toBeVisible();
  expect((await page.request.get('/api/v1/market/dataset-inventory')).status()).toBe(403);
});


test('V2.11 price history keeps the same chart from an allocation and the navigation menu', async ({ page }) => {
  await signIn(page, 'alice');
  const portfolios: Portfolio[] = await (await page.request.get('/api/v1/portfolios?limit=100')).json();
  let saved: Target | null = null, portfolioId = '';
  for (const portfolio of portfolios) {
    const dashboard: Dashboard = await (await page.request.get('/api/v1/portfolios/' + portfolio.id + '/dashboard')).json();
    if (dashboard.accepted_target?.allocation.asset_ids.includes('VFF')) {
      saved = dashboard.accepted_target;
      portfolioId = portfolio.id;
      break;
    }
  }
  expect(saved, 'Saved allocation containing VFF').toBeTruthy();
  const chart = page.locator('.price-series-card');
  const back = page.getByRole('link', { name: 'Trở lại phân bổ' });
  const filters = page.getByText('Đổi mã, khoảng thời gian và nguồn', { exact: true });
  const overview = '#overview?portfolio=' + portfolioId;
  for (const width of [375, 390, 768, 1440]) {
    await checkWidth(page, width);
    await page.goto('/' + overview);
    await page.getByRole('link', { name: 'Xem giá VFF', exact: true }).first().click();
    await expect(chart.getByRole('slider')).toBeVisible();
    await page.mouse.move(0, 0);
    await page.evaluate(() => document.fonts.ready);
    await expect(back).toHaveAttribute('href', overview + '&proposal=' + saved!.recommendation_id);
    const reference = await chart.screenshot();
    const refreshed = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === '/api/v1/market/price-series' && url.searchParams.get('asset_id') === 'VFF';
    });
    const desktopLink = page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('link', { name: 'Giá tài sản' });
    if (await desktopLink.isVisible()) {
      await desktopLink.click();
    } else {
      await page.locator('.mobile-menu summary').click();
      await page.getByRole('navigation', { name: 'Điều hướng thu gọn' }).getByRole('link', { name: 'Giá tài sản' }).click();
    }
    expect((await refreshed).ok()).toBe(true);
    await expect(page).toHaveURL(url => url.hash === '#asset-prices?portfolio=' + portfolioId);
    await expect(page.getByRole('heading', { name: 'VFF · Lịch sử giá' })).toBeVisible();
    await expect(chart.getByRole('slider')).toBeVisible();
    await page.mouse.move(0, 0);
    const menuChart = await chart.screenshot();
    if (!menuChart.equals(reference)) {
      await test.info().attach('allocation-' + width, { body: reference, contentType: 'image/png' });
      await test.info().attach('menu-' + width, { body: menuChart, contentType: 'image/png' });
    }
    expect(menuChart.equals(reference), 'VFF price card at ' + width + ' px').toBe(true);
    if (width === 1440 || width === 390) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await saveImage(page, 'v211-vff-' + width);
    }
    await expect(back).toHaveAttribute('href', overview);
    if (width < 1024) await filters.click();
    const asset = page.getByRole('combobox', { name: 'Tài sản', exact: true });
    await asset.selectOption('FPT');
    await expect(page.getByRole('heading', { name: 'FPT · Lịch sử giá' })).toBeVisible();
    await expect(asset).toBeVisible();
    await expect(chart.getByRole('slider')).toBeVisible();
    await back.click();
    await expect(page).toHaveURL(url => url.hash === overview);
  }
});

test('price chart supports period filters, keyboard, mouse and mobile touch', async ({ page }) => {
  await signIn(page, 'bob');
  await page.goto('/#asset-prices?asset=MBB');
  const chart = page.getByRole('figure');
  await expect(chart).toBeVisible();
  await expect(page.getByText('Ngân hàng MB · Cổ phiếu', { exact: true })).toBeVisible();
  for (const width of [375, 390, 768, 1024, 1440, 1920, 2560]) {
    await checkWidth(page, width, width >= 1440 ? 960 : 844);
    if (width >= 1024) await expect(chart.getByText('Số ngày có giá')).toBeVisible();
    const layout = await chart.evaluate(node => {
      const panel = node.closest('.asset-price-history')!.getBoundingClientRect();
      const workspace = node.closest('.workspace')!.getBoundingClientRect();
      const plot = node.querySelector('.price-chart-plot')!.getBoundingClientRect();
      const axis = node.querySelector('.price-axis-x')!.getBoundingClientRect();
      const yAxis = node.querySelector('.price-axis-y')!.getBoundingClientRect();
      return { plotLeft: plot.left, plotHeight: plot.height, axisBottom: axis.bottom, yAxisRight: yAxis.right, panelWidth: panel.width, centerOffset: Math.abs(panel.left - workspace.left - (workspace.right - panel.right)) };
    });
    expect(layout.plotHeight).toBeGreaterThanOrEqual(width < 600 ? 175 : 190);
    expect(layout.yAxisRight).toBeLessThan(layout.plotLeft);
    expect(layout.axisBottom).toBeLessThan(960);
    if (width >= 1024) {
      const card = (await page.locator('.price-series-card').boundingBox())!;
      const plot = (await chart.locator('.price-chart-frame').boundingBox())!;
      const summary = (await chart.locator('.price-chart-summary').boundingBox())!;
      const periods = (await page.getByRole('group', { name: 'Khoảng thời gian' }).boundingBox())!;
      expect(card.width).toBeCloseTo(layout.panelWidth, 0);
      expect(summary.x).toBeGreaterThan(plot.x + plot.width);
      expect(summary.y).toBeLessThan(plot.y);
      expect(periods.y + periods.height).toBeLessThanOrEqual(card.y);
    }
    if (width >= 1920) {
      expect(layout.panelWidth).toBeGreaterThanOrEqual(1500);
      expect(layout.panelWidth).toBeLessThanOrEqual(1600);
      expect(layout.centerOffset).toBeLessThanOrEqual(2);
    }
    if (width === 2560) await saveImage(page, 'price-chart-2560');
    if (width === 768) await saveImage(page, 'price-chart-768');
  }
  await checkWidth(page, 1440, 960);
  await expect(page.getByRole('navigation', { name: 'Điều hướng chính' }).getByRole('link', { name: 'Giá tài sản' })).toHaveAttribute('aria-current', 'page');
  const pricePlot = page.getByRole('slider', { name: 'Dò giá theo ngày quan sát' });
  const latest = await pricePlot.getAttribute('aria-valuetext');
  await pricePlot.press('Home');
  await expect(pricePlot).toHaveAttribute('aria-valuenow', '1');
  await expect(pricePlot).not.toHaveAttribute('aria-valuetext', latest!);
  await pricePlot.press('ArrowRight');
  await expect(pricePlot).toHaveAttribute('aria-valuenow', '2');
  await pricePlot.press('End');
  await expect(pricePlot).toHaveAttribute('aria-valuetext', latest!);
  await pricePlot.hover({ position: { x: 1, y: 40 } });
  await expect(pricePlot).toHaveAttribute('aria-valuenow', '1');
  await page.getByRole('heading', { name: 'MBB · Lịch sử giá', exact: true }).hover();
  await expect(pricePlot).toHaveAttribute('aria-valuetext', latest!);
  await pricePlot.blur();
  await page.evaluate(() => window.scrollTo(0, 0));
  await saveImage(page, 'price-chart-1440');
  await expect(chart.getByText('Số ngày có giá')).toBeVisible();
  await page.getByRole('button', { name: '180 ngày', exact: true }).click();
  await expect(page.getByRole('button', { name: '180 ngày', pressed: true })).toBeVisible();
  await expect(pricePlot).toBeVisible();
  await page.getByText('Xem bảng giá theo ngày', { exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'Ngày quan sát' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Revision' })).toHaveCount(0);
  await page.getByText('Xem bảng giá theo ngày', { exact: true }).click();
  await checkWidth(page, 375);
  await chart.getByText('Biến động và thống kê', { exact: true }).click();
  const change = (await chart.locator('.price-chart-change').boundingBox())!;
  const stats = (await chart.locator('.price-chart-stats').boundingBox())!;
  expect(stats.y).toBeGreaterThanOrEqual(change.y + change.height);
  await page.getByText('Đổi mã, khoảng thời gian và nguồn', { exact: true }).click();
  const periods = page.getByRole('group', { name: 'Khoảng thời gian' });
  expect(await periods.getByRole('button').evaluateAll(nodes => new Set(nodes.map(node => node.getBoundingClientRect().top)).size)).toBe(1);
  await pricePlot.evaluate(node => node.scrollIntoView({ block: 'center' }));
  const plotBounds = await pricePlot.boundingBox();
  const touch = await page.context().newCDPSession(page);
  await touch.send('Emulation.setTouchEmulationEnabled', { enabled: true });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: plotBounds!.x + 1, y: plotBounds!.y + 40 }] });
  await touch.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await expect.poll(async () => Number(await pricePlot.getAttribute('aria-valuenow'))).toBeLessThanOrEqual(3);
  await touch.send('Emulation.setTouchEmulationEnabled', { enabled: false });
  await touch.detach();
  await saveImage(page, 'price-chart-375');

  await checkWidth(page, 2560, 1308);
  await page.getByRole('combobox', { name: 'Tài sản', exact: true }).selectOption('POW');
  await expect(page.getByRole('heading', { name: 'POW · Lịch sử giá' })).toBeVisible();
  await page.getByRole('button', { name: '90 ngày', exact: true }).click();
  await expect(chart.locator('.price-period-label')).toContainText('90 ngày');
  await expect(chart.getByText('Số ngày có giá')).toBeInViewport();
  await page.mouse.move(0, 0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await saveImage(page, 'pow-desktop-2560');
});

test('portfolio sections remain reachable from desktop tabs and the mobile More menu', async ({ page }) => {
  const user = { username: 'tabs-' + randomUUID().slice(0, 8), password: randomUUID() + '!' };
  await page.goto('/register');
  await page.getByLabel('Tên hiển thị').fill('Fixture điều hướng');
  await page.getByLabel('Tên đăng nhập').fill(user.username);
  await page.getByLabel('Mật khẩu').fill(user.password);
  await page.getByRole('button', { name: 'Đăng ký', exact: true }).click();
  await page.waitForURL('**/login');
  await submitLogin(page, user);
  const { csrfToken } = await (await page.request.get('/auth/session')).json();
  const created = await page.request.post('/api/v1/onboarding/portfolios', {
    headers: { Origin: origin, 'X-CSRF-Token': csrfToken },
    data: { name: 'Danh mục kiểm thử điều hướng', capital_vnd: '100000000', universe_id: 'DEMO', answers: { questionnaire_version: 'risk-v1', horizon_months: 36, liquidity_need: 'low', loss_tolerance: 'medium', experience: 'experienced' } },
  });
  expect(created.status()).toBe(201);
  const { id } = await created.json() as { id: string };
  const route = (section: string) => `/#${section}?portfolio=${id}`;
  await page.goto(route('overview'));
  await expect(page.locator('.plan-overview')).toBeVisible();
  const tabs = page.getByRole('navigation', { name: 'Các phần của danh mục' });
  const menu = page.locator('.portfolio-header .mobile-menu');
  const sections = [
    { route: 'proposal', label: 'Đề xuất', content: page.locator('main .plan-status, main > .readiness, main > .proposal-request').first() },
    { route: 'history', label: 'Lịch sử mục tiêu', content: page.getByTestId('target-history') },
    { route: 'edit', label: 'Sửa danh mục', content: page.getByTestId('portfolio-name-input') },
    { route: 'overview', label: 'Tổng quan', content: page.locator('.plan-overview') },
  ];

  for (const width of [375, 390, 768, 1024, 1200, 1440, 2560]) {
    await checkWidth(page, width, 900);
    if (width < 1200) await expect(tabs).toBeHidden();
    else await expect(tabs).toBeVisible();
    for (const section of sections) {
      const inMenu = width < 1200;
      if (!inMenu && section.route === 'edit') await tabs.locator('.portfolio-extra summary').press('Enter');
      if (inMenu) await menu.getByText('Thêm', { exact: true }).click();
      const link = (inMenu ? menu : tabs).getByRole('link', { name: section.label, exact: true });
      await link.click();
      await page.waitForURL(`**${route(section.route)}`);
      await expect(section.content).toBeVisible();
      if (inMenu) await expect(menu).not.toHaveAttribute('open');
      else if (section.route !== 'edit') await expect(link).toHaveAttribute('aria-current', 'page');
      if ([375, 768, 2560].includes(width)) await saveImage(page, `portfolio-section-${section.route}-${width}`);
    }
  }
});

test('overview keeps the accepted allocation after capital and basket edits on desktop and mobile', async ({ page, browser }) => {
  const fixturePath = process.env.OVERVIEW_EDIT_ARCHIVE_RECEIPT;
  test.skip(!fixturePath, 'Requires an archived disposable basket fixture');
  const archive = await realpath(resolve(generated, 'user-selection/archives'));
  const receiptPath = await realpath(fixturePath!);
  expect(receiptPath.startsWith(archive + '/')).toBe(true);
  const fixture = JSON.parse(await readFile(receiptPath, 'utf8')) as { portfolio_id: string; target: Target; owner_isolation: boolean };
  const active = JSON.parse(await readFile(resolve(generated, 'user-selection/browser-ui-v26-receipt.json'), 'utf8')) as { portfolio_id: string };
  expect(fixture.owner_isolation).toBe(true);
  expect(fixture.portfolio_id).not.toBe(active.portfolio_id);

  const id = fixture.portfolio_id;
  const path = `/api/v1/portfolios/${id}`;
  const overviewUrl = `/#overview?portfolio=${id}`;
  const formatMoney = (value: number | string) => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' }).format(Number(value));
  async function readDashboard(current: Page) {
    const response = await current.request.get(path + '/dashboard');
    expect(response.status()).toBe(200);
    return await response.json() as Dashboard;
  }
  await signIn(page, 'alice');
  const original = await readDashboard(page);
  expect(original.portfolio.name).toMatch(/^Asset basket V2\.6 real \d+$/);
  expect(original.accepted_target).toEqual(fixture.target);
  const pinned = fixture.target.allocation;
  expect(pinned.as_of_date).toBeTruthy();
  const initialBasket = original.portfolio.asset_selection!.candidate_asset_ids;
  const removedAsset = pinned.asset_ids.find((asset, index) => Number(pinned.weights[index]) > 0 && initialBasket.includes(asset));
  expect(removedAsset).toBeTruthy();
  const reducedBasket = initialBasket.filter(asset => asset !== removedAsset);
  const initialCapital = Number(original.portfolio.capital_vnd);
  const revisedCapital = initialCapital + 20_000_000;

  function tab(current: Page, label: string) {
    return current.getByRole('navigation', { name: 'Các phần của danh mục' }).getByRole('link', { name: label, exact: true });
  }
  async function openEdit(current: Page) {
    const edit = tab(current, 'Sửa danh mục');
    const desktopMore = current.locator('.portfolio-tabs .portfolio-extra summary');
    if (await desktopMore.isVisible()) {
      await desktopMore.click();
      await edit.click();
    } else {
      await current.getByLabel('Thêm', { exact: true }).click();
      await current.getByRole('navigation', { name: 'Điều hướng thu gọn' }).getByRole('link', { name: 'Sửa danh mục' }).click();
    }
  }
  async function verifyOverview(current: Page, capital: number, basket: string[], matches: boolean) {
    const overview = current.locator('.plan-overview');
    await expect(current.locator('.plan-heading [title]')).toHaveAttribute('title', formatMoney(capital));
    await expect(overview.locator('.plan-details')).toContainText(basket.join(' · '));
    const saved = overview.locator('.allocation-primary .result-capital');
    await expect(saved.locator('strong')).toHaveText(formatMoney(pinned.capital_vnd));
    await expect(overview.locator('.plan-details')).toContainText(pinned.as_of_date!);
    await expect(overview.getByText('Danh mục đã thay đổi sau lần chấp nhận này.')).toHaveCount(matches ? 0 : 1);
    const latest = await readDashboard(current);
    expect(latest.target_matches_portfolio).toBe(matches);
    expect(Number(latest.portfolio.capital_vnd)).toBe(capital);
    expect(latest.portfolio.asset_selection?.candidate_asset_ids).toEqual(basket);
    expect(latest.accepted_target).toEqual(fixture.target);
    await checkSavedAllocation(overview, pinned);
  }
  async function editCapital(current: Page, capital: number) {
    await openEdit(current);
    await current.getByTestId('portfolio-capital-input').fill(String(capital));
    const saved = current.waitForResponse(response => response.url().endsWith(path) && response.request().method() === 'PATCH');
    await current.getByTestId('edit-portfolio-submit').click();
    expect((await saved).status()).toBe(200);
    await current.waitForURL(`**${overviewUrl}`);
  }
  async function saveBasket(current: Page) {
    const saved = current.waitForResponse(response => response.url().endsWith(path + '/asset-selections') && response.request().method() === 'POST');
    await current.getByRole('button', { name: 'Lưu lựa chọn tài sản', exact: true }).click();
    expect((await saved).status()).toBe(201);
    await tab(current, 'Tổng quan').click();
  }

  await page.goto(overviewUrl);
  await checkWidth(page, 1440, 1000);
  await verifyOverview(page, initialCapital, initialBasket, original.target_matches_portfolio);
  await editCapital(page, revisedCapital);
  await verifyOverview(page, revisedCapital, initialBasket, false);
  await openEdit(page);
  await page.getByRole('button', { name: `Bỏ ${removedAsset} khỏi rổ tài sản`, exact: true }).click();
  await saveBasket(page);
  await verifyOverview(page, revisedCapital, reducedBasket, false);
  await page.reload();
  await verifyOverview(page, revisedCapital, reducedBasket, false);
  await page.evaluate(() => window.scrollTo(0, 0));
  await saveImage(page, 'overview-edited-target-desktop');

  const mobile = await browser.newContext({ baseURL: origin, viewport: { width: 390, height: 900 }, isMobile: true, hasTouch: true });
  try {
    const phone = await mobile.newPage();
    await signIn(phone, 'alice');
    await phone.goto(overviewUrl);
    await verifyOverview(phone, revisedCapital, reducedBasket, false);
    await checkWidth(phone, 390, 900);
    await phone.evaluate(() => window.scrollTo(0, 0));
    await saveImage(phone, 'overview-edited-target-mobile');
    await editCapital(phone, initialCapital);
    await verifyOverview(phone, initialCapital, reducedBasket, false);
    await openEdit(phone);
    await phone.getByRole('button', { name: `Thêm ${removedAsset} vào rổ tài sản`, exact: true }).tap();
    await saveBasket(phone);
    await verifyOverview(phone, initialCapital, initialBasket, false);
    await phone.reload();
    await checkWidth(phone, 375, 900);
    await verifyOverview(phone, initialCapital, initialBasket, false);
    const current = await readDashboard(phone);
    const proposalId = randomUUID();
    await phone.route(url => url.pathname === path + '/recommendations' && url.searchParams.get('limit') === '1', route => route.fulfill({ json: [{
      ...pinned, id: proposalId, portfolio_id: id, portfolio_version: current.portfolio.version, valid_until: new Date(Date.now() + 86_400_000).toISOString(),
    }] }));
    await phone.reload();
    const next = phone.locator('.overview-next-step');
    const pendingLabel = 'Xem đề xuất ' + proposalId.slice(0, 8);
    const pending = next.getByRole('link', { name: pendingLabel });
    await expect(pending).toHaveAttribute('href', `#proposal?portfolio=${id}&proposal=${proposalId}`);
    const readiness = await (await phone.request.get(path + '/readiness')).json();
    if (readiness.reason_code === 'SYSTEM_PAUSED') await expect(next.locator('.plan-status a')).toHaveText('Xem lịch sử đề xuất');
    else await expect(next.locator('.plan-status a')).toHaveText(pendingLabel);
    await expect(phone.locator('.plan-result-actions').getByRole('link', { name: 'Xem mục tiêu đã lưu' })).toHaveAttribute('href', `#proposal?portfolio=${id}&proposal=${fixture.target.recommendation_id}`);
    await expect(phone.locator('.plan-overview .allocation-primary .result-capital strong')).toHaveText(formatMoney(pinned.capital_vnd));
    await saveImage(phone, 'v29-overview-pending-375');
    await phone.unrouteAll({ behavior: 'wait' });
  } finally { await mobile.close(); }
});

test('overview, review and comparison adapt to the workspace and use stored weights', async ({ page }) => {
  await signIn(page, 'alice');
  const portfolios = await (await page.request.get('/api/v1/portfolios?limit=100')).json() as { id: string }[];
  type Stored = { id: string; asset_ids: string[]; weights: (string | number)[]; inputs_provenance?: { data_origin?: string } };
  let target: { portfolioId: string; allocation: Recommendation; portfolio: Portfolio } | undefined;
  let pair: { portfolioId: string; a: Stored; b: Stored } | undefined;
  let demoPair: typeof pair;
  const weights = (value: Stored) => new Map(value.asset_ids.map((asset, index) => [asset, Number(value.weights[index])]));
  for (const portfolio of portfolios) {
    const path = `/api/v1/portfolios/${portfolio.id}`;
    if (!target) {
      const dashboard = await (await page.request.get(path + '/dashboard')).json() as Dashboard;
      if (dashboard.accepted_target) target = { portfolioId: portfolio.id, allocation: dashboard.accepted_target.allocation, portfolio: dashboard.portfolio };
    }
    if (!pair) {
      const proposals = await (await page.request.get(path + '/recommendations?limit=20')).json() as Stored[];
      for (const [i, a] of proposals.entries()) {
        const from = weights(a);
        for (const b of proposals.slice(i + 1)) {
          const to = weights(b);
          const max = Math.max(...[...new Set([...from.keys(), ...to.keys()])].map(asset => Math.abs((to.get(asset) ?? 0) - (from.get(asset) ?? 0))));
          if (max <= .0001) continue;
          const candidate = { portfolioId: portfolio.id, a, b };
          if (a.inputs_provenance?.data_origin === 'real' && b.inputs_provenance?.data_origin === 'real') pair ??= candidate;
          else demoPair ??= candidate;
        }
      }
    }
    if (target && pair) break;
  }
  pair ??= demoPair;
  if (!target || !pair) throw new Error('Saved allocation and differing proposals are required for the read-only check');

  async function checkLayout(region: Locator, chart: string, side: string, name: string, sideBeforeChart = false) {
    await expect(region.locator(chart)).toBeVisible();
    for (const width of [375, 390, 768, 1024, 1200, 1440, 1920, 2560]) {
      await checkWidth(page, width, width >= 1440 ? 1050 : 900);

      const layout = await region.evaluate((node, selectors) => {
        const chart = node.querySelector(selectors.chart)!.getBoundingClientRect();
        const side = node.querySelector(selectors.side)!.getBoundingClientRect();
        const content = node.getBoundingClientRect();
        const workspace = node.closest('main')!.getBoundingClientRect();
        return { chartTop: chart.top, chartRight: chart.right, chartBottom: chart.bottom, sideLeft: side.left, sideTop: side.top, sideBottom: side.bottom, centerOffset: Math.abs(content.left - workspace.left - (workspace.right - content.right)), contentWidth: content.width };
      }, { chart, side });
      expect(layout.centerOffset).toBeLessThanOrEqual(2);
      expect(layout.contentWidth).toBeLessThanOrEqual(1344);
      if (name === 'responsive-comparison' && layout.contentWidth >= 980) expect(layout.sideLeft - layout.chartRight).toBeGreaterThanOrEqual(16);
      else if (sideBeforeChart) expect(layout.chartTop).toBeGreaterThan(layout.sideBottom);
      else expect(layout.sideTop).toBeGreaterThan(layout.chartBottom);
      if ([768, 2560].includes(width)) {
        await page.evaluate(() => window.scrollTo(0, 0));
        await saveImage(page, `${name}-${width}`);
      }
    }
  }

  await page.goto(`/#overview?portfolio=${target.portfolioId}`);
  const overview = page.locator('.plan-overview');
  const money = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' });
  await expect(page.locator('.plan-heading [title]')).toHaveAttribute('title', money.format(Number(target.portfolio.capital_vnd)));
  if (target.portfolio.asset_selection) await expect(overview.locator('.plan-details')).toContainText(target.portfolio.asset_selection.candidate_asset_ids.join(' · '));
  await expect(overview.locator('.allocation-primary .result-capital strong')).toHaveText(money.format(Number(target.allocation.capital_vnd)));
  if (target.allocation.as_of_date) await expect(overview.locator('.plan-details')).toContainText(target.allocation.as_of_date);
  await checkLayout(overview, '.allocation-primary', '.plan-result-actions', 'responsive-overview');
  await checkWidth(page, 390, 900);
  await saveImage(page, 'responsive-overview-390');
  await checkWidth(page, 375);
  await checkSavedAllocation(overview, target.allocation, 'responsive-overview-375');
  await expect(page.locator('.account-actions button')).not.toBeInViewport();

  await overview.locator('.plan-details > details > summary').click();
  await overview.locator('summary').filter({ hasText: /^Dữ liệu và cách tính$/ }).click();
  await page.getByRole('link', { name: 'Xem mục tiêu đã lưu' }).click();
  const review = page.locator('.proposal-review');
  await checkLayout(review, '.allocation-primary', '.plan-status', 'responsive-review', true);
  await checkWidth(page, 390);
  await checkSavedAllocation(review, target.allocation, 'responsive-review-390');
  await expect(review.getByTestId('accept-proposal')).toBeDisabled();
  await review.locator('.plan-evidence > summary').click();
  await expect(review.getByText('Dữ liệu dùng để tính', { exact: true })).toBeVisible();
  await checkWidth(page, 390);

  await page.goto('/#compare?' + new URLSearchParams({ portfolio: pair.portfolioId, a: pair.a.id, b: pair.b.id }));
  const comparison = page.getByTestId('comparison');
  await checkLayout(comparison, '.comparison-chart', '.comparison-context', 'responsive-comparison', true);
  await checkWidth(page, 375);
  const from = weights(pair.a), to = weights(pair.b);
  const assets = [...new Set([...from.keys(), ...to.keys()])];
  const differences = new Map(assets.map((asset): [string, number] => [asset, (to.get(asset) ?? 0) - (from.get(asset) ?? 0)]).filter(([, delta]) => delta !== 0));
  const axisEnd = await comparison.locator('.comparison-chart .weight-chart-axis span').last().textContent();
  const extent = Number(axisEnd?.slice(1).replace(',', '.'));
  const comparisonBars = await comparison.getByRole('list', { name: 'Chênh lệch tỷ trọng theo tài sản' }).getByRole('listitem').evaluateAll(rows => rows.map(row => ({
    asset: row.querySelector('.comparison-bar-label > strong')!.textContent!,
    width: parseFloat(row.querySelector<HTMLElement>('.comparison-bar > span')!.style.width),
    direction: row.querySelector('.comparison-bar > span')!.getAttribute('data-direction'),
  })));
  expect(comparisonBars).toHaveLength(differences.size);
  for (const bar of comparisonBars) {
    const delta = differences.get(bar.asset) ?? NaN;
    expect(bar.width).toBeCloseTo(Math.abs(delta) * 100 / extent * 50, 4);
    expect(bar.direction).toBe(delta < 0 ? 'decrease' : 'increase');
  }
  expect(await comparison.locator('.task-actions').evaluate(node => getComputedStyle(node).position)).toBe('static');
  await page.getByText(/Xem bảng so sánh/).click();
  await expect(page.locator('.comparison-table tbody tr')).toHaveCount(assets.length);
  await checkWidth(page, 375);
  await page.getByText(/Xem bảng so sánh/).click();
  await page.locator('.comparison-chart h2').evaluate(node => node.scrollIntoView({ block: 'start' }));
  await saveImage(page, 'responsive-comparison-375');

  await checkWidth(page, 1440);
  const sidebar = page.getByRole('navigation', { name: 'Điều hướng chính' });
  await sidebar.getByRole('link', { name: 'Giá tài sản' }).click();
  await expect(sidebar.getByRole('link', { name: 'Giá tài sản' })).toHaveAttribute('aria-current', 'page');
  await expect(sidebar.getByRole('link', { name: 'Danh mục' })).not.toHaveAttribute('aria-current', 'page');
  const picker = page.getByLabel('Tài sản', { exact: true });
  await expect(picker).toHaveValue('FPT');
  await expect(page.getByRole('figure')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Về danh mục', exact: true })).toHaveCount(0);
  await picker.selectOption('MBB');
  await expect(page.getByRole('heading', { name: 'MBB · Lịch sử giá', exact: true })).toBeVisible();
  await expect(page.getByRole('figure')).toBeVisible();

  await checkWidth(page, 375);
  await page.locator('.mobile-menu summary').click();
  const mobileMenu = page.getByRole('navigation', { name: 'Điều hướng thu gọn' });
  await expect(mobileMenu.getByRole('link', { name: 'Giá tài sản' })).toHaveAttribute('aria-current', 'page');
  await mobileMenu.getByRole('link', { name: 'Giá tài sản' }).click();
  await expect(page).toHaveURL(url => !new URLSearchParams(url.hash.split('?')[1]).has('asset'));
  await expect(picker).toHaveValue('MBB');
  await expect(page.getByRole('figure')).toBeVisible();

  await page.reload();
  await expect(picker).toHaveValue('MBB');
  await page.goto('/#asset-prices?asset=FPT');
  await expect(picker).toHaveValue('FPT');
  await expect(page.getByRole('figure')).toBeVisible();
  await page.goto('/#asset-prices');
  await expect(picker).toHaveValue('FPT');
  await expect(page.getByRole('figure')).toBeVisible();

});

test('gold price question reads the saved SJC quote without choosing a portfolio', async ({ page }) => {
  await signIn(page, 'bob');
  await page.goto('/#chat');
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-create').click();
  await page.waitForURL(/#chat\?conversation=/);
  const cid = new URLSearchParams(new URL(page.url()).hash.split('?')[1]).get('conversation');
  const path = `/api/v1/conversations/${cid}/messages`;
  const input = page.getByTestId('chat-input');
  await input.fill('Giá vàng hôm nay');
  const submitted = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === path);
  await input.press('Enter');
  const response = await submitted;
  expect(response.status()).toBe(202);
  expect(response.request().postDataJSON().portfolio_id).toBeUndefined();
  const { job_id } = await response.json();
  await expect.poll(async () => {
    const job = await (await page.request.get(`/api/v1/jobs/chat/${job_id}`)).json();
    return [job.status, job.provider_usage, job.recommendation_id];
  }).toEqual(['SUCCEEDED', [], null]);
  const messages = await (await page.request.get(path)).json();
  const { content, structured } = messages.find((m: { role: string }) => m.role === 'assistant');
  expect(structured.facts.scope).toBe('gold_quote');
  const [row] = structured.facts.observations;
  expect(row.asset_id).toBe('GOLD');
  expect(row.provider).toBe('giavang-sjc-hcm-archive-v1');
  const prices = await page.request.get('/api/v1/market/price-series', { params: {
    asset_id: 'GOLD', start_date: row.observation_date, end_date: row.observation_date,
  } });
  expect(prices.ok()).toBe(true);
  const series = (await prices.json()).series.find((s: { provider: string }) => s.provider === row.provider);
  expect(series.observations).toContainEqual(expect.objectContaining({ revision_id: row.revision_id, price_vnd: row.price_vnd }));
  expect(content).toContain(Number(row.price_vnd).toLocaleString('vi-VN') + ' đồng/lượng');
  await page.reload();
  await expect(page.locator('.chat-assistant').last()).toContainText(content);
  await page.getByRole('link', { name: 'Xem lịch sử giá vàng' }).click();
  await expect(page).toHaveURL(/#asset-prices\?asset=GOLD/);
});

test('a saved stock quote opens the same ticker and its own source', async ({ page }) => {
  await signIn(page, 'bob');
  await page.goto('/#chat');
  const composer = page.getByTestId('chat-input');
  await composer.fill('Giá FPT ngày 01/01/2024?');
  const sent = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/messages'));
  await page.getByTestId('chat-send').click();
  const { conversation_id, job_id } = await (await sent).json();
  await expect.poll(async () => (await (await page.request.get('/api/v1/jobs/chat/' + job_id)).json()).status).toBe('SUCCEEDED');
  const messages = await (await page.request.get('/api/v1/conversations/' + conversation_id + '/messages')).json();
  const answer = messages.find((message: {role: string}) => message.role === 'assistant');
  expect(answer.structured.facts).toMatchObject({ scope: 'equity_quote', asset_id: 'FPT', requested_date: '2024-01-01' });
  if (!answer.structured.facts.observations.some((row: {observation_date: string}) => row.observation_date === '2024-01-01')) {
    expect(answer.content).toContain('Chưa có giá FPT đã xác minh cho ngày 01/01/2024');
    expect(answer.content).not.toContain('đồng/cổ phiếu');
  }
  await page.reload();
  const reply = page.locator(`[data-message-id="${answer.id}"]`);
  await reply.getByRole('button', { name: 'Xem dữ kiện và nguồn' }).click();
  await expect(page.locator('.chat-detail-panel')).toContainText('Ngày được hỏi: 2024-01-01');
  const chart = reply.getByRole('link', { name: 'Xem lịch sử giá FPT' });
  if (answer.structured.facts.observations.length) {
    await expect(page.locator('.chat-detail-panel')).toContainText('FPT');
    await page.locator('.chat-detail-header button').click();
    await chart.click();
    await expect(page).toHaveURL(/#asset-prices\?asset=FPT/);
  } else {
    await expect(page.locator('.chat-detail-panel')).toContainText('Chưa có quan sát thị trường.');
    await expect(chart).toHaveCount(0);
  }
});

test('V2.11 saved target retains its identity from FPT prices to a real chat turn', async ({ page }, info) => {
  await signIn(page, 'alice');
  const portfolios: Portfolio[] = await (await page.request.get('/api/v1/portfolios?limit=100')).json();
  let target: Target | null = null, portfolio_id = '';
  for (const item of portfolios) {
    const dashboard: Dashboard = await (await page.request.get('/api/v1/portfolios/' + item.id + '/dashboard')).json();
    if (dashboard.accepted_target?.allocation.asset_ids.includes('FPT')) { target = dashboard.accepted_target; portfolio_id = item.id; break; }
  }
  expect(target, 'Dedicated investor has a saved allocation containing FPT').toBeTruthy();
  const { allocation, recommendation_id } = target!;
  const directory = resolve('../../output/playwright/v211');
  await mkdir(directory, { recursive: true });
  const capture = async (name: string) => page.screenshot({ path: resolve(directory, name + '.png'), mask: [page.locator('.account-name')], maskColor: '#f2f7f5' });
  await checkWidth(page, 390);
  await page.goto('/#overview?portfolio=' + portfolio_id);
  await page.getByRole('link', { name: 'Xem giá FPT', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'FPT · Lịch sử giá' })).toBeVisible();
  await page.getByRole('link', { name: 'Trở lại phân bổ' }).last().click();
  await expect(page).toHaveURL(/#overview\?/);
  await page.getByRole('link', { name: 'Hỏi về kế hoạch' }).first().click();
  await expect(page).toHaveURL(new RegExp('proposal=' + recommendation_id));
  await expect(page.locator('.chat-context-preview')).toContainText('Mục tiêu đã lưu');
  await expect(page.getByRole('heading', { name: 'Bạn muốn hiểu gì về phân bổ đã lưu?' })).toBeVisible();
  let sends = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/messages')) sends++; });
  await page.getByRole('button', { name: 'Tỷ trọng FPT', exact: true }).click();
  const input = page.getByTestId('chat-input');
  await expect(input).toHaveValue('Giải thích tỷ trọng FPT');
  await page.getByRole('button', { name: 'Lịch sử', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Lịch sử hội thoại' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(input).toHaveValue('Giải thích tỷ trọng FPT');
  await capture('chat-saved-draft-390');
  await input.focus();
  await page.evaluate(() => {
    Object.defineProperty(visualViewport, 'height', { configurable: true, value: 455 });
    visualViewport?.dispatchEvent(new Event('resize'));
  });
  await expect(page.locator('.workspace-chat')).toHaveAttribute('data-chat-keyboard', '');
  const box = (await input.boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(455);
  await expect(page.locator('.bottom-nav')).toBeHidden();
  await page.screenshot({ path: resolve(directory, 'chat-keyboard-390.png'), clip: { x: 0, y: 0, width: 390, height: 455 } });
  await page.evaluate(() => {
    if (visualViewport) Reflect.deleteProperty(visualViewport, 'height');
    visualViewport?.dispatchEvent(new Event('resize'));
  });
  expect(sends).toBe(0);
  const sent = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/messages'));
  await input.press('Enter');
  const response = await sent;
  expect(response.status()).toBe(202);
  expect(response.request().postDataJSON()).toMatchObject({ intent: 'explain', content: 'Giải thích tỷ trọng FPT', portfolio_id, recommendation_id });
  const { job_id } = await response.json();
  await expect.poll(async () => (await (await page.request.get('/api/v1/jobs/chat/' + job_id)).json()).status, { timeout: 90000 }).toBe('SUCCEEDED');
  expect(sends).toBe(1);
  const card = page.getByTestId('chat-result').last();
  await expect(card.locator('.chat-answer-text strong')).toContainText('FPT');
  const facts = card.locator('details.chat-turn-facts');
  await facts.locator('summary').click();
  const weight = Number(allocation.weights[allocation.asset_ids.indexOf('FPT')]);
  const amount = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(weight * Number(allocation.capital_vnd));
  await expect(facts).toContainText(amount);
  await capture('chat-saved-facts-390');
  for (const width of [375, 768, 1440]) {
    await checkWidth(page, width, width === 1440 ? 1000 : 844);
    await expect(input).toBeInViewport({ ratio: 1 });
    await expect(facts).toContainText(amount);
    if (width === 1440) await capture('chat-saved-facts-1440');
  }
  info.annotations.push({ type: 'safe-phase', description: 'real-target-price-chat-turn-and-facts' });
});

test('V2.11 plan chat uses the selected portfolio and keeps long replies above the composer', async ({ page }) => {
  await signIn(page, 'bob');
  const portfolios: Portfolio[] = await (await page.request.get('/api/v1/portfolios?limit=100')).json();
  let dashboard: Dashboard | undefined;
  for (const portfolio of portfolios) {
    const state: Dashboard = await (await page.request.get('/api/v1/portfolios/' + portfolio.id + '/dashboard')).json();
    if (state.proposal_count === 0 && state.portfolio.risk_profile?.answers) { dashboard = state; break; }
  }
  async function makePlan(name: string) {
    const { csrfToken } = await (await page.request.get('/auth/session')).json();
    const response = await page.request.post('/api/v1/onboarding/portfolios', {
      headers: { Origin: origin, 'X-CSRF-Token': csrfToken },
      data: { name, capital_vnd: '100000000', universe_id: 'DEMO',
        answers: { questionnaire_version: 'risk-v1', horizon_months: 36, liquidity_need: 'low', loss_tolerance: 'medium', experience: 'experienced' } },
    });
    expect(response.status()).toBe(201);
    return (await response.json()).id as string;
  }
  if (!dashboard) {
    const id = await makePlan('Kế hoạch tích lũy 36 tháng');
    dashboard = await (await page.request.get('/api/v1/portfolios/' + id + '/dashboard')).json();
  }
  const portfolio = dashboard!.portfolio;
  if (!portfolios.some(item => item.id !== portfolio.id)) await makePlan('Kế hoạch thứ hai');
  const readinessPath = '/api/v1/portfolios/' + portfolio.id + '/readiness';
  const readiness = await (await page.request.get(readinessPath)).json();
  if (readiness.reason_code !== 'SYSTEM_PAUSED') {
    await page.route('**' + readinessPath, route => route.fulfill({ json: { ...readiness, can_submit: false, status: 'BLOCKED', reason_code: 'SYSTEM_PAUSED' } }));
  }
  await checkWidth(page, 390);
  await page.goto('/#chat?portfolio=' + portfolio.id);
  await expect(page.locator('.chat-welcome')).toContainText('Tính đề xuất mới đang tạm dừng.');
  await page.getByText('Đặt tên hội thoại (tùy chọn)', { exact: true }).click();
  await page.getByTestId('chat-title').fill('Kiểm tra kế hoạch đã chọn');
  await page.getByRole('button', { name: 'Tóm tắt kế hoạch', exact: true }).click();
  const sent = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/messages'));
  await page.getByTestId('chat-send').click();
  const response = await sent;
  const { job_id, conversation_id } = await response.json();
  const body = response.request().postDataJSON();
  expect(body).toMatchObject({ portfolio_id: portfolio.id, intent: 'portfolio' });
  expect(body).not.toHaveProperty('recommendation_id');
  await expect.poll(async () => (await (await page.request.get('/api/v1/jobs/chat/' + job_id)).json()).status, { timeout: 90000 }).toBe('SUCCEEDED');
  const facts = page.locator('.chat-assistant details.chat-turn-facts');
  await facts.locator('summary').click();
  await expect(facts).toContainText(portfolio.name);
  await expect(facts).toContainText(portfolio.risk_profile!.answers!.horizon_months + ' tháng');
  const directory = resolve('../../output/playwright/v211');
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: resolve(directory, 'chat-plan-facts-390.png') });
  await page.getByRole('button', { name: 'Lịch sử', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('link').filter({ hasText: 'Kiểm tra kế hoạch đã chọn' }).first()).toBeVisible();
  await page.keyboard.press('Escape');
  await page.locator('.chat-context-summary').click();
  const select = page.getByTestId('chat-portfolio');
  const next = await select.locator('option').evaluateAll((options, current) => options.map(option => (option as HTMLOptionElement).value).find(value => value && value !== current), portfolio.id);
  expect(next).toBeTruthy();
  await select.selectOption(next!);
  await expect(page.locator('.chat-context-label')).not.toContainText(portfolio.name);
  await expect(facts).toContainText(portfolio.name);
  await expect(page).toHaveURL(new RegExp('conversation=' + conversation_id));
  const composer = page.getByTestId('chat-input');
  for (const asset of ['FPT', 'MBB', 'VCB']) {
    await composer.fill(`Giá ${asset} ngày 01/01/2024?`);
    const posted = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/messages'));
    await composer.press('Enter');
    const result = await posted;
    expect(result.status()).toBe(202);
    expect(result.request().postDataJSON().portfolio_id).toBe(next);
    const { job_id } = await result.json();
    await expect.poll(async () => (await (await page.request.get('/api/v1/jobs/chat/' + job_id)).json()).status, { timeout: 90000 }).toBe('SUCCEEDED');
    await expect(composer).toBeEnabled();
  }
  const transcript = page.locator('.chat-transcript');
  await expect(transcript.locator('li.chat-message').nth(7)).toBeVisible();
  for (const width of [375, 390, 768, 1440]) {
    await checkWidth(page, width);
    await expect(composer).toBeInViewport({ ratio: 1 });
    await transcript.evaluate(node => { node.scrollTop = 0; });
    const bottom = page.getByRole('button', { name: 'Cuộn đến cuối vùng trao đổi' });
    if (await transcript.evaluate(node => node.scrollHeight - node.clientHeight > 64)) {
      await expect(bottom).toBeVisible();
      await bottom.click();
      await expect(bottom).toBeHidden();
    }
    await expect(composer).toBeInViewport({ ratio: 1 });
    if (width === 390) await page.screenshot({ path: resolve(directory, 'chat-long-390.png') });
  }
});
