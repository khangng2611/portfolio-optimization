'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { dateTime, ApiError, type Api, type Portfolio } from '../lib/portfolio-types';
import { workspaceHash } from '../lib/workspace-state';
import { money, percentage } from './allocation-view';
import { PriceChart } from './price-chart';
import './paper-portfolio.css';

type Order = { asset_id: string; side: 'BUY' | 'SELL'; quantity: number; price_vnd: number; estimated_fee_vnd: number };
type Preview = { id: string; target_id: string; quote_date: string; quote_as_of: string; quote_source: string; expires_at: string; orders: Order[]; drift: number; estimated_fee_vnd: number };
type Review = { checked_at: string; drift: number | null; reason: string | null; date: string; target_id: string; status: 'DUE' | 'SKIPPED' | 'REVIEWED' };
type Valuation = {
  date: string; nav_vnd: number; pnl_vnd: number; return_fraction: number;
  available_cash_vnd: number; reserved_cash_vnd: number; receivable_vnd: number; fees_vnd: number; spread_vnd: number;
};
type PaperAccount = {
  initialized: boolean; target_id: string | null; initial_capital_vnd: number | null; valuation: Valuation | null;
  history: { date: string; nav_vnd: number; stale_assets?: string[] }[];
  positions: { asset_id: string; quantity: number; price_vnd: number | null; price_date: string | null; value_vnd: number | null; weight: number | null; target_weight: number; drift: number | null }[];
  orders: (Order & { status: 'PENDING' | 'FILLED' | 'EXPIRED' | 'SETTLED'; date: string; preview_id: string; expected_session?: string; wait_reason?: keyof typeof waitReason; fill_date?: string; filled_quantity?: number; fill_price_vnd?: number; fee_vnd?: number; settled_date?: string })[];
  decisions: { id: string; action: 'CONFIRM' | 'SKIP'; decided_at: string; target_id: string; review: string | null }[];
  reviews: Review[]; quote_as_of: string | null; quote_source: string | null; quote_status: 'FRESH' | 'STALE' | 'MISSING'; quote_date: string | null;
};

const quantity = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 6 });
const day = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' });
const formatDay = (date: string) => day.format(new Date(date));
const sideName = { BUY: 'Mua', SELL: 'Bán' };
const waitReason = {
  STOCK_CLOSE: 'Chờ giá đóng cửa của phiên kế tiếp.',
  GOLD_QUOTE: 'Chờ báo giá vàng hai chiều đủ điều kiện của phiên kế tiếp.',
  VFF_DEALING: 'Chờ kỳ giao dịch quỹ (thứ Ba hoặc thứ Năm), sớm nhất từ phiên thứ hai sau khi gửi.',
  VFF_NAV: 'Đã đến kỳ giao dịch. Chờ công bố NAV đúng ngày của kỳ này.',
};
const orderState = { PENDING: 'Chờ khớp', FILLED: 'Đã khớp', EXPIRED: 'Hết hiệu lực', SETTLED: 'Đã thanh toán' };
const reviewState = { DUE: 'Đến hạn', SKIPPED: 'Đã bỏ qua', REVIEWED: 'Đã xem xét' };
const reviewReason: Record<string, string> = { PENDING_ORDERS: 'Còn lệnh chờ', VFF_FILL_AWAITING_PUBLICATION: 'Chờ công bố NAV VFF', MISSING_PRICE: 'Thiếu giá', MISSING_GOLD_QUOTE: 'Thiếu giá vàng hai chiều' };
function reviewDetails(row: Review) {
  return [row.drift != null && 'Lệch ' + percentage(row.drift), row.reason && (reviewReason[row.reason] ?? row.reason)].filter(Boolean).join(' · ');
}
const quoteState = { FRESH: 'Giá đủ điều kiện', STALE: 'Báo giá đã cũ', MISSING: 'Thiếu báo giá' };
const apiPath = (id: string) => `/api/v1/portfolios/${id}/paper`;
const post = (body: unknown) => ({ method: 'POST', body: JSON.stringify(body) });

