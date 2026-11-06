export type Allocation = {
  asset_ids: string[]; weights: (string | number)[]; capital_vnd: string;
  strategy: string; requested_strategy?: string; fallback_reason?: string | null;
  demo?: boolean; policy_version_id?: string; data_snapshot_id?: string;
  model_bundle_id?: string | null; bundle_hash?: string; core_version?: string; as_of_date?: string; valid_until?: string;
  inputs_provenance?: { data_origin?: string; snapshot_hash?: string; estimator?: string };
};
export const money = (amount: number | string) => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(Number(amount));
export const profileName = (profile?: string) => !profile ? 'Chưa xác nhận' : ({ conservative: 'Thận trọng', balanced: 'Cân bằng', growth: 'Tăng trưởng' }[profile ?? ''] ?? 'Tùy chỉnh');
export const strategyName = (strategy: string) => strategy === 'BL_ML' ? 'BL + ML' : strategy;
export const percentage = (weight: number) => `${(weight * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

export function AllocationMetadata({ allocation }: { allocation: Allocation }) {
  return <details className="allocation-details"><summary>Nguồn và phiên bản của đề xuất</summary><dl className="provenance">
    {([['Ngày dữ liệu', allocation.as_of_date], ['Policy ID', allocation.policy_version_id], ['Snapshot ID', allocation.data_snapshot_id], ['Bundle hash', allocation.bundle_hash], ['Snapshot hash', allocation.inputs_provenance?.snapshot_hash], ['Core version', allocation.core_version], ['Model', allocation.model_bundle_id]] as const).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>)}
  </dl></details>;
}

export function AllocationView({ allocation, compact = false, metadata = true }: { allocation: Allocation; compact?: boolean; metadata?: boolean }) {
  const weights = allocation.asset_ids.map((_, index) => Number(allocation.weights[index]));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  return <div className={`allocation-view${compact ? ' allocation-compact' : ''}`}>
    <div className="allocation-capital"><strong>{money(allocation.capital_vnd)}</strong><span>Vốn kế hoạch · chưa trừ phí và làm tròn lô</span></div>
    <div className="allocation-tags"><span className="badge">{allocation.requested_strategy && allocation.requested_strategy !== allocation.strategy ? `${strategyName(allocation.requested_strategy)} → ${strategyName(allocation.strategy)}` : strategyName(allocation.strategy)}</span>{allocation.demo && <span className="badge">Dữ liệu minh họa</span>}{!allocation.demo && allocation.inputs_provenance?.data_origin === 'real' && <span className="badge">Giá thị trường</span>}</div>
    {allocation.fallback_reason && <p className="muted small">Đã dùng EW theo lựa chọn dự phòng: chưa có model ML được duyệt.</p>}
    <div className="allocation-stack" aria-hidden="true">{allocation.asset_ids.map((asset, index) => <span key={asset} title={`${asset}: ${percentage(weights[index])}`} style={{ width: `${Math.max(0, Math.min(100, weights[index] * 100))}%`, background: `var(--chart-${index % 5 + 1})` }}/>)}</div>
    <p className="allocation-total muted small">Tổng tỷ trọng: {percentage(total)}</p>
    {compact ? <ul className="allocation-legend">{allocation.asset_ids.map((asset, index) => <li key={asset}><span className="legend-name"><i aria-hidden="true" style={{ background: `var(--chart-${index % 5 + 1})` }}/>{asset}</span><strong>{percentage(weights[index])}</strong></li>)}</ul> : <div className="allocation-table-wrap"><table className="allocation-table">
      <caption className="sr-only">Phân bổ mục tiêu · {money(allocation.capital_vnd)}</caption>
      <colgroup><col className="allocation-asset-col"/><col className="allocation-weight-col"/><col className="allocation-capital-col"/></colgroup>
      <thead><tr><th scope="col">Tài sản</th><th scope="col">Tỷ trọng mục tiêu</th><th scope="col">Vốn mục tiêu (VND)</th></tr></thead>
      <tbody>{allocation.asset_ids.map((asset, index) => <tr key={asset}><th scope="row"><span className="legend-name"><i aria-hidden="true" style={{ background: `var(--chart-${index % 5 + 1})` }}/>{asset}</span></th><td>{percentage(weights[index])}</td><td data-label="Vốn mục tiêu">{money(Number(allocation.capital_vnd) * weights[index])}</td></tr>)}</tbody>
      <tfoot><tr><th scope="row">Tổng</th><td>{percentage(total)}</td><td>{money(Number(allocation.capital_vnd) * total)}</td></tr></tfoot>
    </table></div>}
    {!compact && <p className="muted small allocation-disclaimer">Tỷ trọng mục tiêu là kế hoạch phân bổ; không phản ánh tài sản thực tế. Vốn mục tiêu chưa trừ phí hoặc làm tròn lô.</p>}
    {metadata && <AllocationMetadata allocation={allocation}/>}
  </div>;
}
