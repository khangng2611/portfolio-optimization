import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { PriceChart, type PriceObservation } from '../src/components/price-chart';

const row = (date: string, price_vnd: string): PriceObservation => ({
  date, price_vnd, revision: 1, revision_id: date, available_at: date + 'T18:00:00Z',
});

it('keeps a single observation readable without inventing a move or an interactive range', () => {
  const html = renderToStaticMarkup(<PriceChart periodDays={90} observations={[row('2026-11-17', '12543.2')]}/>);
  expect(html).toContain('12.543,2');
  expect(html).toContain('17/11/2026');
  expect(html).not.toMatch(/role="slider"|Biến động trong khoảng|NaN|Infinity/);
});

it('draws a finite price scale and reports zero change for a flat series', () => {
  const html = renderToStaticMarkup(<PriceChart periodDays={90} observations={[row('2026-11-16', '48000'), row('2026-11-17', '48000')]}/>);
  expect(html).toContain('0,00%');
  expect(html).toContain('aria-valuenow="2"');
  expect(html).toContain('price-chart-line');
  expect(html).not.toMatch(/NaN|Infinity/);
});
