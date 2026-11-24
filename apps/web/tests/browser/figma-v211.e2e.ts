import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

// A browser-only fixture for comparing the same data at the four Figma sizes.
test('saved capital and proposed capital stay pinned across a price round trip', async ({ page }) => {
  const portfolioId = '10000000-0000-4000-8000-000000000001';
  const savedId = '20000000-0000-4000-8000-000000000001';
  const nextId = '20000000-0000-4000-8000-000000000002';
  const until = new Date(Date.now() + 86400000).toISOString();
  const portfolio = { id: portfolioId, version: 2, universe_id: 'USER_SELECTED', name: 'Tích lũy dài hạn',
    capital_vnd: '120000000', risk_profile: { profile: 'balanced', answers: { horizon_months: 36 } } };
  const saved = { asset_ids: ['VFF', 'FPT', 'GOLD'], weights: [.5, .35, .15], capital_vnd: '100000000', as_of_date: '2026-11-17', strategy: 'MVO' };
  const next = { ...saved, id: nextId, portfolio_id: portfolioId, portfolio_version: 2, capital_vnd: '120000000', valid_until: until };
  const assets = ['fund', 'stock', 'gold'].map((kind, i) => ({ asset_id: saved.asset_ids[i], kind, display_name: saved.asset_ids[i], data_status: i === 1 ? 'FRESH' : 'MISSING' }));
  const target = { id: 'saved-target', recommendation_id: savedId, allocation: saved, accepted_at: '2026-11-18', portfolio_version: 1 };
  let pending = false;
  const dir = resolve('../../output/playwright/v211');
  await mkdir(dir, { recursive: true });
  await page.route('**/auth/session', route => route.fulfill({ json: { user: { sub: 'visual-fixture', name: 'Nhà đầu tư', roles: [] }, csrfToken: 'fixture' } }));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    expect(route.request().method()).toBe('GET');
    const responses: Record<string, unknown> = {
      '/api/v1/assets/catalog': { assets, selection_enabled: true }, '/api/v1/market/assets': [], '/api/v1/universes': [],
      [`/api/v1/portfolios/${portfolioId}/dashboard`]: { portfolio, accepted_target: target, target_matches_portfolio: false, proposal_count: pending ? 2 : 1 },
      [`/api/v1/portfolios/${portfolioId}/recommendations`]: pending ? [next] : [{ ...saved, id: savedId, portfolio_id: portfolioId }],
      [`/api/v1/portfolios/${portfolioId}/readiness`]: { readiness_kind: 'user-selection-v1', can_submit: true, reason_code: 'READY', strategies: [{ strategy: 'HYBRID', can_submit: true }], candidate_asset_ids: saved.asset_ids, selection_valid_until: until },
      [`/api/v1/recommendations/${nextId}`]: next,
      '/api/v1/market/price-series': { asset_id: 'FPT', as_of: '2026-11-18', series: [] },
    };
    expect(responses).toHaveProperty(path);
    await route.fulfill({ json: responses[path] });
  });
  await page.goto('/#overview?portfolio=' + portfolioId);
  const fpt = page.locator('.result-assets tr').filter({ has: page.getByRole('link', { name: 'Xem giá FPT' }) });
  await expect(fpt).toContainText('35.000.000');
  for (const width of [375, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: width > 390 ? 1000 : 844 });
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator('.mix-legend li')).toHaveCount(3);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: resolve(dir, `overview-${width}.png`) });
  }
  await fpt.getByRole('link').press('Enter');
  await expect(page.getByRole('heading', { name: 'FPT · Lịch sử giá' })).toBeVisible();
  await expect(page.getByText('Chưa có dữ liệu giá trong khoảng đã chọn.')).toBeVisible();
  await page.getByRole('link', { name: 'Trở lại phân bổ' }).click();
  await expect(fpt).toContainText('35.000.000');
  await expect(page.locator('.plan-result-actions .plan-chat')).toHaveAttribute('href', new RegExp(savedId));
  pending = true;
  await page.reload();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('.plan-status a').click();
  await expect(fpt).toContainText('42.000.000');
  await expect(page.getByTestId('accept-proposal')).toBeEnabled();
  await page.screenshot({ path: resolve(dir, 'new-proposal-390.png') });
  const amountCell = (await fpt.locator('td').last().boundingBox())!;
  await page.mouse.click(amountCell.x + amountCell.width / 2, amountCell.y + amountCell.height / 2);
  await page.getByRole('link', { name: 'Trở lại phân bổ' }).click();
  await expect(fpt).toContainText('42.000.000');
});
