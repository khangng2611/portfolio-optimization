import { expect, test, type Page } from '@playwright/test';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { submitLogin } from './login-form';

const directory = resolve('../../output/playwright/v211');
const widths = [375, 390, 768, 1440] as const;
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3100';
test.use({ baseURL });
test.beforeAll(async () => {
  const url = new URL(baseURL);
  if (!['127.0.0.1', 'localhost'].includes(url.hostname) || url.port !== '3100') throw new Error('Run against local port 3100.');
  await mkdir(directory, { recursive: true });
});

async function capture(page: Page, name: string, width: number) {
  await page.setViewportSize({ width, height: width < 600 ? 844 : 1000 });
  await page.evaluate(() => document.fonts.ready);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(directory, `${name}-${width}.png`), animations: 'disabled', mask: [page.locator('.account-name')], maskColor: '#f1f7f4' });
}

test('V2.11 login, basket drafts, profile and account navigation', async ({ page }) => {
  await page.goto('/login');
  for (const width of widths) {
    await capture(page, 'login', width);
    await expect(page.getByRole('button', { name: 'Đăng nhập', exact: true })).toBeInViewport();
  }
  const accounts = JSON.parse(await readFile(resolve('../../infra/local/.generated/accounts.json'), 'utf8'));
  await submitLogin(page, accounts.users.find((user: { username: string }) => user.username === 'bob'));
  await page.goto('/#create');
  await page.getByLabel('Tên danh mục').fill('Tích lũy dài hạn');
  await expect(page.locator('.wizard-progress-label')).toHaveText('Bước 1/4 · Mục tiêu');
  for (const width of widths) await capture(page, 'plan', width);
  const open = page.getByRole('button', { name: 'Chọn tài sản', exact: true });
  const back = page.getByRole('button', { name: 'Quay lại', exact: true });
  const next = page.getByRole('button', { name: 'Tiếp tục', exact: true });
  await open.click();
  const search = page.getByRole('searchbox', { name: 'Tìm tài sản', exact: true });
  const toggle = (asset: string, selected: boolean) => page.getByRole('button', { name: selected ? `Bỏ ${asset} khỏi rổ tài sản` : `Thêm ${asset} vào rổ tài sản` });
  async function reopen(ids: string[]) {
    await back.click();
    await expect(page.getByLabel('Tên danh mục')).toHaveValue('Tích lũy dài hạn');
    await expect(page.getByLabel('Thời gian đầu tư (tháng)')).toHaveValue('36');
    await expect(page.locator('.wizard-progress-label')).toHaveText('Bước 1/4 · Mục tiêu');
    await open.click();
    await expect(page.locator('.wizard-progress-label')).toHaveText('Bước 2/4 · Rổ tài sản');
    await expect(page.locator('.wizard-asset-toggle[aria-pressed=true]')).toHaveCount(ids.length);
    for (const id of ids) await expect(toggle(id, true)).toHaveAttribute('aria-pressed', 'true');
  }
  await reopen([]);
  await expect(next).toBeDisabled();
  await capture(page, 'basket-empty', 390);
  await toggle('VFF', false).press('Enter');
  await reopen(['VFF']);
  await capture(page, 'basket-vff', 390);
  await search.fill('FPT');
  await toggle('FPT', false).click();
  await search.fill('');
  await toggle('VFF', true).click();
  await reopen(['FPT']);
  await expect(next).toBeEnabled();
  await capture(page, 'basket-fpt', 390);
  await toggle('VFF', false).click();
  await reopen(['VFF', 'FPT']);
  await expect(page.locator('.task-actions')).toContainText('Mã đã chọn có thể nhận tỷ trọng 0%.');
  for (const width of widths) {
    await capture(page, 'basket', width);
    if (width < 960) {
      const fpt = toggle('FPT', true);
      const bounds = (await fpt.boundingBox())!;
      expect(bounds.height).toBeGreaterThanOrEqual(44);
      expect(bounds.width).toBeGreaterThanOrEqual(44);
      expect((await page.locator('li.wizard-asset').filter({has: fpt}).boundingBox())!.height).toBeLessThan(100);
    } else {
      await expect(page.getByRole('combobox', {name: 'Loại tài sản'})).toBeVisible();
    }
    await expect(next).toBeInViewport();
    await expect(toggle('VFF', true)).toBeInViewport();
    await expect(toggle('FPT', true)).toBeInViewport();
  }
  const expand = page.getByRole('button', { name: /^Xem tất cả \d+ mã$/ });
  const rows = page.locator('.wizard-asset:visible');
  const catalogSize = (await (await page.request.get('/api/v1/assets/catalog')).json()).assets.length;
  await expect(rows).toHaveCount(catalogSize);
  const left = page.locator('.wizard-candidates');
  const right = page.locator('.wizard-basket-summary');
  await expect(left.locator('.wizard-asset')).toHaveCount(catalogSize - 2);
  await expect(right.locator('.wizard-asset-id strong')).toHaveText(['VFF', 'FPT']);
  const leftBox = (await left.boundingBox())!;
  expect((await right.boundingBox())!.x).toBeGreaterThan(leftBox.x + leftBox.width);
  await left.getByRole('button', {name: 'Thêm ACB vào rổ tài sản'}).press('Enter');
  await expect(left.locator('[data-asset-id="ACB"]')).toHaveCount(0);
  await right.getByRole('button', {name: 'Bỏ ACB khỏi rổ tài sản'}).press('Enter');
  await expect(left.locator('[data-asset-id="ACB"]')).toHaveCount(1);
  // Fill both panes so their scroll behavior is exercised with real catalog rows.
  const added = await left.locator('[data-asset-id]').evaluateAll(nodes => nodes.slice(0, 12).map(node => node.getAttribute('data-asset-id')!));
  for (const symbol of added) await toggle(symbol, false).click();
  const lists = page.locator('.wizard-asset-list');
  const [availablePane, selectedPane] = await lists.evaluateAll(nodes => nodes.map(node => node.getBoundingClientRect().toJSON()));
  expect(selectedPane.top).toBe(availablePane.top);
  expect(selectedPane.height).toBe(availablePane.height);
  await right.locator('li').filter({has: toggle('VFF', true)}).locator('summary').click();
  const expandedRow = right.locator('li').first();
  const description = (await expandedRow.locator('details p').boundingBox())!;
  expect((await right.locator('li').nth(1).boundingBox())!.y).toBeGreaterThan(description.y + description.height);
  const compact = (await left.locator('li').first().boundingBox())!;
  expect(compact.height).toBeLessThan(90);
  for (const index of [0, 1]) {
    await lists.evaluateAll(nodes => nodes.forEach(n => { n.scrollTop = 0; }));
    await lists.nth(index).evaluate(n => { n.scrollTop = 100; });
    expect(await lists.nth(index).evaluate(n => n.scrollTop)).toBeGreaterThan(0);
    expect(await lists.nth(1 - index).evaluate(n => n.scrollTop)).toBe(0);
  }
  for (const symbol of added) await toggle(symbol, true).click();
  await expect(expand).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(rows).toHaveCount(2);
  await expand.click();
  await expect(rows).toHaveCount(catalogSize);
  await capture(page, 'basket-expanded', 390);
  await toggle('ACB', false).click();
  await page.getByRole('button', { name: 'Thu gọn' }).click();
  await expect(toggle('ACB', true)).toBeVisible();
  await toggle('ACB', true).click();
  await next.click();
  await expect(page.locator('.wizard-progress-label')).toHaveText('Bước 3/4 · Rủi ro');
  await back.click();
  await expect(toggle('FPT', true)).toHaveAttribute('aria-pressed', 'true');

  const inventory = await page.request.get('/api/v1/portfolios?limit=1&offset=0');
  expect(inventory.ok()).toBe(true);
  const [owned] = await inventory.json();
  const portfolio = owned ?? {
    id: '10000000-0000-4000-8000-000000000003', name: 'Tích lũy dài hạn', version: 1, capital_vnd: '100000000',
    risk_profile: { profile: 'balanced', answers: { questionnaire_version: 'risk-v2', horizon_months: 36, loss_tolerance: 'medium', liquidity_need: 'low', reserve_months: 'at_least_6' } },
    constraints: { max_position_weight: .5, min_defensive_weight: .15, max_non_defensive_weight: .7, defensive_asset_ids: ['VFF'] },
  };
  if (!owned) {
    const path = '**/api/v1/portfolios/' + portfolio.id;
    await page.route(path + '/dashboard', route => route.fulfill({ json: { portfolio, accepted_target: null, proposal_count: 0, target_matches_portfolio: true } }));
    await page.route(path + '/readiness', route => route.fulfill({ json: { can_submit: false, reason_code: 'SYSTEM_PAUSED', strategies: [] } }));
    await page.route(path + '/risk-assessments?*', route => route.fulfill({ json: [], headers: { 'x-total-count': '0', 'x-offset': '0', 'x-limit': '10' } }));
  }
  await page.goto('/#settings?portfolio=' + portfolio.id);
  const settings = page.locator('.investor-settings');
  await expect(settings.getByRole('heading', { name: 'Thông tin tài khoản' })).toBeVisible();
  for (const width of widths) await capture(page, 'settings', width);
  await settings.getByRole('link', { name: 'Hồ sơ rủi ro' }).click();
  const profile = page.locator('.investor-profile');
  await expect(profile.locator('.investor-context')).toHaveText(portfolio.name);
  for (const width of widths) await capture(page, owned ? 'profile' : 'profile-fixture', width);
  await profile.getByText('Câu trả lời và giới hạn phân bổ').click();
  await expect(profile.getByRole('heading', { name: 'Giới hạn theo hồ sơ' })).toBeVisible();
  await profile.getByRole('link', { name: 'Đánh giá lại hồ sơ' }).click();
  await expect(page.getByTestId('risk-reassessment')).toBeVisible();
  await page.getByRole('link', { name: 'Về hồ sơ rủi ro', exact: true }).click();
  await expect(profile).toBeVisible();

  await page.goto('/#asset-prices?portfolio=' + portfolio.id + '&asset=FPT');
  const slider = page.getByRole('slider', { name: 'Dò giá theo ngày quan sát' });
  await expect(slider).toBeVisible();
  await page.mouse.move(1, 1);
  await page.getByRole('heading', { name: 'FPT · Lịch sử giá' }).focus();
  for (const width of [1440, 390]) await capture(page, 'price', width);
  await expect(page.getByRole('link', { name: 'Trở lại phân bổ' })).toHaveAttribute('href', '#overview?portfolio=' + portfolio.id);

  // The deployed catalog enables custom selection. Exercise its separate, read-only preset branch in this browser.
  await page.route('**/api/v1/assets/catalog', route => route.fulfill({ json: { catalog_version: 'browser-fixture', selection_enabled: false, assets: [] } }));
  await page.route('**/api/v1/universes', route => route.fulfill({ json: [{ universe_id: 'DEMO', asset_ids: ['FPT', 'VFF', 'GOLD'], as_of_date: '2026-11-17', demo: true }] }));
  await page.goto('/#create');
  await page.reload();
  await expect(page.getByRole('combobox', { name: /Bộ tài sản/ })).toBeEnabled();
  await page.getByLabel('Tên danh mục').fill('Kế hoạch có bộ tài sản sẵn');
  await expect(page.locator('.wizard-progress-label')).toHaveText('Bước 1/3 · Mục tiêu');
  await capture(page, 'plan-preset-fixture', 390);
  await next.click();
  await expect(page.locator('.wizard-progress-label')).toHaveText('Bước 2/3 · Rủi ro');
  await expect(search).toHaveCount(0);
});
