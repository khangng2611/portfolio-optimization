'use client';

import { AnswerRows, quantifiedAnswers, RiskQuestions, RiskReason, type RiskDraft as Draft } from './risk-questions';
import type { RiskAnswers, RiskProfile as Profile } from '../lib/portfolio-types';
import { TaskActions } from './task-actions';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { profileName } from './allocation-view';
import { Pagination } from './portfolio-lifecycle';
import { ApiError, dateTime, type Api, type Page, type PageApi, type Portfolio } from '../lib/portfolio-types';
import { workspaceHash } from '../lib/workspace-state';

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
const percent = (value: number) => `${(value * 100).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%`;

function initialDraft(portfolio: Portfolio): Draft {
  const answers = (portfolio.risk_profile as Profile | null)?.answers;
  const quantified = answers?.questionnaire_version === 'risk-v2' ? answers : undefined;
  return {
    horizon: answers ? String(answers.horizon_months) : '', liquidity: quantified?.liquidity_need ?? '',
    loss: quantified?.loss_tolerance ?? '', reserve: quantified?.reserve_months ?? '', experience: answers?.experience ?? '',
  };
}

function PolicySummary({ value, title }: { value: PolicyState; title: string }) {
  return <section className="market-section" aria-label={title}>
    <h3>{title}</h3><RiskReason profile={value.risk_profile}/>
    <dl className="review-list">
      <div><dt>Hồ sơ rủi ro</dt><dd>{profileName(value.risk_profile?.profile)}</dd></div>
      <div><dt>Tỷ trọng tối đa mỗi tài sản</dt><dd>{percent(value.constraints.max_position_weight)}</dd></div>
      {value.constraints.min_defensive_weight !== undefined && <div><dt>Tỷ trọng phòng thủ tối thiểu</dt><dd>{percent(value.constraints.min_defensive_weight)}</dd></div>}
      {value.constraints.max_non_defensive_weight !== undefined && <div><dt>Tỷ trọng ngoài nhóm phòng thủ tối đa</dt><dd>{percent(value.constraints.max_non_defensive_weight)}</dd></div>}
      {!!value.constraints.defensive_asset_ids?.length && <div><dt>Tài sản phòng thủ</dt><dd>{value.constraints.defensive_asset_ids.join(', ')}</dd></div>}
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
    const answers = quantifiedAnswers(draft);
    if (inFlight.current || conflict || !answers) return;
    if (!event.currentTarget.checkValidity()) { event.currentTarget.reportValidity(); return; }
    inFlight.current = true; setBusy('preview'); setError(''); setSaved(null); setUncertain(false);
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
      <ol className="step-progress" aria-label="Tiến trình đánh giá lại rủi ro">{['Câu trả lời', 'Xem lại', 'Xác nhận'].map((label, index) => <li key={label} className={index <= step ? 'complete' : ''} aria-current={index === step ? 'step' : undefined}><span>{index + 1}. {label}</span>{index < step && <span className="sr-only"> · Đã hoàn thành</span>}</li>)}</ol>
      <p className="muted small">{portfolio.name}</p>
      <h2>Điều chỉnh theo mục tiêu hiện tại</h2>
      <p className="muted">Cập nhật câu trả lời để xem hồ sơ rủi ro và giới hạn phân bổ phù hợp với kế hoạch hiện tại.</p>
      {error && <div className="error" role="alert" tabIndex={-1} ref={alert} data-testid={conflict ? 'risk-conflict-notice' : 'risk-error'}>
        <strong>{conflict ? 'Danh mục đã thay đổi ở nơi khác' : uncertain ? 'Chưa xác định được kết quả xác nhận' : 'Chưa hoàn tất yêu cầu'}</strong><p>{error}</p>
        {uncertain && <p>Chọn xác nhận lại để kiểm tra đúng yêu cầu đã gửi. Hệ thống giữ nguyên mã yêu cầu và phiên bản đã xem lại.</p>}
        {conflict && <button type="button" className="quiet" onClick={reload} disabled={!!busy}>Tải phiên bản mới</button>}
      </div>}
      {saved && <div className="notice" role="status" tabIndex={-1} ref={success}><strong>Đã lưu hồ sơ rủi ro mới</strong><p>{profileName(saved.risk_profile?.profile)}. Tạo đề xuất mới để sử dụng hồ sơ này.</p></div>}
      <form onSubmit={previewAnswers} aria-busy={busy === 'preview'}>
        <fieldset disabled={!!busy || conflict}><legend className="sr-only">Câu trả lời đánh giá rủi ro</legend>
          <div className="form-grid">
            <label>Thời gian đầu tư (tháng)<input data-testid="risk-horizon" type="number" required min="1" max="600" step="1" value={draft.horizon} onChange={event => change('horizon', event.target.value)}/><small>Số nguyên từ 1 đến 600 tháng.</small></label>
          </div>
          <RiskQuestions idPrefix="reassess" draft={draft} capital={portfolio.capital_vnd} onChange={change}/>
          {!preview && <TaskActions hint="Xem lại trước khi xác nhận hồ sơ rủi ro mới."><button data-testid="risk-preview" type="submit">{busy === 'preview' ? 'Đang xem lại…' : 'Xem lại hồ sơ'}</button></TaskActions>}
        </fieldset>
      </form>
    </section>
    {preview && <section className="panel" aria-busy={busy === 'confirm'} aria-labelledby="risk-review-heading">
      <h2 id="risk-review-heading" ref={reviewHeading} tabIndex={-1}>Hồ sơ thay đổi như thế nào?</h2>
      <div><PolicySummary value={preview.before} title="Hồ sơ hiện tại"/><PolicySummary value={preview.after} title="Sau khi xác nhận"/></div>
      <aside className="notice warning">Hồ sơ rủi ro không bảo đảm lợi nhuận hay giới hạn thua lỗ. Sau khi xác nhận, hãy tạo đề xuất mới để dùng hồ sơ này. Mục tiêu đã lưu vẫn giữ tỷ trọng đã chấp nhận.</aside>
      <TaskActions><button type="button" data-testid="risk-confirm" disabled={!!busy || conflict} onClick={confirm}>{busy === 'confirm' ? 'Đang xác nhận…' : uncertain ? 'Xác nhận lại cùng yêu cầu' : 'Xác nhận hồ sơ mới'}</button><button className="quiet" type="button" disabled={!!busy} onClick={() => { setPreview(null); intent.current = null; setUncertain(false); }}>Sửa câu trả lời</button></TaskActions>
    </section>}
    <section className="panel" aria-label="Lịch sử hồ sơ rủi ro" aria-busy={historyBusy}>
      <h2>Lịch sử hồ sơ rủi ro</h2>
      {historyError ? <div className="error" role="alert"><p>{historyError}</p><button className="quiet" type="button" onClick={() => setRevision(value => value + 1)}>Thử tải lại lịch sử</button></div> : <>
        {historyBusy ? <p role="status">Đang tải lịch sử hồ sơ…</p> : history.items.length ? <ol className="target-timeline">{history.items.map(item => <li key={item.id} data-testid={`risk-history-${item.id}`}>
          <div><strong>{profileName(item.risk_profile?.profile)}</strong> <span className={`badge ${item.is_active ? 'success' : ''}`}>{item.is_active ? 'Đang áp dụng' : 'Đã lưu trong lịch sử'}</span>
            <p>{dateTime(item.created_at)} · {item.reason === 'onboarding' ? 'Thiết lập ban đầu' : 'Đánh giá lại'}</p>
            <details><summary>Xem câu trả lời và giới hạn</summary><dl className="review-list">
              <AnswerRows answers={item.answers}/>
              <div><dt>Tỷ trọng tối đa mỗi tài sản</dt><dd>{percent(item.constraints.max_position_weight)}</dd></div>
            </dl></details>
          </div>
        </li>)}</ol> : <div className="empty-state compact"><h3>Chưa có lần đánh giá được ghi nhận</h3><p>Sau khi bạn xác nhận hồ sơ, lần đánh giá sẽ xuất hiện ở đây.</p></div>}
        <Pagination total={history.total} offset={offset} onChange={setOffset} busy={historyBusy}/>
      </>}
    </section>
    <div className="actions"><a className="button quiet" href={workspaceHash({ view: 'profile', portfolioId: portfolio.id })}>Về hồ sơ rủi ro</a><a className="button quiet" href={workspaceHash({ view: 'history', portfolioId: portfolio.id })}>Xem mục tiêu đã lưu</a></div>
  </div>;
}
