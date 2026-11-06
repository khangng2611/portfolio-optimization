import { expect, it } from 'vitest';
import { workspaceHash, parseWorkspaceHash, readinessAllows, comparisonDifferences, proposalCompletionRoute } from '../src/lib/workspace-state';

const pid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const rid = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
it('restores the same portfolio and proposal from an encoded deep link', () => {
  const route = { view: 'proposal' as const, portfolioId: pid, proposalId: rid };
  expect(parseWorkspaceHash(workspaceHash(route))).toEqual(route);
  expect(parseWorkspaceHash('#history?portfolio=' + pid)).toEqual({ view: 'history', portfolioId: pid });
  expect(parseWorkspaceHash('#proposal?portfolio=foreign&proposal=' + rid).invalid).toBe(true);
  expect(parseWorkspaceHash('#compare?portfolio=' + pid + '&a=' + rid + '&b=' + rid).invalid).toBe(true);
});
it('permits explicit EW fallback only for missing models with usable EW inputs', () => {
  const readiness = { status: 'READY', strategies: [
    { strategy: 'MVO', available: true, reason_code: 'READY' },
    { strategy: 'EW', available: true, reason_code: 'READY' },
    { strategy: 'BL_ML', available: false, reason_code: 'MODEL_UNAVAILABLE' },
  ] };
  expect(readinessAllows(readiness, 'MVO', false)).toBe(true);
  expect(readinessAllows(readiness, 'BL_ML', false)).toBe(false);
  expect(readinessAllows(readiness, 'BL_ML', true)).toBe(true);
  expect(readinessAllows({ ...readiness, status: 'EXPIRED' }, 'BL_ML', true)).toBe(false);
  expect(readinessAllows({ ...readiness, strategies: readiness.strategies.map(s => s.strategy === 'BL_ML' ? { ...s, reason_code: 'MODEL_INVALID' } : s) }, 'BL_ML', true)).toBe(false);
  expect(readinessAllows(null, 'MVO', false)).toBe(false);
});
it('identifies differing comparison inputs instead of implying matched performance', () => {
  const a = { data_snapshot_id: 'one', policy_version_id: 'v1', portfolio_version: 1, capital_vnd: '100', core_version: '0.1', as_of_date: '2026-10-23', model_bundle_id: null };
  expect(comparisonDifferences(a, a)).toEqual([]);
  expect(comparisonDifferences(a, { ...a, data_snapshot_id: 'two', capital_vnd: '200' })).toEqual(['Snapshot dữ liệu', 'Vốn kế hoạch']);
  expect(comparisonDifferences({ ...a, bundle_hash: 'one' }, { ...a, bundle_hash: 'two' })).toEqual(['Bộ input']);
});
it('keeps an editor draft in place when a background proposal finishes', () => {
  expect(proposalCompletionRoute({ view: 'edit', portfolioId: pid }, pid, rid)).toBeNull();
  expect(proposalCompletionRoute({ view: 'proposal', portfolioId: pid, proposalId: rid }, pid, pid)).toBeNull();
  expect(proposalCompletionRoute({ view: 'proposal', portfolioId: pid }, pid, rid)).toEqual({ view: 'proposal', portfolioId: pid, proposalId: rid });
});
it('roundtrips operator report and immutable snapshot destinations after login or reload', () => {
  const jobId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  const snapshotId = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  expect(parseWorkspaceHash(workspaceHash({ view: 'market-publications', jobId, snapshotId }))).toEqual({ view: 'market-publications', jobId, snapshotId });
  expect(parseWorkspaceHash('#market-quality?job=' + jobId)).toEqual({ view: 'market-quality', jobId });
  expect(parseWorkspaceHash('#market-quality?job=bad').invalid).toBe(true);
  expect(parseWorkspaceHash('#market-quality?job=' + jobId + '&job=' + snapshotId).invalid).toBe(true);
});
