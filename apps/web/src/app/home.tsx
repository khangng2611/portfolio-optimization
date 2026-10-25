'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { JobTrace } from '../components/job-trace';
import { AllocationView, money, profileName, type Allocation } from '../components/allocation-view';
import { RiskWizard, wizardTitles, type ReadyUniverse } from '../components/risk-wizard';
import type { TraceReference } from '../lib/job-trace';
import { LatestRequest } from '../lib/latest-request';
import { WorkspaceShell, Methodology, DesignIcon, type WorkspaceView } from '../components/workspace-shell';

type Session = { user: { name: string; roles: string[] }; csrfToken: string };
type Portfolio = { id: string; name: string; capital_vnd: string; universe_id: string; version: number; constraints: { risk_aversion: number; max_position_weight: number }; risk_profile: { profile: string } | null; policy_version_id: string };
type Job = TraceReference & { job_id: string; status: string; portfolio_id: string; recommendation_id?: string; error?: { message?: string } };
type Recommendation = TraceReference & Allocation & { id: string; portfolio_id: string; portfolio_version: number };
type Target = { id: string; recommendation_id: string; accepted_at: string; allocation: Recommendation };
type Dashboard = { portfolio: Portfolio; accepted_target: Target | null; proposal_count: number; target_matches_portfolio: boolean };
const terminal = (status: string) => ['SUCCEEDED', 'FAILED', 'CANCELLED', 'COMPLETED'].includes(status);

