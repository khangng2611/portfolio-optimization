'use client';
import { useState } from 'react';
import { ActionIcon } from './action-controls';
import type { SelectionProof } from '../lib/selection-types';
import type { AllocationConstraints, Phase1Full } from '../lib/p1-types';
export type Allocation = {
  asset_ids: string[]; weights: (string | number)[]; capital_vnd: string;
  strategy: string; requested_strategy?: string; fallback_reason?: string | null;
  demo?: boolean; policy_version_id?: string; data_snapshot_id?: string;
  model_bundle_id?: string | null; bundle_hash?: string; core_version?: string; as_of_date?: string; valid_until?: string;
  selection_context?: { revision_id: string; candidate_asset_ids: string[]; candidate_hash: string; selection_policy_id: string; risk_policy_id: string; data_policy_id?: string; regime_policy_id?: string; valid_until: string; regime: { regime: string; vol_ratio?: number; drawdown?: number; equity_momentum?: number } };
  selection_proof?: SelectionProof;
  constraints?: AllocationConstraints; requested_constraints?: AllocationConstraints;
  diagnostics?: { inference?: { model_manifest_hash?: string }; hybrid?: {
    mvo_share: number; version: string; mvo_weights: number[]; ew_weights: number[];
    ew_constraint_violations: string[]; daily_volatility: { hybrid: number; mvo: number; ew: number };
    covariance_window_sessions: number;
  } };
  inputs_provenance?: { data_origin?: string; snapshot_hash?: string; estimator?: string; phase1_full?: Phase1Full };
};
export const money = (amount: number | string) => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(Number(amount));
export const profileName = (profile?: string) => !profile ? 'Chưa xác nhận' : ({ conservative: 'Thận trọng', balanced: 'Cân bằng', growth: 'Tăng trưởng' }[profile ?? ''] ?? 'Tùy chỉnh');
export const strategyName = (strategy: string) => strategy === 'HYBRID' ? 'Đề xuất của hệ thống' : strategy === 'BL_ML' ? 'BL + ML' : strategy;
export const percentage = (weight: number) => `${(weight * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

function AllocationReferences({ allocation }: { allocation: Allocation }) {
  const comparison = allocation.diagnostics?.hybrid;
  if (allocation.strategy !== 'HYBRID' || !comparison) return null;
  const label: Record<string, string> = {
    defensive_floor: 'tỷ trọng phòng thủ tối thiểu', non_defensive_cap: 'giới hạn nhóm ngoài phòng thủ',
    position_cap: 'tỷ trọng tối đa mỗi mã', budget: 'tổng tỷ trọng', long_only: 'tỷ trọng không âm',
  };
  return <details className="allocation-details" data-testid="allocation-references">
    <summary>So sánh với phương án tham chiếu</summary>
    <p>EW chia đều tỷ trọng. MVO tính từ lợi nhuận và biến động lịch sử. Cả hai dùng cùng rổ và ngày dữ liệu với đề xuất.</p>
    <div className="allocation-table-wrap"><table>
      <caption className="sr-only">So sánh tỷ trọng và biến động</caption>
      <thead><tr><th scope="col">Chỉ tiêu</th><th scope="col">Đề xuất</th><th scope="col">EW</th><th scope="col">MVO</th></tr></thead>
      <tbody>{allocation.asset_ids.map((asset, i) => <tr key={asset}><th scope="row">{asset}</th><td>{percentage(Number(allocation.weights[i]))}</td><td>{percentage(comparison.ew_weights[i])}</td><td>{percentage(comparison.mvo_weights[i])}</td></tr>)}
        <tr><th scope="row">Biến động ngày ước tính</th><td>{percentage(comparison.daily_volatility.hybrid)}</td><td>{percentage(comparison.daily_volatility.ew)}</td><td>{percentage(comparison.daily_volatility.mvo)}</td></tr>
      </tbody>
    </table></div>
    <p className="muted small">Ước tính từ {comparison.covariance_window_sessions} phiên. {comparison.ew_constraint_violations.length > 0 && <>EW không đáp ứng {comparison.ew_constraint_violations.map(code => label[code] ?? code).join(', ')}.</>}</p>
  </details>;
}

export function AllocationMetadata({ allocation }: { allocation: Allocation }) {
  return <details className="allocation-details"><summary>Nguồn và phiên bản của đề xuất</summary><dl className="provenance">
    {([['Ngày dữ liệu', allocation.as_of_date], ['Policy ID', allocation.policy_version_id], ['Snapshot ID', allocation.data_snapshot_id], ['Bundle hash', allocation.bundle_hash], ['Snapshot hash', allocation.inputs_provenance?.snapshot_hash], ['Core version', allocation.core_version], ['Model', allocation.model_bundle_id]] as const).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>)}
    {allocation.inputs_provenance?.phase1_full && <>
      <div><dt>Selection hash</dt><dd>{allocation.inputs_provenance.phase1_full.selection_id}</dd></div>
      <div><dt>Selection / fit epoch</dt><dd>{allocation.inputs_provenance.phase1_full.selection_epoch} / {allocation.inputs_provenance.phase1_full.fit_epoch}</dd></div>
    </>}
    {allocation.selection_context && <><div><dt>Candidate revision / hash</dt><dd>{allocation.selection_context.revision_id} · {allocation.selection_context.candidate_hash}</dd></div><div><dt>Selection / data / risk policy</dt><dd>{allocation.selection_context.selection_policy_id} · {allocation.selection_context.data_policy_id} · {allocation.selection_context.risk_policy_id}</dd></div><div><dt>Selection hash</dt><dd>{allocation.selection_proof?.selection_hash}</dd></div><div><dt>Selection price end / decision</dt><dd>{allocation.selection_proof?.selection_price_end_date} / {allocation.selection_proof?.decision_session}</dd></div><div><dt>Hạn dữ liệu lựa chọn</dt><dd>{allocation.selection_context.valid_until}</dd></div></>}
  </dl></details>;
}

export function AllocationView({ allocation, compact = false, metadata = true, summaryFirst = false, capitalLabel = 'Vốn kế hoạch' }: { allocation: Allocation; compact?: boolean; metadata?: boolean; summaryFirst?: boolean; capitalLabel?: string }) {
  const [sort, setSort] = useState<{ key: 'asset' | 'weight' | 'capital'; direction: 'ascending' | 'descending' }>({ key: 'weight', direction: 'descending' });
  const weights = allocation.asset_ids.map((_, index) => Number(allocation.weights[index]));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const rows = allocation.asset_ids.map((asset, index) => ({ asset, index, weight: weights[index], capital: Number(allocation.capital_vnd) * weights[index] })).filter(row => row.weight !== 0);
  const sortedRows = [...rows].sort((a, b) => (sort.direction === 'ascending' ? 1 : -1) * (sort.key === 'asset' ? a.asset.localeCompare(b.asset, 'vi') : a[sort.key] - b[sort.key]));
  const calculationDetails = <>
    {allocation.inputs_provenance?.phase1_full && <section className="notice" aria-label="K5 và policy hiệu lực">
      <p>K5: {allocation.inputs_provenance.phase1_full.selected_equity_ids.join(' · ')} · GOLD · VFF. Tài sản ngoài K5 có tỷ trọng 0%.</p>
      {Object.entries(allocation.inputs_provenance.phase1_full.availability ?? {}).map(([asset, item]) => <p key={asset}>{asset === 'VFF' ? 'NAV VFF' : asset}: ngày {item.observation_date} · tuổi {item.age_days} ngày · khả dụng từ {item.policy_available_at}</p>)}
      {allocation.constraints && <p>Policy hiệu lực: VFF phòng thủ tối thiểu {percentage(allocation.constraints.min_defensive_weight ?? 0)}; nhóm còn lại (gồm GOLD) tối đa {percentage(allocation.constraints.max_non_defensive_weight ?? 1)}; mỗi tài sản tối đa {percentage(allocation.constraints.max_position_weight)}. Ngại rủi ro: {allocation.constraints.risk_aversion}{allocation.requested_constraints && ` (hồ sơ: ${allocation.requested_constraints.risk_aversion})`} · regime {allocation.inputs_provenance.phase1_full.regime?.regime ?? 'normal'}.</p>}
    </section>}
    {allocation.selection_context && <details className="notice allocation-selection-details" aria-label="Lựa chọn đã ghim của đề xuất"><summary>Chi tiết tính toán · {rows.length} tài sản được phân bổ</summary><p>Tài sản được phép cân nhắc khi tính: {allocation.selection_context.candidate_asset_ids.join(' · ')}.</p>{allocation.selection_proof && <><p>{allocation.selection_proof.applied_selection === 'equity-k5-v1' ? 'K5 thực tế' : 'Cổ phiếu được dùng'}: {allocation.selection_proof.selected_equity_ids.join(' · ') || 'Không có'}. {allocation.strategy === 'HYBRID' ? 'Tập của nhánh dùng mô hình' : 'Tập tính toán'}: {allocation.selection_proof.active_asset_ids.join(' · ')}.</p><p>{allocation.strategy !== 'HYBRID' && `${allocation.selection_proof.active_asset_ids.length} tài sản trong tập tính toán; `}{weights.filter(weight => weight > 0).length} tài sản có tỷ trọng dương. Tài sản được chọn vẫn có thể nhận 0%.</p></>}{allocation.constraints && <p>Policy hiệu lực: vị thế tối đa {percentage(allocation.constraints.max_position_weight)}; VFF phòng thủ tối thiểu {percentage(allocation.constraints.min_defensive_weight ?? 0)}; nhóm còn lại tối đa {percentage(allocation.constraints.max_non_defensive_weight ?? 1)}. Ngại rủi ro {allocation.constraints.risk_aversion} (hồ sơ {allocation.requested_constraints?.risk_aversion ?? '—'}; regime {allocation.selection_context.regime.regime}).</p>}</details>}
  </>;
  return <div className={`allocation-view${compact ? ' allocation-compact' : ''}`}>
    <div className="allocation-capital"><strong>{money(allocation.capital_vnd)}</strong><span>{capitalLabel} · chưa trừ phí và làm tròn lô</span></div>
    <div className="allocation-tags"><span className="badge">{allocation.requested_strategy && allocation.requested_strategy !== allocation.strategy ? `${strategyName(allocation.requested_strategy)} → ${strategyName(allocation.strategy)}` : strategyName(allocation.strategy)}</span>{allocation.demo && <span className="badge">Dữ liệu minh họa</span>}{!allocation.demo && allocation.inputs_provenance?.data_origin === 'real' && <span className="badge">Giá thị trường</span>}</div>
    {allocation.fallback_reason && <p className="muted small">Đã dùng EW theo lựa chọn dự phòng: chưa có model ML được duyệt.</p>}
    {!summaryFirst && calculationDetails}
    <div className="allocation-stack" aria-hidden="true">{rows.map(({ asset, index, weight }) => <span key={asset} title={`${asset}: ${percentage(weight)}`} style={{ width: `${Math.max(0, Math.min(100, weight * 100))}%`, background: `var(--chart-${index % 5 + 1})` }}/>)}</div>
    <p className="allocation-total muted small">Tổng tỷ trọng: {percentage(total)}</p>
    {!rows.length && <p className="muted" role="status">Chưa có tài sản được phân bổ.</p>}
    {compact ? <ul className="allocation-legend">{sortedRows.map(({ asset, index, weight, capital }) => <li key={asset}><span className="legend-name"><i aria-hidden="true" style={{ background: `var(--chart-${index % 5 + 1})` }}/>{asset}</span><span className="allocation-legend-values"><strong>{percentage(weight)}</strong><span className="muted small">{money(capital)}</span></span></li>)}</ul> : <div className="allocation-table-wrap"><table className="allocation-table">
      <caption className="sr-only">Phân bổ mục tiêu · {money(allocation.capital_vnd)}</caption>
      <colgroup><col className="allocation-asset-col"/><col className="allocation-weight-col"/><col className="allocation-capital-col"/></colgroup>
      <thead><tr>{([['asset', 'Tài sản'], ['weight', 'Tỷ trọng mục tiêu'], ['capital', 'Vốn mục tiêu (VND)']] as const).map(([key, label]) => <th key={key} scope="col" aria-sort={sort.key === key ? sort.direction : 'none'}><button type="button" className="allocation-sort" aria-label={`${label}: sắp xếp ${sort.key === key && sort.direction === 'ascending' ? 'giảm dần' : 'tăng dần'}`} onClick={() => setSort(current => ({ key, direction: current.key === key && current.direction === 'ascending' ? 'descending' : 'ascending' }))}>{label}{sort.key === key ? <span aria-hidden="true">{sort.direction === 'ascending' ? '↑' : '↓'}</span> : <ActionIcon name="sort"/>}</button></th>)}</tr></thead>
      <tbody>{sortedRows.map(({ asset, index, weight, capital }) => <tr key={asset}><th scope="row"><span className="legend-name"><i aria-hidden="true" style={{ background: `var(--chart-${index % 5 + 1})` }}/>{asset}</span></th><td>{percentage(weight)}</td><td data-label="Vốn mục tiêu">{money(capital)}</td></tr>)}</tbody>
      <tfoot><tr><th scope="row">Tổng</th><td>{percentage(total)}</td><td>{money(Number(allocation.capital_vnd) * total)}</td></tr></tfoot>
    </table></div>}
    {!compact && <p className="muted small allocation-disclaimer">Tỷ trọng mục tiêu là kế hoạch phân bổ; không phản ánh tài sản thực tế. Vốn mục tiêu chưa trừ phí hoặc làm tròn lô.</p>}
    {summaryFirst && (allocation.selection_context || allocation.inputs_provenance?.phase1_full) && <details className="allocation-calculation-details"><summary>Chi tiết tính toán · {rows.length} tài sản được phân bổ</summary>{calculationDetails}</details>}
    {allocation.strategy === 'HYBRID' && allocation.diagnostics?.hybrid && <details className="allocation-details"><summary>Cách hệ thống tính</summary><p>Hồ sơ và trạng thái thị trường xác định mức ngại rủi ro và tỷ lệ phối. Đề xuất này phối {percentage(allocation.diagnostics.hybrid.mvo_share)} nhánh dùng thống kê lịch sử với {percentage(1 - allocation.diagnostics.hybrid.mvo_share)} nhánh dùng mô hình đã được duyệt.</p></details>}
    <AllocationReferences allocation={allocation}/>
    {metadata && <AllocationMetadata allocation={allocation}/>}
  </div>;
}
