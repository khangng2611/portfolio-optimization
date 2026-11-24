'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AssetPriceHistory } from '../components/asset-price-history';
import { AccountSettings, UnavailableWorkspace, unavailableWorkspaces } from '../components/account-settings';
import { AssetSelectionEditor } from '../components/asset-picker';
import { isSelectionReadiness, mergeAssetMetadata, type AssetCatalog, type AssetMetadata } from '../lib/selection-types';
import { ChatWorkspace } from '../components/chat-workspace';
import { DataRefresh } from '../components/data-refresh';
import { KnowledgeOperations } from '../components/knowledge-operations';
import { ModelOperations } from '../components/model-operations';
import { RiskReassessment } from '../components/risk-reassessment';
import { p1Titles } from '../lib/p1-types';
import { MarketOperations } from '../components/market-operations';
import { marketTitles } from '../lib/market-types';
import { JobTrace } from '../components/job-trace';
import { PausedProposal, PlanHeading, PortfolioOverview, proposalStrategy, ProposalRequest, ProposalReview, RiskProfileView } from '../components/portfolio-workspace';
import { RiskWizard, wizardProgressLabel, wizardTitles, type WizardStep, type ReadyUniverse } from '../components/risk-wizard';
import { ComparisonTable, EditPortfolio, PortfolioList, ProposalHistory, ReadinessNotice, TargetHistory } from '../components/portfolio-lifecycle';
import { WorkspaceShell, Methodology } from '../components/workspace-shell';
import { ApiError, dateTime, type Dashboard, type Page, type Portfolio, type Recommendation } from '../lib/portfolio-types';
import { parseWorkspaceHash, proposalCompletionRoute, readinessAllows, workspaceHash, type Readiness, type WorkspaceRoute, type WorkspaceView } from '../lib/workspace-state';
import type { TraceReference } from '../lib/job-trace';

type Session = { user: { sub: string; name: string; roles: string[] }; csrfToken: string };
type Job = TraceReference & { job_id: string; status: string; portfolio_id: string; recommendation_id?: string; error?: { message?: string | null } };
const terminal = (status: string) => ['SUCCEEDED', 'FAILED', 'CANCELLED', 'COMPLETED'].includes(status);
const resumeKey = 'portfolio.resume-destination';
const portfolioSections = [['overview', 'Tổng quan'], ['proposal', 'Đề xuất'], ['history', 'Lịch sử mục tiêu'], ['edit', 'Sửa danh mục']] as const;
const portfolioContextTitles: Partial<Record<WorkspaceView, string>> = { overview: 'xem kế hoạch', proposal: 'xem đề xuất', profile: 'xem hồ sơ', history: 'xem lịch sử', edit: 'điều chỉnh kế hoạch', compare: 'so sánh phương án', 'risk-assessment': 'đánh giá lại rủi ro' };