export default function Home({ viewerBase }: { viewerBase: string | null }) {
  const [view, setView] = useState<WorkspaceView>('overview');
  const [wizardStep, setWizardStep] = useState(0);
  const [query, setQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');
  const [portfoliosLoaded, setPortfoliosLoaded] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [universes, setUniverses] = useState<ReadyUniverse[]>([]);
  const [selected, setSelected] = useState<Portfolio | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [proposalLoading, setProposalLoading] = useState(false);
  const [detail, setDetail] = useState<Recommendation | null>(null);
  const [strategy, setStrategy] = useState('MVO');
  const [fallback, setFallback] = useState(false);
  const selection = useRef(0);
  const navigation = useRef(0);
  const activeView = useRef<WorkspaceView>('overview');
  const proposalRequest = useRef(new LatestRequest());
  const api = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store', headers: { 'content-type': 'application/json', ...(session ? { 'x-csrf-token': session.csrfToken } : {}), ...init.headers } });
    const body = await response.json();
    if (!response.ok) {
      if (response.status === 401) { selection.current++; setSession(null); setSelected(null); setDashboard(null); setDetail(null); setJob(null); setPortfolios([]); setPortfoliosLoaded(false); setOpening(null); setWizardStep(0); }
      throw new Error(typeof body.error === 'string' ? body.error : body.error?.message ?? (typeof body.detail === 'string' ? body.detail : `Yêu cầu thất bại (${response.status}).`));
    }
    return body;
  }, [session]);
  useEffect(() => { let active = true; fetch('/auth/session', { cache: 'no-store' }).then(async response => { if (response.ok) { const data = await response.json(); if (active) setSession(data); } else if (response.status !== 401) throw new Error('Dịch vụ đăng nhập chưa sẵn sàng.'); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoaded(true); }); return () => { active = false; }; }, []);
  function navigate(next: WorkspaceView) {
    if (activeView.current !== next) navigation.current++;
    activeView.current = next; window.location.hash = next; setView(next);
  }
  useEffect(() => {
    const sync = () => {
      const hash = window.location.hash.slice(1);
      if (hash === 'main-content' || hash === 'methodology') return;
      const next = ['overview', 'portfolios', 'create', 'proposal', 'profile'].includes(hash) ? hash as WorkspaceView : 'overview';
      if (activeView.current !== next) navigation.current++;
      activeView.current = next; setView(next);
    };
    sync(); window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);
  useEffect(() => { if (loaded) { titleRef.current?.focus({ preventScroll: true }); window.scrollTo(0, 0); } }, [view, loaded]);
  const refreshPortfolios = useCallback(async () => { const data = await api('/api/v1/portfolios'); setPortfolios(data); setPortfoliosLoaded(true); }, [api]);
  useEffect(() => { if (session) refreshPortfolios().catch(err => setError(err.message)); }, [session, refreshPortfolios]);
  useEffect(() => { let active = true; if (session) api('/api/v1/universes').then(data => { if (active) setUniverses(data); }).catch(err => { if (active) setError(err.message); }); else setUniverses([]); return () => { active = false; }; }, [session, api]);
  const selectPortfolio = async (portfolio: Portfolio, destination: WorkspaceView = 'overview') => {
    const epoch = ++selection.current;
    const navigationEpoch = navigation.current;
    proposalRequest.current.invalidate();
    setOpening(portfolio.id); setProposalLoading(false); setError(''); setSelected(null); setDetail(null); setDashboard(null); setRecommendations([]); setJob(null);
    try {
      const [current, items] = await Promise.all([api(`/api/v1/portfolios/${portfolio.id}/dashboard`), api(`/api/v1/portfolios/${portfolio.id}/recommendations`)]);
      if (selection.current !== epoch) return;
      setSelected(current.portfolio); setDashboard(current); setRecommendations(items);
      if (navigation.current === navigationEpoch) navigate(destination);
    } catch (err) { if (selection.current === epoch) setError((err as Error).message); }
    finally { if (selection.current === epoch) setOpening(null); }
  };
  useEffect(() => {
    if (!job || terminal(job.status)) return;
    const epoch = selection.current;
    let active = true;
    const timer = setTimeout(async () => {
      try {
        const next = await api(`/api/v1/jobs/portfolio/${job.job_id}`);
        if (!active || epoch !== selection.current) return;
        if (next.recommendation_id) {
          const item = await api(`/api/v1/recommendations/${next.recommendation_id}`);
          if (!active || epoch !== selection.current) return;
          setDetail(item); setRecommendations(items => [item, ...items.filter(i => i.id !== item.id)]);
        }
        setJob({ ...next, portfolio_id: job.portfolio_id });
      } catch (err) { if (active && epoch === selection.current) { setError((err as Error).message); setJob(null); } }
    }, 1500);
    return () => { active = false; clearTimeout(timer); };
  }, [job, api]);
  async function createPortfolio(body: unknown) {
    setBusy(true); setError('');
    try { const created = await api('/api/v1/onboarding/portfolios', { method: 'POST', body: JSON.stringify(body) }); await refreshPortfolios(); await selectPortfolio(created); return true; }
    catch (err) { setError((err as Error).message); return false; } finally { setBusy(false); }
  }
  async function optimize() {
    if (!selected) return;
    const epoch = selection.current;
    proposalRequest.current.invalidate();
    setBusy(true); setError(''); setDetail(null); setProposalLoading(false);
    try {
      const result = await api(`/api/v1/portfolios/${selected.id}/recommendations`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ strategy, ...(strategy === 'BL_ML' && fallback ? { fallback_strategy: 'EW' } : {}) }) });
      if (epoch === selection.current) setJob({ ...result, status: 'QUEUED', portfolio_id: selected.id });
    } catch (err) { if (epoch === selection.current) setError((err as Error).message); } finally { setBusy(false); }
  }
  async function showProposal(id: string) {
    const epoch = selection.current;
    setDetail(null); setError(''); setProposalLoading(true);
    try { const item = await proposalRequest.current.run(() => api(`/api/v1/recommendations/${id}`)); if (item && epoch === selection.current) { setDetail(item); setProposalLoading(false); } }
    catch (err) { if (epoch === selection.current) { setError((err as Error).message); setProposalLoading(false); } }
  }
  async function acceptTarget() {
    if (!detail || !selected) return;
    const epoch = selection.current;
    setBusy(true); setError('');
    try {
      await api(`/api/v1/recommendations/${detail.id}/accept`, { method: 'POST', headers: { 'If-Match': `"${selected.version}"` }, body: '{}' });
      const current = await api(`/api/v1/portfolios/${selected.id}/dashboard`);
      if (epoch === selection.current) { setDashboard(current); setSelected(current.portfolio); }
      await refreshPortfolios();
    } catch (err) { if (epoch === selection.current) setError((err as Error).message); } finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true);
    try { const result = await api('/auth/logout', { method: 'POST' }); selection.current++; setSession(null); setWizardStep(0); setPortfolios([]); setPortfoliosLoaded(false); setSelected(null); setDashboard(null); setRecommendations([]); setJob(null); setDetail(null); if (!result.providerRevoked) setError('Đã đóng phiên ứng dụng; Identity chưa xác nhận thu hồi token.'); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  const accepted = !!detail && dashboard?.accepted_target?.recommendation_id === detail.id;
  const stale = !!detail && !!selected && (detail.portfolio_version !== selected.version || !detail.valid_until || !(Date.parse(detail.valid_until) > Date.now()));
  const waiting = busy || opening !== null;
  const title = !session ? 'Đầu tư có kế hoạch. Quyết định có cơ sở.'
    : view === 'create' ? wizardTitles[wizardStep]
    : view === 'proposal' ? detail ? 'Một phân bổ để bạn cân nhắc' : 'Lập phương án phù hợp với bạn'
    : view === 'profile' ? 'Hồ sơ rủi ro của bạn'
    : view === 'portfolios' ? 'Danh mục của bạn'
    : selected ? selected.name : portfolios.length ? 'Tổng quan kế hoạch đầu tư' : 'Bắt đầu với danh mục đầu tiên';
  const subtitle = !session ? 'Tư vấn phân bổ tài sản cuối ngày cho thị trường Việt Nam.'
    : view === 'create' ? wizardStep === 2 ? 'Kiểm tra thông tin và ảnh hưởng trước khi tiếp tục.' : 'Điền thông tin bên dưới. Bạn có thể xem lại trước khi xác nhận.'
    : view === 'proposal' ? detail ? 'Tỷ trọng, cơ sở đề xuất và các giới hạn để bạn cân nhắc.' : 'Xem phương án phân bổ trước khi chọn tỷ trọng mục tiêu.'
    : view === 'profile' ? 'Thông tin và chính sách để bạn xem lại khi cần.'
    : view === 'portfolios' ? 'Tìm kiếm, lọc và mở chi tiết nội dung bạn cần.'
    : 'Theo dõi kế hoạch vốn, hồ sơ rủi ro và mục tiêu đã chấp nhận.';
  const filtered = portfolios.filter(item => `${item.name} ${item.universe_id}`.toLocaleLowerCase('vi').includes(query.toLocaleLowerCase('vi')) && (riskFilter === 'all' || item.risk_profile?.profile === riskFilter));
  const portfolioList = <>
    {portfolios.length ? <section className="panel portfolio-list" aria-label="Danh sách danh mục">
      <div className="list-toolbar"><label>Tìm trong danh sách<input type="search" placeholder="Tìm theo tên hoặc mã…" value={query} onChange={e => setQuery(e.target.value)}/></label><label>Lọc theo hồ sơ<select value={riskFilter} onChange={e => setRiskFilter(e.target.value)}><option value="all">Tất cả hồ sơ</option><option value="conservative">Thận trọng</option><option value="balanced">Cân bằng</option><option value="growth">Tăng trưởng</option></select></label><span className="muted small" role="status">{filtered.length} kết quả</span></div>
      <div className="table-wrap mobile-cards"><table><caption>Danh mục của bạn · Vốn kế hoạch do bạn cung cấp.</caption><thead><tr><th scope="col">Danh mục</th><th scope="col">Hồ sơ rủi ro</th><th scope="col">Vốn kế hoạch</th><th scope="col">Bộ tài sản</th><th scope="col"><span className="sr-only">Thao tác</span></th></tr></thead><tbody>{filtered.map(item => <tr key={item.id}><th scope="row"><button className="text-button" disabled={waiting} onClick={() => selectPortfolio(item, view === 'proposal' ? 'proposal' : view === 'profile' ? 'profile' : 'overview')}>{item.name}</button><small className="muted">Phiên bản {item.version}</small></th><td data-label="Hồ sơ rủi ro"><span className="badge">{profileName(item.risk_profile?.profile)}</span></td><td data-label="Vốn kế hoạch">{money(item.capital_vnd)}</td><td data-label="Bộ tài sản">{item.universe_id}</td><td><button className="quiet" disabled={waiting} onClick={() => selectPortfolio(item, view === 'proposal' ? 'proposal' : view === 'profile' ? 'profile' : 'overview')} aria-label={`Mở danh mục ${item.name}`}>{opening === item.id ? 'Đang mở…' : 'Mở danh mục'}</button></td></tr>)}</tbody></table></div>
      {!filtered.length && <div className="empty-state compact"><h2>Không tìm thấy danh mục</h2><p>Thử tên khác hoặc thay đổi bộ lọc.</p><button className="quiet" onClick={() => { setQuery(''); setRiskFilter('all'); }}>Xóa bộ lọc</button></div>}
    </section> : <section className="panel"><div className="empty-state"><span className="empty-icon"><DesignIcon name="empty-portfolio"/></span><h2>Chưa có dữ liệu phù hợp</h2><p>Bắt đầu từ dữ liệu cần thiết. Chúng tôi sẽ hiển thị kết quả khi đủ cơ sở.</p></div></section>}
    <div className="actions"><a className="button" href="#create">Tạo danh mục</a>{selected && <a className="button quiet" href="#overview">Về tổng quan</a>}</div>
  </>;
  return <WorkspaceShell view={view} account={session?.user.name ?? null} busy={waiting} onLogout={logout} context={view === 'create' ? 'Onboarding' : view === 'proposal' ? 'Đề xuất' : view === 'profile' ? 'Hồ sơ' : 'Danh mục'}>
    <header className="page-heading"><p className="eyebrow">KẾ HOẠCH ĐẦU TƯ CỦA BẠN</p><h1 ref={titleRef} tabIndex={-1}>{title}</h1><p className="muted">{subtitle}</p></header>
    {error && <div className="error" role="alert"><strong>Chưa thể hoàn tất yêu cầu</strong><p>{error}</p></div>}
    {session && <div hidden={view !== 'create'}>
        <aside className="notice">{wizardStep === 2 ? 'Hệ thống xác định hồ sơ và policy từ câu trả lời của bạn. Chỉ tạo danh mục sau khi bạn xác nhận.' : 'Lập kế hoạch theo khả năng và nhu cầu vốn thực tế. Thời gian đầu tư không thay đổi thời hạn dự báo của model.'}</aside>
        <RiskWizard busy={waiting} onCreate={createPortfolio} universes={universes} onStepChange={setWizardStep} onCancel={() => navigate('portfolios')}/>
    </div>}
    {!loaded ? <section className="panel loading-state" role="status"><span className="loading-mark" aria-hidden="true"/>Đang kiểm tra phiên…</section>
      : !session ? <>
        <aside className="notice">Ứng dụng tư vấn phân bổ tài sản cuối ngày cho thị trường Việt Nam. Nguồn dữ liệu được ghi rõ trên từng đề xuất.</aside>
        <section className="panel welcome-card"><p className="eyebrow">HIỂU RÕ TRƯỚC KHI QUYẾT ĐỊNH</p><h2>Từ nhu cầu của bạn<br/>đến một kế hoạch có thể theo dõi.</h2><p className="muted">Đánh giá rủi ro, xem đề xuất có nguồn và chủ động chọn mục tiêu. Bạn quyết định tỷ trọng mục tiêu được lưu.</p><ol className="journey-steps"><li>01 · Hiểu nhu cầu</li><li>02 · Review phương án</li><li>03 · Chủ động quyết định</li></ol></section>
        <div className="actions"><a className="button" href="/auth/login">Đăng nhập qua Identity</a><a className="button quiet" href="#methodology" onClick={() => { const disclosure = document.getElementById('methodology'); if (disclosure instanceof HTMLDetailsElement) disclosure.open = true; }}>Xem cách hoạt động</a></div>
      </> : view === 'create' ? null : !portfoliosLoaded ? <section className="panel loading-state" role="status">{error ? <><p>Danh sách danh mục chưa tải được.</p><button className="quiet" onClick={() => { setError(''); refreshPortfolios().catch(err => setError(err.message)); }}>Thử lại</button></> : <><span className="loading-mark" aria-hidden="true"/>Đang tải danh mục…</>}</section>
      : opening ? <section className="panel loading-state" role="status"><span className="loading-mark" aria-hidden="true"/>Đang mở danh mục…</section>
      : view === 'portfolios' || !selected ? <>
        <aside className="notice">{view === 'proposal' || view === 'profile' ? 'Chọn một danh mục để xem hồ sơ và đề xuất tương ứng.' : 'Lập kế hoạch vốn trước, sau đó xem đề xuất. Chấp nhận chỉ lưu tỷ trọng mục tiêu, không thực hiện giao dịch.'}</aside>{portfolioList}
      </> : view === 'profile' ? <>
        <aside className="notice">Hồ sơ được xác định theo policy khi tạo danh mục. Hồ sơ rủi ro không bảo đảm mức thua lỗ tối đa hoặc lợi nhuận.</aside>
        <section className="panel"><div className="section-heading"><h2>{selected.name}</h2><span className="badge">{profileName(selected.risk_profile?.profile)}</span></div><dl className="review-list"><div><dt>Hồ sơ hiện tại</dt><dd>{profileName(selected.risk_profile?.profile)}</dd></div><div><dt>Policy áp dụng</dt><dd>{selected.policy_version_id}</dd></div><div><dt>Ngại rủi ro</dt><dd>{selected.constraints.risk_aversion}</dd></div><div><dt>Giới hạn một tài sản</dt><dd>{(selected.constraints.max_position_weight * 100).toFixed(0)}%</dd></div><div><dt>Bộ tài sản</dt><dd>{selected.universe_id}</dd></div></dl></section><div className="actions"><a className="button" href="#proposal">Xem đề xuất</a><a className="button quiet" href="#portfolios">Đổi danh mục</a></div>
      </> : view === 'overview' ? <>
        <aside className="notice">Tỷ trọng mục tiêu thể hiện kế hoạch bạn đã chấp nhận. Chưa theo dõi tài sản thực tế hoặc hiệu suất đầu tư.</aside>
        <div className="metric-grid"><section className="panel metric-card"><p>Vốn kế hoạch</p><strong>{money(selected.capital_vnd)}</strong><small>Vốn do bạn cung cấp · VND</small></section><section className="panel metric-card"><p>Hồ sơ rủi ro</p><strong>{profileName(selected.risk_profile?.profile)}</strong><small>Tối đa {(selected.constraints.max_position_weight * 100).toFixed(0)}% mỗi tài sản</small></section><section className="panel metric-card"><p>Đề xuất phân bổ</p><strong>{recommendations.length}</strong><small>{dashboard?.accepted_target ? 'Đã có mục tiêu được lưu' : 'Chưa có mục tiêu được lưu'}</small></section></div>
        <section className="panel dashboard"><div className="section-heading"><div><p className="eyebrow">KẾ HOẠCH PHÂN BỔ</p><h2>Mục tiêu đã chấp nhận</h2></div><span className={`badge ${dashboard?.accepted_target ? 'success' : ''}`}>{dashboard?.accepted_target ? 'Đã lưu mục tiêu' : 'Chưa có mục tiêu'}</span></div>
          {dashboard?.accepted_target ? <><p className="muted small">Đã lưu {new Date(dashboard.accepted_target.accepted_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh' })}{!dashboard.target_matches_portfolio && ' · Danh mục đã thay đổi sau lần chấp nhận này'}</p><AllocationView allocation={dashboard.accepted_target.allocation}/></> : <div className="empty-state compact"><span className="empty-icon"><DesignIcon name="views"/></span><h3>Một kế hoạch bắt đầu từ đề xuất</h3><p>Tạo và xem lại phương án trước khi lưu tỷ trọng mục tiêu.</p><a className="button" href="#proposal">Tạo đề xuất phân bổ</a></div>}
          <p className="target-note">Chưa theo dõi holdings hoặc giao dịch. Tỷ trọng mục tiêu không phản ánh tài sản thực tế.</p>
        </section><div className="actions"><a className="button" href="#proposal">{dashboard?.accepted_target ? 'Xem / tạo đề xuất' : 'Lập phương án phân bổ'}</a><a className="button quiet" href="#portfolios">Đổi danh mục</a><a className="button quiet" href="#profile">Xem hồ sơ rủi ro</a></div>
      </> : <>
        <aside className="notice">Mọi đề xuất sử dụng phiên bản danh mục và policy đã chốt. Kết quả hết hạn hoặc khác phiên bản cần được tính lại.</aside>
        {proposalLoading && <section className="panel loading-state" role="status"><span className="loading-mark" aria-hidden="true"/>Đang tải đề xuất…</section>}{!detail && !proposalLoading && <section className="panel"><div className="form-grid optimizer-form"><label>Danh mục<input readOnly value={selected.name}/><small>{selected.universe_id} · Phiên bản {selected.version}</small></label><label>Vốn kế hoạch (VND)<input readOnly value={money(selected.capital_vnd)}/><small>Vốn do bạn cung cấp; chưa phản ánh tài sản thực tế.</small></label><label>Chiến lược được cho phép<select value={strategy} onChange={e => { setStrategy(e.target.value); setFallback(false); }} disabled={waiting || !!job && !terminal(job.status)}><option value="MVO">MVO · Lợi nhuận / rủi ro</option><option value="EW">EW · Phân bổ đều có ràng buộc</option><option value="BL_ML">BL + ML · Model được duyệt</option></select></label><label>Giới hạn một tài sản<input readOnly value={`${(selected.constraints.max_position_weight * 100).toFixed(0)}% · theo policy`}/><small>{profileName(selected.risk_profile?.profile)} · Ngại rủi ro {selected.constraints.risk_aversion}</small></label>{strategy === 'BL_ML' && <label className="check fallback-choice"><input type="checkbox" checked={fallback} onChange={e => setFallback(e.target.checked)} disabled={waiting || !!job && !terminal(job.status)}/><span>Cho phép phương án EW nếu model chưa sẵn sàng<small>Cần chủ động lựa chọn.</small></span></label>}</div></section>}
        {!detail && !proposalLoading && <div className="actions"><button onClick={optimize} disabled={waiting || !!job && !terminal(job.status)}>{waiting ? 'Đang gửi yêu cầu…' : job && !terminal(job.status) ? 'Đang xử lý đề xuất…' : 'Tạo đề xuất'}</button><a className="button quiet" href="#overview">Về tổng quan</a></div>}
        {job && !detail && !proposalLoading && <section className="panel job" role="status" aria-live="polite"><div className="section-heading"><h2>{job.status === 'SUCCEEDED' || job.status === 'COMPLETED' ? 'Đề xuất đã sẵn sàng' : job.status === 'FAILED' ? 'Chưa thể tạo đề xuất' : job.status === 'CANCELLED' ? 'Yêu cầu đã hủy' : 'Đang lập phương án cho bạn'}</h2><span className="badge">{{ QUEUED: 'Đang chờ', RUNNING: 'Đang xử lý', SUCCEEDED: 'Hoàn tất', COMPLETED: 'Hoàn tất', FAILED: 'Thất bại', CANCELLED: 'Đã hủy' }[job.status] ?? job.status}</span></div><small>Mã công việc: {job.job_id}</small><JobTrace reference={job} viewerBase={viewerBase}/>{job.error && <p className="error">{job.error.message ?? 'Tác vụ thất bại. Hãy tạo yêu cầu mới.'}</p>}</section>}
        {recommendations.length > 0 && <nav className="recommendations" aria-label="Lịch sử đề xuất">{recommendations.map((item, i) => <button className={`quiet ${detail?.id === item.id ? 'selected' : ''}`} key={item.id} disabled={waiting} aria-pressed={detail?.id === item.id} onClick={() => showProposal(item.id)}>Đề xuất {recommendations.length - i} · {item.strategy}</button>)}</nav>}
        {detail ? <section className="panel results"><div className="section-heading"><div><p className="eyebrow">ĐỀ XUẤT PHÂN BỔ</p><h2>Phân bổ đề xuất</h2></div><span className={`badge ${accepted ? 'success' : ''}`}>{accepted ? 'Đã lưu mục tiêu' : stale ? 'Cần tính lại' : 'Chờ bạn xem xét'}</span></div><AllocationView allocation={detail}/><div className={`accept-panel ${accepted ? 'accepted' : ''}`} role={accepted ? 'status' : undefined}><div><h3>{accepted ? 'Đã lưu tỷ trọng mục tiêu' : stale ? 'Đề xuất không còn hiệu lực' : 'Bạn chủ động quyết định'}</h3><p>{accepted ? 'Mục tiêu đã được cập nhật trên tổng quan danh mục.' : stale ? 'Hãy tạo đề xuất mới từ phiên bản danh mục hiện tại.' : 'Chấp nhận sẽ lưu tỷ trọng mục tiêu để theo dõi; chưa phát sinh lệnh mua bán.'}</p></div><button onClick={acceptTarget} disabled={waiting || accepted || stale}>{accepted ? 'Đã lưu mục tiêu ✓' : stale ? 'Đề xuất cũ — hãy tạo lại' : busy ? 'Đang lưu…' : 'Chấp nhận làm mục tiêu'}</button></div><div className="actions"><button className="quiet" onClick={() => { proposalRequest.current.invalidate(); setDetail(null); setError(''); }}>Chỉnh phương án</button><a className="button quiet" href="#overview">Về tổng quan</a></div>{accepted && <a className="button quiet" href="#overview">Xem tổng quan danh mục</a>}<details className="diagnostics"><summary>Nguồn dữ liệu và chẩn đoán</summary><JobTrace reference={detail} viewerBase={viewerBase}/><pre>{JSON.stringify(detail, null, 2)}</pre></details></section> : !job && <p className="muted small">Đề xuất được xử lý bất đồng bộ. Ngày dữ liệu, phương pháp và policy được hiển thị cùng kết quả.</p>}
      </>}
    <Methodology/>
  </WorkspaceShell>;
}
