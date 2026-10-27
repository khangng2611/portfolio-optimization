import { expect, it } from 'vitest';
import { marketCutoffDate } from '../src/lib/market-types';
it('keeps default snapshot cutoff valid during the Vietnam/UTC midnight boundary', () => {
  expect(marketCutoffDate(new Date('2026-10-28T00:30:00+07:00'))).toBe('2026-10-27');
  expect(marketCutoffDate(new Date('2026-10-28T07:00:00+07:00'))).toBe('2026-10-28');
});
