'use client';
import { ActionIcon, IconButton } from './action-controls';
import { TaskActions } from './task-actions';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { AllocationView, money, percentage, profileName, strategyName } from './allocation-view';
import { ApiError, dateTime, type Api, type Page, type PageApi, type Portfolio, type Recommendation, type Target } from '../lib/portfolio-types';
import { comparisonDifferences, workspaceHash, type Readiness, type WorkspaceView } from '../lib/workspace-state';

export function Pagination({ total, offset, limit = 10, onChange, busy = false }: { total: number; offset: number; limit?: number; onChange: (offset: number) => void; busy?: boolean }) {
  if (offset === 0 && total <= limit) return total ? <p className="pagination-summary" role="status">{total} kết quả</p> : null;
  return <nav className="pagination" aria-label="Phân trang"><IconButton icon="previous" label="Trang trước" disabled={busy || offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}/><span role="status">Trang {Math.floor(offset / limit) + 1} · {total} kết quả</span><IconButton icon="next" label="Trang sau" disabled={busy || offset + limit >= total} onClick={() => onChange(offset + limit)}/></nav>;
}
export function ReadinessNotice({ value, onRefresh, busy = false, failed = false }: { value: Readiness | null; onRefresh: () => void; busy?: boolean; failed?: boolean }) {
  const expired = value?.status === 'EXPIRED';
  return <aside className={`readiness notice ${value?.status !== 'READY' ? 'warning' : ''}`} data-testid={expired ? 'expired-input-notice' : 'readiness-notice'} aria-label="Tình trạng dữ liệu và model">
    <div><strong>{!value ? failed ? 'Chưa kiểm tra được dữ liệu' : 'Đang kiểm tra dữ liệu' : expired ? 'Dữ liệu đã hết hiệu lực' : value.status !== 'READY' ? 'Dữ liệu chưa sẵn sàng' : 'Dữ liệu sẵn sàng'}</strong>
      <p>{value ? `${value.demo ? 'Dữ liệu minh họa' : value.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}${value.as_of_date ? ` · Ngày dữ liệu ${value.as_of_date}` : ''}` : 'Kiểm tra bộ dữ liệu trước khi gửi yêu cầu.'}</p>
      <details className="readiness-detail"><summary>Điều kiện & hiệu lực dữ liệu</summary>{value && <p>Bộ tài sản: {value.universe_id}</p>}{value?.valid_until && <p>Hiệu lực đến {dateTime(value.valid_until)} · GMT+7</p>}
      {value?.checked_at && <p className="muted small">Đã kiểm tra {dateTime(value.checked_at)} · GMT+7</p>}
      {value?.status === 'READY' && <ul className="capability-list">{value.strategies.map(s => <li key={s.strategy}><span className={`badge ${s.available ? 'success' : ''}`}>{s.strategy === 'BL_ML' ? 'BL + ML' : s.strategy} · {s.available ? 'Sẵn sàng' : s.reason_code === 'MODEL_UNAVAILABLE' ? 'Chờ model được duyệt' : 'Chưa sẵn sàng'}</span></li>)}</ul>}
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
  return firstUse ? <div className="portfolio-onboarding"><h2>Bắt đầu từ một danh mục</h2><p className="muted">Cho biết kế hoạch và khả năng chịu rủi ro để xem phương án phân bổ phù hợp với các giới hạn của bạn.</p><ol className="first-use-steps"><li><strong>Thông tin kế hoạch</strong><span>Vốn dự định và thời gian đầu tư.</span></li><li><strong>Khả năng chịu rủi ro</strong><span>Bạn chủ động chọn câu trả lời theo khả năng thực tế.</span></li><li><strong>Xem lại và xác nhận</strong><span>Sau đó bạn có thể tạo đề xuất phân bổ.</span></li></ol><a className="button" href="#create">Tạo danh mục đầu tiên</a><p className="muted small">Chấp nhận mục tiêu chỉ lưu tỷ trọng, không thực hiện giao dịch.</p></div>
    : <div className="empty-state compact"><h2>Không tìm thấy danh mục</h2><p>Thử tên khác hoặc xóa điều kiện tìm kiếm để xem lại danh sách.</p><button className="quiet" onClick={onClear}>Xóa bộ lọc</button></div>;
}
export function PortfolioList({ fetchPage, destination = 'overview', mode = 'manage', onInventoryEmpty }: { fetchPage: PageApi; destination?: WorkspaceView; mode?: 'manage' | 'choose'; onInventoryEmpty?: (empty: boolean) => void }) {
  const [query, setQuery] = useState(''), [search, setSearch] = useState(''), [risk, setRisk] = useState('all'), [sort, setSort] = useState('created_desc'), [offset, setOffset] = useState(0);
  useEffect(() => { const timer = setTimeout(() => { setSearch(query.trim()); setOffset(0); }, 250); return () => clearTimeout(timer); }, [query]);
  const params = new URLSearchParams({ limit: '10', offset: String(offset), q: search, risk_profile: risk, sort });
  const { data, busy, error, retry } = usePage<Portfolio>(fetchPage, '/api/v1/portfolios?' + params);
  const firstUse = !busy && !error && data.total === 0 && offset === 0 && !search && risk === 'all';
  useEffect(() => { if (!busy && !error && !search && risk === 'all' && offset === 0) onInventoryEmpty?.(data.total === 0); }, [busy, error, search, risk, offset, data.total, onInventoryEmpty]);
  return <>
    {mode === 'choose' && !firstUse && <p className="portfolio-selection-guidance muted">{['profile', 'risk-assessment'].includes(destination) ? 'Hồ sơ rủi ro được lưu theo từng danh mục. Chọn kế hoạch bạn muốn xem.' : 'Chọn danh mục bạn muốn tiếp tục làm việc.'}</p>}
    <section className={`panel portfolio-list ${mode === 'choose' ? 'portfolio-context-picker' : 'portfolio-management'} ${firstUse ? 'portfolio-first-use' : ''}`} aria-label={mode === 'choose' ? 'Chọn danh mục' : 'Danh sách danh mục'} aria-busy={busy}>
      {!firstUse && <div className="portfolio-toolbar"><label className="portfolio-search"><span className="sr-only">Tìm trong danh sách</span><ActionIcon name="search"/><input type="search" placeholder="Tìm theo tên hoặc mã…" maxLength={120} value={query} onChange={e => setQuery(e.target.value)}/></label>{mode === 'manage' && <><label className="portfolio-risk-filter"><span className="sr-only">Lọc theo hồ sơ</span><ActionIcon name="filter"/><select value={risk} onChange={e => { setRisk(e.target.value); setOffset(0); }}><option value="all">Tất cả hồ sơ</option><option value="conservative">Thận trọng</option><option value="balanced">Cân bằng</option><option value="growth">Tăng trưởng</option><option value="manual">Tùy chỉnh</option></select></label><label className="portfolio-sort"><span className="sr-only">Sắp xếp danh mục</span><ActionIcon name="sort"/><select value={sort} onChange={e => { setSort(e.target.value); setOffset(0); }}><option value="created_desc">Mới tạo trước</option><option value="name_asc">Tên A → Z</option><option value="capital_desc">Vốn giảm dần</option></select></label><a className="button portfolio-create" href="#create">Tạo danh mục</a></>}</div>}
      {error ? <div role="alert" className="error"><p>{error}</p><button className="quiet" onClick={retry}>Thử lại</button></div> : <>
        {busy && <p role="status" className="muted">Đang tải danh mục…</p>}
        {!busy && !data.items.length ? <PortfolioEmptyState firstUse={firstUse} onClear={() => { setQuery(''); setSearch(''); setRisk('all'); setOffset(0); }}/> : mode === 'choose' ? <ul className="portfolio-choices" aria-label="Danh mục có thể chọn">{data.items.map(item => <li key={item.id}><a className="portfolio-choice" href={workspaceHash({ view: destination, portfolioId: item.id })} aria-label={`Chọn danh mục ${item.name}`}><span className="portfolio-choice-summary"><strong>{item.name}</strong><span className="portfolio-choice-profile">{profileName(item.risk_profile?.profile)}</span><span className="portfolio-choice-capital">{money(item.capital_vnd)}</span></span><span className="portfolio-choice-action" aria-hidden="true"><ActionIcon name="next"/></span></a></li>)}</ul> : <div className="table-wrap mobile-cards"><table className="portfolio-management-table"><caption className="sr-only">Danh mục của bạn · Vốn kế hoạch do bạn cung cấp.</caption><colgroup><col className="portfolio-name-col"/><col className="portfolio-risk-col"/><col className="portfolio-capital-col"/><col/><col className="portfolio-action-col"/></colgroup><thead><tr><th>Danh mục</th><th>Hồ sơ rủi ro</th><th className="portfolio-capital-cell">Vốn kế hoạch</th><th>Bộ tài sản</th><th><span className="sr-only">Thao tác</span></th></tr></thead><tbody>{data.items.map(item => <tr key={item.id}><th scope="row"><a href={workspaceHash({ view: destination, portfolioId: item.id })}>{item.name}</a><small className="muted">Phiên bản {item.version}</small></th><td data-label="Hồ sơ rủi ro"><span className="badge">{profileName(item.risk_profile?.profile)}</span></td><td className="portfolio-capital-cell" data-label="Vốn kế hoạch">{money(item.capital_vnd)}</td><td className="portfolio-universe-cell" data-label="Bộ tài sản">{item.universe_id}</td><td><a className="button quiet" href={workspaceHash({ view: destination, portfolioId: item.id })} aria-label={`Mở danh mục ${item.name}`}>Mở danh mục</a></td></tr>)}</tbody></table></div>}
        <Pagination total={data.total} offset={offset} onChange={setOffset} busy={busy}/>
      </>}
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
  return <form className="panel" onSubmit={submit} aria-busy={busy}>
    <h2>Thông tin kế hoạch</h2><p className="muted">Thay đổi tạo phiên bản danh mục mới. Mục tiêu đã lưu được giữ nguyên; đề xuất cũ cần được tính lại.</p>
    {error && <div className="error" role="alert" tabIndex={-1} ref={alert} data-testid={conflict ? 'conflict-notice' : 'edit-error'}><strong>{conflict ? 'Danh mục đã thay đổi ở nơi khác' : 'Chưa lưu được thay đổi'}</strong><p>{conflict ? 'Tải phiên bản mới trước khi sửa tiếp. Thao tác này thay nội dung biểu mẫu bằng thông tin mới nhất.' : error}</p>{conflict && <button type="button" className="quiet" onClick={reload} disabled={busy}>Tải phiên bản mới</button>}</div>}
    <div className="form-grid"><label>Tên danh mục<input data-testid="portfolio-name-input" required minLength={1} maxLength={120} value={name} onChange={e => setName(e.target.value)} disabled={busy}/></label><label>Vốn kế hoạch (VND)<input data-testid="portfolio-capital-input" type="number" required min="1" max="10000000000000000000" step="1" value={capital} onChange={e => setCapital(e.target.value)} disabled={busy}/></label></div>
    <p className="muted small">Phiên bản {version} · Hồ sơ rủi ro và policy giữ nguyên.</p><TaskActions hint="Thay đổi kế hoạch sẽ tạo một phiên bản danh mục mới."><button data-testid="edit-portfolio-submit" disabled={busy || conflict || !name.trim()}>{busy ? 'Đang lưu…' : 'Lưu thay đổi'}</button><a className="button quiet" href={workspaceHash({ view: 'overview', portfolioId: portfolio.id })}>Hủy chỉnh sửa</a></TaskActions>
  </form>;
}

