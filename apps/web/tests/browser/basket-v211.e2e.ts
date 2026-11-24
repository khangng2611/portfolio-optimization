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
    await expect(next).toBeInViewport();
    await expect(toggle('VFF', true)).toBeInViewport();
    await expect(toggle('FPT', true)).toBeInViewport();
  }
  await page.getByRole('button', { name: /^Xem tất cả \d+ mã$/ }).click();
  await expect(page.getByTestId('selected-assets').locator('[data-asset-id]')).toHaveCount(2);
  await page.getByRole('button', { name: 'Xem danh sách đơn' }).click();
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
