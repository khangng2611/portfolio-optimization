'use client';
import { ArrowDownWideNarrow, ChevronLeft, ChevronRight, Funnel } from 'lucide-react';
import { isSelectionReadiness, type AssetCatalogItem } from '../lib/selection-types';
import { SearchField, SelectField } from './list-fields';
import { IconButton } from './action-controls';
import { TaskActions } from './task-actions';
import { useEffect, useRef, useState, type FormEvent, type ReactElement } from 'react';
import { AllocationView, money, percentage, profileName, weightPercentage } from './allocation-view';
import { ApiError, dateTime, type Api, type Page, type PageApi, type Portfolio, type Recommendation, type Target } from '../lib/portfolio-types';
import { allocationPausedTitle, assetUniverseName, savedProposalsHint, comparisonDifferences, readinessReason, workspaceHash, type Readiness, type WorkspaceView } from '../lib/workspace-state';

const portfolioPageIcons = {
  previous: <ChevronLeft aria-hidden="true"/>,
  next: <ChevronRight aria-hidden="true"/>,
};

export function Pagination({ total, offset, limit = 10, onChange, busy = false, icons }: { total: number; offset: number; limit?: number; onChange: (offset: number) => void; busy?: boolean; icons?: { previous: ReactElement; next: ReactElement } }) {
  if (offset === 0 && total <= limit) return total ? <p className="pagination-summary" role="status">{total} kết quả</p> : null;
  return <nav className="pagination" aria-label="Phân trang">
    <IconButton icon={icons?.previous ?? 'previous'} label="Trang trước" disabled={busy || offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}/>
    <span role="status">Trang {Math.floor(offset / limit) + 1} · {total} kết quả</span>
    <IconButton icon={icons?.next ?? 'next'} label="Trang sau" disabled={busy || offset + limit >= total} onClick={() => onChange(offset + limit)}/>
  </nav>;
}
export function ReadinessNotice({ value, onRefresh, busy = false, failed = false, pausedPortfolio }: { value: Readiness | null; onRefresh: () => void; busy?: boolean; failed?: boolean; pausedPortfolio?: { id: string; hasProposals: boolean } }) {
  if (value?.reason_code === 'SYSTEM_PAUSED') return <aside className="readiness notice warning" data-testid="paused-input-notice" aria-label="Tạm dừng tính đề xuất">
    <div><strong>{allocationPausedTitle}</strong><p>{pausedPortfolio?.hasProposals ? savedProposalsHint : 'Bạn có thể xem lại kế hoạch hoặc trao đổi với trợ lý.'}</p>
      {pausedPortfolio && <div className="actions">
        {pausedPortfolio.hasProposals && <a className="button" href={workspaceHash({ view: 'proposal', portfolioId: pausedPortfolio.id, focus: 'history' })}>Xem đề xuất đã lưu</a>}
        <a className={`button ${pausedPortfolio.hasProposals ? 'quiet' : ''}`} href={workspaceHash({ view: 'overview', portfolioId: pausedPortfolio.id })}>{pausedPortfolio.hasProposals ? 'Về tổng quan' : 'Xem kế hoạch đã lưu'}</a>
        <a className="button quiet" href={workspaceHash({ view: 'chat', portfolioId: pausedPortfolio.id })}>Hỏi trợ lý về kế hoạch</a>
      </div>}
    </div>
    <IconButton icon="refresh" label="Kiểm tra lại" onClick={onRefresh} disabled={busy} aria-busy={busy}/>
  </aside>;
  if (isSelectionReadiness(value)) return <aside className={`readiness notice selection-readiness ${value.can_submit ? '' : 'warning'}`} data-testid="readiness-notice" aria-label="Tình trạng dữ liệu">
    <div className="readiness-summary">
      <strong>{value.can_submit ? 'Sẵn sàng tạo đề xuất' : 'Chưa thể tạo đề xuất'}</strong>
      {value.candidate_asset_ids.length > 0 && <p>{value.candidate_asset_ids.length} tài sản được cân nhắc</p>}
      {!value.can_submit && <p>{readinessReason[value.reason_code] ?? 'Thử kiểm tra lại dữ liệu.'}</p>}
      <details className="readiness-detail"><summary>Xem chi tiết dữ liệu và tài sản</summary>
        {value.candidate_asset_ids.length > 0 && value.asset_status.length === 0 && <p>{value.candidate_asset_ids.join(' · ')}</p>}
        {value.asset_status.length > 0 && <table className="readiness-asset-table"><caption className="sr-only">Dữ liệu từng tài sản</caption><thead><tr><th scope="col">Tài sản</th><th scope="col">Ngày dữ liệu</th><th scope="col">Độ trễ dữ liệu</th></tr></thead><tbody>{value.asset_status.map((item, index) => <tr key={String(item.asset_id ?? index)}><th scope="row">{String(item.asset_id ?? '—')}</th><td>{String(item.eligible_observation_date ?? item.observation_date ?? 'Chưa có dữ liệu')}</td><td>{item.age_days != null ? `tuổi ${String(item.age_days)} ngày / tối đa 7 ngày` : 'Chưa xác minh'}</td></tr>)}</tbody></table>}
        {value.selection_valid_until && <p>Hiệu lực đến {dateTime(value.selection_valid_until)} · GMT+7</p>}
        {value.checked_at && <p className="muted small">Đã kiểm tra {dateTime(value.checked_at)} · GMT+7</p>}
      </details>
    </div>
    <IconButton icon="refresh" label={busy ? 'Đang kiểm tra dữ liệu' : 'Kiểm tra lại'} onClick={onRefresh} disabled={busy} aria-busy={busy}/>
  </aside>;
  const expired = value?.status === 'EXPIRED';
  return <aside className={`readiness notice ${value?.status !== 'READY' ? 'warning' : ''}`} data-testid={expired ? 'expired-input-notice' : 'readiness-notice'} aria-label="Tình trạng dữ liệu">
    <div><strong>{!value ? failed ? 'Chưa kiểm tra được dữ liệu' : 'Đang kiểm tra dữ liệu' : expired ? 'Dữ liệu đã hết hiệu lực' : value.status !== 'READY' ? 'Dữ liệu chưa sẵn sàng' : 'Dữ liệu sẵn sàng'}</strong>
      <p>{value ? `${value.demo ? 'Dữ liệu minh họa' : value.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}${value.as_of_date ? ` · Ngày dữ liệu ${value.as_of_date}` : ''}` : 'Kiểm tra bộ dữ liệu trước khi gửi yêu cầu.'}</p>
      {value && readinessReason[value.reason_code] && <p role="status">{readinessReason[value.reason_code]}</p>}
      <details className="readiness-detail"><summary>Điều kiện & hiệu lực dữ liệu</summary>{value && <p>Bộ tài sản: {assetUniverseName(value.universe_id)}</p>}{value?.valid_until && <p>Hiệu lực đến {dateTime(value.valid_until)} · GMT+7</p>}
      {value?.provenance?.phase1_full && <>{Object.entries(value.provenance.phase1_full.availability ?? {}).map(([asset, item]) => <p key={asset}>{asset === 'VFF' ? 'NAV VFF' : asset}: ngày {item.observation_date} · tuổi {item.age_days} ngày · khả dụng từ {dateTime(item.policy_available_at)} · GMT+7</p>)}</>}
      {value?.checked_at && <p className="muted small">Đã kiểm tra {dateTime(value.checked_at)} · GMT+7</p>}
      </details>{value?.status !== 'READY' && <p>{expired ? 'Cần bản dữ liệu mới. Mục tiêu đã lưu vẫn được giữ trong lịch sử.' : 'Thử kiểm tra lại. Nếu tình trạng chưa thay đổi, cần người vận hành cập nhật dữ liệu.'}</p>}

    </div><IconButton icon="refresh" label={busy ? 'Đang kiểm tra dữ liệu' : 'Kiểm tra lại'} onClick={onRefresh} disabled={busy} aria-busy={busy}/>
  </aside>;
}

