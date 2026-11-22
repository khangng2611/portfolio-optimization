import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ProposalRequest } from '../src/components/portfolio-workspace';
import { ReadinessNotice } from '../src/components/portfolio-lifecycle';
import { readinessAllows, type Readiness } from '../src/lib/workspace-state';

it('explains stale eligible VFF NAV and blocks EW fallback', () => {
  const state: Readiness = { universe_id: 'VN_PHASE1_FULL', asset_ids: ['GOLD', 'VFF'], as_of_date: '2026-11-11', valid_until: null, demo: false, data_origin: 'real', status: 'UNAVAILABLE', reason_code: 'VFF_STALE', strategies: [{ strategy: 'BL_ML', available: false, reason_code: 'VFF_STALE' }, { strategy: 'EW', available: true, reason_code: 'READY' }], next_action: 'REFRESH_DATA', checked_at: '2026-11-11T12:00:00Z' };
  const html = renderToStaticMarkup(<ReadinessNotice value={state} onRefresh={() => {}}/>);
  expect(html).toContain('NAV VFF đủ điều kiện đã quá 7 ngày');
  expect(readinessAllows(state, 'BL_ML', true)).toBe(false);
});

it('does not offer legacy allocation methods on the system proposal screen', () => {
  const state: Readiness = { universe_id: 'VN_PHASE1_FULL', asset_ids: ['A', 'GOLD', 'VFF'], as_of_date: '2026-11-11', valid_until: '2026-11-12T00:00:00Z', demo: false, data_origin: 'real', status: 'READY', reason_code: 'READY', strategies: [{ strategy: 'BL_ML', available: true, reason_code: 'READY' }], next_action: 'NONE', checked_at: '2026-11-11T12:00:00Z', provenance: { phase1_full: { active_asset_ids: ['A', 'GOLD', 'VFF'], selected_equity_ids: ['A'], selection_id: 'hash', selection_epoch: '2026-11-01', fit_epoch: '2026-11-02', regime: { regime: 'crisis' } } } };
  const html = renderToStaticMarkup(<ProposalRequest portfolio={{ id: 'id', name: 'Full', capital_vnd: '1000000', universe_id: 'VN_PHASE1_FULL', version: 1, policy_version_id: 'risk-v1', risk_profile: { profile: 'balanced' }, constraints: { risk_aversion: 3, max_position_weight: .5, min_defensive_weight: .15, max_non_defensive_weight: .7 } }} readiness={state} busy={false} onSubmit={() => {}}/>);
  expect(html).toContain('Cân bằng');
  expect(html).toMatch(/data-testid="propose-portfolio" disabled=""/);
  expect(html).not.toContain('type="radio"');
  expect(html).not.toContain('type="checkbox"');
});
