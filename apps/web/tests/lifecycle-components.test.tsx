import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ReadinessNotice, ComparisonTable } from '../src/components/portfolio-lifecycle';
it('names expired inputs and provides an explicit refresh action', () => {
  const html = renderToStaticMarkup(<ReadinessNotice value={{ universe_id: 'REAL', asset_ids: [], as_of_date: '2026-10-23', valid_until: '2026-10-24', demo: false, data_origin: 'real', status: 'EXPIRED', reason_code: 'INPUT_EXPIRED', strategies: [], next_action: 'REFRESH_DATA', checked_at: '2026-10-25' }} onRefresh={() => {}}/>);
  expect(html).toContain('Dữ liệu đã hết hiệu lực');
  expect(html).toContain('Kiểm tra lại');
  expect(html).toContain('expired-input-notice');
});
it('compares actual asset weights and warns when source pins differ', () => {
  const common = { id: 'one', portfolio_id: 'pid', portfolio_version: 1, capital_vnd: '100000000', asset_ids: ['FPT'], weights: ['1'], strategy: 'EW', data_snapshot_id: 'a' };
  const html = renderToStaticMarkup(<ComparisonTable items={[common, { ...common, id: 'two', data_snapshot_id: 'b', strategy: 'MVO' }]}/>);
  expect(html).toContain('Snapshot dữ liệu');
  expect(html).toContain('FPT');
  expect(html).toContain('100,0%');
  expect(html).toContain('không phải hiệu suất đầu tư');
});