export function TargetHistory({ portfolioId, fetchPage }: { portfolioId: string; fetchPage: PageApi }) {
  const [offset, setOffset] = useState(0), [opened, setOpened] = useState<Target | null>(null);
  const { data, busy, error, retry } = usePage<Target>(fetchPage, `/api/v1/portfolios/${portfolioId}/targets?limit=10&offset=${offset}`);
  return <section className="panel" data-testid="target-history" aria-busy={busy}><h2>Các mục tiêu đã chấp nhận</h2><p className="muted">Bản lưu thể hiện quyết định tại thời điểm chấp nhận, kể cả khi dữ liệu đề xuất đã hết hạn.</p>{error ? <div role="alert"><p>{error}</p><button className="quiet" onClick={retry}>Thử lại</button></div> : <>
    {busy ? <p role="status">Đang tải lịch sử…</p> : data.items.length ? <ol className="target-timeline">{data.items.map(item => <li key={item.id} data-testid={'target-row-' + item.id}><div><strong>{dateTime(item.accepted_at)}</strong><p className="muted small">Phiên bản {item.portfolio_version} · {item.allocation.strategy} · {money(item.allocation.capital_vnd)}</p></div><button className="quiet" onClick={() => setOpened(opened?.id === item.id ? null : item)} aria-expanded={opened?.id === item.id}>Xem mục tiêu</button></li>)}</ol> : <div className="empty-state compact"><h3>Chưa có mục tiêu đã lưu</h3><p>Tạo và chấp nhận một đề xuất để bắt đầu lịch sử.</p></div>}
    <Pagination total={data.total} offset={offset} onChange={value => { setOffset(value); setOpened(null); }} busy={busy}/>
    {opened && <div className="historical-allocation"><h3>Mục tiêu lưu {dateTime(opened.accepted_at)}</h3><AllocationView allocation={opened.allocation}/></div>}
  </>}</section>;
}

