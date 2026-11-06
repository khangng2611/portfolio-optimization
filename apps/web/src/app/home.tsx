'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ChatWorkspace } from '../components/chat-workspace';
import { DataRefresh } from '../components/data-refresh';
import { ModelOperations } from '../components/model-operations';
import { RiskReassessment } from '../components/risk-reassessment';
import { p1Titles } from '../lib/p1-types';
import { MarketOperations } from '../components/market-operations';
import { marketTitles } from '../lib/market-types';
import { JobTrace } from '../components/job-trace';
import { PortfolioOverview, ProposalRequest, ProposalReview, RiskProfileView } from '../components/portfolio-workspace';
import { RiskWizard, wizardTitles, type ReadyUniverse } from '../components/risk-wizard';
import { ComparisonTable, EditPortfolio, PortfolioList, ProposalHistory, ReadinessNotice, TargetHistory } from '../components/portfolio-lifecycle';
import { WorkspaceShell, Methodology } from '../components/workspace-shell';
import { ApiError, dateTime, type Dashboard, type Page, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { parseWorkspaceHash, proposalCompletionRoute, readinessAllows, workspaceHash, type Readiness, type WorkspaceRoute, type WorkspaceView } from '../lib/workspace-state';
import type { TraceReference } from '../lib/job-trace';

type Session = { user: { sub: string; name: string; roles: string[] }; csrfToken: string };
type Job = TraceReference & { job_id: string; status: string; portfolio_id: string; recommendation_id?: string; error?: { message?: string } };
const terminal = (status: string) => ['SUCCEEDED', 'FAILED', 'CANCELLED', 'COMPLETED'].includes(status);
const resumeKey = 'portfolio.resume-destination';
const portfolioContextTitles: Partial<Record<WorkspaceView, string>> = { overview: 'xem kế hoạch', proposal: 'xem đề xuất', profile: 'xem hồ sơ', history: 'xem lịch sử', edit: 'điều chỉnh kế hoạch', compare: 'so sánh phương án', 'risk-assessment': 'đánh giá lại rủi ro' };

export default function Home({ viewerBase }: { viewerBase: string | null }) {
  const [route, setRoute] = useState<WorkspaceRoute>({ view: 'overview' });
  const [session, setSession] = useState<Session | null>(null), [loaded, setLoaded] = useState(false), [expired, setExpired] = useState(false);
  const [inventoryEmpty, setInventoryEmpty] = useState<boolean | null>(null);
  const [selected, setSelected] = useState<Portfolio | null>(null), [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null), [readinessFailed, setReadinessFailed] = useState(false), [universes, setUniverses] = useState<ReadyUniverse[]>([]);
  const [detail, setDetail] = useState<Recommendation | null>(null), [comparison, setComparison] = useState<[Recommendation, Recommendation] | null>(null), [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false), [opening, setOpening] = useState(false), [proposalLoading, setProposalLoading] = useState(false), [error, setError] = useState(''), [conflict, setConflict] = useState(false);
  const [wizardStep, setWizardStep] = useState(0), [strategy, setStrategy] = useState('MVO'), [fallback, setFallback] = useState(false), [refresh, setRefresh] = useState(0), [historyVersion, setHistoryVersion] = useState(0), [clock, setClock] = useState(Date.now());
  const selection = useRef(0), heading = useRef<HTMLHeadingElement>(null), errorRef = useRef<HTMLDivElement>(null);
  const view = route.view;
  const browsingProposals = view === 'proposal' && route.focus === 'history';
  const marketView = view.startsWith('market');
  const modelView = ['models', 'model-training', 'model-review'].includes(view);
  const reviewer = session?.user.roles.includes('model-reviewer') ?? false;
  const operator = session?.user.roles.includes('data-operator') ?? false;
  const clearSession = useCallback((remember: boolean) => {
    selection.current++;
    if (remember) { try { sessionStorage.setItem(resumeKey, workspaceHash(parseWorkspaceHash(window.location.hash))); } catch { /* URL remains usable without storage. */ } }
    setSession(null); setInventoryEmpty(null); setSelected(null); setDashboard(null); setDetail(null); setComparison(null); setReadiness(null); setJob(null); setOpening(false); setProposalLoading(false); setUniverses([]); setWizardStep(0);
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
  useEffect(() => { if (loaded) { heading.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); } }, [view, loaded, route.conversationId, route.focus]);
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
  const onChatExpired = useCallback(() => clearSession(true), [clearSession]);
  const accepted = !!detail && dashboard?.accepted_target?.recommendation_id === detail.id;
  const stale = !!detail && !!selected && (detail.portfolio_version !== selected.version || !detail.valid_until || !(Date.parse(detail.valid_until) > clock));
  const waiting = busy || opening;
  const title = !session ? 'Đầu tư có kế hoạch. Quyết định có cơ sở.' : view === 'chat' ? route.conversationId ? 'Hiểu rõ hơn trước mỗi quyết định' : 'Hội thoại của bạn' : !route.portfolioId && portfolioContextTitles[view] ? inventoryEmpty ? 'Bắt đầu kế hoạch đầu tư của bạn' : `Chọn danh mục để ${portfolioContextTitles[view]}` : p1Titles[view] ? p1Titles[view] : marketView ? marketTitles[view] : view === 'create' ? wizardTitles[wizardStep] : view === 'edit' ? 'Điều chỉnh kế hoạch của bạn' : view === 'history' ? 'Lịch sử mục tiêu' : view === 'compare' ? 'So sánh hai phương án' : view === 'proposal' ? browsingProposals ? 'Các đề xuất của danh mục' : detail ? stale && !accepted ? 'Đề xuất cần tính lại' : 'Xem lại đề xuất' : 'Tạo đề xuất phân bổ' : view === 'profile' ? 'Hồ sơ rủi ro của danh mục' : view === 'portfolios' ? 'Danh mục của bạn' : view === 'overview' ? 'Kế hoạch của bạn' : selected?.name ?? 'Tổng quan kế hoạch đầu tư';
  const refreshData = () => { setError(''); setConflict(false); setRefresh(value => value + 1); };
  return <WorkspaceShell view={view} portfolioId={route.portfolioId} account={session?.user.name ?? null} busy={waiting} onLogout={logout} operator={operator} reviewer={reviewer} context={view === 'chat' ? 'Hội thoại' : modelView ? 'Mô hình' : marketView ? 'Dữ liệu' : selected?.name ?? (['profile', 'risk-assessment'].includes(view) ? 'Hồ sơ rủi ro' : 'Danh mục')}>
    <header className={`page-heading ${view === 'chat' && route.conversationId ? 'sr-only' : ''}`}>{(!session || modelView || marketView) && <p className="eyebrow">{modelView && session ? reviewer ? 'MODEL REVIEWER' : 'DATA OPERATOR' : marketView && session ? 'DATA OPERATOR' : 'KẾ HOẠCH ĐẦU TƯ CỦA BẠN'}</p>}<h1 ref={heading} tabIndex={-1}>{title}</h1>{!session && <p className="muted">Tư vấn phân bổ tài sản cuối ngày cho thị trường Việt Nam.</p>}</header>
    {error && <div ref={errorRef} tabIndex={-1} className="error" role="alert" data-testid={conflict ? 'conflict-notice' : 'request-error'}><strong>{conflict ? 'Thông tin đã thay đổi' : 'Chưa thể hoàn tất yêu cầu'}</strong><p>{error}</p>{conflict && <button className="quiet" onClick={refreshData}>Tải phiên bản mới</button>}</div>}
    {!loaded ? <section className="panel loading-state" role="status">Đang kiểm tra phiên…</section> : !session ? <>
      {expired && <aside className="notice warning" role="alert" data-testid="session-expired-notice"><strong>Phiên đăng nhập đã hết hạn</strong><p>Đăng nhập lại để mở đúng danh mục đang xem. Yêu cầu thay đổi sẽ không tự được gửi lại.</p><a className="button" href="/auth/login">Đăng nhập lại</a></aside>}
      <aside className="notice">Ứng dụng tư vấn phân bổ tài sản cuối ngày. Chấp nhận chỉ lưu tỷ trọng mục tiêu.</aside><section className="panel welcome-card"><p className="eyebrow">HIỂU RÕ TRƯỚC KHI QUYẾT ĐỊNH</p><h2>Từ nhu cầu của bạn<br/>đến một kế hoạch có thể theo dõi.</h2><p className="muted">Đánh giá rủi ro, xem đề xuất có nguồn và chủ động chọn mục tiêu.</p><ol className="journey-steps"><li>01 · Hiểu nhu cầu</li><li>02 · Review phương án</li><li>03 · Chủ động quyết định</li></ol></section><div className="actions"><a className="button" href="/auth/login">Đăng nhập qua Identity</a><a className="button quiet" href="#methodology" onClick={() => document.getElementById('methodology')?.setAttribute('open', '')}>Xem cách hoạt động</a></div>
    </> : route.invalid ? <section className="panel empty-state"><h2>Đường dẫn không hợp lệ</h2><a className="button" href="#portfolios">Danh mục của bạn</a></section> : view === 'chat' ? <ChatWorkspace api={api} apiPage={fetchPage} route={route} navigate={navigate} ownerKey={session.user.sub} onSessionExpired={onChatExpired}/> : modelView ? operator || reviewer ? <ModelOperations key={view + (route.modelId ?? '')} route={route} api={api} fetchPage={fetchPage} operator={operator} reviewer={reviewer}/> : <section className="panel empty-state"><h2>Cần quyền vận hành mô hình</h2><p>Tài khoản hiện tại chưa có quyền data operator hoặc model reviewer.</p><a href="#portfolios">Về danh mục</a></section> : marketView ? operator ? view === 'market-refresh' ? <DataRefresh route={route} api={api} fetchPage={fetchPage}/> : <MarketOperations route={route} api={api} fetchPage={fetchPage}/> : <section className="panel empty-state"><h2>Cần quyền data operator</h2><p>Tài khoản hiện tại chưa được cấp quyền vận hành dữ liệu.</p><a href="#portfolios">Về danh mục của bạn</a></section> : <>
      <div className="onboarding-workspace" hidden={view !== 'create'}><RiskWizard busy={waiting} onCreate={createPortfolio} universes={universes} onStepChange={setWizardStep} onCancel={() => navigate({ view: 'portfolios' })}/></div>
      {view === 'create' ? null : opening ? <section className="panel loading-state" role="status">Đang mở danh mục…</section> : view === 'portfolios' || !route.portfolioId ? <PortfolioList key={view} fetchPage={fetchPage} mode={view === 'portfolios' ? 'manage' : 'choose'} destination={view === 'portfolios' ? 'overview' : view} onInventoryEmpty={setInventoryEmpty}/> : !selected ? <section className="panel empty-state"><h2>Chưa mở được danh mục</h2><p>Kiểm tra quyền truy cập hoặc thử tải lại.</p><button onClick={refreshData}>Thử lại</button><a href="#portfolios">Về danh sách</a></section> : <>
        <nav className="portfolio-tabs" aria-label="Các phần của danh mục">{([['overview', 'Tổng quan'], ['proposal', 'Đề xuất'], ['history', 'Lịch sử mục tiêu'], ['edit', 'Sửa danh mục']] as const).map(([target, label]) => <a key={target} href={href(target)} aria-current={view === target ? 'page' : undefined}>{label}</a>)}</nav>
        {view === 'proposal' && !detail && !browsingProposals && <ReadinessNotice value={currentReadiness} onRefresh={refreshData} busy={opening} failed={readinessFailed}/>}
        {view === 'risk-assessment' ? <RiskReassessment portfolio={selected} api={api} fetchPage={fetchPage} onSaved={refreshData} onReload={refreshData}/> : view === 'edit' ? <EditPortfolio key={selected.id} portfolio={selected} api={api} onReload={refreshData} onSaved={value => { setSelected(value); refreshData(); navigate({ view: 'overview', portfolioId: value.id }); }}/>
          : view === 'history' ? <TargetHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage}/>
          : view === 'compare' ? proposalLoading ? <p role="status">Đang tải các phương án…</p> : comparison ? <ComparisonTable items={comparison}/> : <><aside className="notice">Chọn hai đề xuất của danh mục để so sánh.</aside><ProposalHistory portfolioId={selected.id} fetchPage={fetchPage}/></>
          : view === 'profile' ? <RiskProfileView portfolio={selected}/>
          : view === 'overview' ? <PortfolioOverview portfolio={selected} dashboard={dashboard}/> : <>
            {browsingProposals ? <div className="proposal-browser-actions"><p className="muted">Mở từng đề xuất để xem lại, hoặc chọn hai phương án để so sánh.</p><a className="button quiet" href={href('proposal')}>Tạo đề xuất mới</a></div> : proposalLoading ? <section className="panel loading-state" role="status">Đang tải đề xuất…</section> : detail ? <ProposalReview portfolio={selected} recommendation={detail} accepted={accepted} stale={stale} conflict={conflict} busy={waiting} onAccept={acceptTarget} viewerBase={viewerBase}/> : <>
              {job && <section className="job-progress" role="status"><span className="badge">{job.status === 'QUEUED' ? 'Đang xếp hàng' : ['FAILED', 'CANCELLED'].includes(job.status) ? 'Chưa hoàn tất' : terminal(job.status) ? 'Đã hoàn tất' : 'Đang xử lý'}</span><h2>{job.status === 'FAILED' ? 'Chưa thể tạo đề xuất' : job.status === 'CANCELLED' ? 'Yêu cầu đã dừng' : terminal(job.status) ? 'Đã xử lý yêu cầu' : 'Đang tính phân bổ'}</h2><p>{job.error?.message ?? (terminal(job.status) ? 'Xem kết quả nếu đã có, hoặc kiểm tra lại trước khi tạo yêu cầu mới.' : 'Yêu cầu đã được tiếp nhận. Hệ thống đang tính phân bổ theo policy.')}</p><p className="muted small">Trạng thái được cập nhật tự động. Kết quả sẽ mở khi tính toán hoàn tất.</p><details className="diagnostics"><summary>Chi tiết tác vụ</summary><JobTrace reference={job} viewerBase={viewerBase}/></details>{job.recommendation_id && <a className="button" href={workspaceHash({ view: 'proposal', portfolioId: selected.id, proposalId: job.recommendation_id })}>Xem đề xuất vừa hoàn tất</a>}</section>}
              {(!job || terminal(job.status)) && <ProposalRequest portfolio={selected} readiness={currentReadiness} strategy={strategy} fallback={fallback} busy={waiting} onStrategy={value => { setStrategy(value); setFallback(false); }} onFallback={setFallback} onSubmit={optimize}/>}
            </>}
            {browsingProposals ? <ProposalHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage}/> : <details className="proposal-history-disclosure"><summary>Các đề xuất đã tạo · Xem lại hoặc so sánh</summary><ProposalHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage} selectedId={detail?.id}/></details>}

          </>}
      </>}
    </>}
    <Methodology/>
  </WorkspaceShell>;
}
