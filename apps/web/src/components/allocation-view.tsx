export type Allocation = {
  asset_ids: string[]; weights: (string | number)[]; capital_vnd: string;
  strategy: string; requested_strategy?: string; fallback_reason?: string | null;
  demo?: boolean; policy_version_id?: string; data_snapshot_id?: string;
  model_bundle_id?: string | null; bundle_hash?: string; core_version?: string; as_of_date?: string; valid_until?: string;
  inputs_provenance?: { data_origin?: string; snapshot_hash?: string; estimator?: string };
};
export const money = (amount: number | string) => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(Number(amount));
export const profileName = (profile?: string) => ({ conservative: 'Thận trọng', balanced: 'Cân bằng', growth: 'Tăng trưởng' }[profile ?? ''] ?? 'Tùy chỉnh');

const percentage = (weight: number) => `${(weight * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

export function AllocationView({ allocation }: { allocation: Allocation }) {
  const weights = allocation.asset_ids.map((_, index) => Number(allocation.weights[index]));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  let cumulative = 0;
  const segments = weights.map((weight, index) => {
    const start = cumulative;
    cumulative += total > 0 ? Math.max(0, weight) / total * 100 : 0;
    return `var(--chart-${index % 5 + 1}) ${start}% ${cumulative}%`;
  });
  return <div className="allocation-view">
    <div className="allocation-tags"><span className="badge">{allocation.requested_strategy && allocation.requested_strategy !== allocation.strategy ? `${allocation.requested_strategy} → ${allocation.strategy}` : allocation.strategy}</span>{allocation.demo && <span className="badge">Dữ liệu minh họa</span>}{!allocation.demo && allocation.inputs_provenance?.data_origin === 'real' && <span className="badge">Giá thị trường</span>}</div>
    {allocation.fallback_reason && <p className="muted">Đã dùng EW theo lựa chọn dự phòng: chưa có model ML được duyệt.</p>}
    <div className="allocation-chart" role="group" aria-label="Phân bổ mục tiêu">
      <div className="allocation-donut" style={{ background: total > 0 ? `conic-gradient(${segments.join(', ')})` : 'var(--soft)' }} aria-hidden="true"><div><strong>{percentage(total)}</strong><span>Tổng tỷ trọng</span></div></div>
      <ul className="allocation-legend">{allocation.asset_ids.map((asset, index) => <li key={asset}><span className="legend-name"><i aria-hidden="true" style={{ background: `var(--chart-${index % 5 + 1})` }}/>{asset}</span><strong>{percentage(weights[index])}</strong></li>)}</ul>
    </div>
    <table><caption>Phân bổ mục tiêu · {money(allocation.capital_vnd)}</caption><thead><tr><th>Tài sản</th><th>Tỷ trọng</th><th>Vốn mục tiêu</th></tr></thead><tbody>{allocation.asset_ids.map((asset, i) => <tr key={asset}><th scope="row">{asset}</th><td><span className="weight-bar" style={{ width: `${Math.max(0, Math.min(100, Number(allocation.weights[i]) * 100))}%` }}/>{(Number(allocation.weights[i]) * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</td><td>{money(Number(allocation.capital_vnd) * Number(allocation.weights[i]))}</td></tr>)}</tbody><tfoot><tr><th scope="row">Tổng</th><td>{percentage(total)}</td><td>{money(Number(allocation.capital_vnd) * total)}</td></tr></tfoot></table>
    <p className="muted small">Vốn mục tiêu là giá trị dự kiến theo tỷ trọng, chưa trừ phí hoặc làm tròn lô.</p>
    <dl className="provenance"><div><dt>Ngày dữ liệu</dt><dd>{allocation.as_of_date ?? '—'}</dd></div><div><dt>Policy</dt><dd>{allocation.policy_version_id ?? 'manual-constraints-v1'}</dd></div><div><dt>Core</dt><dd>{allocation.core_version ?? '—'}</dd></div></dl>
  </div>;
}
