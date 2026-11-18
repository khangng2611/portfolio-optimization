import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AllocationView } from '../src/components/allocation-view';
import { ReadinessNotice } from '../src/components/portfolio-lifecycle';
import { readinessAllows } from '../src/lib/workspace-state';
import type { SelectionReadiness } from '../src/lib/selection-types';
it('preserves saved candidates and selection proof while hiding inactive zero rows', () => {
  const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['FPT', 'MWG', 'VFF'], weights: [0, .5, .5], capital_vnd: '100', strategy: 'BL_ML', selection_context: { revision_id: 'old-revision', candidate_asset_ids: ['FPT', 'MWG', 'VFF'], candidate_hash: 'old-hash', selection_policy_id: 'user-k5-v1', risk_policy_id: 'custom-mixed-risk-v1', valid_until: '2026-11-14T00:00:00Z', regime: { regime: 'normal' } }, selection_proof: { candidate_hash: 'old-hash', active_asset_ids: ['MWG', 'VFF'], selected_equity_ids: ['MWG'], rejected_equity_ids: ['FPT'], selection_hash: 'selection-hash', applied_selection: 'equity-k5-v1', decision_session: '2026-11-12', selection_price_end_date: '2026-11-11' } }}/>);
  expect(html).toContain('old-revision');
  expect(html).toContain('FPT · MWG · VFF');
  expect(html).toContain('K5 thực tế');
  expect(html).not.toContain('Không thuộc tập tính toán · 0%');
  expect(html.split('<tbody>')[1].split('</tbody>')[0]).not.toContain('FPT');
  expect(html).toContain('2 tài sản trong tập tính toán; 2 tài sản có tỷ trọng dương');
});
it('keeps stale custom NAV blocked even with explicit fallback', () => {
  const readiness: SelectionReadiness = { readiness_kind: 'user-selection-v1', candidate_asset_ids: ['GOLD', 'VFF'], can_submit: false, reason_code: 'VFF_STALE', strategies: [{ strategy: 'BL_ML', can_submit: false, reason_code: 'VFF_STALE' }, { strategy: 'EW', can_submit: false, reason_code: 'VFF_STALE' }], asset_status: [{ asset_id: 'VFF', observation_date: '2026-11-03', age_days: 8 }], selection_valid_until: '2099-01-01T00:00:00Z' };
  expect(readinessAllows(readiness, 'BL_ML', true)).toBe(false);
  const html = renderToStaticMarkup(<ReadinessNotice value={readiness} onRefresh={() => {}}/>);
  expect(html.split('<details')[0]).toContain('NAV VFF đủ điều kiện đã quá 7 ngày');
  expect(html).toContain('2026-11-03');
  expect(html).toContain('tuổi 8 ngày / tối đa 7 ngày');
});

it('groups a large ready selection into a summary and collapsed asset details', () => {
  const ids = Array.from({ length: 32 }, (_, index) => `ASSET${index}`);
  const readiness: SelectionReadiness = { readiness_kind: 'user-selection-v1', candidate_asset_ids: ids, can_submit: true, reason_code: 'READY', strategies: [{ strategy: 'MVO', can_submit: true, reason_code: 'READY' }], asset_status: ids.map(asset_id => ({ asset_id, eligible_observation_date: '2026-11-17', age_days: 1 })) };
  const html = renderToStaticMarkup(<ReadinessNotice value={readiness} onRefresh={() => {}} busy/>);
  expect(html).toContain('class="readiness-summary"');
  expect(html).toContain('32 tài sản được cân nhắc');
  expect(html).toMatch(/<details class="readiness-detail"(?![^>]*open)[^>]*>/);
  expect(html).toContain('<caption class="sr-only">Dữ liệu từng tài sản</caption>');
  expect(html.match(/scope="row"/g)).toHaveLength(32);
  expect(html).toContain('2026-11-17');
  expect(html).toContain('Đang kiểm tra dữ liệu');
  expect(html).toContain('aria-busy="true"');
});
