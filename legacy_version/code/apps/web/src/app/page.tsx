'use client';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
type Session = { user: { name: string; roles: string[] }; csrfToken: string };
type Portfolio = { id: string; name: string; capital_vnd: number; universe_id: string; version: number };
type Job = { job_id: string; status: string; recommendation_id?: string; error?: unknown };
type Recommendation = { id: string; weights?: Record<string, number> | number[]; [key: string]: unknown };
const money = (amount: number) => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(amount);
export default function Home() {
  const [session, setSession] = useState<Session | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selected, setSelected] = useState<Portfolio | null>(null);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState<Recommendation | null>(null);
  const api = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(path, { ...init, credentials: 'same-origin', cache: 'no-store', headers: { 'content-type': 'application/json', ...(session ? { 'x-csrf-token': session.csrfToken } : {}), ...init.headers } });
    const body = await response.json();
    if (!response.ok) { if (response.status === 401) setSession(null); throw new Error(typeof body.error === 'string' ? body.error : typeof body.detail === 'string' ? body.detail : `Yêu cầu thất bại (${response.status}).`); }
    return body;
  }, [session]);
  useEffect(() => { let active = true; fetch('/auth/session', { cache: 'no-store' }).then(async response => { if (response.ok) { const data = await response.json(); if (active) setSession(data); } else if (response.status !== 401) throw new Error('Dịch vụ đăng nhập chưa sẵn sàng.'); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoaded(true); }); return () => { active = false; }; }, []);
  const refreshPortfolios = useCallback(async () => { const data = await api('/api/v1/portfolios'); setPortfolios(Array.isArray(data) ? data : data.items ?? []); }, [api]);
  useEffect(() => { if (session) refreshPortfolios().catch(err => setError(err.message)); }, [session, refreshPortfolios]);
  const selectPortfolio = async (portfolio: Portfolio) => { setError(''); setDetail(null); setJob(null); try { const current = await api(`/api/v1/portfolios/${portfolio.id}`); setSelected(current); const items = await api(`/api/v1/portfolios/${portfolio.id}/recommendations`); setRecommendations(Array.isArray(items) ? items : items.items ?? []); } catch (err) { setError((err as Error).message); } };
  useEffect(() => {
    if (!job || ['SUCCEEDED', 'FAILED', 'CANCELLED', 'COMPLETED'].includes(job.status)) return;
    const timer = setTimeout(async () => { try { const next = await api(`/api/v1/jobs/portfolio/${job.job_id}`); setJob(next); if (next.recommendation_id) { const item = await api(`/api/v1/recommendations/${next.recommendation_id}`); setDetail(item); setRecommendations(items => [item, ...items.filter(i => i.id !== item.id)]); } } catch (err) { setError((err as Error).message); setJob(null); } }, 2000);
    return () => clearTimeout(timer);
  }, [job, api]);
  async function createPortfolio(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); setBusy(true); setError('');
    try { const created = await api('/api/v1/portfolios', { method: 'POST', body: JSON.stringify({ name: form.get('name'), capital_vnd: Number(form.get('capital')), universe_id: 'DEMO', risk_aversion: 1.5, max_position_weight: 0.6 }) }); await refreshPortfolios(); await selectPortfolio(created); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function optimize() {
    if (!selected) return; setBusy(true); setError(''); setDetail(null);
    try { const result = await api(`/api/v1/portfolios/${selected.id}/recommendations`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ strategy: 'MVO' }) }); setJob({ job_id: result.job_id, status: 'PENDING' }); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function logout() { setBusy(true); try { const result = await api('/auth/logout', { method: 'POST' }); setSession(null); setPortfolios([]); setSelected(null); setJob(null); setDetail(null); if (!result.providerRevoked) setError('Đã đóng phiên ứng dụng; máy chủ Identity chưa xác nhận thu hồi token.'); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }
  return <main>
    <header><a className="brand" href="/">◈ <span>PORTFOLIO LAB</span></a><div className="account">{session && <><span>{session.user.name}</span><button className="quiet" onClick={logout} disabled={busy}>Đăng xuất</button></>}</div></header>
    <section className="hero"><p className="eyebrow">NGHIÊN CỨU PHÂN BỔ TÀI SẢN</p><h1>Hiểu rõ danh mục.<br/><span>Chủ động phân bổ.</span></h1><p>Tạo danh mục riêng và theo dõi từng đề xuất tối ưu hóa, từ yêu cầu đến kết quả.</p></section>
    <aside className="notice"><span className="pill">DỮ LIỆU MINH HỌA</span><p>Bộ dữ liệu DEMO cố định dành cho kiểm thử. MVO dùng đầu vào đã chuẩn bị; chưa có dự báo ML trực tiếp hay giao dịch thực.</p></aside>
    {error && <p className="error" role="alert">{error}</p>}
    {!loaded ? <p role="status">Đang kiểm tra phiên…</p> : !session ? <section className="login panel"><p className="eyebrow">KHÔNG GIAN CÁ NHÂN</p><h2>Bắt đầu với danh mục của bạn</h2><p>Đăng nhập qua Identity để tạo và xem các danh mục thuộc tài khoản của bạn.</p><a className="button" href="/auth/login">Đăng nhập với Keycloak <span>↗</span></a></section> : <>
      <div className="section-heading"><h2>Danh mục của bạn</h2><span className="muted">Vai trò: {session.user.roles.join(', ') || 'chưa được cấp'}</span></div>
      <div className="workspace"><section className="panel"><h3>Tạo danh mục</h3><form onSubmit={createPortfolio}><label>Tên danh mục<input name="name" required maxLength={120} placeholder="Danh mục nghiên cứu"/></label><label>Vốn dự kiến (VND)<input name="capital" type="number" required min="1" step="1" defaultValue="100000000"/></label><p className="muted small">Universe DEMO · Hệ số ngại rủi ro 1,5 · Tỷ trọng tối đa 60% mỗi tài sản.</p><button disabled={busy} type="submit">{busy ? 'Đang xử lý…' : 'Tạo danh mục'}</button></form></section>
      <section className="panel list"><h3>Đang quản lý <span className="count">{portfolios.length}</span></h3>{portfolios.length === 0 ? <div className="empty">Chưa có danh mục.<br/>Tạo danh mục đầu tiên để bắt đầu.</div> : portfolios.map(item => <button key={item.id} className={`portfolio ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => selectPortfolio(item)}><span><strong>{item.name}</strong><small>{item.universe_id} · Phiên bản {item.version}</small></span><span>{money(item.capital_vnd)} →</span></button>)}</section></div>
      {selected && <section className="panel results"><div className="section-heading"><div><p className="eyebrow">ĐỀ XUẤT PHÂN BỔ</p><h2>{selected.name}</h2></div><button onClick={optimize} disabled={busy || !!job && !['SUCCEEDED', 'FAILED', 'CANCELLED', 'COMPLETED'].includes(job.status)}>Tạo đề xuất MVO →</button></div>
        {job && <div className="job" role="status"><strong>Trạng thái: {job.status}</strong><small>Mã công việc: {job.job_id}</small>{job.error != null && <p className="error">{typeof job.error === 'string' ? job.error : JSON.stringify(job.error)}</p>}</div>}
        {recommendations.length > 0 && <div className="recommendations">{recommendations.map((item, index) => <button className="quiet" key={item.id} onClick={async () => { try { setDetail(await api(`/api/v1/recommendations/${item.id}`)); } catch (err) { setError((err as Error).message); } }}>Xem đề xuất {index + 1}</button>)}</div>}
        {detail ? <div><h3>Kết quả và nguồn đầu vào</h3><pre>{JSON.stringify(detail, null, 2)}</pre></div> : !job && <p className="muted">Đề xuất chạy bất đồng bộ. Kết quả và thông tin đầu vào sẽ hiển thị tại đây.</p>}
      </section>}
    </>}
    <footer>Portfolio Lab <span>Thử nghiệm định lượng · Không thực hiện giao dịch</span></footer>
  </main>;
}