export function PaperReviewReminder({ portfolioId, api }: { portfolioId: string; api: Api }) {
  const [due, setDue] = useState<Review>();
  useEffect(() => {
    const controller = new AbortController();
    api<PaperAccount>(apiPath(portfolioId), { signal: controller.signal }).then(state => {
      if (!controller.signal.aborted) setDue(state.reviews.find(row => row.status === 'DUE'));
    }).catch(() => { if (!controller.signal.aborted) setDue(undefined); });
    return () => controller.abort();
  }, [portfolioId, api]);
  return !!due && <aside className="notice"><strong>Đến kỳ xem xét danh mục mô phỏng</strong>
    <p>Phiên {formatDay(due.date)} · mục tiêu {due.target_id.slice(0, 8)} {reviewDetails(due)}</p>
    <a href={workspaceHash({ view: 'rebalance', portfolioId })}>Xem xét tái cân bằng</a></aside>;
}

export function PaperHoldings({ account }: { account: PaperAccount }) {
  const valuation = account.valuation;
  return <>
    {valuation && <section className="panel"><h2>Giá trị tài khoản</h2>
      <p className="muted">Phiên định giá {formatDay(valuation.date)}</p>
      <dl className="paper-facts">
        <div><dt>Tổng tài sản</dt><dd>{money(valuation.nav_vnd)}</dd></div>
        <div><dt>Lời/lỗ ròng</dt><dd>{money(valuation.pnl_vnd)} · {percentage(valuation.return_fraction)}</dd></div>
        <div><dt>Vốn đầu kỳ</dt><dd>{account.initial_capital_vnd != null && money(account.initial_capital_vnd)}</dd></div>
        <div><dt>Tiền khả dụng</dt><dd>{money(valuation.available_cash_vnd)}</dd></div>
        <div><dt>Tiền dành mua</dt><dd>{money(valuation.reserved_cash_vnd)}</dd></div>
        <div><dt>Tiền bán chờ về</dt><dd>{money(valuation.receivable_vnd)}</dd></div>
        <div><dt>Phí và thuế đã trả</dt><dd>{money(valuation.fees_vnd)}</dd></div>
        <div><dt>Chênh lệch giá mua/bán</dt><dd>{money(valuation.spread_vnd)}</dd></div>
      </dl></section>}
    {account.history.length > 0 && <section className="panel"><h2>Tổng tài sản theo ngày (VND)</h2>
      <PriceChart nav observations={account.history.map(row => ({ date: row.date, price_vnd: String(row.nav_vnd),
        note: row.stale_assets?.length ? 'Dùng giá gần nhất của ' + row.stale_assets.join(', ') : undefined }))}/>
    </section>}
  </>;
}