function usePage<T>(fetchPage: PageApi, path: string) {
  const [data, setData] = useState<Page<T>>({ items: [], total: 0, limit: 10, offset: 0 });
  const [busy, setBusy] = useState(true), [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true; setBusy(true); setError('');
    fetchPage<T>(path).then(value => { if (active) setData(value); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [fetchPage, path, refresh]);
  return { data, busy, error, retry: () => setRefresh(value => value + 1) };
}
export function PortfolioEmptyState({ firstUse, onClear }: { firstUse: boolean; onClear: () => void }) {
  return firstUse ? <div className="portfolio-onboarding"><h2>Bắt đầu từ một danh mục</h2><p className="muted">Cho biết kế hoạch và khả năng chịu rủi ro để xem phương án phân bổ phù hợp với các giới hạn của bạn.</p><ol className="first-use-steps"><li><strong>Thông tin kế hoạch</strong><span>Vốn dự định và thời gian đầu tư.</span></li><li><strong>Khả năng chịu rủi ro</strong><span>Bạn chủ động chọn câu trả lời theo khả năng thực tế.</span></li><li><strong>Xem lại và xác nhận</strong><span>Sau đó bạn có thể tạo đề xuất phân bổ.</span></li></ol><a className="button list-action" href="#create">Tạo danh mục đầu tiên</a><p className="muted small">Chấp nhận mục tiêu chỉ lưu tỷ trọng, không thực hiện giao dịch.</p></div>
    : <div className="empty-state compact"><h2>Không tìm thấy danh mục</h2><p>Thử tên khác hoặc xóa điều kiện tìm kiếm để xem lại danh sách.</p><button className="quiet list-action" onClick={onClear}>Xóa bộ lọc</button></div>;
}
export function PortfolioList({ fetchPage, destination = 'overview', mode = 'manage', onInventoryEmpty }: { fetchPage: PageApi; destination?: WorkspaceView; mode?: 'manage' | 'choose'; onInventoryEmpty?: (empty: boolean) => void }) {
  const [query, setQuery] = useState(''), [search, setSearch] = useState(''), [risk, setRisk] = useState('all'), [sort, setSort] = useState('created_desc'), [offset, setOffset] = useState(0);
  useEffect(() => {
    const next = query.trim();
    if (next === search) return;
    const timer = setTimeout(() => { setSearch(next); setOffset(0); }, 250);
    return () => clearTimeout(timer);
  }, [query, search]);
  const params = new URLSearchParams({ limit: '10', offset: String(offset), q: search, risk_profile: risk, sort });
  const { data, busy, error, retry } = usePage<Portfolio>(fetchPage, '/api/v1/portfolios?' + params);
  const firstUse = !busy && !error && data.total === 0 && offset === 0 && !search && risk === 'all';
  useEffect(() => { if (!busy && !error && !search && risk === 'all' && offset === 0) onInventoryEmpty?.(data.total === 0); }, [busy, error, search, risk, offset, data.total, onInventoryEmpty]);
  return <>
    {mode === 'choose' && !firstUse && <p className="portfolio-selection-guidance muted">{['profile', 'risk-assessment'].includes(destination) ? 'Hồ sơ rủi ro được lưu theo từng danh mục. Chọn kế hoạch bạn muốn xem.' : 'Chọn danh mục bạn muốn tiếp tục làm việc.'}</p>}
    <section className={`panel portfolio-list ${mode === 'choose' ? 'portfolio-context-picker' : 'portfolio-management'} ${firstUse ? 'portfolio-first-use' : ''}`} aria-label={mode === 'choose' ? 'Chọn danh mục' : 'Danh sách danh mục'} aria-busy={busy}>
      {mode === 'manage' && !firstUse && <p className="portfolio-list-subtitle">Kế hoạch đầu tư</p>}
      {!firstUse && (mode === 'choose' || busy || data.total > 1 || query || search || risk !== 'all' || sort !== 'created_desc') && <div className="portfolio-toolbar">
        <SearchField label="Tìm trong danh sách" hideLabel placeholder="Tìm theo tên hoặc mã…" maxLength={120} value={query} onChange={e => setQuery(e.target.value)}/>
        {mode === 'manage' && <>
          <SelectField label="Lọc theo hồ sơ" hideLabel icon={Funnel} value={risk} onChange={e => { setRisk(e.target.value); setOffset(0); }}>
              <option value="all">Tất cả hồ sơ</option>
              <option value="conservative">Thận trọng</option>
              <option value="balanced">Cân bằng</option>
              <option value="growth">Tăng trưởng</option>
              <option value="manual">Tùy chỉnh</option>
          </SelectField>
          <SelectField label="Sắp xếp danh mục" hideLabel icon={ArrowDownWideNarrow} value={sort} onChange={e => { setSort(e.target.value); setOffset(0); }}>
              <option value="created_desc">Mới tạo trước</option>
              <option value="name_asc">Tên A → Z</option>
              <option value="capital_desc">Vốn giảm dần</option>
          </SelectField>
        </>}
      </div>}
      {error ? <div role="alert" className="error"><p>{error}</p><button className="quiet list-action" onClick={retry}>Thử lại</button></div> : <>
        {busy && <p role="status" className="muted">Đang tải danh mục…</p>}
        {!busy && !data.items.length ? <PortfolioEmptyState firstUse={firstUse} onClear={() => { setQuery(''); setSearch(''); setRisk('all'); setOffset(0); }}/> : mode === 'choose' ? <ul className="portfolio-choices" aria-label="Danh mục có thể chọn">{data.items.map(item => <li key={item.id}><a className="portfolio-choice" href={workspaceHash({ view: destination, portfolioId: item.id })} aria-label={`Chọn danh mục ${item.name}`}><span className="portfolio-choice-summary"><strong>{item.name}</strong><span className="portfolio-choice-profile">{profileName(item.risk_profile?.profile)}</span><span className="portfolio-choice-capital">{money(item.capital_vnd)}</span></span><span className="portfolio-choice-action" aria-hidden="true"><ChevronRight aria-hidden="true"/></span></a></li>)}</ul> : <ul className="plan-list-rows" aria-label="Kế hoạch đầu tư">{data.items.map(item => {
          const horizon = item.risk_profile?.answers?.horizon_months;
          return <li key={item.id}><a href={workspaceHash({ view: destination, portfolioId: item.id })} aria-label={`Mở danh mục ${item.name}`} aria-describedby={`plan-summary-${item.id}`}>
            <strong>{item.name}</strong><span id={`plan-summary-${item.id}`}>{money(item.capital_vnd)}{horizon ? ` · ${horizon} tháng` : ''} · {profileName(item.risk_profile?.profile)}</span>
          </a></li>;
        })}</ul>}
        {(mode === 'choose' || data.total !== 1 || search || risk !== 'all') && <Pagination total={data.total} offset={offset} onChange={setOffset} busy={busy} icons={portfolioPageIcons}/>}
      </>}
      {mode === 'manage' && !firstUse && <a className="button list-action portfolio-create" href="#create">Tạo danh mục</a>}
    </section>
    {mode === 'choose' && !firstUse && <p className="portfolio-selection-footer"><a href="#portfolios">Quản lý danh mục</a></p>}
  </>;
}

export function EditPortfolio({ portfolio, api, onSaved, onReload }: { portfolio: Portfolio; api: Api; onSaved: (value: Portfolio) => void; onReload?: () => void }) {
  const [name, setName] = useState(portfolio.name), [capital, setCapital] = useState(portfolio.capital_vnd), [version, setVersion] = useState(portfolio.version);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [conflict, setConflict] = useState(false);
  const alert = useRef<HTMLDivElement>(null);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { const value = await api<Portfolio>(`/api/v1/portfolios/${portfolio.id}`, { method: 'PATCH', headers: { 'If-Match': `"${version}"` }, body: JSON.stringify({ name: name.trim(), capital_vnd: capital }) }); onSaved(value); }
    catch (err) { setConflict(err instanceof ApiError && err.status === 412); setError((err as Error).message); requestAnimationFrame(() => alert.current?.focus()); }
    finally { setBusy(false); }
  }
  async function reload() {
    setBusy(true);
    try { const latest = await api<Portfolio>(`/api/v1/portfolios/${portfolio.id}`); setName(latest.name); setCapital(latest.capital_vnd); setVersion(latest.version); setConflict(false); setError(''); onReload?.(); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <form className="panel plan-information-editor" onSubmit={submit} aria-busy={busy}>
    <h2>Thông tin kế hoạch</h2><p className="muted">Sau khi sửa tên hoặc vốn, hãy tạo đề xuất mới để dùng thông tin vừa lưu.</p>
    {error && <div className="error" role="alert" tabIndex={-1} ref={alert} data-testid={conflict ? 'conflict-notice' : 'edit-error'}><strong>{conflict ? 'Danh mục đã thay đổi ở nơi khác' : 'Chưa lưu được thay đổi'}</strong><p>{conflict ? 'Tải phiên bản mới trước khi sửa tiếp. Thao tác này thay nội dung biểu mẫu bằng thông tin mới nhất.' : error}</p>{conflict && <button type="button" className="quiet" onClick={reload} disabled={busy}>Tải phiên bản mới</button>}</div>}
    <div className="form-grid"><label>Tên danh mục<input data-testid="portfolio-name-input" required minLength={1} maxLength={120} value={name} onChange={e => setName(e.target.value)} disabled={busy}/></label><label>Vốn kế hoạch (VND)<input data-testid="portfolio-capital-input" type="number" required min="1" max="10000000000000000000" step="1" value={capital} onChange={e => setCapital(e.target.value)} disabled={busy}/></label></div>
    <TaskActions><button data-testid="edit-portfolio-submit" disabled={busy || conflict || !name.trim()}>{busy ? 'Đang lưu…' : 'Lưu thay đổi'}</button><a className="button quiet" href={workspaceHash({ view: 'overview', portfolioId: portfolio.id })}>Hủy chỉnh sửa</a></TaskActions>
  </form>;
}

export function TargetHistory({ portfolioId, fetchPage, assets }: { portfolioId: string; fetchPage: PageApi; assets?: AssetCatalogItem[] }) {
  const [offset, setOffset] = useState(0), [openedId, setOpenedId] = useState<string | null>(null);
  const { data, busy, error, retry } = usePage<Target>(fetchPage, `/api/v1/portfolios/${portfolioId}/targets?limit=10&offset=${offset}`);
  return <section className="panel target-history" data-testid="target-history" aria-busy={busy}><h2>Các mục tiêu đã chấp nhận</h2><p className="muted">Bản lưu thể hiện quyết định tại thời điểm chấp nhận, kể cả khi dữ liệu đề xuất đã hết hạn.</p>{error ? <div role="alert"><p>{error}</p><button className="quiet" onClick={retry}>Thử lại</button></div> : <>
    {busy ? <p role="status">Đang tải lịch sử…</p> : data.items.length ? <ol className="target-timeline">{data.items.map(item => {
      const expanded = openedId === item.id;
      const panelId = `target-allocation-${item.id}`;
      return <li key={item.id} data-expanded={expanded || undefined} data-testid={'target-row-' + item.id}>
        <div className="target-timeline-row">
          <div><strong><time dateTime={item.accepted_at}>{dateTime(item.accepted_at)}</time></strong><p className="muted small">Phiên bản {item.portfolio_version} · {money(item.allocation.capital_vnd)}</p></div>
          <button type="button" className="quiet" onClick={() => setOpenedId(expanded ? null : item.id)} aria-expanded={expanded} aria-controls={expanded ? panelId : undefined}>{expanded ? 'Thu gọn mục tiêu' : 'Xem mục tiêu'}</button>
        </div>
        {expanded && <section id={panelId} className="historical-allocation" aria-labelledby={`${panelId}-title`}>
          <h3 id={`${panelId}-title`}>Phân bổ đã lưu</h3>
          <AllocationView allocation={item.allocation} assets={assets} presentation="chart" summaryFirst capitalLabel="Vốn tại thời điểm chấp nhận"/>
        </section>}
      </li>;
    })}</ol> : <div className="empty-state compact"><h3>Chưa có mục tiêu đã lưu</h3><p>Tạo và chấp nhận một đề xuất để bắt đầu lịch sử.</p></div>}
    <Pagination total={data.total} offset={offset} onChange={value => { setOffset(value); setOpenedId(null); }} busy={busy}/>
  </>}</section>;
}

export function ProposalHistory({ portfolioId, fetchPage, selectedId }: { portfolioId: string; fetchPage: PageApi; selectedId?: string }) {
  const [offset, setOffset] = useState(0), [compare, setCompare] = useState<string[]>([]);
  const { data, busy, error, retry } = usePage<Recommendation>(fetchPage, `/api/v1/portfolios/${portfolioId}/recommendations?limit=10&offset=${offset}`);
  return <section id="proposal-history" tabIndex={-1} className="panel proposal-history" aria-busy={busy}><h2>Lịch sử đề xuất</h2><p className="muted small">Chọn hai đề xuất để so sánh tỷ trọng và nguồn dữ liệu.</p>{error ? <div role="alert"><p>{error}</p><button className="quiet" onClick={retry}>Thử lại</button></div> : <>
    {data.items.length ? <ol className="proposal-list">{data.items.map(item => {
      const expired = Date.parse(item.valid_until ?? '') <= Date.now();
      return <li key={item.id} data-testid={'proposal-row-' + item.id}>
        <h3 title={item.id}>{item.strategy} · {item.id.slice(0, 8)}{expired && ' · Đã hết hạn'}{selectedId === item.id && ' · Đang xem'}</h3>
        <p>Ngày dữ liệu {item.as_of_date ? <time dateTime={item.as_of_date}>{item.as_of_date}</time> : 'chưa xác định'} · Vốn tại lần tính {money(item.capital_vnd)} · Phiên bản {item.portfolio_version}</p>
        <div className="actions">
          <a className="button" href={workspaceHash({ view: 'proposal', portfolioId, proposalId: item.id })}>{expired ? 'Mở phân bổ cũ' : 'Xem đề xuất'}</a>
          <label className="row-check-hit"><input className="row-check" type="checkbox" aria-label={`So sánh đề xuất ${item.id}`} checked={compare.includes(item.id)} disabled={!compare.includes(item.id) && compare.length === 2} onChange={event => setCompare(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))}/>So sánh</label>
        </div>
      </li>;
    })}</ol> : <p className="muted">{busy ? 'Đang tải lịch sử…' : 'Chưa có đề xuất.'}</p>}
    <div className="actions comparison-selection"><span className="muted small" role="status">Đã chọn {compare.length}/2 đề xuất</span>{compare.length === 2 ? <a className="button" href={workspaceHash({ view: 'compare', portfolioId, compareIds: [compare[0], compare[1]] })}>So sánh đề xuất</a> : <button disabled>Chọn {2 - compare.length} đề xuất để so sánh</button>}</div>
    <Pagination total={data.total} offset={offset} onChange={setOffset} busy={busy}/>

  </>}</section>;
}

export function ComparisonTable({ items }: { items: [Recommendation, Recommendation] }) {
  const [a, b] = items, differences = comparisonDifferences(a, b);
  const assets = [...new Set([...a.asset_ids, ...b.asset_ids])];
  const weight = (item: Recommendation, asset: string) => { const index = item.asset_ids.indexOf(asset); return index < 0 ? 0 : Number(item.weights[index]); };
  const rows = assets.map(asset => {
    const from = weight(a, asset), to = weight(b, asset);
    return { asset, from, to, change: to - from };
  });
  const changes = rows.filter(row => row.change !== 0).sort((left, right) => Math.abs(right.change) - Math.abs(left.change));
  const maxPoints = Math.abs(changes[0]?.change ?? 0) * 100;
  const limit = [.01, .02, .05, .1, .2, .5, 1, 2, 5, 10, 20, 25, 50, 100].find(value => value >= maxPoints) ?? Math.ceil(maxPoints);
  const tick = limit.toLocaleString('vi-VN');
  const increased = changes.filter(row => row.change > 0).length;
  const delta = (change: number) => {
    if (change && Math.abs(change) < .0001) return change > 0 ? 'Tăng <0,01 điểm %' : 'Giảm <0,01 điểm %';
    return `${change > 0 ? '+' : change < 0 ? '−' : ''}${weightPercentage(Math.abs(change)).slice(0, -1)} điểm %`;
  };
  return <section className="comparison-workspace" data-testid="comparison">
    <aside className={`notice ${differences.length ? 'warning' : ''}`}><strong>{differences.length ? 'Các phương án khác cơ sở đầu vào' : 'Các phương án có cùng cơ sở đầu vào được ghi nhận'}</strong><p>{differences.length > 0 && <>Khác nhau về {differences.join(', ')}. </>}Bảng so sánh thể hiện thay đổi về phân bổ và vốn kế hoạch.</p></aside>
    <div className="comparison-analysis">
      <div className="comparison-context">{items.map((item, index) => <div key={item.id}><h3><span>Phương án {index === 0 ? 'A' : 'B'}</span></h3><strong>{money(item.capital_vnd)}</strong><p>Vốn kế hoạch</p><p>{item.as_of_date ? <>Dữ liệu <time dateTime={item.as_of_date}>{item.as_of_date}</time></> : 'Chưa xác định ngày dữ liệu'}</p></div>)}</div>
      <section className="panel comparison-chart"><h2>Thay đổi tỷ trọng · B trừ A</h2>
      {!changes.length ? <p>{rows.length ? 'Tỷ trọng giống nhau ở tất cả tài sản.' : 'Chưa có tài sản để so sánh.'}</p> : <>
        <p className="weight-chart-summary">{increased} tài sản tăng · {changes.length - increased} giảm{rows.length > changes.length && <> · {rows.length - changes.length} giữ nguyên</>}</p>
        <div className="weight-chart-plot">
          <p className="comparison-axis-caption">Điểm phần trăm · Giảm bên trái, tăng bên phải</p>
          <div className="weight-chart-axis" aria-hidden="true"><span style={{ left: '0%' }}>−{tick}</span><span style={{ left: '50%' }}>0</span><span style={{ left: '100%' }}>+{tick}</span></div>
          <ul aria-label="Chênh lệch tỷ trọng theo tài sản">{changes.map(({ asset, from, to, change }) => <li key={asset}>
            <div className="comparison-bar-label"><strong>{asset}</strong><span><span className="sr-only">Phương án </span>A {weightPercentage(from)} <span aria-hidden="true">→</span> B {weightPercentage(to)}</span><strong data-direction={change < 0 ? 'decrease' : 'increase'}>{delta(change)}</strong></div>
            <div className="comparison-bar" aria-hidden="true"><span data-direction={change < 0 ? 'decrease' : 'increase'} style={{ width: `${Math.abs(change) * 100 / limit * 50}%` }}/></div>
          </li>)}</ul>
        </div>
      </>}
      </section>
    </div>
    <details className="allocation-details"><summary>Xem bảng so sánh · {rows.length} tài sản</summary><div className="table-wrap comparison-wrap"><table className="comparison-table"><caption className="sr-only">So sánh tỷ trọng và vốn mục tiêu của hai phương án</caption><thead><tr><th scope="col">Tài sản</th><th scope="col">Phương án A</th><th scope="col">Phương án B</th><th scope="col">Δ B − A</th></tr></thead><tbody>
      {rows.map(({ asset, from, to, change }) => <tr key={asset}><th scope="row">{asset}</th>{[from, to].map((value, index) => <td key={items[index].id} data-label={`Phương án ${index === 0 ? 'A' : 'B'}`}>{weightPercentage(value)}<small className="muted">{money(Number(items[index].capital_vnd) * value)}</small></td>)}<td className="comparison-delta" data-label="Δ B − A">{delta(change)}</td></tr>)}
    </tbody><tfoot><tr><th scope="row">Tổng</th>{items.map(item => <td key={item.id} data-label={item.id === a.id ? 'A · Tổng' : 'B · Tổng'}>{percentage(item.weights.reduce<number>((sum, value) => sum + Number(value), 0))}<small>{money(Number(item.capital_vnd) * item.weights.reduce<number>((sum, value) => sum + Number(value), 0))}</small></td>)}<td>—</td></tr></tfoot></table></div></details>
    <p className="muted small">Chênh lệch phân bổ không thể hiện lợi nhuận hoặc mức vượt trội. Số hiển thị được làm tròn.</p>
    <details className="allocation-details"><summary>Xem hồ sơ và ngày dữ liệu</summary><div className="table-wrap"><table className="comparison-pins"><thead><tr><th scope="col">Cơ sở</th><th scope="col">A</th><th scope="col">B</th></tr></thead><tbody>
      <tr><th scope="row">Ngày dữ liệu</th>{items.map(item => <td key={item.id}>{item.as_of_date ?? 'Chưa xác định'}</td>)}</tr>
      <tr><th scope="row">Hồ sơ rủi ro</th>{items.map(item => <td key={item.id}>{profileName(item.risk_profile?.profile)}</td>)}</tr>
      <tr><th scope="row">Phiên bản danh mục</th>{items.map(item => <td key={item.id}>{item.portfolio_version}</td>)}</tr>
    </tbody></table></div></details>
    <TaskActions label="Mở phương án để quyết định" hint="Chọn A hoặc B để xem lại; so sánh không tự chấp nhận mục tiêu.">{items.map((item, index) => <a className="button quiet" key={item.id} href={workspaceHash({ view: 'proposal', portfolioId: item.portfolio_id, proposalId: item.id })}>Mở {index === 0 ? 'A' : 'B'} để xem lại</a>)}</TaskActions>
  </section>;
}