export function ProposalHistory({ portfolioId, fetchPage, selectedId }: { portfolioId: string; fetchPage: PageApi; selectedId?: string }) {
  const [offset, setOffset] = useState(0), [compare, setCompare] = useState<string[]>([]);
  const { data, busy, error, retry } = usePage<Recommendation>(fetchPage, `/api/v1/portfolios/${portfolioId}/recommendations?limit=10&offset=${offset}`);
  return <section id="proposal-history" tabIndex={-1} className="panel proposal-history" aria-busy={busy}><h2>Lịch sử đề xuất</h2><p className="muted small">Chọn hai đề xuất để so sánh tỷ trọng và nguồn dữ liệu.</p>{error ? <div role="alert"><p>{error}</p><button className="quiet" onClick={retry}>Thử lại</button></div> : <>
    <div className="actions comparison-selection"><span className="muted small" role="status">Đã chọn {compare.length}/2 đề xuất</span>{compare.length === 2 ? <a className="button" href={workspaceHash({ view: 'compare', portfolioId, compareIds: [compare[0], compare[1]] })}>So sánh đề xuất</a> : <button disabled>Chọn {2 - compare.length} đề xuất để so sánh</button>}</div>
    {!data.items.length && !busy ? <p className="muted">Chưa có đề xuất.</p> : <div className="table-wrap mobile-cards"><table><caption>Đề xuất thuộc danh mục hiện tại</caption><thead><tr><th>So sánh</th><th>Phương pháp</th><th>Ngày dữ liệu</th><th>Phiên bản</th><th><span className="sr-only">Mở đề xuất</span></th></tr></thead><tbody>{data.items.map(item => <tr key={item.id} data-testid={'proposal-row-' + item.id}><td><label className="row-check-hit"><input className="row-check" type="checkbox" aria-label={`So sánh đề xuất ${item.id}`} checked={compare.includes(item.id)} disabled={!compare.includes(item.id) && compare.length === 2} onChange={event => setCompare(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))}/></label></td><th scope="row">{strategyName(item.strategy)}{selectedId === item.id && <span className="sr-only"> · Đang xem</span>}</th><td data-label="Ngày dữ liệu">{item.as_of_date}</td><td data-label="Phiên bản">{item.portfolio_version}</td><td><a className="button quiet" href={workspaceHash({ view: 'proposal', portfolioId, proposalId: item.id })}>Xem đề xuất</a></td></tr>)}</tbody></table></div>}
    <Pagination total={data.total} offset={offset} onChange={setOffset} busy={busy}/>

  </>}</section>;
}

