'use client';
import { useRef, useState, type FormEvent } from 'react';
import { TaskActions } from './task-actions';
import { money } from './allocation-view';

export type ReadyUniverse = { universe_id: string; asset_ids: string[]; as_of_date: string; demo: boolean; bundle_id?: string; provenance?: { data_origin?: string } | null };
const initialAnswers = { name: '', capital: '100000000', horizon: '36', liquidity: '', loss: '', experience: '' };
const levels: Record<string, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao' };
export const wizardTitles = ['Mục tiêu và thời gian của bạn', 'Bạn có thể chấp nhận biến động đến đâu?', 'Xem lại trước khi xác nhận'];

export function RiskWizard({ busy, onCreate, universes = [], onStepChange, onCancel }: {
  busy: boolean; onCreate: (body: unknown) => Promise<boolean>; universes?: ReadyUniverse[];
  onStepChange?: (step: number) => void; onCancel?: () => void;
}) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState(initialAnswers);
  const [chosen, setChosen] = useState('');
  const [riskAttempted, setRiskAttempted] = useState(false);
  const riskAlert = useRef<HTMLDivElement>(null);
  const riskKeys = ['loss', 'experience', 'liquidity'] as const;
  const missingRisk = riskKeys.filter(key => !answers[key]);
  const focusRiskError = () => requestAnimationFrame(() => riskAlert.current?.focus());
  const heading = useRef<HTMLParagraphElement>(null);
  const selectedUniverse = universes.find(u => u.universe_id === chosen) ?? universes.find(u => u.provenance?.data_origin === 'real') ?? universes[0];
  function changeStep(next: number) {
    setStep(next); onStepChange?.(next);
    requestAnimationFrame(() => heading.current?.focus());
  }
  function update(key: keyof typeof initialAnswers, value: string) { setAnswers(current => ({ ...current, [key]: value })); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step > 0 && missingRisk.length) { setRiskAttempted(true); if (step !== 1) changeStep(1); focusRiskError(); return; }
    if (step < 2) { changeStep(step + 1); return; }
    if (!selectedUniverse) return;
    const done = await onCreate({ name: answers.name, capital_vnd: answers.capital, universe_id: selectedUniverse.universe_id, answers: {
      questionnaire_version: 'risk-v1', horizon_months: Number(answers.horizon),
      liquidity_need: answers.liquidity, loss_tolerance: answers.loss, experience: answers.experience,
    } });
    if (done) { setAnswers(initialAnswers); setRiskAttempted(false); changeStep(0); }
  }
  return <form className="risk-wizard" onSubmit={submit} aria-busy={busy} onInvalidCapture={event => {
    if (step !== 1) return;
    event.preventDefault(); setRiskAttempted(true);
    if (event.target === event.currentTarget.querySelector(`input[name="${missingRisk[0]}"]`)) focusRiskError();
  }}>
    <section className="panel wizard-card">
      <ol className="step-progress" aria-label="Tiến trình tạo danh mục">{['Mục tiêu', 'Rủi ro', 'Xác nhận'].map((label, index) => <li key={label} className={index <= step ? 'complete' : ''} aria-current={index === step ? 'step' : undefined}><span>{index + 1}. {label}</span>{index < step && <span className="sr-only"> · Đã hoàn thành</span>}</li>)}</ol>
      <p ref={heading} className="wizard-step sr-only" tabIndex={-1}>BƯỚC {step + 1} / 3 · {['MỤC TIÊU', 'KHẨU VỊ RỦI RO', 'XÁC NHẬN'][step]}</p>
      <fieldset hidden={step !== 0} disabled={busy || step !== 0}><legend className="sr-only">Mục tiêu đầu tư</legend><div className="form-grid">
        <label>Tên danh mục<input name="name" required maxLength={120} placeholder="Tích lũy dài hạn" autoComplete="off" value={answers.name} onChange={e => update('name', e.target.value)}/><small>Bạn có thể xem lại trước khi xác nhận.</small></label>
        <label>Vốn kế hoạch (VND)<input name="capital" type="number" required min="1" max="10000000000000000000" step="1" value={answers.capital} onChange={e => update('capital', e.target.value)}/><small>{answers.capital && Number(answers.capital) > 0 ? money(answers.capital) : 'Nhập số tiền bằng VND'} · Không phải số dư tài khoản.</small></label>
        <label>Thời gian đầu tư (tháng)<input name="horizon" type="number" required min="1" max="600" step="1" value={answers.horizon} onChange={e => update('horizon', e.target.value)}/><small>Số nguyên từ 1 đến 600 tháng.</small></label>
        <label>Bộ tài sản<select name="universe" required value={selectedUniverse?.universe_id ?? ''} onChange={e => setChosen(e.target.value)} disabled={!universes.length}>
          {!universes.length && <option value="">Chưa có bộ dữ liệu sẵn sàng</option>}
          {universes.map(u => <option key={u.universe_id} value={u.universe_id}>{u.asset_ids.join(' · ')} · {u.demo ? 'minh họa' : u.provenance?.data_origin === 'real' ? 'giá thị trường' : 'nguồn chưa xác minh'} · {u.as_of_date}</option>)}
        </select><small>{selectedUniverse ? `${selectedUniverse.asset_ids.join(', ')} · Ngày dữ liệu ${selectedUniverse.as_of_date}` : 'Cần bộ dữ liệu sẵn sàng để tạo danh mục.'}</small></label>
      </div></fieldset>
      <fieldset hidden={step !== 1} disabled={busy || step !== 1}><legend className="sr-only">Khả năng chấp nhận rủi ro</legend>
        <p className="muted small">Chọn một câu trả lời cho mỗi nhóm theo khả năng thực tế của bạn.</p>
        {riskAttempted && missingRisk.length > 0 && <div ref={riskAlert} className="error risk-error-summary" role="alert" tabIndex={-1}><strong>Hãy trả lời đủ các nhóm trước khi xem lại.</strong><ul>{missingRisk.map(key => <li key={key}><a href={`#risk-${key}`} onClick={event => { event.preventDefault(); event.currentTarget.closest('form')?.querySelector<HTMLInputElement>(`input[name="${key}"]`)?.focus(); }}>{key === 'loss' ? 'Khả năng chịu biến động' : key === 'experience' ? 'Kinh nghiệm đầu tư' : 'Nhu cầu rút vốn sớm'}</a></li>)}</ul></div>}
        <div className="risk-questions">
        {([
          ['loss', 'Khi danh mục giảm giá, mức chịu đựng của bạn', [['low', 'Thấp — ưu tiên giữ vốn'], ['medium', 'Vừa — chấp nhận dao động'], ['high', 'Cao — chấp nhận giảm mạnh']]],
          ['experience', 'Kinh nghiệm đầu tư', [['beginner', 'Mới bắt đầu'], ['experienced', 'Đã có kinh nghiệm']]],
          ['liquidity', 'Nhu cầu rút vốn sớm', [['low', 'Thấp — có nguồn dự phòng riêng'], ['medium', 'Vừa — có thể cần một phần'], ['high', 'Cao — có thể cần phần lớn']]],
        ] as const).map(([key, question, options]) => <fieldset id={`risk-${key}`} className="risk-question" key={key} aria-describedby={riskAttempted && !answers[key] ? `risk-${key}-error` : undefined}><legend>{question}</legend><div className="risk-options">{options.map(([value, label]) => <label className="risk-choice" key={value}><input type="radio" name={key} value={value} required checked={answers[key] === value} aria-invalid={riskAttempted && !answers[key] || undefined} aria-describedby={riskAttempted && !answers[key] ? `risk-${key}-error` : undefined} onChange={() => update(key, value)}/><span>{label}</span></label>)}</div>{riskAttempted && !answers[key] && <p id={`risk-${key}-error`} className="field-error">Chọn một câu trả lời.</p>}</fieldset>)}
        <p className="muted small">Chọn theo khả năng thực tế. Hệ thống chỉ xác định hồ sơ sau khi bạn xem lại và xác nhận.</p>
      </div></fieldset>
      {step === 2 && <div className="wizard-review"><dl className="review-list">
        <div><dt>Danh mục / thời gian</dt><dd>{answers.name} · {answers.horizon} tháng</dd></div>
        <div><dt>Vốn kế hoạch</dt><dd>{money(answers.capital)}</dd></div>
        <div><dt>Thanh khoản / chịu biến động</dt><dd>{levels[answers.liquidity]} · {levels[answers.loss]}</dd></div>
        <div><dt>Kinh nghiệm</dt><dd>{answers.experience === 'beginner' ? 'Mới bắt đầu' : 'Đã có kinh nghiệm'}</dd></div>
        <div><dt>Bộ tài sản</dt><dd>{selectedUniverse?.universe_id} · {selectedUniverse?.demo ? 'Dữ liệu minh họa' : selectedUniverse?.provenance?.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}</dd></div>
        <div><dt>Hồ sơ & policy</dt><dd>Hệ thống xác định sau khi bạn xác nhận</dd></div>
      </dl><p className="muted small">Hồ sơ rủi ro không bảo đảm mức thua lỗ tối đa hoặc lợi nhuận. Bạn sẽ duyệt từng đề xuất trước khi lưu tỷ trọng mục tiêu.</p></div>}
    </section>
    <TaskActions hint={`Bước ${step + 1}/3 · ${['Mục tiêu', 'Rủi ro', 'Xem lại và xác nhận'][step]}`}><button data-testid={step === 2 ? 'create-portfolio-submit' : undefined} type="submit" disabled={busy || !selectedUniverse}>{busy ? 'Đang xử lý…' : step < 2 ? step === 0 ? 'Tiếp tục' : 'Xem lại hồ sơ' : 'Xác nhận & tạo danh mục'}</button>{step > 0 ? <button type="button" className="quiet" disabled={busy} onClick={() => changeStep(step - 1)}>{step === 2 ? 'Sửa câu trả lời' : 'Quay lại'}</button> : onCancel && <button type="button" className="quiet" disabled={busy} onClick={onCancel}>Quay lại</button>}</TaskActions>
  </form>;
}
