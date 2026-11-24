'use client';
import { useState, type ReactNode } from 'react';
import './allocation-view.css';
import { dateTime } from '../lib/portfolio-types';
import { workspaceHash } from '../lib/workspace-state';
import { ActionIcon } from './action-controls';
import { assetKindName, type AssetCatalogItem, type SelectionProof } from '../lib/selection-types';
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
const currency = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 });
export const money = (amount: number | string) => amount != null && String(amount).trim() && Number.isFinite(Number(amount)) ? currency.format(Number(amount)) : 'Chưa có số tiền';
export const profileName = (profile?: string) => !profile ? 'Chưa xác nhận' : ({ conservative: 'Thận trọng', balanced: 'Cân bằng', growth: 'Tăng trưởng' }[profile ?? ''] ?? 'Tùy chỉnh');
export const percentage = (weight: number) => `${(weight * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
export function weightPercentage(weight: number) {
  const magnitude = Math.abs(weight);
  if (magnitude > 0 && magnitude < .0001) return weight < 0 ? '−<0,01%' : '<0,01%';
  if (magnitude > 0 && magnitude < .001) return `${(weight * 100).toLocaleString('vi-VN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  return percentage(weight);
}

export function AllocationReferencesDetails({ allocation }: { allocation: Allocation }) {
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
    <p className="muted small">Ước tính từ {comparison.covariance_window_sessions} phiên. {comparison.ew_constraint_violations.length > 0 && <>EW không đáp ứng {comparison.ew_constraint_violations.map(code => label[code] ?? 'một giới hạn phân bổ khác').join(', ')}.</>}</p>
  </details>;
}

export function AllocationMetadata({ allocation }: { allocation: Allocation }) {
  const source = allocation.demo ? 'Dữ liệu minh họa' : allocation.inputs_provenance?.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh';
  const priceEnd = allocation.selection_proof?.selection_price_end_date;
  return <details className="allocation-details"><summary>Dữ liệu dùng để tính</summary><dl className="provenance">
    <div><dt>Loại dữ liệu</dt><dd>{source}</dd></div>
    {allocation.as_of_date && <div><dt>Ngày dữ liệu</dt><dd>{allocation.as_of_date}</dd></div>}
    {priceEnd && priceEnd !== allocation.as_of_date && <div><dt>Ngày giá cuối dùng để chọn tài sản</dt><dd>{priceEnd}</dd></div>}
  </dl></details>;
}

type Kind = AssetCatalogItem['kind'] | 'unknown';
const groupNames = { ...assetKindName, unknown: 'Chưa rõ loại' };
const groupOrder: Kind[] = ['fund', 'stock', 'gold', 'unknown'];
const summaryPercent = (weight: number) => weightPercentage(weight).replace(/,0%$/, '%');

type AllocationRow = { asset: string; kind: Kind; weight: number; capital: number; priceHref?: string };
function AllocationMix({ rows, title }: { rows: AllocationRow[]; title: string }) {
  const groups = groupOrder.map(kind => ({
    kind, weight: rows.reduce((sum, row) => sum + (row.kind === kind ? row.weight : 0), 0),
  })).filter(group => group.weight > 0);
  return <section className="allocation-mix">
    <h2>{title}</h2>
    {groups.length ? <>
      <div className="mix-track" aria-hidden="true">{groups.map(({ kind, weight }) => <span key={kind} data-asset-kind={kind} style={{ width: `${weight * 100}%` }}/>)}</div>
      <ul className="mix-legend" aria-label="Tỷ trọng theo nhóm tài sản">{groups.map(({ kind, weight }) => <li key={kind} data-asset-kind={kind}>
        <span>{groupNames[kind]}</span><strong>{summaryPercent(weight)}</strong>
      </li>)}</ul>
    </> : <p role="status">Chưa có tài sản được phân bổ.</p>}
  </section>;
}

type AllocationViewProps = {
  allocation: Allocation; assets?: AssetCatalogItem[]; metadata?: boolean; summaryFirst?: boolean;
  showDataDate?: boolean; presentation?: 'table' | 'chart' | 'summary'; capitalLabel?: string;
  pricePortfolioId?: string; priceProposalId?: string; priceReturnView?: 'overview';
  chartTitle?: string; capitalNote?: ReactNode; capitalAction?: ReactNode; summaryVariant?: 'compact';
};
export function AllocationView({ allocation, assets, metadata = true, summaryFirst = false, showDataDate = false, presentation = 'table', capitalLabel = 'Vốn kế hoạch', pricePortfolioId, priceProposalId, priceReturnView, chartTitle = 'Phân bổ mục tiêu', capitalNote, capitalAction, summaryVariant }: AllocationViewProps) {
  const [sort, setSort] = useState<{ key: 'asset' | 'weight' | 'capital'; direction: 'ascending' | 'descending' }>({ key: 'weight', direction: 'descending' });
  const [showTable, setShowTable] = useState(false), [showZero, setShowZero] = useState(false);
  const chart = presentation === 'chart', tableVisible = !chart || showTable;
  if (!Array.isArray(allocation.asset_ids) || !Array.isArray(allocation.weights) || allocation.weights.length !== allocation.asset_ids.length ||
      allocation.weights.some(weight => weight == null || String(weight).trim() === '' || !Number.isFinite(Number(weight)))) {
    return <p role="status">Bản ghi chưa có đủ dữ liệu tỷ trọng.</p>;
  }
  const recordCapital = allocation.capital_vnd != null && String(allocation.capital_vnd).trim() ? Number(allocation.capital_vnd) : NaN;
  const allRows: AllocationRow[] = allocation.asset_ids.map((asset, index) => {
    const item = assets?.find(entry => entry.asset_id === asset);
    const weight = Number(allocation.weights[index]);
    const hasPrice = item && (item.data_status === 'FRESH' || item.data_status === 'STALE' || !!item.latest_observation_date);
    return { asset, weight, capital: recordCapital * weight,
      kind: item?.kind ?? (asset === 'VFF' ? 'fund' : asset === 'GOLD' ? 'gold' : 'unknown'),
      priceHref: pricePortfolioId && hasPrice ? workspaceHash({ view: 'asset-prices', portfolioId: pricePortfolioId, proposalId: priceProposalId, returnView: priceReturnView, assetId: asset }) : undefined,
    };
  });
  const assetLink = ({ asset, priceHref }: Pick<AllocationRow, 'asset' | 'priceHref'>) => priceHref
    ? <a className="allocation-price-link" aria-label={`Xem giá ${asset}`} href={priceHref}>{asset}</a> : asset;
  const total = allRows.reduce((sum, row) => sum + row.weight, 0);
  const rows = allRows.filter(row => row.weight !== 0);
  const zeroCount = allRows.length - rows.length;
  const sortedRows = (showZero && tableVisible ? allRows : [...rows]).sort((a, b) => (sort.direction === 'ascending' ? 1 : -1) * (sort.key === 'asset' ? a.asset.localeCompare(b.asset, 'vi') : a[sort.key] - b[sort.key]));
  if (presentation === 'summary') return <div className="result-allocation" data-variant={summaryVariant}>
    <div className="result-allocation-head">
      <div className="result-capital">
        <span>{capitalLabel}</span><strong>{money(allocation.capital_vnd)}</strong>
        {capitalNote && <div className="result-capital-note">{capitalNote}</div>}
        {capitalAction && <div className="result-capital-action">{capitalAction}</div>}
      </div>
      <AllocationMix rows={allRows} title={chartTitle}/>
    </div>
    {allRows.length > 0 && <section className="result-assets">
      <h2>Chi tiết theo tài sản</h2>
      <table><caption className="sr-only">Phân bổ mục tiêu · {money(allocation.capital_vnd)}</caption>
        <thead><tr><th scope="col">Tài sản</th><th scope="col">Tỷ trọng</th><th scope="col">Vốn mục tiêu</th></tr></thead>
        <tbody>{[...allRows].sort((a, b) => b.weight - a.weight).map(row => <tr key={row.asset} data-asset-kind={row.kind}>
          <th scope="row"><strong>{assetLink(row)}</strong><small>{groupNames[row.kind]}</small></th>
          <td>{summaryPercent(row.weight)}</td><td>{money(row.capital)}</td>
        </tr>)}</tbody>
      </table>
    </section>}
    {allocation.demo && <small className="muted">Dữ liệu minh họa</small>}
  </div>;
  const phase = allocation.inputs_provenance?.phase1_full, selection = allocation.selection_context;
  const proof = allocation.selection_proof, constraints = allocation.constraints;
  const calculationDetails = (phase || selection) && <details className="allocation-calculation-details">
    <summary>Tài sản và giới hạn khi tính</summary>
    {phase && <>
      <p>Tài sản dùng trong lần tính: {phase.active_asset_ids.join(' · ')}.</p>
      {Object.entries(phase.availability ?? {}).map(([asset, item]) => <p key={asset}>{asset === 'VFF' ? 'NAV VFF' : asset}: ngày {item.observation_date}. Dữ liệu chậm {item.age_days} ngày, khả dụng từ {dateTime(item.policy_available_at)} (GMT+7).</p>)}
    </>}
    {selection && <>
      <p>Tài sản được cân nhắc: {selection.candidate_asset_ids.join(' · ')}.</p>
      {!!proof?.selected_equity_ids.length && <p>Cổ phiếu được dùng: {proof.selected_equity_ids.join(' · ')}.</p>}
      {proof && <p>{allocation.strategy === 'HYBRID' ? 'Tài sản của nhánh dùng mô hình' : 'Tài sản dùng trong lần tính'}: {proof.active_asset_ids.join(' · ')}.</p>}
    </>}
    {constraints && <p>Mỗi tài sản tối đa {percentage(constraints.max_position_weight)}.{constraints.min_defensive_weight != null && <> Nhóm phòng thủ tối thiểu {percentage(constraints.min_defensive_weight)}.</>}{constraints.max_non_defensive_weight != null && <> Nhóm còn lại tối đa {percentage(constraints.max_non_defensive_weight)}.</>}</p>}
  </details>;
  return <div className={`allocation-view${chart ? ' allocation-chart-view' : ''}`}>
    <div className="allocation-capital"><strong>{money(allocation.capital_vnd)}</strong><span>{capitalLabel}</span>
      {showDataDate && <span className="allocation-data-date">Ngày dữ liệu{allocation.as_of_date ? <time dateTime={allocation.as_of_date}>{allocation.as_of_date}</time> : <span>Chưa xác định</span>}</span>}
    </div>
    {(allocation.demo || allocation.inputs_provenance?.data_origin === 'real') && <div className="allocation-tags">{allocation.demo ? <span className="badge">Dữ liệu minh họa</span> : <span className="badge">Giá thị trường</span>}</div>}
    {!summaryFirst && calculationDetails}
    {chart ? <>
      <div className="allocation-chart-toolbar">
        <p className="weight-chart-summary"><strong>{percentage(total)}</strong> tổng tỷ trọng <span>· {rows.length} tài sản có phân bổ</span></p>
        <div className="weight-chart-tabs" role="group" aria-label="Cách hiển thị phân bổ">
          <button type="button" className="quiet" aria-label="Xem biểu đồ phân bổ" aria-pressed={!showTable} onClick={() => setShowTable(false)}>Biểu đồ</button>
          <button type="button" className="quiet" aria-label="Xem bảng số liệu" aria-pressed={showTable} onClick={() => setShowTable(true)}>Bảng số liệu</button>
        </div>
      </div>
      {!showTable && rows.length > 0 && <div className="weight-chart-plot">
        <div className="weight-chart-axis" aria-hidden="true">{[0, 25, 50, 75, 100].map(tick => <span key={tick} style={{ left: `${tick}%` }}>{tick}%</span>)}</div>
        <ul className="allocation-bars" aria-label="Biểu đồ tỷ trọng theo tài sản">{sortedRows.map(({ asset, kind, weight, capital, priceHref }) => <li key={asset}>
          <div className="allocation-bar-label">
            <div><strong>{assetLink({ asset, priceHref })}</strong><span> {groupNames[kind]}</span></div>
            <strong>{weightPercentage(weight)}</strong><span>{money(capital)}</span>
          </div>
          <div className="allocation-bar-track" aria-hidden="true"><span data-asset-kind={kind} style={{ width: `${Math.max(0, Math.min(100, weight * 100))}%` }}/></div>
        </li>)}</ul>
      </div>}

    </> : <><div className="allocation-stack" aria-hidden="true">{rows.map(({ asset, kind, weight }) => <span key={asset} title={`${asset}: ${percentage(weight)}`} data-asset-kind={kind} style={{ width: `${Math.max(0, Math.min(100, weight * 100))}%` }}/>)}</div><p className="allocation-total muted small">Tổng tỷ trọng: {percentage(total)}</p></>}
    {tableVisible && zeroCount > 0 && <button type="button" className="quiet allocation-zero-toggle" aria-pressed={showZero} onClick={() => setShowZero(value => !value)}>{showZero ? 'Ẩn mã có tỷ trọng 0%' : `Xem ${zeroCount} mã có tỷ trọng 0%`}</button>}
    {!rows.length && <p className="muted" role="status">Chưa có tài sản được phân bổ.</p>}
    {tableVisible && <div className="allocation-table-wrap"><table className="allocation-table">
      <caption className="sr-only">Phân bổ mục tiêu · {money(allocation.capital_vnd)}</caption>
      <colgroup><col className="allocation-asset-col"/><col className="allocation-weight-col"/><col className="allocation-capital-col"/></colgroup>
      <thead><tr>{([['asset', 'Tài sản'], ['weight', 'Tỷ trọng mục tiêu'], ['capital', 'Vốn mục tiêu (VND)']] as const).map(([key, label]) => <th key={key} scope="col" aria-sort={sort.key === key ? sort.direction : 'none'}><button type="button" className="allocation-sort" aria-label={`${label}: sắp xếp ${sort.key === key && sort.direction === 'ascending' ? 'giảm dần' : 'tăng dần'}`} onClick={() => setSort(current => ({ key, direction: current.key === key && current.direction === 'ascending' ? 'descending' : 'ascending' }))}>{label}{sort.key === key ? <span aria-hidden="true">{sort.direction === 'ascending' ? '↑' : '↓'}</span> : <ActionIcon name="sort"/>}</button></th>)}</tr></thead>
      <tbody>{sortedRows.map(({ asset, kind, weight, capital, priceHref }) => <tr key={asset}><th scope="row"><span className="legend-name"><i aria-hidden="true" data-asset-kind={kind}/>{assetLink({ asset, priceHref })}</span></th><td>{weightPercentage(weight)}</td><td data-label="Vốn mục tiêu">{money(capital)}</td></tr>)}</tbody>
      <tfoot><tr><th scope="row">Tổng</th><td>{percentage(total)}</td><td>{money(recordCapital * total)}</td></tr></tfoot>
    </table></div>}
    <p className="muted small allocation-disclaimer">Tỷ trọng mục tiêu là kế hoạch phân bổ; không phản ánh tài sản thực tế. Vốn mục tiêu chưa trừ phí hoặc làm tròn lô.</p>
    {summaryFirst && calculationDetails}
    {(!chart || metadata) && <AllocationReferencesDetails allocation={allocation}/>}
    {metadata && <AllocationMetadata allocation={allocation}/>}
  </div>;
}
