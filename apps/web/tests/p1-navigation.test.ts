import { expect, it } from 'vitest';
import { modelServingReady, parseWorkspaceHash, workspaceHash } from '../src/lib/workspace-state';
const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
it('retains P1 destinations through login and reload', () => {
  for (const route of [{ view: 'models' as const }, { view: 'model-review' as const, modelId: id }, { view: 'model-training' as const, snapshotId: id }, { view: 'market-refresh' as const, jobId: id }, { view: 'risk-assessment' as const, portfolioId: id }]) {
    expect(parseWorkspaceHash(workspaceHash(route))).toEqual(route);
  }
  expect(parseWorkspaceHash('#model-review?model=bad').invalid).toBe(true);
  expect(parseWorkspaceHash('#model-review?model=' + id + '&model=' + id).invalid).toBe(true);
});
it('stops advertising the selected model at input expiry without another API response', () => {
  const row = { status: 'READY', valid_until: '2026-10-27T16:00:00Z', strategies: [{ strategy: 'BL_ML', available: true, reason_code: 'READY' }] };
  expect(modelServingReady(row, Date.parse('2026-10-27T15:59:59Z'))).toBe(true);
  expect(modelServingReady(row, Date.parse(row.valid_until))).toBe(false);
  expect(modelServingReady({ ...row, valid_until: null }, 0)).toBe(false);
  expect(modelServingReady({ ...row, strategies: [{ strategy: 'BL_ML', available: false, reason_code: 'MODEL_INVALID' }] }, 0)).toBe(false);
});
