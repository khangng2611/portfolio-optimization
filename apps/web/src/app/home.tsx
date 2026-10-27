'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { MarketOperations } from '../components/market-operations';
import { marketTitles } from '../lib/market-types';
import { JobTrace } from '../components/job-trace';
import { AllocationView, money, profileName } from '../components/allocation-view';
import { RiskWizard, wizardTitles, type ReadyUniverse } from '../components/risk-wizard';
import { ComparisonTable, EditPortfolio, PortfolioList, ProposalHistory, ReadinessNotice, TargetHistory } from '../components/portfolio-lifecycle';
import { WorkspaceShell, Methodology } from '../components/workspace-shell';
import { ApiError, dateTime, type Dashboard, type Page, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { parseWorkspaceHash, proposalCompletionRoute, readinessAllows, workspaceHash, type Readiness, type WorkspaceRoute, type WorkspaceView } from '../lib/workspace-state';
import type { TraceReference } from '../lib/job-trace';

type Session = { user: { name: string; roles: string[] }; csrfToken: string };
type Job = TraceReference & { job_id: string; status: string; portfolio_id: string; recommendation_id?: string; error?: { message?: string } };
const terminal = (status: string) => ['SUCCEEDED', 'FAILED', 'CANCELLED', 'COMPLETED'].includes(status);
const resumeKey = 'portfolio.resume-destination';

export default function Home({ viewerBase }: { viewerBase: string | null }) {
  const [route, setRoute] = useState<WorkspaceRoute>({ view: 'overview' });
  const [session, setSession] = useState<Session | null>(null), [loaded, setLoaded] = useState(false), [expired, setExpired] = useState(false);
  const [selected, setSelected] = useState<Portfolio | null>(null), [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null), [readinessFailed, setReadinessFailed] = useState(false), [universes, setUniverses] = useState<ReadyUniverse[]>([]);
  const [detail, setDetail] = useState<Recommendation | null>(null), [comparison, setComparison] = useState<[Recommendation, Recommendation] | null>(null), [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false), [opening, setOpening] = useState(false), [proposalLoading, setProposalLoading] = useState(false), [error, setError] = useState(''), [conflict, setConflict] = useState(false);
  const [wizardStep, setWizardStep] = useState(0), [strategy, setStrategy] = useState('MVO'), [fallback, setFallback] = useState(false), [refresh, setRefresh] = useState(0), [historyVersion, setHistoryVersion] = useState(0), [clock, setClock] = useState(Date.now());
  const selection = useRef(0), heading = useRef<HTMLHeadingElement>(null), errorRef = useRef<HTMLDivElement>(null);
  const view = route.view;
  const marketView = view.startsWith('market');
  const operator = session?.user.roles.includes('data-operator') ?? false;
  const clearSession = useCallback((remember: boolean) => {
    selection.current++;
    if (remember) { try { sessionStorage.setItem(resumeKey, workspaceHash(parseWorkspaceHash(window.location.hash))); } catch { /* URL remains usable without storage. */ } }
    setSession(null); setSelected(null); setDashboard(null); setDetail(null); setComparison(null); setReadiness(null); setJob(null); setOpening(false); setProposalLoading(false); setUniverses([]); setWizardStep(0);
  }, []);
  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store', headers: { 'content-type': 'application/json', ...(session ? { 'x-csrf-token': session.csrfToken } : {}), ...init.headers } });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      if (response.status === 401) { clearSession(true); setExpired(true); }
      throw new ApiError(response.status, typeof body.error === 'string' ? body.error : body.error?.message ?? (typeof body.detail === 'string' ? body.detail : `Yêu cầu thất bại (${response.status}).`));
    }
    return response;
  }, [session, clearSession]);
  const api = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => (await request(path, init)).json(), [request]);
  const fetchPage = useCallback(async <T,>(path: string): Promise<Page<T>> => {
    const response = await request(path), items = await response.json() as T[];
    return { items, total: Number(response.headers.get('x-total-count') ?? items.length), limit: Number(response.headers.get('x-limit') ?? 10), offset: Number(response.headers.get('x-offset') ?? 0) };
  }, [request]);
  const navigate = useCallback((next: WorkspaceRoute) => { window.location.hash = workspaceHash(next); setRoute(next); setError(''); setConflict(false); }, []);
  const href = (next: WorkspaceView) => workspaceHash({ view: next, ...(['create', 'portfolios'].includes(next) ? {} : { portfolioId: route.portfolioId }) });
  useEffect(() => {
    const sync = () => { if (['#main-content', '#methodology'].includes(window.location.hash)) return; setRoute(parseWorkspaceHash(window.location.hash)); setError(''); setConflict(false); };
    sync(); window.addEventListener('hashchange', sync); return () => window.removeEventListener('hashchange', sync);
  }, []);
  useEffect(() => {
    let active = true;
    fetch('/auth/session', { cache: 'no-store' }).then(async response => {
      if (response.ok) { const data = await response.json(); if (!active) return; setSession(data); try { const resume = sessionStorage.getItem(resumeKey); sessionStorage.removeItem(resumeKey); if (resume && !window.location.hash && !parseWorkspaceHash(resume).invalid) navigate(parseWorkspaceHash(resume)); } catch { /* Resume is optional. */ } }
      else if (response.status === 401) { if (window.location.hash && !parseWorkspaceHash(window.location.hash).invalid) clearSession(true); }
      else throw new Error('Dịch vụ đăng nhập chưa sẵn sàng.');
    }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, [navigate, clearSession]);
  useEffect(() => { if (loaded) { heading.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); } }, [view, loaded]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 15000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (!session) return; let active = true;
    api<ReadyUniverse[]>('/api/v1/universes').then(values => { if (active) setUniverses(values); }).catch(() => { if (active) setUniverses([]); });
    return () => { active = false; };
  }, [session, api, refresh]);
  useEffect(() => {
    const epoch = ++selection.current;
    setSelected(null); setDashboard(null); setReadiness(null); setReadinessFailed(false); setDetail(null); setComparison(null); setJob(null);
    if (!session || !route.portfolioId || route.invalid) { setOpening(false); return; }
    setOpening(true); const path = `/api/v1/portfolios/${route.portfolioId}`;
    Promise.all([api<Dashboard>(path + '/dashboard'), api<Readiness>(path + '/readiness').catch(err => { if (selection.current === epoch && !(err instanceof ApiError && err.status === 401)) setReadinessFailed(true); return null; })])
      .then(([current, ready]) => { if (selection.current === epoch) { setSelected(current.portfolio); setDashboard(current); setReadiness(ready); } })
      .catch(err => { if (selection.current === epoch) setError(err.message); }).finally(() => { if (selection.current === epoch) setOpening(false); });
    return () => { if (selection.current === epoch) selection.current++; };
  }, [session, route.portfolioId, route.invalid, api, refresh]);
  const compareKey = route.compareIds?.join(',');
  useEffect(() => {
    if (!session || !selected || selected.id !== route.portfolioId) return;
    let active = true; setDetail(null); setComparison(null);
    const ids = view === 'compare' ? route.compareIds : view === 'proposal' && route.proposalId ? [route.proposalId] : null;
    if (!ids) { setProposalLoading(false); return; } setProposalLoading(true);
    Promise.all(ids.map(id => api<Recommendation>(`/api/v1/recommendations/${id}`))).then(items => {
      if (!active) return; if (items.some(item => item.portfolio_id !== selected.id)) throw new Error('Đề xuất không thuộc danh mục đang mở.');
      if (items.length === 2) setComparison(items as [Recommendation, Recommendation]); else setDetail(items[0]);
    }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setProposalLoading(false); });
    return () => { active = false; };
  }, [session, selected, route.portfolioId, route.proposalId, compareKey, view, api]);
  useEffect(() => {
    if (!job || terminal(job.status)) return; const epoch = selection.current; let active = true;
    const timer = setTimeout(async () => {
      try { const next = await api<Job>(`/api/v1/jobs/portfolio/${job.job_id}`); if (!active || epoch !== selection.current) return; const current = next.recommendation_id ? await api<Dashboard>(`/api/v1/portfolios/${job.portfolio_id}/dashboard`) : null; if (!active || epoch !== selection.current) return; if (current) { setSelected(current.portfolio); setDashboard(current); } setJob({ ...next, portfolio_id: job.portfolio_id }); if (next.recommendation_id) { setHistoryVersion(value => value + 1); const destination = proposalCompletionRoute(parseWorkspaceHash(window.location.hash), job.portfolio_id, next.recommendation_id); if (destination) navigate(destination); } }
      catch (err) { if (active && epoch === selection.current) { setError((err as Error).message); setJob(null); } }
    }, 1000); return () => { active = false; clearTimeout(timer); };
  }, [job, api, navigate]);
  async function createPortfolio(body: unknown) {
    setBusy(true); setError(''); try { const created = await api<Portfolio>('/api/v1/onboarding/portfolios', { method: 'POST', body: JSON.stringify(body) }); navigate({ view: 'overview', portfolioId: created.id }); return true; }
    catch (err) { setError((err as Error).message); return false; } finally { setBusy(false); }
  }
  const currentReadiness = readiness?.valid_until && Date.parse(readiness.valid_until) <= clock ? { ...readiness, status: 'EXPIRED' } : readiness;
  const canPropose = readinessAllows(currentReadiness, strategy, fallback);
  async function optimize() {
    if (!selected || !canPropose) return; const epoch = selection.current; setBusy(true); setError('');
    try { const result = await api<Job>(`/api/v1/portfolios/${selected.id}/recommendations`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ strategy, ...(strategy === 'BL_ML' && fallback ? { fallback_strategy: 'EW' } : {}) }) }); if (epoch === selection.current) setJob({ ...result, status: 'QUEUED', portfolio_id: selected.id }); }
    catch (err) { if (epoch === selection.current) { setError((err as Error).message); setReadiness(null); setReadinessFailed(true); } } finally { setBusy(false); }
  }
  async function acceptTarget() {
    if (!detail || !selected) return; const epoch = selection.current; setBusy(true); setError('');
    try { await api(`/api/v1/recommendations/${detail.id}/accept`, { method: 'POST', headers: { 'If-Match': `"${selected.version}"` }, body: '{}' }); const current = await api<Dashboard>(`/api/v1/portfolios/${selected.id}/dashboard`); if (epoch === selection.current) { setDashboard(current); setSelected(current.portfolio); setHistoryVersion(value => value + 1); } }
    catch (err) { if (epoch === selection.current) { setConflict(err instanceof ApiError && [409, 412].includes(err.status)); setError((err as Error).message); } } finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); try { const result = await api<{ providerRevoked: boolean }>('/auth/logout', { method: 'POST' }); clearSession(false); setExpired(false); try { sessionStorage.removeItem(resumeKey); } catch { /* Optional storage. */ } navigate({ view: 'overview' }); if (!result.providerRevoked) setError('Đã đóng phiên ứng dụng; Identity chưa xác nhận thu hồi token.'); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  const accepted = !!detail && dashboard?.accepted_target?.recommendation_id === detail.id;
  const stale = !!detail && !!selected && (detail.portfolio_version !== selected.version || !detail.valid_until || !(Date.parse(detail.valid_until) > clock));
  const waiting = busy || opening;
  const title = !session ? 'Đầu tư có kế hoạch. Quyết định có cơ sở.' : marketView ? marketTitles[view] : view === 'create' ? wizardTitles[wizardStep] : view === 'edit' ? 'Điều chỉnh kế hoạch của bạn' : view === 'history' ? 'Lịch sử mục tiêu' : view === 'compare' ? 'So sánh phương án trên cùng cơ sở' : view === 'proposal' ? detail ? stale && !accepted ? 'Đề xuất đã hết hiệu lực' : 'Một phân bổ để bạn cân nhắc' : 'Lập phương án phù hợp với bạn' : view === 'profile' ? 'Hồ sơ rủi ro của bạn' : view === 'portfolios' ? 'Danh mục của bạn' : selected?.name ?? 'Tổng quan kế hoạch đầu tư';
  const refreshData = () => { setError(''); setConflict(false); setRefresh(value => value + 1); };
  return <WorkspaceShell view={view} portfolioId={route.portfolioId} account={session?.user.name ?? null} busy={waiting} onLogout={logout} operator={operator} context={marketView ? 'Dữ liệu' : selected?.name ?? 'Danh mục'}>
    <header className="page-heading"><p className="eyebrow">{marketView && session ? 'DATA OPERATOR' : 'KẾ HOẠCH ĐẦU TƯ CỦA BẠN'}</p><h1 ref={heading} tabIndex={-1}>{title}</h1><p className="muted">{!session ? 'Tư vấn phân bổ tài sản cuối ngày cho thị trường Việt Nam.' : marketView ? 'Theo dõi nguồn, chất lượng và dữ liệu được phép dùng cho đề xuất.' : 'Xem lại dữ liệu và chủ động quyết định từng bước.'}</p></header>
    {error && <div ref={errorRef} tabIndex={-1} className="error" role="alert" data-testid={conflict ? 'conflict-notice' : 'request-error'}><strong>{conflict ? 'Thông tin đã thay đổi' : 'Chưa thể hoàn tất yêu cầu'}</strong><p>{error}</p>{conflict && <button className="quiet" onClick={refreshData}>Tải phiên bản mới</button>}</div>}
    {!loaded ? <section className="panel loading-state" role="status">Đang kiểm tra phiên…</section> : !session ? <>
      {expired && <aside className="notice warning" role="alert" data-testid="session-expired-notice"><strong>Phiên đăng nhập đã hết hạn</strong><p>Đăng nhập lại để mở đúng danh mục đang xem. Yêu cầu thay đổi sẽ không tự được gửi lại.</p><a className="button" href="/auth/login">Đăng nhập lại</a></aside>}
      <aside className="notice">Ứng dụng tư vấn phân bổ tài sản cuối ngày. Chấp nhận chỉ lưu tỷ trọng mục tiêu.</aside><section className="panel welcome-card"><p className="eyebrow">HIỂU RÕ TRƯỚC KHI QUYẾT ĐỊNH</p><h2>Từ nhu cầu của bạn<br/>đến một kế hoạch có thể theo dõi.</h2><p className="muted">Đánh giá rủi ro, xem đề xuất có nguồn và chủ động chọn mục tiêu.</p><ol className="journey-steps"><li>01 · Hiểu nhu cầu</li><li>02 · Review phương án</li><li>03 · Chủ động quyết định</li></ol></section><div className="actions"><a className="button" href="/auth/login">Đăng nhập qua Identity</a><a className="button quiet" href="#methodology" onClick={() => document.getElementById('methodology')?.setAttribute('open', '')}>Xem cách hoạt động</a></div>
    </> : route.invalid ? <section className="panel empty-state"><h2>Đường dẫn không hợp lệ</h2><a className="button" href="#portfolios">Danh mục của bạn</a></section> : marketView ? operator ? <MarketOperations route={route} api={api} fetchPage={fetchPage}/> : <section className="panel empty-state"><h2>Cần quyền data operator</h2><p>Tài khoản hiện tại chưa được cấp quyền vận hành dữ liệu.</p><a href="#portfolios">Về danh mục của bạn</a></section> : <>
      <div hidden={view !== 'create'}><aside className="notice">Xem lại câu trả lời trước khi xác nhận. Backend xác định hồ sơ và policy từ thông tin bạn cung cấp.</aside><RiskWizard busy={waiting} onCreate={createPortfolio} universes={universes} onStepChange={setWizardStep} onCancel={() => navigate({ view: 'portfolios' })}/></div>
      {view === 'create' ? null : opening ? <section className="panel loading-state" role="status">Đang mở danh mục…</section> : view === 'portfolios' || !route.portfolioId ? <PortfolioList fetchPage={fetchPage} destination={view === 'proposal' || view === 'profile' ? view : 'overview'}/> : !selected ? <section className="panel empty-state"><h2>Chưa mở được danh mục</h2><p>Kiểm tra quyền truy cập hoặc thử tải lại.</p><button onClick={refreshData}>Thử lại</button><a href="#portfolios">Về danh sách</a></section> : <>
        <nav className="portfolio-tabs" aria-label="Các phần của danh mục">{([['overview', 'Tổng quan'], ['proposal', 'Đề xuất'], ['history', 'Lịch sử mục tiêu'], ['edit', 'Sửa danh mục']] as const).map(([target, label]) => <a key={target} href={href(target)} aria-current={view === target ? 'page' : undefined}>{label}</a>)}</nav>
        <ReadinessNotice value={currentReadiness} onRefresh={refreshData} busy={opening} failed={readinessFailed}/>
        {view === 'edit' ? <EditPortfolio key={selected.id} portfolio={selected} api={api} onReload={refreshData} onSaved={value => { setSelected(value); refreshData(); navigate({ view: 'overview', portfolioId: value.id }); }}/>
          : view === 'history' ? <TargetHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage}/>
          : view === 'compare' ? proposalLoading ? <p role="status">Đang tải các phương án…</p> : comparison ? <><ComparisonTable items={comparison}/><div className="actions">{comparison.map(item => <a className="button quiet" key={item.id} href={workspaceHash({ view: 'proposal', portfolioId: selected.id, proposalId: item.id })}>Mở phương án {item.strategy}</a>)}</div></> : <><aside className="notice">Chọn hai đề xuất của danh mục để so sánh.</aside><ProposalHistory portfolioId={selected.id} fetchPage={fetchPage}/></>
          : view === 'profile' ? <section className="panel"><h2>{profileName(selected.risk_profile?.profile)}</h2><dl className="review-list"><div><dt>Policy</dt><dd>{selected.policy_version_id}</dd></div><div><dt>Ngại rủi ro</dt><dd>{selected.constraints.risk_aversion}</dd></div><div><dt>Giới hạn một tài sản</dt><dd>{selected.constraints.max_position_weight * 100}%</dd></div></dl></section>
          : view === 'overview' ? <>
            <aside className="notice">Tỷ trọng mục tiêu thể hiện kế hoạch đã chấp nhận. Chưa theo dõi tài sản thực tế hoặc hiệu suất đầu tư.</aside><div className="metric-grid"><section className="panel metric-card"><p>Vốn kế hoạch</p><strong>{money(selected.capital_vnd)}</strong><small>Vốn do bạn cung cấp · VND</small></section><section className="panel metric-card"><p>Hồ sơ rủi ro</p><strong>{profileName(selected.risk_profile?.profile)}</strong><small>Tối đa {selected.constraints.max_position_weight * 100}% mỗi tài sản</small></section><section className="panel metric-card"><p>Đề xuất phân bổ</p><strong>{dashboard?.proposal_count ?? 0}</strong><small>{dashboard?.accepted_target ? 'Đã có mục tiêu được lưu' : 'Chưa có mục tiêu được lưu'}</small></section></div>
            <section className="panel dashboard"><div className="section-heading"><h2>Mục tiêu đã chấp nhận</h2><span className={`badge ${dashboard?.accepted_target ? 'success' : ''}`}>{dashboard?.accepted_target ? 'Đã lưu mục tiêu' : 'Chưa có mục tiêu'}</span></div>{dashboard?.accepted_target ? <><p className="muted small">Đã lưu {dateTime(dashboard.accepted_target.accepted_at)}{!dashboard.target_matches_portfolio && ' · Danh mục đã thay đổi sau lần chấp nhận này'}</p><AllocationView allocation={dashboard.accepted_target.allocation}/></> : <div className="empty-state compact"><h3>Một kế hoạch bắt đầu từ đề xuất</h3><p>Tạo và xem lại phương án trước khi lưu tỷ trọng mục tiêu.</p><a className="button" href={href('proposal')}>Tạo đề xuất phân bổ</a></div>}<p className="target-note">Target không tạo holdings hoặc lệnh giao dịch.</p></section>
            <div className="actions"><a className="button" href={href('proposal')}>Lập phương án phân bổ</a><a className="button quiet" href={href('history')}>Lịch sử mục tiêu</a><a className="button quiet" href={href('edit')}>Sửa danh mục</a><a className="button quiet" href={href('profile')}>Xem hồ sơ rủi ro</a></div>
          </> : <>
            {proposalLoading ? <section className="panel loading-state" role="status">Đang tải đề xuất…</section> : detail ? <section className="panel results"><div className="section-heading"><h2>Phân bổ đề xuất</h2><span className={`badge ${accepted ? 'success' : ''}`}>{accepted ? 'Đã lưu mục tiêu' : stale ? 'Cần tính lại' : 'Chờ bạn xem xét'}</span></div>{stale && !accepted && <aside className="notice warning" data-testid="stale-proposal-notice"><strong>{detail.portfolio_version !== selected.version ? 'Input đã thay đổi sau khi tính' : 'Đề xuất đã hết hiệu lực'}</strong><p>Kết quả thuộc phiên bản hoặc thời hạn cũ. Hãy tạo đề xuất mới từ dữ liệu hiện hành.</p></aside>}<AllocationView allocation={detail}/><div className="accept-panel"><div><h3>{accepted ? 'Đã lưu tỷ trọng mục tiêu' : 'Bạn chủ động quyết định'}</h3><p>{accepted ? 'Mục tiêu đã được cập nhật trên tổng quan danh mục.' : 'Chấp nhận sẽ lưu tỷ trọng mục tiêu; chưa phát sinh lệnh mua bán.'}</p></div><button data-testid="accept-proposal" onClick={acceptTarget} disabled={waiting || accepted || stale || conflict}>{accepted ? 'Đã lưu mục tiêu ✓' : stale ? 'Đề xuất cũ — hãy tạo lại' : busy ? 'Đang lưu…' : 'Chấp nhận làm mục tiêu'}</button></div><div className="actions"><a className="button quiet" href={href('proposal')}>Tính lại đề xuất</a><a className="button quiet" href={href('overview')}>Xem tổng quan danh mục</a></div><details className="diagnostics"><summary>Nguồn dữ liệu và chẩn đoán</summary><JobTrace reference={detail} viewerBase={viewerBase}/><pre>{JSON.stringify(detail, null, 2)}</pre></details></section> : <>
              <section className="panel"><div className="form-grid"><label>Danh mục<input readOnly value={selected.name}/></label><label>Vốn kế hoạch (VND)<input readOnly value={money(selected.capital_vnd)}/></label><label>Chiến lược được cho phép<select value={strategy} onChange={e => { setStrategy(e.target.value); setFallback(false); }} disabled={waiting || !!job && !terminal(job.status)}><option value="MVO">MVO · Lợi nhuận / rủi ro</option><option value="EW">EW · Phân bổ đều có ràng buộc</option><option value="BL_ML">BL + ML · Model được duyệt</option></select></label><label>Giới hạn một tài sản<input readOnly value={`${selected.constraints.max_position_weight * 100}% · theo policy`}/></label>{strategy === 'BL_ML' && <label className="check fallback-choice"><input type="checkbox" checked={fallback} onChange={e => setFallback(e.target.checked)} disabled={waiting}/><span>Cho phép phương án EW nếu model chưa sẵn sàng<small>Chỉ dùng EW khi thiếu model phù hợp; dữ liệu hết hạn hoặc model không hợp lệ vẫn bị chặn.</small></span></label>}</div>{!canPropose && readiness?.status === 'READY' && <p className="inline-warning" role="status">Model hoặc phương pháp hiện chưa sẵn sàng. Bạn có thể chọn EW hoặc chủ động cho phép EW dự phòng khi thiếu model.</p>}</section>
              <div className="actions"><button data-testid="propose-portfolio" onClick={optimize} disabled={waiting || !canPropose || !!job && !terminal(job.status)}>{job && !terminal(job.status) ? 'Đang xử lý đề xuất…' : 'Tạo đề xuất'}</button><a className="button quiet" href={href('overview')}>Về tổng quan</a></div>{job && <section className="panel job" role="status"><h2>{job.status === 'FAILED' ? 'Chưa thể tạo đề xuất' : terminal(job.status) ? 'Đề xuất đã sẵn sàng' : 'Đang lập phương án cho bạn'}</h2><p>{job.error?.message ?? 'Yêu cầu được xử lý bất đồng bộ.'}</p><JobTrace reference={job} viewerBase={viewerBase}/>{job.recommendation_id && <a className="button quiet" href={workspaceHash({ view: 'proposal', portfolioId: selected.id, proposalId: job.recommendation_id })}>Xem đề xuất vừa hoàn tất</a>}</section>}
            </>}
            <ProposalHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage} selectedId={detail?.id}/>
          </>}
      </>}
    </>}
    <Methodology/>
  </WorkspaceShell>;
}
