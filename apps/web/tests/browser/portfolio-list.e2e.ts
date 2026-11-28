import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { submitLogin } from './login-form';

const firstPlan = 'Kế hoạch đầu tư 01';
const secondPagePlan = 'Kế hoạch đầu tư 11';
const screenshotOptions = {
  animations: 'disabled',
  scale: 'css',
  maxDiffPixels: 0,
  stylePath: fileURLToPath(new URL('./portfolio-list-screenshot.css', import.meta.url)),
} as const;

async function checkLayouts(page: Page, region: Locator, prefix = '') {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.mouse.move(0, 0);
  await page.evaluate(() => document.fonts.ready);
  await expect.soft(region).toHaveScreenshot(prefix + 'desktop.png', screenshotOptions);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.soft(region).toHaveScreenshot(prefix + 'mobile.png', screenshotOptions);
  await page.setViewportSize({ width: 320, height: 740 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  const controls = region.locator('button:visible, input:visible, select:visible, a:visible');
  expect(await controls.evaluateAll(nodes => nodes.every(node => {
    const box = node.getBoundingClientRect();
    return box.left >= 0 && box.right <= document.documentElement.clientWidth;
  }))).toBe(true);
}

async function login(page: Page, baseURL?: string) {
  const origin = new URL(baseURL ?? '');
  if (process.env.E2E_DISPOSABLE_STACK !== '1' || origin.protocol !== 'http:' ||
    !['localhost', '127.0.0.1'].includes(origin.hostname)) {
    throw new Error('Portfolio list visuals require the disposable localhost stack.');
  }
  const account = { username: `visual-${randomUUID().slice(0, 8)}`, password: `${randomUUID()}!` };
  const registration = await page.request.post('/auth/register', {
    headers: { origin: origin.origin },
    data: { ...account, name: 'Nhà đầu tư mẫu' },
  });
  expect(registration.status()).toBe(201);
  await page.goto('/login');
  await submitLogin(page, account);
  const session = await page.request.get('/auth/session');
  expect(session.status()).toBe(200);
  const { csrfToken } = await session.json();

  return { origin: origin.origin, csrfToken };
}

test('Portfolio list and context picker use the same controls on desktop and mobile', async ({ page, baseURL }, info) => {
  const phase = (description: string) => { info.annotations = [{ type: 'safe-phase', description }]; };
  phase('real-login');
  const { origin, csrfToken } = await login(page, baseURL);
  phase('seed-portfolios');
  for (let index = 1; index <= 12; index++) {
    const response = await page.request.post('/api/v1/onboarding/portfolios', {
      headers: { origin, 'x-csrf-token': csrfToken },
      data: {
        name: `Kế hoạch đầu tư ${String(index).padStart(2, '0')}`,
        capital_vnd: String(index * 25_000_000),
        universe_id: 'DEMO',
        answers: {
          questionnaire_version: 'risk-v1',
          horizon_months: [6, 36, 84][(index - 1) % 3],
          liquidity_need: 'low',
          loss_tolerance: 'high',
          experience: 'experienced',
        },
      },
    });
    expect(response.status()).toBe(201);
  }

  phase('portfolio-list');
  const start = new Date();
  await page.clock.install({ time: new Date(start.getTime() - 1000) });
  await page.clock.pauseAt(start);
  await page.goto('/#portfolios');
  const list = page.getByRole('region', { name: 'Danh sách danh mục' });
  const sort = list.getByRole('combobox', { name: 'Sắp xếp danh mục' });
  const risk = list.getByRole('combobox', { name: 'Lọc theo hồ sơ' });
  const search = list.getByRole('searchbox', { name: 'Tìm trong danh sách' });
  const paging = list.getByRole('navigation', { name: 'Phân trang' });
  const next = paging.getByRole('button', { name: 'Trang sau' });
  const previous = paging.getByRole('button', { name: 'Trang trước' });
  const first = list.getByRole('link', { name: `Mở danh mục ${firstPlan}`, exact: true });
  const eleventh = list.getByRole('link', { name: `Mở danh mục ${secondPagePlan}`, exact: true });
  await test.step('Immediate pagination survives the initial search debounce', async () => {
    await expect(next).toBeEnabled();
    await next.press('Enter');
    await expect(paging.getByRole('status')).toHaveText('Trang 2 · 12 kết quả');
    await page.clock.runFor(300);
    await expect(paging.getByRole('status')).toHaveText('Trang 2 · 12 kết quả');
    await expect(previous).toBeEnabled();
    await previous.press('Enter');
    await expect(paging.getByRole('status')).toHaveText('Trang 1 · 12 kết quả');
    await page.clock.resume();
  });
  await sort.selectOption('name_asc');
  await expect(first).toBeVisible();
  await expect(paging.getByRole('status')).toHaveText('Trang 1 · 12 kết quả');
  await expect(previous).toBeDisabled();
  phase('visual-comparison');
  await checkLayouts(page, list);

  phase('real-list-controls');
  await next.click();
  await expect(eleventh).toBeVisible();
  await expect(paging.getByRole('status')).toHaveText('Trang 2 · 12 kết quả');
  await expect(next).toBeDisabled();
  await previous.click();
  await expect(first).toBeVisible();
  await risk.selectOption('growth');
  await expect(list.getByText('4 kết quả', { exact: true })).toBeVisible();
  await search.fill('Không có danh mục này');
  await list.getByRole('button', { name: 'Xóa bộ lọc' }).click();
  await expect(risk).toHaveValue('all');
  await search.fill('12');
  await expect(list.getByText('1 kết quả', { exact: true })).toBeVisible();
  await list.getByRole('link', { name: 'Mở danh mục Kế hoạch đầu tư 12', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Kế hoạch đầu tư 12', exact: true })).toBeVisible();
  await page.goto('/#portfolios');
  await list.getByRole('link', { name: 'Tạo danh mục', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Lập kế hoạch đầu tư', exact: true })).toBeVisible();

  phase('choose-portfolio');
  await page.goto('/#profile');
  const chooser = page.getByRole('region', { name: 'Chọn danh mục' });
  const chooseSearch = chooser.getByRole('searchbox');
  const choose = chooser.getByRole('link', { name: 'Chọn danh mục ' + firstPlan, exact: true });
  await expect(chooser.getByRole('navigation', { name: 'Phân trang' }).getByRole('status')).toHaveText('Trang 1 · 12 kết quả');
  await checkLayouts(page, chooser, 'choose-');
  await chooser.getByRole('button', { name: 'Trang sau' }).click();
  await expect(choose).toBeVisible();
  await chooseSearch.fill(firstPlan);
  await expect(chooser.getByText('1 kết quả', { exact: true })).toBeVisible();
  const destination = await choose.getAttribute('href');
  expect(destination).toMatch(/^#profile\?portfolio=/);
  await choose.focus();
  await page.keyboard.press('Enter');
  await expect.poll(() => new URL(page.url()).hash).toBe(destination);
  await expect(chooser).toHaveCount(0);

});

test('Portfolio list account controls remain accessible across investor routes', async ({ page, baseURL }) => {
  const { origin, csrfToken } = await login(page, baseURL);
  const portfolio = await page.request.post('/api/v1/onboarding/portfolios', {
    headers: { origin, 'x-csrf-token': csrfToken },
    data: { name: firstPlan, capital_vnd: '25000000', universe_id: 'DEMO',
      answers: { questionnaire_version: 'risk-v1', horizon_months: 6, liquidity_need: 'low', loss_tolerance: 'high', experience: 'experienced' } },
  });
  expect(portfolio.status()).toBe(201);
  const portfolioQuery = '?portfolio=' + (await portfolio.json()).id;
  const conversation = await page.request.post('/api/v1/conversations', {
    headers: { origin, 'x-csrf-token': csrfToken }, data: { title: 'Kiểm tra thanh điều hướng' },
  });
  expect(conversation.status()).toBe(201);
  const chat = 'chat?conversation=' + (await conversation.json()).id;
  const context = page.context();
  await page.close();
  for (const width of [390, 1024, 1200, 1440, 2560]) {
    const screen = await context.newPage();
    const accountActions = screen.locator('.account-bar .account-actions');
    const logout = accountActions.getByRole('button', { name: 'Đăng xuất' });
    await screen.setViewportSize({ width, height: 900 });
    await screen.goto('/#portfolios');
    await screen.evaluate(() => window.scrollTo(0, 0));
    let reference = await accountActions.boundingBox();
    for (const hash of ['overview' + portfolioQuery, 'history' + portfolioQuery, 'create', 'portfolios', 'asset-prices', 'chat', chat, 'settings']) {
      await screen.goto('/#' + hash);
      await expect(screen.locator('main')).toHaveAttribute('data-view', hash.split('?')[0]);
      if (hash.endsWith(portfolioQuery)) {
        if (width < 1200) await expect(screen.locator('.portfolio-header .mobile-menu > summary')).toBeVisible();
        else await expect(screen.getByRole('navigation', { name: 'Các phần của danh mục' })).toBeVisible();
      }
      if (hash === 'create' && await screen.locator('.wizard-mobile-nav').isVisible()) {
        await screen.locator('.wizard-mobile-nav').getByRole('link', { name: 'Danh mục' }).click();
        await expect(screen.getByRole('region', {name: 'Danh sách danh mục'})).toBeVisible();
      }
      if (width < 1200 && !await logout.isVisible()) {
        const menu = screen.locator('main .mobile-menu');
        const trigger = menu.locator(':scope > summary');
        await trigger.click();
        await menu.getByRole('button', { name: 'Đăng xuất' }).click({ trial: true });
        await trigger.press('Escape');
      } else {
        await expect(logout).toBeVisible();
        reference ??= await accountActions.boundingBox();
        await expect.poll(() => accountActions.boundingBox()).toEqual(reference);
        await logout.click({ trial: true });
      }
      if (hash === chat) {
        const actions = screen.locator('.chat-topline-actions:visible').or(screen.getByRole('link', { name: 'Hội thoại mới', exact: true })).first();
        await expect(actions).toBeVisible();
        const box = (await actions.boundingBox())!;
        if (width <= 800) {
          const menu = (await screen.locator('main .mobile-menu > summary').boundingBox())!;
          expect(menu.x + menu.width <= box.x || menu.y + menu.height <= box.y).toBe(true);
        } else expect(box.y >= reference!.y + reference!.height || box.x + box.width <= reference!.x).toBe(true);
      }
    }
    await screen.close();
  }
});

test('Portfolio list controls in the asset picker preserve the basket through creation and editing', async ({ page, baseURL }, info) => {
  await login(page, baseURL);
  await page.goto('/#create');
  await page.getByLabel(/^Tên danh mục/).fill('Kế hoạch chọn tài sản');
  await page.getByRole('button', { name: 'Chọn tài sản', exact: true }).click();

  const next = page.getByRole('button', {name: 'Tiếp tục', exact: true});
  await expect(next).toBeDisabled();
  await page.getByRole('button', {name: 'Thêm VFF vào rổ tài sản'}).press('Enter');
  await next.click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  const questions = page.locator('.risk-question:visible');
  await expect(questions).toHaveCount(3);
  const rows = await questions.evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().toJSON()));
  expect(rows[1].top).toBeGreaterThanOrEqual(rows[0].bottom);
  expect(rows[2].top).toBeGreaterThanOrEqual(rows[1].bottom);
  await page.setViewportSize({ width: 320, height: 740 });
  await page.getByRole('radio', { name: 'Vừa · Từ 5% đến dưới 15%' }).check();
  await page.getByRole('radio', { name: 'Tối đa 10%' }).check();
  await page.getByRole('radio', { name: 'Từ 6 tháng trở lên' }).check();
  await page.getByRole('button', { name: 'Xem lại hồ sơ' }).click();
  const created = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/v1/onboarding/portfolios'));
  await page.getByTestId('create-portfolio-submit').click();
  const response = await created;
  expect(response.status()).toBe(201);
  const portfolio = await response.json();
  expect(portfolio.asset_selection.candidate_asset_ids).toEqual(['VFF']);
  await page.goto('/#edit?portfolio=' + portfolio.id);
  const picker = page.getByRole('group', { name: 'Rổ tài sản tự chọn' });
  const assetRows = picker.locator('.wizard-asset:visible');
  const expand = picker.getByRole('button', { name: /^Xem tất cả/ });
  await expect(assetRows).toHaveCount(2);
  await expand.click();
  await expect(assetRows).toHaveCount(32);
  const search = picker.getByRole('searchbox');
  await search.fill('ACB');
  await picker.getByRole('button', { name: 'Thêm ACB vào rổ tài sản' }).press('Enter');
  await search.fill('');
  await picker.getByRole('button', { name: 'Thu gọn' }).click();
  await expect(assetRows).toHaveCount(2);
  await page.setViewportSize({width:1440,height:1000});
  await expect(assetRows).toHaveCount(32);
  await expect(picker.locator('.wizard-basket-summary .wizard-asset-id strong')).toHaveText(['VFF', 'ACB']);
  await expect(picker.locator('.wizard-candidates .wizard-asset')).toHaveCount(30);
  const save = page.getByRole('button', { name: 'Lưu lựa chọn tài sản' });
  const saved = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/asset-selections'));
  await save.click();
  expect((await saved).status()).toBe(201);
  await page.reload();
  await expect(picker.locator('[aria-pressed=true]')).toHaveCount(2);
  await expect(picker.getByRole('button', { name: 'Bỏ ACB khỏi rổ tài sản' })).toBeVisible();
  await expect(picker.getByRole('button', { name: 'Bỏ VFF khỏi rổ tài sản' })).toBeVisible();
  await expect(save).toBeDisabled();
  const panes = await picker.locator('.wizard-asset-list').evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect().toJSON()));
  expect(panes[0].top).toBe(panes[1].top);
  expect(panes[0].height).toBe(panes[1].height);
  await picker.screenshot({ path: '../../output/playwright/v211/edit-basket-1440.png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expand.click();
  await search.fill('BID');
  await picker.getByRole('button', { name: 'Thêm BID vào rổ tài sản' }).click();
  const mobileSave = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/asset-selections'));
  await save.click();
  expect((await mobileSave).status()).toBe(201);
  await page.reload();
  await expect(picker.getByRole('button', { name: 'Bỏ BID khỏi rổ tài sản' })).toBeVisible();
  await expect(save).toBeDisabled();
  const removeBID = picker.getByRole('button', { name: 'Bỏ BID khỏi rổ tài sản' });
  expect((await removeBID.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect(await removeBID.evaluate(button => button.closest('li')!.getBoundingClientRect().height)).toBeLessThan(100);
  await picker.screenshot({ path: '../../output/playwright/v211/edit-basket-390.png' });
});