function Positions({ positions }: { positions: PaperAccount['positions'] }) {
  return <section className="panel"><h2>Vị thế và mục tiêu</h2>
    {positions.length ? <div className="paper-table" tabIndex={0} role="region" aria-label="Vị thế và tỷ trọng">
      <table><thead><tr>{['Tài sản', 'Số lượng', 'Giá (VND)', 'Ngày giá', 'Giá trị (VND)', 'Tỷ trọng', 'Mục tiêu', 'Lệch (điểm %)'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
      <tbody>{positions.map(row => <tr key={row.asset_id}><th scope="row">{row.asset_id}</th><td>{quantity.format(row.quantity)}</td>
        <td>{row.price_vnd == null ? '—' : quantity.format(row.price_vnd)}</td><td>{row.price_date ? formatDay(row.price_date) : '—'}</td><td>{row.value_vnd == null ? '—' : quantity.format(row.value_vnd)}</td>
        <td>{row.weight == null ? '—' : percentage(row.weight)}</td><td>{percentage(row.target_weight)}</td><td>{row.drift == null ? '—' : (row.drift * 100).toLocaleString('vi-VN', { maximumFractionDigits: 2, signDisplay: 'exceptZero' })}</td></tr>)}</tbody></table>
    </div> : <p>Chưa có vị thế đã khớp.</p>}
  </section>;
}

function PreviewOrders({ preview }: { preview: Preview }) {
  return <><h2>Lệnh dự kiến</h2>
    <p>Mục tiêu {preview.target_id.slice(0, 8)} · Độ lệch {percentage(preview.drift)}</p>
    <p className="muted">Phiên giá {formatDay(preview.quote_date)}{preview.quote_as_of && <> · Dữ liệu lúc {dateTime(preview.quote_as_of)}</>}{preview.quote_source && <> · {preview.quote_source}</>}. Có hiệu lực đến {dateTime(preview.expires_at)}.</p>
    {preview.orders.length ? <div className="paper-table" tabIndex={0} role="region" aria-label="Chi tiết lệnh dự kiến"><table><thead><tr>
      {['Tài sản', 'Lệnh', 'Số lượng', 'Giá dự kiến (VND)', 'Chi phí ước tính (VND)'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{preview.orders.map(row => <tr key={row.asset_id}><th scope="row">{row.asset_id}</th><td>{sideName[row.side]}</td><td>{quantity.format(row.quantity)}</td><td>{quantity.format(row.price_vnd)}</td><td>{quantity.format(row.estimated_fee_vnd)}</td></tr>)}</tbody></table></div> : <p>Không có lệnh khả thi ở phiên này.</p>}
    <p>Tổng chi phí ước tính <strong>{money(preview.estimated_fee_vnd)}</strong></p>
    {preview.orders.length > 0 && <p>Số lượng trên là dự kiến. Lệnh mua có thể khớp ít hơn hoặc không khớp nếu thiếu tiền khả dụng. Tiền bán chỉ dùng được sau khi thanh toán.</p>}</>;
}

export function PaperPortfolio({ portfolio, view, api, targetCurrent }: { portfolio: Portfolio; targetCurrent: boolean; view: 'holdings' | 'rebalance'; api: Api }) {
  const [account, setAccount] = useState<PaperAccount>(), [preview, setPreview] = useState<Preview>();
  const [capital, setCapital] = useState(portfolio.capital_vnd);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [expired, setExpired] = useState(false);
  const version = useRef(0), submitting = useRef(false);
  const base = apiPath(portfolio.id);
  const read = useCallback(async () => {
    if (submitting.current) return;
    const request = ++version.current;
    try {
      const data = await api<PaperAccount>(base);
      if (request === version.current) setAccount(data);
    } catch (err) {
      if (request === version.current) setError((err as Error).message);
    }
  }, [api, base]);
  useEffect(() => {
    void read();
    const refresh = () => { if (!document.hidden) void read(); };
    const timer = window.setInterval(refresh, 60000);
    document.addEventListener('visibilitychange', refresh);
    return () => { version.current++; window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [read]);
  useEffect(() => {
    setExpired(false);
    if (!preview) return;
    const timer = window.setTimeout(() => setExpired(true), Math.max(0, Date.parse(preview.expires_at) - Date.now()));
    return () => window.clearTimeout(timer);
  }, [preview]);

  async function submit(path: string, body: unknown, message = '') {
    if (submitting.current) return;
    submitting.current = true;
    const request = ++version.current;
    setBusy(true); setError(''); setNotice('');
    try {
      if (path === '/preview') {
        const next = await api<Preview>(base + path, post(body));
        if (request === version.current) setPreview(next);
      } else {
        const next = await api<PaperAccount>(base + path, post(body));
        if (request === version.current) { setAccount(next); setPreview(undefined); setNotice(message); }
      }
    } catch (err) {
      if (request !== version.current) return;
      if (err instanceof ApiError && [409, 410, 412].includes(err.status)) {
        setPreview(undefined);
        submitting.current = false; void read();
      }
      setError((err as Error).message);
    } finally { submitting.current = false; setBusy(false); }
  }

  const rebalance = workspaceHash({ view: 'rebalance', portfolioId: portfolio.id });
  const proposal = workspaceHash({ view: 'proposal', portfolioId: portfolio.id });
  const pending = account?.orders.some(order => order.status === 'PENDING');
  const outdated = preview && (!targetCurrent || pending || expired || account?.quote_status !== 'FRESH' || preview.quote_date !== account.quote_date || preview.target_id !== account.target_id);
  return <div className="paper-account" aria-busy={busy}>
    {error && <div className="error" role="alert">{error} <button className="quiet" disabled={busy} onClick={() => { setError(''); void read(); }}>Tải lại tài khoản</button></div>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {!account ? !error && <p role="status">Đang tải tài khoản mô phỏng…</p> : !account.initialized ? <section className="panel"><h2>Mở tài khoản mô phỏng</h2>
      {account.target_id && targetCurrent ? <form onSubmit={event => { event.preventDefault(); void submit('/initialize', { capital_vnd: capital }, 'Đã mở tài khoản bằng tiền mặt.'); }}>
        <p>Vốn ban đầu được ghi nhận bằng tiền mặt. Lịch sử bắt đầu từ lúc mở tài khoản.</p>
        <label>Vốn mô phỏng ban đầu (VND)<input required type="number" min="0.0001" max="10000000000000000000" step="0.0001" value={capital} disabled={busy} onChange={e => setCapital(e.target.value)}/></label>
        <button disabled={busy} type="submit">Khởi tạo bằng tiền mặt</button>
      </form> : <><p>Chấp nhận một mục tiêu phù hợp với phiên bản danh mục hiện tại để mở tài khoản mô phỏng.</p><a className="button quiet" href={proposal}>Xem đề xuất</a></>}
    </section> : <>
      <div className={account.quote_status === 'FRESH' ? 'paper-quotes' : 'notice warning'}><span>{quoteState[account.quote_status]}{account.quote_date && <> · Phiên {formatDay(account.quote_date)}</>}{account.quote_source && <> · {account.quote_source}</>}{account.quote_as_of && <> · Dữ liệu lúc {dateTime(account.quote_as_of)}</>}</span>
        <button className="quiet" disabled={busy} onClick={() => { setError(''); void read(); }}>Cập nhật số liệu</button></div>
      {account.reviews.some(row => row.status === 'DUE') && <aside className="notice"><h2>Đến kỳ xem xét danh mục</h2>
        <p>Cứ 5 phiên thị trường, bạn có thể đối chiếu vị thế với mục tiêu.</p>
        {view === 'holdings' ? <a href={rebalance}>Xem xét tái cân bằng</a> : account.reviews.filter(row => row.status === 'DUE').map(row => <div className="paper-review" key={row.date}>
          <span>Phiên {formatDay(row.date)} · mục tiêu {row.target_id.slice(0, 8)} · {reviewDetails(row)}</span>
          <button className="quiet" disabled={busy} onClick={() => void submit(`/reviews/${row.date}/skip`, {}, 'Đã bỏ qua kỳ xem xét.')}>Bỏ qua kỳ {formatDay(row.date)}</button>
        </div>)}</aside>}
      {view === 'holdings' && <PaperHoldings account={account}/>}
      <Positions positions={account.positions}/>
      {view === 'rebalance' ? <section className="panel">{preview ? <>
        <PreviewOrders preview={preview}/>
        {outdated && <p role="alert">Bản xem trước đã hết hiệu lực. Cần lấy lại báo giá và mục tiêu.</p>}
        <div className="actions">{outdated ? <button disabled={busy || pending || !targetCurrent || account.quote_status !== 'FRESH'} onClick={() => void submit('/preview', {})}>Xem trước lại</button> :
          <button disabled={busy || !preview.orders.length} onClick={() => void submit('/decisions', { preview_id: preview.id, action: 'CONFIRM' }, 'Đã gửi lệnh mô phỏng. Theo dõi khớp lệnh trong sổ lệnh.')}>Xác nhận gửi lệnh mô phỏng</button>}
          {outdated ? <button className="quiet" disabled={busy} onClick={() => setPreview(undefined)}>Đóng bản xem trước</button> :
          <button className="quiet" disabled={busy} onClick={() => void submit('/decisions', { preview_id: preview.id, action: 'SKIP' }, 'Đã bỏ qua bản xem trước.')}>Bỏ qua bản xem trước</button>}</div></> : <>
        <h2>Xem trước tái cân bằng</h2><p>Đối chiếu với mục tiêu đã chấp nhận để xem số lượng, giá và phí dự kiến.</p>
        {!targetCurrent && <p className="notice warning">Hãy chấp nhận một mục tiêu phù hợp với phiên bản danh mục hiện tại.</p>}
        {pending && <p className="notice">Cần đối soát lệnh đang chờ trước khi lập lệnh mới.</p>}
        <div className="actions"><button disabled={busy || pending || account.quote_status !== 'FRESH' || !account.target_id || !targetCurrent} onClick={() => void submit('/preview', {})}>Xem trước lệnh mô phỏng</button>
          <a className="button quiet" href={proposal}>Xem đề xuất</a></div></>}</section> : <div className="actions"><a className="button" href={rebalance}>Xem xét tái cân bằng</a></div>}
      <section className="panel"><h2>Sổ lệnh mô phỏng</h2>
        {pending && <p className="muted">Phiên dự kiến có thể thay đổi theo lịch nghỉ và dữ liệu thị trường. Với VFF, ngày hiển thị là ngày giao dịch của quỹ. Kết quả có thể ghi nhận muộn hơn khi có NAV.</p>}
        {account.orders.length ? <div className="paper-table" tabIndex={0} role="region" aria-label="Sổ lệnh mô phỏng"><table><thead><tr>{['Ngày gửi', 'Tài sản', 'Lệnh', 'Số lượng đặt', 'Trạng thái', 'Phiên dự kiến', 'Ngày khớp', 'Số lượng khớp', 'Giá khớp (VND)', 'Phí và thuế (VND)', 'Ngày tiền về'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
          <tbody>{account.orders.map(row => <tr key={row.preview_id + row.asset_id}><td>{formatDay(row.date)}</td><th scope="row">{row.asset_id}</th><td>{sideName[row.side]}</td><td>{quantity.format(row.quantity)}</td><td>{orderState[row.status]}{row.wait_reason && <small className="paper-wait">{waitReason[row.wait_reason]}</small>}</td>
            <td>{row.expected_session ? formatDay(row.expected_session) : '—'}</td>
            <td>{row.fill_date && formatDay(row.fill_date) || '—'}</td><td>{row.filled_quantity == null ? '—' : quantity.format(row.filled_quantity)}</td>
            <td>{row.fill_price_vnd == null ? '—' : quantity.format(row.fill_price_vnd)}</td><td>{row.fee_vnd == null ? '—' : quantity.format(row.fee_vnd)}</td><td>{row.settled_date && formatDay(row.settled_date) || '—'}</td></tr>)}</tbody></table></div> : <p>Chưa có lệnh mô phỏng.</p>}</section>
      {view === 'rebalance' && account.decisions.length > 0 && <details className="panel"><summary>Quyết định thủ công</summary><ul>
        {account.decisions.map(row => <li key={row.id}>{dateTime(row.decided_at)} · {row.action === 'CONFIRM' ? 'Đã xác nhận' : 'Đã bỏ qua'} · mục tiêu {row.target_id.slice(0, 8)}{row.review && <> · kỳ {formatDay(row.review)}</>}</li>)}</ul></details>}
      {view === 'rebalance' && account.reviews.length > 0 && <details className="panel"><summary>Lịch sử xem xét định kỳ</summary><ul>
        {account.reviews.map(row => <li key={row.date}>{formatDay(row.date)} · mục tiêu {row.target_id.slice(0, 8)} · {reviewState[row.status]} · Kiểm tra lúc {dateTime(row.checked_at)} · {reviewDetails(row)}</li>)}</ul></details>}
    </>}
  </div>;
}
