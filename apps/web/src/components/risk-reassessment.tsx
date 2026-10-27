'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { profileName } from './allocation-view';
import { Pagination } from './portfolio-lifecycle';
import { ApiError, dateTime, type Api, type Page, type PageApi, type Portfolio } from '../lib/portfolio-types';
import { workspaceHash } from '../lib/workspace-state';

type Level = 'low' | 'medium' | 'high';
type RiskAnswers = {
  questionnaire_version: 'risk-v1'; horizon_months: number; liquidity_need: Level;
  loss_tolerance: Level; experience: 'beginner' | 'experienced';
};
type Draft = { horizon: string; liquidity: Level; loss: Level; experience: RiskAnswers['experience'] };
type Profile = { profile: string; answers?: RiskAnswers; version_id?: string; mapping_version?: string };
type PolicyState = {
  risk_profile: Profile | null; policy_version_id: string;
  constraints: Portfolio['constraints'] & {
    defensive_asset_ids?: string[]; min_defensive_weight?: number; max_non_defensive_weight?: number;
  };
};
type Preview = { portfolio_id: string; portfolio_version: number; before: PolicyState; after: PolicyState };
type Revision = PolicyState & {
  id: string; portfolio_id: string; portfolio_version: number;
  reason: 'onboarding' | 'reassessment'; created_at: string;
  answers: RiskAnswers; mapping_version: string;
};
type HistoryEntry = Revision & { is_active: boolean };
type Intent = { key: string; version: number; body: string };
const levels: Record<Level, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao' };
const percent = (value: number) => `${(value * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`;
const number = (value: number) => value.toLocaleString('vi-VN', { maximumFractionDigits: 2 });

function initialDraft(portfolio: Portfolio): Draft {
  const answers = (portfolio.risk_profile as Profile | null)?.answers;
  return {
    horizon: String(answers?.horizon_months ?? 36), liquidity: answers?.liquidity_need ?? 'low',
    loss: answers?.loss_tolerance ?? 'medium', experience: answers?.experience ?? 'beginner',
  };
}

function PolicySummary({ value, title, proposed = false }: { value: PolicyState; title: string; proposed?: boolean }) {
  return <section className="market-section" aria-label={title}>
    <h3>{title}</h3>
    <dl className="review-list">
      <div><dt>Hồ sơ rủi ro</dt><dd>{profileName(value.risk_profile?.profile)}</dd></div>
      <div><dt>Mức ngại rủi ro</dt><dd>{number(value.constraints.risk_aversion)}</dd></div>
      <div><dt>Tỷ trọng tối đa mỗi tài sản</dt><dd>{percent(value.constraints.max_position_weight)}</dd></div>
      {value.constraints.min_defensive_weight !== undefined && <div><dt>Tỷ trọng phòng thủ tối thiểu</dt><dd>{percent(value.constraints.min_defensive_weight)}</dd></div>}
      {value.constraints.max_non_defensive_weight !== undefined && <div><dt>Tỷ trọng ngoài nhóm phòng thủ tối đa</dt><dd>{percent(value.constraints.max_non_defensive_weight)}</dd></div>}
      {!!value.constraints.defensive_asset_ids?.length && <div><dt>Tài sản phòng thủ</dt><dd>{value.constraints.defensive_asset_ids.join(', ')}</dd></div>}
      <div><dt>Policy</dt><dd className="market-code">{value.policy_version_id}</dd></div>
      <div><dt>Phiên bản hồ sơ</dt><dd className="market-code">{value.risk_profile?.version_id ?? (proposed ? 'Được cấp khi xác nhận' : 'Chưa có mã phiên bản được ghi nhận')}</dd></div>
    </dl>
  </section>;
}

