import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { PaperHoldings } from '../src/components/paper-portfolio';

it('shows NAV and net return from the same ledger row, including reserved and unsettled cash', () => {
  const valuation = { date: '2026-11-24', nav_vnd: 10040000, pnl_vnd: 40000, return_fraction: .004,
    available_cash_vnd: 150000, reserved_cash_vnd: 50000, receivable_vnd: 250000, fees_vnd: 5000, spread_vnd: 0 };
  const account = { initialized: true, target_id: 'target', initial_capital_vnd: 10000000, quote_status: 'FRESH' as const,
    quote_as_of: null, quote_source: null, decisions: [], quote_date: valuation.date, valuation, history: [{ date: '2026-11-23', nav_vnd: 10000000 }, valuation], positions: [], orders: [], reviews: [] };
  const html = renderToStaticMarkup(<PaperHoldings account={account}/>);
  expect(html).toContain('10.040.000');
  expect(html).toContain('40.000');
  expect(html).toContain('0,4%');
  expect(html).toContain('Tiền bán chờ về</dt><dd>250.000');
  expect(html).toContain('Tiền dành mua</dt><dd>50.000');
  expect(html).toContain('Phí và thuế đã trả</dt><dd>5.000');
  expect(html).toContain('aria-label="Dò tổng tài sản theo phiên"');
  expect(html).not.toContain('NaN');
  expect(renderToStaticMarkup(<PaperHoldings account={{ ...account, initialized: false, history: [], valuation: null }}/>)).toBe('');
});