export function ComparisonTable({ items }: { items: [Recommendation, Recommendation] }) {
  const [a, b] = items, differences = comparisonDifferences(a, b);
  const assets = [...new Set([...a.asset_ids, ...b.asset_ids])];
  const weight = (item: Recommendation, asset: string) => { const index = item.asset_ids.indexOf(asset); return index < 0 ? 0 : Number(item.weights[index]); };
  const delta = (asset: string) => {
    const value = Math.round((weight(b, asset) - weight(a, asset)) * 1000) / 10;
    return `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} điểm %`;
  };
  return <section className="comparison-workspace" data-testid="comparison">
    <aside className={`notice ${differences.length ? 'warning' : ''}`}><strong>{differences.length ? 'Các phương án khác cơ sở đầu vào' : 'Các phương án có cùng cơ sở đầu vào được ghi nhận'}</strong><p>{differences.length ? `Khác: ${differences.join(', ')}. ` : ''}Đây là tỷ trọng và vốn kế hoạch, không phải hiệu suất đầu tư. Không suy ra phương án tốt hơn từ các lần tính khác điều kiện.</p></aside>
    <div className="comparison-context">{items.map((item, index) => <div key={item.id}><span className="badge">Phương án {index === 0 ? 'A' : 'B'}</span><h3>{strategyName(item.strategy)}</h3><strong>{money(item.capital_vnd)}</strong><p>Vốn kế hoạch · Ngày dữ liệu {item.as_of_date ?? 'Chưa xác định'}</p></div>)}</div><p className="muted small">Δ = B − A · đơn vị điểm phần trăm</p>
    <div className="table-wrap comparison-wrap"><table className="comparison-table"><caption className="sr-only">So sánh tỷ trọng và vốn mục tiêu của hai phương án</caption><thead><tr><th scope="col">Tài sản</th><th scope="col">A · {strategyName(a.strategy)}</th><th scope="col">B · {strategyName(b.strategy)}</th><th scope="col">Δ B − A</th></tr></thead><tbody>
      {assets.map(asset => <tr key={asset}><th scope="row">{asset}</th>{items.map((item, index) => <td key={item.id} data-label={`${index === 0 ? 'A' : 'B'} · ${strategyName(item.strategy)}`}>{percentage(weight(item, asset))}<small className="muted">{money(Number(item.capital_vnd) * weight(item, asset))}</small></td>)}<td className="comparison-delta" data-label="Δ B − A">{delta(asset)}</td></tr>)}
    </tbody><tfoot><tr><th scope="row">Tổng</th>{items.map(item => <td key={item.id} data-label={item.id === a.id ? 'A · Tổng' : 'B · Tổng'}>{percentage(item.weights.reduce<number>((sum, value) => sum + Number(value), 0))}<small>{money(Number(item.capital_vnd) * item.weights.reduce<number>((sum, value) => sum + Number(value), 0))}</small></td>)}<td>—</td></tr></tfoot></table></div>
    <p className="muted small">Chênh lệch phân bổ không thể hiện lợi nhuận hoặc mức vượt trội. Số hiển thị được làm tròn.</p>
    <TaskActions label="Mở phương án để quyết định" hint="Chọn A hoặc B để xem lại; so sánh không tự chấp nhận mục tiêu.">{items.map((item, index) => <a className="button quiet" key={item.id} href={workspaceHash({ view: 'proposal', portfolioId: item.portfolio_id, proposalId: item.id })}>Mở {index === 0 ? 'A' : 'B'} để xem lại</a>)}</TaskActions>
    <details className="allocation-details"><summary>Đối chiếu dữ liệu & phiên bản</summary><div className="table-wrap"><table className="comparison-pins"><thead><tr><th scope="col">Cơ sở</th><th scope="col">A</th><th scope="col">B</th></tr></thead><tbody>
      {([['Ngày dữ liệu', 'as_of_date'], ['Policy', 'policy_version_id'], ['Phiên bản danh mục', 'portfolio_version'], ['Snapshot dữ liệu', 'data_snapshot_id'], ['Bộ input', 'bundle_hash'], ['Core', 'core_version'], ['Model', 'model_bundle_id']] as const).map(([label, key]) => <tr key={key}><th scope="row">{label}</th>{items.map(item => <td key={item.id}>{item[key] ?? '—'}</td>)}</tr>)}
    </tbody></table></div></details>
  </section>;
}
