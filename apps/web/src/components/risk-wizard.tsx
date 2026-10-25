'use client';
import { useRef, useState, type FormEvent } from 'react';
import { money } from './allocation-view';

export type ReadyUniverse = { universe_id: string; asset_ids: string[]; as_of_date: string; demo: boolean; bundle_id?: string; provenance?: { data_origin?: string } | null };
const initialAnswers = { name: '', capital: '100000000', horizon: '36', liquidity: 'low', loss: 'medium', experience: 'beginner' };
const levels: Record<string, string> = { low: 'Thấp', medium: 'Vừa', high: 'Cao' };
export const wizardTitles = ['Mục tiêu và thời gian của bạn', 'Bạn có thể chấp nhận biến động đến đâu?', 'Xem lại trước khi xác nhận'];

export function RiskWizard({ busy, onCreate, universes = [], onStepChange, onCancel }: {
  busy: boolean; onCreate: (body: unknown) => Promise<boolean>; universes?: ReadyUniverse[];
  onStepChange?: (step: number) => void; onCancel?: () => void;
}) {
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState(initialAnswers);
  const [chosen, setChosen] = useState('');
  const heading = useRef<HTMLParagraphElement>(null);
  const selectedUniverse = universes.find(u => u.universe_id === chosen) ?? universes.find(u => u.provenance?.data_origin === 'real') ?? universes[0];
  function changeStep(next: number) {
    setStep(next); onStepChange?.(next);
    requestAnimationFrame(() => heading.current?.focus());
  }
  function update(key: keyof typeof initialAnswers, value: string) { setAnswers(current => ({ ...current, [key]: value })); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step < 2) { changeStep(step + 1); return; }
    if (!selectedUniverse) return;
    const done = await onCreate({ name: answers.name, capital_vnd: answers.capital, universe_id: selectedUniverse.universe_id, answers: {
      questionnaire_version: 'risk-v1', horizon_months: Number(answers.horizon),
      liquidity_need: answers.liquidity, loss_tolerance: answers.loss, experience: answers.experience,
    } });
    if (done) { setAnswers(initialAnswers); changeStep(0); }
  }
  return <form className="risk-wizard" onSubmit={submit} aria-busy={busy}>
    <section className="panel wizard-card">
      <ol className="step-progress" aria-label="Tiến trình tạo danh mục">{['Mục tiêu', 'Rủi ro', 'Xác nhận'].map((label, index) => <li key={label} className={index <= step ? 'complete' : ''} aria-current={index === step ? 'step' : undefined}><span className="sr-only">{index + 1}. {label}{index < step ? ' · Đã hoàn thành' : ''}</span></li>)}</ol>
      <p ref={heading} className="eyebrow wizard-step" tabIndex={-1}>BƯỚC {step + 1} / 3 · {['MỤC TIÊU', 'KHẨU VỊ RỦI RO', 'XÁC NHẬN'][step]}</p>
      <fieldset hidden={step !== 0} disabled={busy || step !== 0}><legend className="sr-only">Mục tiêu đầu tư</legend><div className="form-grid">
        <label>Tên danh mục<input name="name" required maxLength={120} placeholder="Tích lũy dài hạn" autoComplete="off" value={answers.name} onChange={e => update('name', e.target.value)}/><small>Bạn có thể xem lại trước khi xác nhận.</small></label>
        <label>Vốn kế hoạch (VND)<input name="capital" type="number" required min="1" max="10000000000000000000" step="1" value={answers.capital} onChange={e => update('capital', e.target.value)}/><small>Nhập số tiền bằng VND; không tự suy ra số dư tài khoản.</small></label>
        <label>Thời gian đầu tư (tháng)<input name="horizon" type="number" required min="1" max="600" step="1" value={answers.horizon} onChange={e => update('horizon', e.target.value)}/><small>Số nguyên từ 1 đến 600 tháng.</small></label>
        <label>Bộ tài sản<select name="universe" required value={selectedUniverse?.universe_id ?? ''} onChange={e => setChosen(e.target.value)} disabled={!universes.length}>
          {!universes.length && <option value="">Chưa có bộ dữ liệu sẵn sàng</option>}
          {universes.map(u => <option key={u.universe_id} value={u.universe_id}>{u.universe_id} · {u.demo ? 'minh họa' : u.provenance?.data_origin === 'real' ? 'giá thật' : 'nguồn chưa xác minh'} · {u.asset_ids.join(', ')} · {u.as_of_date}</option>)}
        </select><small>{selectedUniverse ? `${selectedUniverse.asset_ids.join(', ')} · Ngày dữ liệu ${selectedUniverse.as_of_date}` : 'Cần bộ dữ liệu sẵn sàng để tạo danh mục.'}</small></label>
      </div></fieldset>
      <fieldset hidden={step !== 1} disabled={busy || step !== 1}><legend className="sr-only">Khả năng chấp nhận rủi ro</legend><div className="form-grid">
        <label>Khi danh mục giảm giá, mức chịu đựng của bạn<select name="loss" value={answers.loss} onChange={e => update('loss', e.target.value)}><option value="low">Thấp — ưu tiên giữ vốn</option><option value="medium">Vừa — chấp nhận dao động</option><option value="high">Cao — chấp nhận giảm mạnh</option></select><small>Chọn theo khả năng thực tế của bạn.</small></label>
        <label>Kinh nghiệm đầu tư<select name="experience" value={answers.experience} onChange={e => update('experience', e.target.value)}><option value="beginner">Mới bắt đầu</option><option value="experienced">Đã có kinh nghiệm</option></select></label>
        <label>Nhu cầu rút vốn sớm<select name="liquidity" value={answers.liquidity} onChange={e => update('liquidity', e.target.value)}><option value="low">Thấp — có nguồn dự phòng riêng</option><option value="medium">Vừa — có thể cần một phần</option><option value="high">Cao — có thể cần phần lớn</option></select><small>Khoản tiền bạn có thể cần trong thời gian đầu tư.</small></label>
      </div></fieldset>
      {step === 2 && <div className="wizard-review"><dl className="review-list">
        <div><dt>Danh mục / thời gian</dt><dd>{answers.name} · {answers.horizon} tháng</dd></div>
        <div><dt>Vốn kế hoạch</dt><dd>{money(answers.capital)}</dd></div>
        <div><dt>Thanh khoản / chịu biến động</dt><dd>{levels[answers.liquidity]} · {levels[answers.loss]}</dd></div>
        <div><dt>Kinh nghiệm</dt><dd>{answers.experience === 'beginner' ? 'Mới bắt đầu' : 'Đã có kinh nghiệm'}</dd></div>
        <div><dt>Bộ tài sản</dt><dd>{selectedUniverse?.universe_id} · {selectedUniverse?.demo ? 'Dữ liệu minh họa' : selectedUniverse?.provenance?.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}</dd></div>
        <div><dt>Hồ sơ & policy</dt><dd>Hệ thống xác định khi xác nhận · risk-v1</dd></div>
      </dl><p className="muted small">Hồ sơ rủi ro không bảo đảm mức thua lỗ tối đa hoặc lợi nhuận. Bạn sẽ duyệt từng đề xuất trước khi lưu tỷ trọng mục tiêu.</p></div>}
    </section>
    <div className="actions"><button type="submit" disabled={busy || !selectedUniverse}>{busy ? 'Đang xử lý…' : step < 2 ? step === 0 ? 'Tiếp tục' : 'Xem lại hồ sơ' : 'Xác nhận & tạo danh mục'}</button>{step > 0 ? <button type="button" className="quiet" disabled={busy} onClick={() => changeStep(step - 1)}>{step === 2 ? 'Sửa câu trả lời' : 'Quay lại'}</button> : onCancel && <button type="button" className="quiet" disabled={busy} onClick={onCancel}>Quay lại</button>}</div>
  </form>;
}
