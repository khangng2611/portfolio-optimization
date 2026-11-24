import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RecommendationEvidenceView } from '../src/components/recommendation-evidence';
import type { RecommendationEvidence } from '../src/lib/chat-types';
import type { Recommendation } from '../src/lib/portfolio-types';

const facts: Recommendation = { id: 'rec', portfolio_id: 'p', portfolio_version: 1, run_id: 'run', asset_ids: ['ACB', 'VFF'], weights: ['0', '1'], strategy: 'BL_ML', capital_vnd: '100000000' };
const evidence: RecommendationEvidence = { schema_version: 'recommendation-evidence-v1', recommendation_id: 'rec', run_id: 'run', facts_hash: 'a'.repeat(64), evidence_hash: 'b'.repeat(64), status: 'PARTIAL', quant: null, limitations: ['NOT_RETAINED'] };

it('renders four evidence groups and honest legacy gaps', () => {
  const html = renderToStaticMarkup(<RecommendationEvidenceView evidence={evidence} facts={facts} factsHash={'a'.repeat(64)}/>);
  for (const title of ['Tín hiệu mô hình', 'Bối cảnh và rủi ro của rổ', 'Vai trò các tài sản', 'Liên hệ hồ sơ của bạn']) expect(html).toContain(title);
  expect(html).toContain('chưa lưu');
  expect(html).not.toContain('xác suất tăng');
});

it('withholds evidence for a different resource or canonical hash', () => {
  for (const changes of [{ recommendation_id: 'other' }, { facts_hash: 'c'.repeat(64) }, { run_id: 'other' }]) {
    const html = renderToStaticMarkup(<RecommendationEvidenceView evidence={{...evidence, ...changes}} facts={facts} factsHash={'a'.repeat(64)}/>);
    expect(html).toContain('chưa khớp');
    expect(html).not.toContain('Tín hiệu mô hình');
  }
});

it('labels raw five-session forecasts separately from daily applied Q', () => {
  const quant = { asset_ids: ['ACB', 'VFF'], active_asset_ids: ['ACB', 'VFF'], history_end_date: '2026-11-17', views: [{ source_kind: 'ML', status: 'APPLIED', coefficients: { ACB: 1 }, raw_mean_return: -.02, applied_q_daily: -.0002, confidence_applied: .4, horizon_sessions: 5, transform_version: 'phase1-option-b-v1' }], features: { ACB: [{ name: 'rsi_14', value: 55, unit: 'index' }] }, regime: null };
  const html = renderToStaticMarkup(<RecommendationEvidenceView evidence={{ ...evidence, status: 'COMPLETE', quant } as RecommendationEvidence} facts={facts} factsHash={'a'.repeat(64)}/>);
  expect(html).toContain('Hướng giảm');
  expect(html).toContain('5 phiên');
  expect(html).toContain('Q áp dụng');
  expect(html).toContain('0,400');
  expect(html).toContain('RSI14');
  expect(html).not.toContain('40%');
  expect(html).not.toContain('/accept');
});

it('uses retained regime from the old canonical result without recomputing raw views', () => {
  const old = { ...facts, selection_context: { candidate_asset_ids: ['ACB', 'VFF'], regime: { regime: 'stress', vol_ratio: 1.5, drawdown: -.12, equity_momentum: -.001 } } } as Recommendation;
  const html = renderToStaticMarkup(<RecommendationEvidenceView evidence={evidence} facts={old} factsHash={'a'.repeat(64)}/>);
  expect(html).toContain('căng thẳng');
  expect(html).toContain('1,500');
  expect(html).toContain('chưa lưu dự báo từ mô hình');
});

it('keeps user views distinct from the defensive VFF policy', () => {
  const quant = { asset_ids: ['ACB', 'VFF'], active_asset_ids: ['ACB', 'VFF'], history_end_date: '2026-11-17', views: [{ source_kind: 'USER', status: 'APPLIED', coefficients: { ACB: 1 }, raw_mean_return: null, applied_q_daily: .001, confidence_applied: .4, horizon_sessions: null, transform_version: 'phase1-option-b-v1' }], features: {}, regime: null };
  const html = renderToStaticMarkup(<RecommendationEvidenceView evidence={{ ...evidence, quant } as RecommendationEvidence} facts={facts} factsHash={'a'.repeat(64)}/>);
  expect(html).toContain('người dùng');
  expect(html).not.toContain('Tín hiệu phòng thủ');
});
