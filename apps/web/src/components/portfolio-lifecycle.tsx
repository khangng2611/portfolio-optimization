'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { AllocationView, money, profileName } from './allocation-view';
import { ApiError, dateTime, type Api, type Page, type PageApi, type Portfolio, type Recommendation, type Target } from '../lib/portfolio-types';
import { comparisonDifferences, workspaceHash, type Readiness, type WorkspaceView } from '../lib/workspace-state';

export function Pagination({ total, offset, limit = 10, onChange, busy = false }: { total: number; offset: number; limit?: number; onChange: (offset: number) => void; busy?: boolean }) {
  return <nav className="pagination" aria-label="Phân trang"><button className="quiet" disabled={busy || offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Trang trước</button><span role="status">Trang {Math.floor(offset / limit) + 1} · {total} kết quả</span><button className="quiet" disabled={busy || offset + limit >= total} onClick={() => onChange(offset + limit)}>Trang sau</button></nav>;
}
export function ReadinessNotice({ value, onRefresh, busy = false, failed = false }: { value: Readiness | null; onRefresh: () => void; busy?: boolean; failed?: boolean }) {
  const expired = value?.status === 'EXPIRED';
  return <aside className={`readiness notice ${value?.status !== 'READY' ? 'warning' : ''}`} data-testid={expired ? 'expired-input-notice' : 'readiness-notice'} aria-label="Tình trạng dữ liệu và model">
    <div><strong>{!value ? failed ? 'Chưa kiểm tra được dữ liệu' : 'Đang kiểm tra dữ liệu' : expired ? 'Dữ liệu đã hết hiệu lực' : value.status !== 'READY' ? 'Dữ liệu chưa sẵn sàng' : 'Dữ liệu sẵn sàng'}</strong>
      <p>{value ? `${value.universe_id} · ${value.demo ? 'Dữ liệu minh họa' : value.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}${value.as_of_date ? ` · Ngày dữ liệu ${value.as_of_date}` : ''}` : 'Kiểm tra bộ dữ liệu trước khi gửi yêu cầu.'}</p>
      {value?.valid_until && <p>Hiệu lực đến {dateTime(value.valid_until)} · GMT+7</p>}
      {value?.checked_at && <p className="muted small">Đã kiểm tra {dateTime(value.checked_at)} · GMT+7</p>}
      {value?.status !== 'READY' && <p>{expired ? 'Cần bản dữ liệu mới. Mục tiêu đã lưu vẫn được giữ trong lịch sử.' : 'Thử kiểm tra lại. Nếu tình trạng chưa thay đổi, cần người vận hành cập nhật dữ liệu.'}</p>}
      {value?.status === 'READY' && <ul className="capability-list">{value.strategies.map(s => <li key={s.strategy}><span className={`badge ${s.available ? 'success' : ''}`}>{s.strategy === 'BL_ML' ? 'BL + ML' : s.strategy} · {s.available ? 'Sẵn sàng' : s.reason_code === 'MODEL_UNAVAILABLE' ? 'Chờ model được duyệt' : 'Chưa sẵn sàng'}</span></li>)}</ul>}
    </div><button className="quiet" onClick={onRefresh} disabled={busy}>{busy ? 'Đang kiểm tra…' : 'Kiểm tra lại'}</button>
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
export function PortfolioList({ fetchPage, destination = 'overview' }: { fetchPage: PageApi; destination?: WorkspaceView }) {
  const [query, setQuery] = useState(''), [search, setSearch] = useState(''), [risk, setRisk] = useState('all'), [sort, setSort] = useState('created_desc'), [offset, setOffset] = useState(0);
  useEffect(() => { const timer = setTimeout(() => { setSearch(query.trim()); setOffset(0); }, 250); return () => clearTimeout(timer); }, [query]);
  const params = new URLSearchParams({ limit: '10', offset: String(offset), q: search, risk_profile: risk, sort });
  const { data, busy, error, retry } = usePage<Portfolio>(fetchPage, '/api/v1/portfolios?' + params);
  return <>
    <section className="panel portfolio-list" aria-label="Danh sách danh mục" aria-busy={busy}>
      <div className="list-toolbar"><label>Tìm trong danh sách<input type="search" placeholder="Tìm theo tên hoặc mã…" maxLength={120} value={query} onChange={e => setQuery(e.target.value)}/></label><label>Lọc theo hồ sơ<select value={risk} onChange={e => { setRisk(e.target.value); setOffset(0); }}><option value="all">Tất cả hồ sơ</option><option value="conservative">Thận trọng</option><option value="balanced">Cân bằng</option><option value="growth">Tăng trưởng</option><option value="manual">Tùy chỉnh</option></select></label><label>Sắp xếp danh mục<select value={sort} onChange={e => { setSort(e.target.value); setOffset(0); }}><option value="created_desc">Mới tạo trước</option><option value="name_asc">Tên A → Z</option><option value="capital_desc">Vốn giảm dần</option></select></label></div>
      {error ? <div role="alert" className="error"><p>{error}</p><button className="quiet" onClick={retry}>Thử lại</button></div> : <>
        {busy && <p role="status" className="muted">Đang tải danh mục…</p>}
        {!busy && !data.items.length ? <div className="empty-state compact"><h2>{search || risk !== 'all' ? 'Không tìm thấy danh mục' : 'Chưa có danh mục'}</h2><p>Thử điều chỉnh bộ lọc hoặc tạo một kế hoạch mới.</p>{(search || risk !== 'all') && <button className="quiet" onClick={() => { setQuery(''); setSearch(''); setRisk('all'); setOffset(0); }}>Xóa bộ lọc</button>}</div> : <div className="table-wrap mobile-cards"><table><caption>Danh mục của bạn · Vốn kế hoạch do bạn cung cấp.</caption><thead><tr><th>Danh mục</th><th>Hồ sơ rủi ro</th><th>Vốn kế hoạch</th><th>Bộ tài sản</th><th><span className="sr-only">Thao tác</span></th></tr></thead><tbody>{data.items.map(item => <tr key={item.id}><th scope="row"><a href={workspaceHash({ view: destination, portfolioId: item.id })}>{item.name}</a><small className="muted">Phiên bản {item.version}</small></th><td data-label="Hồ sơ rủi ro"><span className="badge">{profileName(item.risk_profile?.profile)}</span></td><td data-label="Vốn kế hoạch">{money(item.capital_vnd)}</td><td data-label="Bộ tài sản">{item.universe_id}</td><td><a className="button quiet" href={workspaceHash({ view: destination, portfolioId: item.id })} aria-label={`Mở danh mục ${item.name}`}>Mở danh mục</a></td></tr>)}</tbody></table></div>}
        <Pagination total={data.total} offset={offset} onChange={setOffset} busy={busy}/>
      </>}
    </section><div className="actions"><a className="button" href="#create">Tạo danh mục</a></div>
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
    <p className="muted small">Phiên bản {version} · Hồ sơ rủi ro và policy giữ nguyên.</p><div className="actions"><button data-testid="edit-portfolio-submit" disabled={busy || conflict || !name.trim()}>{busy ? 'Đang lưu…' : 'Lưu thay đổi'}</button><a className="button quiet" href={workspaceHash({ view: 'overview', portfolioId: portfolio.id })}>Hủy chỉnh sửa</a></div>
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
  return <section className="panel proposal-history" aria-busy={busy}><h2>Lịch sử đề xuất</h2><p className="muted small">Chọn hai đề xuất để so sánh tỷ trọng và nguồn dữ liệu.</p>{error ? <div role="alert"><p>{error}</p><button className="quiet" onClick={retry}>Thử lại</button></div> : <>
    {!data.items.length && !busy ? <p className="muted">Chưa có đề xuất.</p> : <div className="table-wrap"><table><caption>Đề xuất thuộc danh mục hiện tại</caption><thead><tr><th>So sánh</th><th>Phương pháp</th><th>Ngày dữ liệu</th><th>Phiên bản</th><th><span className="sr-only">Mở đề xuất</span></th></tr></thead><tbody>{data.items.map(item => <tr key={item.id} data-testid={'proposal-row-' + item.id}><td><label className="row-check-hit"><input className="row-check" type="checkbox" aria-label={`So sánh đề xuất ${item.id}`} checked={compare.includes(item.id)} disabled={!compare.includes(item.id) && compare.length === 2} onChange={event => setCompare(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))}/></label></td><th scope="row">{item.strategy}{selectedId === item.id && <span className="sr-only"> · Đang xem</span>}</th><td>{item.as_of_date}</td><td>{item.portfolio_version}</td><td><a className="button quiet" href={workspaceHash({ view: 'proposal', portfolioId, proposalId: item.id })}>Xem đề xuất</a></td></tr>)}</tbody></table></div>}
    <Pagination total={data.total} offset={offset} onChange={setOffset} busy={busy}/>
    <div className="actions">{compare.length === 2 ? <a className="button" href={workspaceHash({ view: 'compare', portfolioId, compareIds: [compare[0], compare[1]] })}>So sánh đề xuất</a> : <button disabled>Chọn {2 - compare.length} đề xuất để so sánh</button>}</div>
  </>}</section>;
}

export function ComparisonTable({ items }: { items: [Recommendation, Recommendation] }) {
  const [a, b] = items, differences = comparisonDifferences(a, b);
  const assets = [...new Set([...a.asset_ids, ...b.asset_ids])];
  const weight = (item: Recommendation, asset: string) => { const index = item.asset_ids.indexOf(asset); return index < 0 ? 0 : Number(item.weights[index]); };
  return <section className="panel" data-testid="comparison"><aside className={`notice ${differences.length ? 'warning' : ''}`}><strong>{differences.length ? 'Các phương án khác cơ sở đầu vào' : 'Các phương án có cùng cơ sở đầu vào được ghi nhận'}</strong><p>{differences.length ? `Khác: ${differences.join(', ')}. ` : ''}Đây là tỷ trọng và vốn kế hoạch, không phải hiệu suất đầu tư. Không suy ra phương án tốt hơn từ các lần tính khác điều kiện.</p></aside>
    <div className="table-wrap"><table className="comparison-table"><caption>So sánh hai phương án · Dữ liệu trả về từ backend</caption><thead><tr><th>Chỉ tiêu</th>{items.map(item => <th key={item.id}>{item.strategy}<small className="muted">{item.id.slice(0, 8)}</small></th>)}</tr></thead><tbody>
      {([['Ngày dữ liệu', 'as_of_date'], ['Policy', 'policy_version_id'], ['Phiên bản danh mục', 'portfolio_version'], ['Snapshot dữ liệu', 'data_snapshot_id'], ['Bộ input', 'bundle_hash'], ['Core', 'core_version'], ['Model', 'model_bundle_id']] as const).map(([label, key]) => <tr key={key}><th scope="row">{label}</th>{items.map(item => <td key={item.id}>{item[key] ?? '—'}</td>)}</tr>)}
      <tr><th scope="row">Vốn kế hoạch</th>{items.map(item => <td key={item.id}>{money(item.capital_vnd)}</td>)}</tr>
      {assets.map(asset => <tr key={asset}><th scope="row">{asset}</th>{items.map(item => <td key={item.id}>{(weight(item, asset) * 100).toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%<small className="muted">{money(Number(item.capital_vnd) * weight(item, asset))}</small></td>)}</tr>)}
    </tbody></table></div>
  </section>;
}
