import { test, expect } from '@playwright/test';

const fixture = 'http://127.0.0.1:32159';
const money = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 });
const chartValue = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 6 });

test('explicit paper decisions, fills, sale proceeds, settlement and scheduled review share the NAV ledger', async ({ page, request }) => {
  const scenario = await (await request.get(fixture + '/scenario')).json();
  const portfolioId = scenario.portfolio;
  const base = `/api/v1/portfolios/${portfolioId}/paper`;
  const headers = { authorization: 'Bearer alice' };
  const readAccount = async () => (await request.get(fixture + base, { headers })).json();
  await page.clock.setFixedTime(new Date(scenario.now));
  async function advance(i: number) {
    const result = await request.post(fixture + '/scenario/session/' + i);
    expect(result.ok()).toBe(true);
    await page.clock.setFixedTime(new Date((await result.json()).now));
  }

  // Identity and unrelated services are fixtures. Paper requests use the actual HTTP handlers and DB.
  await page.route('**/auth/session', route => route.fulfill({ json: { user: { sub: 'alice', name: 'Mô phỏng', roles: ['investor'] }, csrfToken: 'fixture' } }));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith(base) || path.endsWith('/dashboard')) {
      const response = await route.fetch({ url: fixture + path, headers: { ...headers, 'content-type': 'application/json' } });
      await route.fulfill({ response });
      return;
    }
    await route.fulfill({ json: path.endsWith('/catalog') ? { assets: [] } : path.endsWith('/readiness') ? { status: 'READY', strategies: [] } : [] });
  });

  const open = (view: string) => page.goto(`/#${view}?portfolio=${portfolioId}`);
  const preview = page.getByRole('button', { name: 'Xem trước lệnh mô phỏng' });
  const confirm = page.getByRole('button', { name: 'Xác nhận gửi lệnh mô phỏng' });
  const book = page.getByRole('region', { name: 'Sổ lệnh mô phỏng' });
  async function checkNav() {
    await open('holdings');
    await Promise.all([page.waitForResponse(r => new URL(r.url()).pathname === base), page.getByRole('button', { name: 'Cập nhật số liệu' }).click()]);
    const state = await readAccount();
    const v = state.valuation;
    let expected = v.available_cash_vnd + v.reserved_cash_vnd + v.receivable_vnd;
    for (const position of state.positions) expected += position.value_vnd;
    expect(v.nav_vnd).toBeCloseTo(expected, 5);
    expect(v.pnl_vnd).toBeCloseTo(expected - 10_000_000, 5);
    const facts = page.locator('.paper-facts');
    await expect(facts.getByText('Lời/lỗ ròng').locator('..')).toContainText(money.format(v.pnl_vnd));
    await expect(facts.getByText('Tiền bán chờ về').locator('..')).toContainText(money.format(v.receivable_vnd));
    await expect(facts.getByText('Phí và thuế đã trả').locator('..')).toContainText(money.format(v.fees_vnd));
    await expect(page.locator('.price-chart-quote strong')).toContainText(chartValue.format(state.history.at(-1).nav_vnd));
    expect(state.history.at(-1).nav_vnd).toBeCloseTo(expected, 5);
    return state;
  }

  await open('holdings');
  await page.getByLabel('Vốn mô phỏng ban đầu (VND)').fill('10000000');
  await expect(page.getByRole('figure')).toHaveCount(0);
  await page.getByRole('button', { name: 'Khởi tạo bằng tiền mặt' }).click();
  await expect(page.getByRole('heading', { name: 'Giá trị tài khoản' })).toBeVisible();
  await open('rebalance');
  await preview.click();
  await page.getByRole('button', { name: 'Bỏ qua bản xem trước' }).click();
  await expect(page.getByText('Đã bỏ qua bản xem trước.')).toBeVisible();
  expect((await readAccount()).orders).toHaveLength(0);
  await preview.click();
  await confirm.click();
  await expect(book).toContainText('Chờ khớp');
  await page.reload();
  await expect(book).toContainText('Chờ khớp');
  expect((await checkNav()).valuation.pnl_vnd).toBe(0);
  await advance(3);
  const bought = await checkNav();
  expect(bought.orders[0].status).toBe('FILLED');
  expect(bought.valuation.fees_vnd).toBeGreaterThan(0);

  expect((await request.post(fixture + '/scenario/second-target')).ok()).toBe(true);
  await open('rebalance');
  await preview.click();
  await expect(page.getByRole('region', { name: 'Chi tiết lệnh dự kiến' })).toContainText('Bán');
  await confirm.click();
  await expect(book).toContainText('Chờ khớp');
  await advance(4);
  const sold = await checkNav();
  expect(sold.valuation.receivable_vnd).toBeGreaterThan(0);
  expect(sold.valuation.fees_vnd).toBeGreaterThan(bought.valuation.fees_vnd);
  await advance(6);
  const settled = await checkNav();
  expect(settled.valuation.receivable_vnd).toBe(0);
  expect(settled.valuation.available_cash_vnd).toBeCloseTo(sold.valuation.available_cash_vnd + sold.valuation.receivable_vnd, 4);
  expect(settled.orders.some((o: { status: string }) => o.status === 'SETTLED')).toBe(true);
  await open('overview');
  await page.getByRole('link', { name: 'Xem xét tái cân bằng', exact: true }).click();
  await page.getByRole('button', { name: /Bỏ qua kỳ/ }).click();
  await expect(page.getByText('Đã bỏ qua kỳ xem xét.')).toBeVisible();
  const final = await readAccount();
  expect(final.orders).toHaveLength(settled.orders.length);
  expect(final.reviews[0].status).toBe('SKIPPED');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