export default function Home({ viewerBase }: { viewerBase: string | null }) {
  const [route, setRoute] = useState<WorkspaceRoute>({ view: 'overview' });
  const [session, setSession] = useState<Session | null>(null), [loaded, setLoaded] = useState(false), [expired, setExpired] = useState(false);
  const [online, setOnline] = useState(true);
  const [openFirstPortfolio, setOpenFirstPortfolio] = useState(false);
  const [inventoryEmpty, setInventoryEmpty] = useState<boolean | null>(null);
  const [selected, setSelected] = useState<Portfolio | null>(null), [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [catalog, setCatalog] = useState<AssetCatalog | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null), [readinessFailed, setReadinessFailed] = useState(false), [universes, setUniverses] = useState<ReadyUniverse[]>([]);
  const [detail, setDetail] = useState<Recommendation | null>(null), [comparison, setComparison] = useState<[Recommendation, Recommendation] | null>(null), [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false), [opening, setOpening] = useState(false), [proposalLoading, setProposalLoading] = useState(false), [error, setError] = useState(''), [conflict, setConflict] = useState(false);
  const [wizardStep, setWizardStep] = useState<WizardStep>('plan'), [refresh, setRefresh] = useState(0), [historyVersion, setHistoryVersion] = useState(0), [clock, setClock] = useState(Date.now());
  const [jobReadFailed, setJobReadFailed] = useState(false);
  const pendingProposal = useRef<{ fingerprint: string; key: string } | null>(null);
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
    pendingProposal.current = null;
    setSession(null); setOpenFirstPortfolio(false); setInventoryEmpty(null); setSelected(null); setDashboard(null); setDetail(null); setComparison(null); setReadiness(null); setJob(null); setOpening(false); setProposalLoading(false); setUniverses([]); setCatalog(null); setWizardStep('plan');
  }, []);
  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store', headers: { 'content-type': 'application/json', ...(session ? { 'x-csrf-token': session.csrfToken } : {}), ...init.headers } });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      if (response.status === 401) { clearSession(true); setExpired(true); }
      throw new ApiError(response.status, typeof body.error === 'string' ? body.error : body.error?.message ?? (typeof body.detail === 'string' ? body.detail : `Yêu cầu thất bại (${response.status}).`), body.error?.code ?? body.detail?.code);
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
    const sync = () => setOnline(navigator.onLine);
    sync();
    window.addEventListener('online', sync); window.addEventListener('offline', sync);
    return () => { window.removeEventListener('online', sync); window.removeEventListener('offline', sync); };
  }, []);
  useEffect(() => {
    const sync = () => { if (['#main-content', '#methodology'].includes(window.location.hash)) return; setRoute(parseWorkspaceHash(window.location.hash)); setError(''); setConflict(false); };
    sync(); window.addEventListener('hashchange', sync); return () => window.removeEventListener('hashchange', sync);
  }, []);
  useEffect(() => {
    let active = true;
    fetch('/auth/session', { cache: 'no-store' }).then(async response => {
      if (response.ok) {
        const data = await response.json();
        if (!active) return;
        setSession(data);
        let resume: string | null = null;
        try { resume = sessionStorage.getItem(resumeKey); sessionStorage.removeItem(resumeKey); } catch { /* Resume is optional. */ }
        const url = new URL(window.location.href);
        const signedIn = url.searchParams.get('signed-in') === '1';
        url.searchParams.delete('signed-in');
        const destination = resume && !url.hash ? parseWorkspaceHash(resume) : null;
        if (destination && !destination.invalid) {
          url.hash = workspaceHash(destination);
          setRoute(destination);
        }
        if (signedIn || (destination && !destination.invalid)) {
          window.history.replaceState(window.history.state, '', url);
        }
        if (signedIn && !url.hash) setOpenFirstPortfolio(true);
      }
      else if (response.status === 401) { if (window.location.hash && !parseWorkspaceHash(window.location.hash).invalid) clearSession(true); }
      else throw new Error('Dịch vụ đăng nhập chưa sẵn sàng.');
    }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, [navigate, clearSession]);
  useEffect(() => {
    if (!openFirstPortfolio || inventoryEmpty === null) return;
    setOpenFirstPortfolio(false);
    if (inventoryEmpty && !window.location.hash) navigate({ view: 'create' });
  }, [inventoryEmpty, navigate, openFirstPortfolio]);
  useEffect(() => { if (loaded) { heading.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); } }, [view, loaded, route.conversationId, route.focus]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 15000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (!session) return; let active = true;
    Promise.all([api<AssetCatalog>('/api/v1/assets/catalog'), api<AssetMetadata[]>('/api/v1/market/assets').catch(() => [])]).then(([value, metadata]) => { if (active) setCatalog(mergeAssetMetadata(value, metadata)); }).catch(() => { if (active) setCatalog(null); });
    api<ReadyUniverse[]>('/api/v1/universes').then(values => { if (active) setUniverses(values); }).catch(() => { if (active) setUniverses([]); });
    return () => { active = false; };
  }, [session, api, refresh]);
  useEffect(() => {
    const epoch = ++selection.current;
    setSelected(null); setDashboard(null); setReadiness(null); setReadinessFailed(false); setDetail(null); setComparison(null); setJob(null);
    if (!session || !route.portfolioId || route.invalid) { setOpening(false); return; }
    setOpening(true); const path = `/api/v1/portfolios/${route.portfolioId}`;
    api<Dashboard>(path + '/dashboard')
      .then(current => { if (selection.current === epoch) { setSelected(current.portfolio); setDashboard(current); } })
      .catch(err => { if (selection.current === epoch) setError(err.message); }).finally(() => { if (selection.current === epoch) setOpening(false); });
    api<Readiness>(path + '/readiness')
      .then(ready => { if (selection.current === epoch) setReadiness(ready); })
      .catch(err => { if (selection.current === epoch && !(err instanceof ApiError && err.status === 401)) setReadinessFailed(true); });
    return () => { if (selection.current === epoch) selection.current++; };
  }, [session, route.portfolioId, route.invalid, api, refresh]);
  useEffect(() => {
    if (view === 'overview' && route.proposalId && dashboard?.portfolio.id === route.portfolioId &&
        dashboard && dashboard.accepted_target?.recommendation_id !== route.proposalId) {
      navigate({ view: 'proposal', portfolioId: route.portfolioId, proposalId: route.proposalId });
    }
  }, [dashboard, navigate, route.portfolioId, route.proposalId, view]);
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
    const id = view === 'proposal' && !route.proposalId && route.jobId;
    const portfolioId = selected?.id;
    if (!id || !portfolioId || portfolioId !== route.portfolioId) return;
    let active = true, timer: ReturnType<typeof setTimeout>;
    setJobReadFailed(false);
    async function poll(jobId: string, ownerPortfolio: string) {
      try {
        const next = await api<Job>(`/api/v1/jobs/portfolio/${jobId}`);
        if (!active) return;
        if (next.portfolio_id !== ownerPortfolio) throw new ApiError(404, 'Tác vụ không thuộc danh mục đang mở.');
        setJob(next);
        if (!terminal(next.status)) {
          timer = setTimeout(() => void poll(jobId, ownerPortfolio), 1000);
        } else if (next.recommendation_id) {
          const dashboard = await api<Dashboard>(`/api/v1/portfolios/${ownerPortfolio}/dashboard`).catch(() => null);
          if (!active) return;
          if (dashboard) { setDashboard(dashboard); setSelected(dashboard.portfolio); }
          setHistoryVersion(value => value + 1);
          const destination = proposalCompletionRoute(parseWorkspaceHash(window.location.hash), ownerPortfolio, next.recommendation_id);
          if (destination) navigate(destination);
        }
      } catch (err) {
        if (!active) return;
        setError((err as Error).message); setJobReadFailed(true);
      }
    }
    void poll(id, portfolioId);
    return () => { active = false; clearTimeout(timer); };
  }, [view, route.proposalId, route.jobId, route.portfolioId, selected?.id, api, navigate, refresh]);
  async function createPortfolio(body: unknown) {
    setBusy(true); setError(''); try { const created = await api<Portfolio>('/api/v1/onboarding/portfolios', { method: 'POST', body: JSON.stringify(body) }); navigate({ view: 'overview', portfolioId: created.id }); return true; }
    catch (err) { setError((err as Error).message); return false; } finally { setBusy(false); }
  }
  const currentReadiness = isSelectionReadiness(readiness) && readiness.can_submit && readiness.selection_valid_until && Date.parse(readiness.selection_valid_until) <= clock
    ? { ...readiness, can_submit: false, reason_code: 'INPUT_EXPIRED' }
    : readiness && !isSelectionReadiness(readiness) && readiness.valid_until && Date.parse(readiness.valid_until) <= clock ? { ...readiness, status: 'EXPIRED' } : readiness;
  async function optimize(strategy: 'EW' | 'MVO' | 'HYBRID') {
    if (!selected?.risk_profile || selected.id !== route.portfolioId || busy || !readinessAllows(currentReadiness, strategy, false)) return;
    const epoch = selection.current, fingerprint = JSON.stringify([selected.id, selected.version, strategy]);
    if (pendingProposal.current?.fingerprint !== fingerprint) pendingProposal.current = { fingerprint, key: crypto.randomUUID() };
    setBusy(true); setError('');
    try {
      const result = await api<Job>(`/api/v1/portfolios/${selected.id}/recommendations`, { method: 'POST', headers: { 'Idempotency-Key': pendingProposal.current.key, 'If-Match': `"${selected.version}"` }, body: JSON.stringify(strategy === 'HYBRID' ? { mode: 'system' } : { strategy }) });
      pendingProposal.current = null;
      if (epoch === selection.current) {
        setJob({ ...result, status: 'QUEUED', portfolio_id: selected.id });
        navigate({ view: 'proposal', portfolioId: selected.id, jobId: result.job_id });
      }
    } catch (err) {
      if (err instanceof ApiError && err.status < 500) pendingProposal.current = null;
      if (epoch === selection.current) {
        setError((err as Error).message);
        if (err instanceof ApiError && err.code === 'SYSTEM_PAUSED' && isSelectionReadiness(readiness)) setReadiness({ ...readiness, can_submit: false, reason_code: 'SYSTEM_PAUSED', strategies: [] });
        else if (err instanceof ApiError && [409, 412].includes(err.status)) setConflict(true);
      }
    } finally { setBusy(false); }
  }
  async function acceptTarget() {
    if (!detail || !selected || detail.id !== route.proposalId || selected.id !== route.portfolioId
      || detail.portfolio_id !== selected.id || detail.portfolio_version !== selected.version || busy || conflict
      || dashboard?.accepted_target?.recommendation_id === detail.id || !(Date.parse(detail.valid_until ?? '') > Date.now())) return;
    const epoch = selection.current; setBusy(true); setError('');
    try { await api(`/api/v1/recommendations/${detail.id}/accept`, { method: 'POST', headers: { 'If-Match': `"${selected.version}"` }, body: '{}' }); const current = await api<Dashboard>(`/api/v1/portfolios/${selected.id}/dashboard`); if (epoch === selection.current) { setDashboard(current); setSelected(current.portfolio); setHistoryVersion(value => value + 1); } }
    catch (err) { if (epoch === selection.current) { setConflict(err instanceof ApiError && [409, 412].includes(err.status)); setError((err as Error).message); } } finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true); try { const result = await api<{ providerRevoked: boolean }>('/auth/logout', { method: 'POST' }); clearSession(false); setExpired(false); try { sessionStorage.removeItem(resumeKey); } catch { /* Optional storage. */ } navigate({ view: 'overview' }); if (!result.providerRevoked) setError('Đã đóng phiên ứng dụng; Dịch vụ xác thực chưa xác nhận thu hồi phiên.'); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  const onChatExpired = useCallback(() => clearSession(true), [clearSession]);
  const accepted = !!detail && dashboard?.accepted_target?.recommendation_id === detail.id;
  const stale = !!detail && !!selected && (detail.portfolio_version !== selected.version || !detail.valid_until || !(Date.parse(detail.valid_until) > clock));
  const waiting = busy || opening;
  const unavailable = unavailableWorkspaces[view];
  const proposalJob = job?.job_id === route.jobId ? job : null;
  const title = !session ? 'Đầu tư có kế hoạch. Quyết định có cơ sở.' : unavailable ? unavailable.title : view === 'knowledge' ? 'Kho tri thức' : view === 'settings' ? 'Cài đặt' : view === 'asset-prices' ? 'Lịch sử giá tài sản' : view === 'chat' ? route.conversationId ? 'Hiểu rõ hơn trước mỗi quyết định' : 'Hội thoại của bạn' : !route.portfolioId && portfolioContextTitles[view] ? inventoryEmpty ? 'Bắt đầu kế hoạch đầu tư của bạn' : `Chọn danh mục để ${portfolioContextTitles[view]}` : p1Titles[view] ? p1Titles[view] : marketView ? marketTitles[view] : view === 'create' ? wizardTitles[wizardStep] : view === 'edit' ? 'Điều chỉnh kế hoạch của bạn' : view === 'history' ? 'Lịch sử mục tiêu' : view === 'compare' ? 'So sánh hai phương án' : view === 'proposal' ? browsingProposals ? 'Các đề xuất của danh mục' : detail ? stale && !accepted ? 'Đề xuất đã lưu' : 'Xem lại đề xuất' : 'Tạo đề xuất phân bổ' : view === 'profile' ? 'Hồ sơ rủi ro' : view === 'portfolios' ? 'Danh mục của bạn' : view === 'overview' ? 'Kế hoạch của bạn' : selected?.name ?? 'Tổng quan kế hoạch đầu tư';
  const refreshData = () => { setError(''); setConflict(false); setRefresh(value => value + 1); };
  const sharedPortfolioHeader = !!session && !!selected && selected.id === route.portfolioId && !route.invalid && portfolioSections.some(([section]) => section === view);
  const showPlanHeading = sharedPortfolioHeader && (view === 'overview' || view === 'proposal');
  const paused = currentReadiness?.reason_code === 'SYSTEM_PAUSED';
  const pausedProposal = view === 'proposal' && paused && !route.proposalId && !route.jobId && !browsingProposals;
  const universeAssetIds = universes.find(universe => universe.universe_id === selected?.universe_id)?.asset_ids;
  const sectionLink = ([target, label]: typeof portfolioSections[number], index: number) => (
    <a key={target} className={index > 1 ? 'portfolio-secondary-link' : undefined} href={href(target)} aria-current={view === target ? 'page' : undefined}>{label}</a>
  );
  const portfolioTabs = <nav className="portfolio-tabs" aria-label="Các phần của danh mục">
    {portfolioSections.slice(0, 3).map(sectionLink)}
    <details className="portfolio-extra" key={view} onKeyDown={event => {
      if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus(); }
    }}><summary>Thêm</summary><div>{sectionLink(portfolioSections[3], 3)}<a href={href('profile')}>Hồ sơ rủi ro</a></div></details>
  </nav>;
  return <WorkspaceShell view={view} portfolioId={route.portfolioId}
    portfolioMore={sharedPortfolioHeader && portfolioSections.slice(1).map(sectionLink)}
    portfolioNavigation={sharedPortfolioHeader && <>
      {showPlanHeading && <PlanHeading portfolio={selected} recommendation={view === 'proposal' && !browsingProposals ? detail ?? undefined : undefined} headingRef={heading}/>}
      {portfolioTabs}
    </>} account={session?.user.name ?? null} busy={waiting} onLogout={logout} operator={operator} reviewer={reviewer} researcher={session?.user.roles.some(role => role === 'researcher' || role === 'system-admin')} context={view === 'chat' ? 'Hội thoại' : view === 'asset-prices' ? 'Giá tài sản' : view === 'knowledge' ? 'Kho tri thức' : modelView ? 'Mô hình' : marketView ? 'Dữ liệu' : selected?.name ?? (['profile', 'risk-assessment'].includes(view) ? 'Hồ sơ rủi ro' : 'Danh mục')}>
    {!showPlanHeading && !(session && view === 'asset-prices' && !route.invalid) && <header className={`page-heading ${session && view === 'chat' ? 'sr-only' : ''}`}>
      {session && (modelView || marketView) && <p className="eyebrow">{modelView && session ? reviewer ? 'MODEL REVIEWER' : 'DATA OPERATOR' : marketView && session ? 'DATA OPERATOR' : 'KẾ HOẠCH ĐẦU TƯ CỦA BẠN'}</p>}
      {sharedPortfolioHeader && view !== 'overview' && <a className="breadcrumb" href={href('overview')}>{selected.name}</a>}
      {session && view === 'create' && <p className="wizard-progress-label">{wizardProgressLabel(wizardStep, !!catalog?.selection_enabled)}</p>}
      <h1 ref={heading} tabIndex={-1}>{title}</h1>
      {!session && <p className="muted">Tư vấn phân bổ tài sản cuối ngày cho thị trường Việt Nam.</p>}
    </header>}
    {!online && <aside className="notice warning offline-notice" role="status"><strong>Bạn đang ngoại tuyến</strong><p>Kết nối lại để tải dữ liệu hoặc gửi yêu cầu mới.</p></aside>}
    {error && <div ref={errorRef} tabIndex={-1} className="error" role="alert" data-testid={conflict ? 'conflict-notice' : 'request-error'}><strong>{conflict ? 'Thông tin đã thay đổi' : 'Chưa thể hoàn tất yêu cầu'}</strong><p>{error}</p>{conflict && <button className="quiet" onClick={refreshData}>Tải phiên bản mới</button>}</div>}
    {!loaded ? <section className="panel loading-state" role="status">Đang kiểm tra phiên…</section> : !session ? <>
      {expired && <aside className="notice warning" role="alert" data-testid="session-expired-notice"><strong>Phiên đăng nhập đã hết hạn</strong><p>Đăng nhập lại để mở đúng danh mục đang xem. Yêu cầu thay đổi sẽ không tự được gửi lại.</p><a className="button" href="/login">Đăng nhập lại</a></aside>}
      <div className="actions welcome-actions"><a className="button" href="/login">Đăng nhập</a><a className="button quiet" href="/register">Đăng ký</a></div>
      <section className="panel welcome-card">
        <h2>Từ nhu cầu của bạn đến một kế hoạch có thể theo dõi</h2>
        <p className="muted">Đánh giá rủi ro, xem đề xuất có nguồn và chủ động chọn mục tiêu.</p>
        <ol className="journey-steps"><li>01 · Hiểu nhu cầu</li><li>02 · Xem đề xuất</li><li>03 · Chủ động quyết định</li></ol>
        <p>Chấp nhận đề xuất chỉ lưu tỷ trọng mục tiêu.</p>
        <a href="#methodology" onClick={event => {
          const detail = document.getElementById('methodology');
          if (detail instanceof HTMLDetailsElement) {
            event.preventDefault();
            detail.open = true;
            detail.querySelector('summary')?.focus();
          }
        }}>Xem cách hoạt động</a>
      </section>
    </> : route.invalid ? <section className="panel empty-state"><h2>Đường dẫn không hợp lệ</h2><a className="button" href="#portfolios">Danh mục của bạn</a></section> : view === 'knowledge' ? operator ? <KnowledgeOperations route={route} api={api} fetchPage={fetchPage}/> : <section className="panel empty-state"><h2>Cần quyền vận hành dữ liệu</h2><a href="#overview">Về tổng quan</a></section> : view === 'settings' ? <AccountSettings name={session.user.name} roles={session.user.roles} busy={waiting} logout={logout} profileHref={href('profile')} overviewHref={href('overview')}/> : view === 'asset-prices' ? <AssetPriceHistory headingRef={heading} key={session.user.sub} assetId={route.assetId} returnView={route.returnView} assets={catalog?.assets} ownerKey={session.user.sub} portfolioId={route.portfolioId} proposalId={route.proposalId} api={api}/> : unavailable ? <UnavailableWorkspace content={unavailable} canResearch={session.user.roles.some(role => role === 'researcher' || role === 'system-admin')} overviewHref={href('overview')}/> : view === 'chat' ? <ChatWorkspace systemPaused={paused} api={api} apiPage={fetchPage} route={route} navigate={navigate} ownerKey={session.user.sub} onSessionExpired={onChatExpired} assets={catalog?.assets}/> : modelView ? operator || reviewer ? <ModelOperations key={view + (route.modelId ?? '')} route={route} api={api} fetchPage={fetchPage} operator={operator} reviewer={reviewer}/> : <section className="panel empty-state"><h2>Cần quyền vận hành mô hình</h2><p>Tài khoản hiện tại chưa có quyền data operator hoặc model reviewer.</p><a href="#portfolios">Về danh mục</a></section> : marketView ? operator ? view === 'market-refresh' ? <DataRefresh route={route} api={api} fetchPage={fetchPage}/> : <MarketOperations route={route} api={api} fetchPage={fetchPage}/> : <section className="panel empty-state"><h2>Cần quyền data operator</h2><p>Tài khoản hiện tại chưa được cấp quyền vận hành dữ liệu.</p><a href="#portfolios">Về danh mục của bạn</a></section> : <>
      <div className="onboarding-workspace" hidden={view !== 'create'}><RiskWizard busy={waiting} onCreate={createPortfolio} universes={universes} catalog={catalog} onStepChange={setWizardStep} onCancel={() => navigate({ view: 'portfolios' })}/></div>
      {view === 'create' ? null : opening ? <section className="panel loading-state" role="status">Đang mở danh mục…</section> : view === 'portfolios' || !route.portfolioId ? <PortfolioList key={view} fetchPage={fetchPage} mode={view === 'portfolios' ? 'manage' : 'choose'} destination={view === 'portfolios' ? 'overview' : view} onInventoryEmpty={setInventoryEmpty}/> : !selected ? <section className="panel empty-state"><h2>Chưa mở được danh mục</h2><p>Kiểm tra quyền truy cập hoặc thử tải lại.</p><button onClick={refreshData}>Thử lại</button><a href="#portfolios">Về danh sách</a></section> : <>
        {!sharedPortfolioHeader && view !== 'profile' && portfolioTabs}
        {view === 'proposal' && !route.proposalId && !route.jobId && !browsingProposals && !paused && <ReadinessNotice value={currentReadiness} onRefresh={refreshData} busy={opening} failed={readinessFailed} pausedPortfolio={{ id: selected.id, hasProposals: !!dashboard?.proposal_count }}/>}
        {view === 'risk-assessment' ? <RiskReassessment portfolio={selected} api={api} fetchPage={fetchPage} onSaved={refreshData} onReload={refreshData}/> : view === 'edit' ? <><AssetSelectionEditor portfolio={selected} catalog={catalog} api={api} onSaved={refreshData}/><EditPortfolio key={selected.id} portfolio={selected} api={api} onReload={refreshData} onSaved={value => { setSelected(value); refreshData(); navigate({ view: 'overview', portfolioId: value.id }); }}/></>
          : view === 'history' ? <TargetHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage} assets={catalog?.assets}/>
          : view === 'compare' ? proposalLoading ? <p role="status">Đang tải các phương án…</p> : comparison ? <ComparisonTable items={comparison}/> : <><aside className="notice">Chọn hai đề xuất của danh mục để so sánh.</aside><ProposalHistory portfolioId={selected.id} fetchPage={fetchPage}/></>
          : view === 'profile' ? <RiskProfileView portfolio={selected}/>
          : view === 'overview' ? <PortfolioOverview portfolio={selected} dashboard={dashboard} readiness={currentReadiness} assets={catalog?.assets} universeAssetIds={universeAssetIds} readinessFailed={readinessFailed} onRefresh={refreshData} api={api}/> : pausedProposal ? <PausedProposal portfolio={selected} dashboard={dashboard} readiness={currentReadiness} universeAssetIds={universeAssetIds} onRefresh={refreshData}/> : <>
            {browsingProposals ? !selected.risk_profile || !readinessAllows(currentReadiness, proposalStrategy(selected, currentReadiness), false) ? null : <div className="proposal-browser-actions"><a className="button quiet" href={href('proposal')}>Tạo đề xuất mới</a></div> : proposalLoading ? <section className="panel loading-state" role="status">Đang tải đề xuất…</section> : detail ? <ProposalReview api={api} universeAssetIds={universeAssetIds} key={detail.id} portfolio={selected} recommendation={detail} accepted={accepted} stale={stale} conflict={conflict} busy={waiting} onAccept={acceptTarget} viewerBase={operator ? viewerBase : null} assets={catalog?.assets} readiness={currentReadiness} readinessFailed={readinessFailed} onRefresh={refreshData}/> : route.proposalId ? <section className="panel empty-state"><h2>Chưa mở được đề xuất</h2><p>Kiểm tra đường dẫn hoặc quyền truy cập.</p><a className="button quiet" href={workspaceHash({ view: 'proposal', portfolioId: selected.id, focus: 'history' })}>Xem đề xuất đã lưu</a></section> : <>
              {route.jobId && !proposalJob && !jobReadFailed && <p role="status">Đang tải tiến trình…</p>}
              {jobReadFailed && <button className="quiet" onClick={refreshData}>Tải lại tiến trình</button>}
              {proposalJob && <section className="job-progress" role="status"><span className="badge">{proposalJob.status === 'QUEUED' ? 'Đang xếp hàng' : ['FAILED', 'CANCELLED'].includes(proposalJob.status) ? 'Chưa hoàn tất' : terminal(proposalJob.status) ? 'Đã hoàn tất' : 'Đang xử lý'}</span><h2>{proposalJob.status === 'FAILED' ? 'Chưa thể tạo đề xuất' : proposalJob.status === 'CANCELLED' ? 'Yêu cầu đã dừng' : terminal(proposalJob.status) ? 'Đã xử lý yêu cầu' : 'Đang tính phân bổ'}</h2><p>{proposalJob.error?.message ?? (terminal(proposalJob.status) ? 'Xem kết quả nếu đã có, hoặc kiểm tra lại trước khi tạo yêu cầu mới.' : 'Kết quả sẽ mở khi tính xong.')}</p>{operator && proposalJob.job_trace_id && <details className="diagnostics"><summary>Chi tiết tác vụ</summary><JobTrace reference={proposalJob} viewerBase={viewerBase}/></details>}{proposalJob.recommendation_id && <a className="button" href={workspaceHash({ view: 'proposal', portfolioId: selected.id, proposalId: proposalJob.recommendation_id })}>Xem đề xuất vừa hoàn tất</a>}</section>}
              {(!route.jobId || proposalJob && terminal(proposalJob.status)) && <ProposalRequest key={route.focus ?? 'new'} initialReview={route.focus === 'request'} portfolio={selected} readiness={currentReadiness} busy={waiting} onSubmit={optimize}/>}
            </>}
            {browsingProposals ? <><ProposalHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage}/><a className="button quiet proposal-history-chat" href={href('chat')}>Hỏi về kế hoạch</a></> : <details className="proposal-history-disclosure"><summary>Các đề xuất đã tạo · Xem lại hoặc so sánh</summary><ProposalHistory key={selected.id + historyVersion} portfolioId={selected.id} fetchPage={fetchPage} selectedId={detail?.id}/></details>}

          </>}
      </>}
    </>}
    {(!session || view !== 'chat') && !(sharedPortfolioHeader && (view === 'overview' || view === 'proposal' && (pausedProposal || detail && !browsingProposals && !proposalLoading))) && <Methodology/>}
  </WorkspaceShell>;
}
