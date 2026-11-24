import { useEffect, useState } from 'react';
import { RiskReason } from './risk-questions';
import type { RecommendationEvidence } from '../lib/chat-types';
import type { Api, Recommendation } from '../lib/portfolio-types';
import { percentage, profileName } from './allocation-view';

const number = (value: number) => value.toLocaleString('vi-VN', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const featureNames: Record<string, string> = { momentum_5: 'Lợi suất 5 phiên đã qua', momentum_10: 'Lợi suất 10 phiên đã qua', momentum_20: 'Lợi suất 20 phiên đã qua', rsi_14: 'RSI14', ma_ratio_10_30: 'Tỷ lệ EMA10/30 trừ 1', volatility_20: 'Biến động lợi suất ngày 20 phiên', macd_hist: 'MACD histogram (nghìn VND)', price_std_20: 'Độ lệch chuẩn giá / giá trung bình 20 phiên' };

export function RecommendationEvidenceView({ evidence, facts, factsHash }: { evidence: RecommendationEvidence; facts: Recommendation; factsHash?: string }) {
  if (evidence.recommendation_id !== facts.id || evidence.run_id !== facts.run_id || (factsHash !== undefined && evidence.facts_hash !== factsHash) || (evidence.quant && (evidence.quant.asset_ids.length !== facts.asset_ids.length || evidence.quant.asset_ids.some((a, i) => a !== facts.asset_ids[i])))) return <p role="alert" className="notice warning">Dữ liệu giải thích chưa khớp với đề xuất. Hãy thử tải lại dữ kiện.</p>;
  const quant = evidence.quant, legacy = facts.selection_context?.regime;
  const regime = quant?.regime ?? (legacy && typeof legacy.vol_ratio === 'number' && typeof legacy.drawdown === 'number' && typeof legacy.equity_momentum === 'number' && ['normal', 'stress', 'crisis'].includes(legacy.regime) ? { regime: legacy.regime as 'normal' | 'stress' | 'crisis', asset_ids: facts.selection_context!.candidate_asset_ids, vol_ratio: legacy.vol_ratio, drawdown: legacy.drawdown, equity_momentum: legacy.equity_momentum } : null);
  const active = quant?.active_asset_ids ?? facts.selection_proof?.active_asset_ids;
  return <div className="recommendation-evidence" data-testid="recommendation-evidence">
    {evidence.status !== 'COMPLETE' && <p className="muted small">{evidence.status === 'PARTIAL' ? 'Đề xuất này chỉ có một phần dữ liệu giải thích.' : 'Chưa có dữ liệu giải thích cho đề xuất này.'}</p>}
    <section><h4>Liên hệ hồ sơ của bạn</h4><p>Hồ sơ tại thời điểm tính: {profileName(facts.risk_profile?.profile)}.{facts.risk_profile?.answers && <> Thời hạn {facts.risk_profile.answers.horizon_months} tháng · Mức chịu lỗ {({ low: 'thấp', medium: 'vừa', high: 'cao' })[facts.risk_profile.answers.loss_tolerance]}.</>}</p><RiskReason profile={facts.risk_profile}/></section>
    <section><h4>Tín hiệu mô hình</h4>{quant?.views.length ? <><p className="muted small">Dự báo có sai số. Hệ thống dùng điểm tin cậy của tín hiệu khi tính tỷ trọng.</p><ul className="explanation-view-list">{quant.views.map((view, index) => <li key={index}>{view.source_kind === 'ML' ? <><strong>{Object.keys(view.coefficients).join(', ')} · {Number(view.raw_mean_return) > 0 ? 'Hướng tăng' : Number(view.raw_mean_return) < 0 ? 'Hướng giảm' : 'Trung tính'}</strong><p>Dự báo {percentage(Number(view.raw_mean_return))} trong {view.horizon_sessions} phiên.</p>{view.status === 'APPLIED' ? <details><summary>Thông số tín hiệu</summary><p className="muted small">Q áp dụng {number(Number(view.applied_q_daily) * 100)}%/ngày · Điểm tin cậy {number(Number(view.confidence_applied))} (không phải xác suất tăng giá).</p></details> : <p className="muted small">Tín hiệu dưới ngưỡng sử dụng khi tính phân bổ.</p>}</> : view.source_kind === 'POLICY' ? <><strong>Tín hiệu phòng thủ</strong><p>VFF tương đối so với phần còn lại của rổ, theo trạng thái rổ tại lần tính.</p></> : <><strong>Nhận định của người dùng</strong><p>Nhận định được lưu cùng đề xuất.</p></>}</li>)}</ul></> : <p>{facts.strategy === 'EW' || facts.strategy === 'MVO' ? `Phương pháp ${facts.strategy} không dùng dự báo từ mô hình.` : 'Đề xuất này chưa lưu dự báo từ mô hình.'}</p>}</section>
    <section><h4>Bối cảnh và rủi ro của rổ</h4>{regime ? <><p>Rổ {regime.asset_ids.join(', ')} · Trạng thái {({ normal: 'bình thường', stress: 'căng thẳng', crisis: 'khủng hoảng' })[regime.regime]}.</p><dl><div><dt>Tỷ lệ biến động 20/120 phiên</dt><dd>{number(regime.vol_ratio)}</dd></div><div><dt>Mức giảm từ đỉnh 60 phiên đến ngày tính</dt><dd>{percentage(regime.drawdown)}</dd></div><div><dt>Trung bình lợi suất ngày trong cửa sổ 60 phiên</dt><dd>{percentage(regime.equity_momentum)}</dd></div></dl><p className="muted small">Chỉ mô tả rổ đã dùng tại lần tính, {quant?.regime ? <>với {Math.min(120, quant.regime.observed_sessions)} phiên quan sát trong cửa sổ dài.</> : <>Số phiên thực tế trong cửa sổ chưa được lưu đầy đủ.</>} Không dùng làm nhận định mới về VNINDEX.</p></> : <p>Đề xuất này chưa đủ dữ liệu để mô tả rủi ro của rổ.</p>}</section>
    <section><h4>Vai trò các tài sản</h4><p>{facts.selection_proof?.applied_selection === 'equity-k5-v1' ? (facts.strategy === 'HYBRID' ? 'Hệ thống chọn cổ phiếu đại diện cho nhánh dùng mô hình.' : 'Hệ thống chọn cổ phiếu đại diện theo tương quan lịch sử.') : 'Đề xuất dùng danh sách tài sản tại thời điểm tính.'}{active && <> {facts.strategy === 'HYBRID' ? 'Tài sản của nhánh dùng mô hình' : 'Tài sản được dùng khi tính'}: {active.join(', ')}.</>}</p><p className="muted small">Các chỉ số dưới đây mô tả dữ liệu đầu vào. Chúng không cho biết nguyên nhân riêng của từng tỷ trọng.</p>{quant && Object.keys(quant.features).length > 0 && <details><summary>Đặc trưng quan sát · đến {quant.history_end_date}</summary>{Object.entries(quant.features).map(([asset, features]) => <div key={asset}><h5>{asset}</h5><dl>{features.map(feature => <div key={feature.name}><dt>{featureNames[feature.name] ?? feature.name}</dt><dd>{feature.unit === 'fraction' ? percentage(feature.value) : number(feature.value)}</dd></div>)}</dl></div>)}</details>}</section>
    <p className="muted small">Dữ liệu lịch sử chưa được chứng nhận đầy đủ theo thời điểm. Giải thích giúp đọc kết quả; không bảo đảm lợi nhuận.</p>
  </div>;
}

export function SavedRecommendationEvidence({ facts, api }: { facts: Recommendation; api: Api }) {
  const [evidence, setEvidence] = useState<RecommendationEvidence | null>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    api<RecommendationEvidence>(`/api/v1/recommendations/${facts.id}/evidence`).then(value => {
      if (active) setEvidence(value);
    }).catch(() => { if (active) setEvidence(null); });
    return () => { active = false; };
  }, [facts.id, api, attempt]);
  if (evidence === undefined) return <p role="status">Đang tải dữ kiện của lần tính…</p>;
  if (!evidence) return <div role="alert"><p>Chưa tải được dữ kiện của lần tính.</p><button type="button" className="quiet" onClick={() => { setEvidence(undefined); setAttempt(attempt + 1); }}>Tải lại dữ kiện</button></div>;
  return <RecommendationEvidenceView evidence={evidence} facts={facts}/>;
}