export function RiskReassessment({ portfolio, api, fetchPage, onSaved, onReload }: {
  portfolio: Portfolio; api: Api; fetchPage: PageApi; onSaved: () => void; onReload: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => initialDraft(portfolio));
  const [preview, setPreview] = useState<Preview | null>(null);
  const [saved, setSaved] = useState<Revision | null>(null);
  const [busy, setBusy] = useState<'preview' | 'confirm' | null>(null);
  const [error, setError] = useState(''), [conflict, setConflict] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [offset, setOffset] = useState(0), [revision, setRevision] = useState(0);
  const [history, setHistory] = useState<Page<HistoryEntry>>({ items: [], total: 0, limit: 10, offset: 0 });
  const [historyBusy, setHistoryBusy] = useState(true), [historyError, setHistoryError] = useState('');
  const intent = useRef<Intent | null>(null);
  const inFlight = useRef(false);
  const alert = useRef<HTMLDivElement>(null), reviewHeading = useRef<HTMLHeadingElement>(null);
  const success = useRef<HTMLDivElement>(null);
  const base = `/api/v1/portfolios/${portfolio.id}/risk-assessments`;
  const step = saved ? 2 : preview ? 1 : 0;

  useEffect(() => {
    setDraft(initialDraft(portfolio)); setPreview(null); setError(''); setConflict(false); setUncertain(false);
    intent.current = null;
  }, [portfolio.id, portfolio.version]);

  useEffect(() => {
    let active = true;
    setHistoryBusy(true); setHistoryError('');
    fetchPage<HistoryEntry>(`${base}?limit=10&offset=${offset}`)
      .then(value => { if (active) setHistory(value); })
      .catch(err => { if (active) setHistoryError((err as Error).message); })
      .finally(() => { if (active) setHistoryBusy(false); });
    return () => { active = false; };
  }, [fetchPage, base, offset, revision, portfolio.version]);

  function change<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft(current => ({ ...current, [key]: value }));
    setPreview(null); setSaved(null); setError(''); setUncertain(false);
    intent.current = null;
  }

  function failed(err: unknown, confirming: boolean) {
    const stale = err instanceof ApiError && err.status === 412;
    setConflict(stale);
    setUncertain(confirming && (!(err instanceof ApiError) || err.status >= 500 || err.status <= 0));
    setError(stale ? 'Danh mục đã thay đổi. Tải phiên bản mới rồi xem lại hồ sơ trước khi xác nhận.' : (err as Error).message || 'Chưa hoàn tất yêu cầu. Vui lòng thử lại.');
    requestAnimationFrame(() => alert.current?.focus());
  }

  async function previewAnswers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || conflict) return;
    inFlight.current = true; setBusy('preview'); setError(''); setSaved(null); setUncertain(false);
    const answers: RiskAnswers = {
      questionnaire_version: 'risk-v1', horizon_months: Number(draft.horizon),
      liquidity_need: draft.liquidity, loss_tolerance: draft.loss, experience: draft.experience,
    };
    intent.current = null;
    try {
      const value = await api<Preview>(`${base}/preview`, { method: 'POST', body: JSON.stringify({ answers }) });
      setPreview(value);
      requestAnimationFrame(() => reviewHeading.current?.focus());
    } catch (err) { setPreview(null); failed(err, false); }
    finally { inFlight.current = false; setBusy(null); }
  }

  async function confirm() {
    if (!preview || conflict || inFlight.current) return;
    inFlight.current = true; setBusy('confirm'); setError('');
    // Keep the exact reviewed body, key and version after an uncertain response.
    // An explicit retry recovers the receipt; no effect replays a mutation.
    const current = intent.current ?? {
      key: crypto.randomUUID(), version: preview.portfolio_version,
      body: JSON.stringify({ answers: preview.after.risk_profile?.answers }),
    };
    intent.current = current;
    try {
      const value = await api<Revision>(base, {
        method: 'POST', body: current.body,
        headers: { 'Idempotency-Key': current.key, 'If-Match': `"${current.version}"` },
      });
      setSaved(value); setPreview(null); setUncertain(false); intent.current = null;
      setOffset(0); setRevision(value => value + 1);
      requestAnimationFrame(() => success.current?.focus());
      onSaved();
    } catch (err) { failed(err, true); }
    finally { inFlight.current = false; setBusy(null); }
  }

  function reload() {
    if (inFlight.current) return;
    setPreview(null); setSaved(null); intent.current = null;
    onReload();
  }

  return <div className="risk-wizard" data-testid="risk-reassessment">
    <section className="panel wizard-card">
      <ol className="step-progress" aria-label="Tiến trình đánh giá lại rủi ro">{['Câu trả lời', 'Xem lại', 'Xác nhận'].map((label, index) => <li key={label} className={index <= step ? 'complete' : ''} aria-current={index === step ? 'step' : undefined}><span className="sr-only">{index + 1}. {label}{index < step ? ' · Đã hoàn thành' : ''}</span></li>)}</ol>
      <p className="eyebrow">HỒ SƠ RỦI RO · {portfolio.name}</p>
      <h2>Điều chỉnh theo mục tiêu hiện tại</h2>
      <p className="muted">Xem lại câu trả lời và policy do hệ thống xác định trước khi xác nhận. Mục tiêu đã chấp nhận được giữ nguyên trong lịch sử; đề xuất cũ cần được tính lại sau khi hồ sơ thay đổi.</p>
      {error && <div className="error" role="alert" tabIndex={-1} ref={alert} data-testid={conflict ? 'risk-conflict-notice' : 'risk-error'}>
        <strong>{conflict ? 'Danh mục đã thay đổi ở nơi khác' : uncertain ? 'Chưa xác định được kết quả xác nhận' : 'Chưa hoàn tất yêu cầu'}</strong><p>{error}</p>
        {uncertain && <p>Chọn xác nhận lại để kiểm tra đúng yêu cầu đã gửi. Hệ thống giữ nguyên mã yêu cầu và phiên bản đã xem lại.</p>}
        {conflict && <button type="button" className="quiet" onClick={reload} disabled={!!busy}>Tải phiên bản mới</button>}
      </div>}
      {saved && <div className="notice" role="status" tabIndex={-1} ref={success}><strong>Đã lưu hồ sơ rủi ro mới</strong><p>{profileName(saved.risk_profile?.profile)} · Phiên bản danh mục {saved.portfolio_version}. Tạo đề xuất mới để sử dụng hồ sơ này.</p><p className="market-code small">Mã hồ sơ {saved.id}</p></div>}
      <form onSubmit={previewAnswers} aria-busy={busy === 'preview'}>
        <fieldset disabled={!!busy || conflict}><legend className="sr-only">Câu trả lời đánh giá rủi ro</legend>
          <div className="form-grid">
            <label>Thời gian đầu tư (tháng)<input data-testid="risk-horizon" type="number" required min="1" max="600" step="1" value={draft.horizon} onChange={event => change('horizon', event.target.value)}/><small>Số nguyên từ 1 đến 600 tháng.</small></label>
            <label>Nhu cầu rút vốn sớm<select data-testid="risk-liquidity" value={draft.liquidity} onChange={event => change('liquidity', event.target.value as Level)}><option value="low">Thấp — có nguồn dự phòng riêng</option><option value="medium">Vừa — có thể cần một phần</option><option value="high">Cao — có thể cần phần lớn</option></select></label>
            <label>Khi danh mục giảm giá, mức chịu đựng của bạn<select data-testid="risk-loss" value={draft.loss} onChange={event => change('loss', event.target.value as Level)}><option value="low">Thấp — ưu tiên giữ vốn</option><option value="medium">Vừa — chấp nhận dao động</option><option value="high">Cao — chấp nhận giảm mạnh</option></select></label>
            <label>Kinh nghiệm đầu tư<select data-testid="risk-experience" value={draft.experience} onChange={event => change('experience', event.target.value as RiskAnswers['experience'])}><option value="beginner">Mới bắt đầu</option><option value="experienced">Đã có kinh nghiệm</option></select></label>
          </div>
          <div className="actions"><button data-testid="risk-preview" type="submit">{busy === 'preview' ? 'Đang xem lại…' : 'Xem lại hồ sơ'}</button></div>
        </fieldset>
      </form>
    </section>
    {preview && <section className="panel" aria-busy={busy === 'confirm'} aria-labelledby="risk-review-heading">
      <p className="eyebrow">XEM LẠI TRƯỚC KHI XÁC NHẬN</p>
      <h2 id="risk-review-heading" ref={reviewHeading} tabIndex={-1}>Hồ sơ thay đổi như thế nào?</h2>
      <p className="muted">Đang xem lại phiên bản danh mục {preview.portfolio_version}. Chỉ bước xác nhận bên dưới mới lưu hồ sơ mới.</p>
      <div><PolicySummary value={preview.before} title="Hồ sơ hiện tại"/><PolicySummary value={preview.after} title="Sau khi xác nhận" proposed/></div>
      <aside className="notice warning">Hồ sơ rủi ro không bảo đảm mức thua lỗ tối đa hoặc lợi nhuận. Xác nhận tạo phiên bản mới và yêu cầu tính lại các đề xuất cũ; các mục tiêu đã lưu giữ nguyên tỷ trọng và policy tại thời điểm chấp nhận.</aside>
      <div className="actions"><button type="button" data-testid="risk-confirm" disabled={!!busy || conflict} onClick={confirm}>{busy === 'confirm' ? 'Đang xác nhận…' : uncertain ? 'Xác nhận lại cùng yêu cầu' : 'Xác nhận hồ sơ mới'}</button><button className="quiet" type="button" disabled={!!busy} onClick={() => { setPreview(null); intent.current = null; setUncertain(false); }}>Sửa câu trả lời</button></div>
    </section>}
    <section className="panel" aria-label="Lịch sử hồ sơ rủi ro" aria-busy={historyBusy}>
      <h2>Lịch sử hồ sơ rủi ro</h2><p className="muted">Mỗi lần xác nhận lưu câu trả lời, ràng buộc và mã policy của riêng lần đánh giá đó. Trạng thái hiện tại cho biết hồ sơ nào đang được áp dụng.</p>
      {historyError ? <div className="error" role="alert"><p>{historyError}</p><button className="quiet" type="button" onClick={() => setRevision(value => value + 1)}>Thử tải lại lịch sử</button></div> : <>
        {historyBusy ? <p role="status">Đang tải lịch sử hồ sơ…</p> : history.items.length ? <ol className="target-timeline">{history.items.map(item => <li key={item.id} data-testid={`risk-history-${item.id}`}>
          <div><strong>{profileName(item.risk_profile?.profile)}</strong> <span className={`badge ${item.is_active ? 'success' : ''}`}>{item.is_active ? 'Đang áp dụng' : 'Đã lưu trong lịch sử'}</span>
            <p>{dateTime(item.created_at)} · {item.reason === 'onboarding' ? 'Thiết lập ban đầu' : 'Đánh giá lại'} · Phiên bản danh mục {item.portfolio_version}</p>
            <details><summary>Xem câu trả lời và policy</summary><dl className="review-list">
              <div><dt>Thời gian đầu tư</dt><dd>{item.answers.horizon_months} tháng</dd></div>
              <div><dt>Rút vốn sớm / chịu biến động</dt><dd>{levels[item.answers.liquidity_need]} / {levels[item.answers.loss_tolerance]}</dd></div>
              <div><dt>Kinh nghiệm</dt><dd>{item.answers.experience === 'beginner' ? 'Mới bắt đầu' : 'Đã có kinh nghiệm'}</dd></div>
              <div><dt>Mức ngại rủi ro / tỷ trọng tối đa</dt><dd>{number(item.constraints.risk_aversion)} / {percent(item.constraints.max_position_weight)}</dd></div>
              <div><dt>Mã hồ sơ</dt><dd className="market-code">{item.id}</dd></div>
              <div><dt>Policy / phiên bản ánh xạ</dt><dd className="market-code">{item.policy_version_id}<small>{item.mapping_version}</small></dd></div>
            </dl></details>
          </div>
        </li>)}</ol> : <div className="empty-state compact"><h3>Chưa có lần đánh giá được ghi nhận</h3><p>Danh mục cũ hoặc danh mục dùng ràng buộc tùy chỉnh có thể chưa có lịch sử đánh giá. Hệ thống không suy đoán câu trả lời hay thời điểm đánh giá trước đây.</p></div>}
        <Pagination total={history.total} offset={offset} onChange={setOffset} busy={historyBusy}/>
      </>}
    </section>
    <div className="actions"><a className="button quiet" href={workspaceHash({ view: 'profile', portfolioId: portfolio.id })}>Về hồ sơ & cài đặt</a><a className="button quiet" href={workspaceHash({ view: 'history', portfolioId: portfolio.id })}>Xem mục tiêu đã lưu</a></div>
  </div>;
}
