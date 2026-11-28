'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight } from 'lucide-react';
import { AnswerRows, emptyRiskDraft, quantifiedAnswers, riskKeys, RiskQuestions, shortLabels } from './risk-questions';
import { TaskActions } from './task-actions';
import { AssetPicker } from './asset-picker';
import type { AssetCatalog } from '../lib/selection-types';
import './risk-wizard.css';
import { CapitalInput } from './capital-input';
import type { Phase1Full } from '../lib/p1-types';

export type ReadyUniverse = { universe_id: string; asset_ids: string[]; as_of_date: string; demo: boolean; bundle_id?: string; provenance?: { data_origin?: string; phase1_full?: Phase1Full } | null };
const initialAnswers = { name: '', capital: '100.000.000', ...emptyRiskDraft, horizon: '36' };
export const wizardTitles = { plan: 'Lập kế hoạch đầu tư', basket: 'Chọn rổ tài sản', risk: 'Bạn có thể chấp nhận biến động đến đâu?', review: 'Xem lại trước khi xác nhận' };
export type WizardStep = keyof typeof wizardTitles;
const labels = { plan: 'Mục tiêu', basket: 'Rổ tài sản', risk: 'Rủi ro', review: 'Xác nhận' };

function wizardSteps(custom: boolean): WizardStep[] {
  return custom ? ['plan', 'basket', 'risk', 'review'] : ['plan', 'risk', 'review'];
}
export function wizardProgressLabel(step: WizardStep, custom: boolean) {
  const steps = wizardSteps(custom);
  const current = steps.includes(step) ? step : 'plan';
  return `Bước ${steps.indexOf(current) + 1}/${steps.length} · ${labels[current]}`;
}

export function RiskWizard({ busy, onCreate, universes = [], catalog = null, onStepChange, onCancel }: {
  busy: boolean; onCreate: (body: unknown) => Promise<boolean>; universes?: ReadyUniverse[]; catalog?: AssetCatalog | null;
  onStepChange?: (step: WizardStep) => void; onCancel?: () => void;
}) {
  const [requestedStep, setStep] = useState<WizardStep>('plan');
  const [answers, setAnswers] = useState(initialAnswers);
  const [assetIds, setAssetIds] = useState<string[]>([]);
  const custom = !!catalog?.selection_enabled;
  const steps = wizardSteps(custom);
  const step = requestedStep === 'basket' && !custom ? 'plan' : requestedStep;
  const position = steps.indexOf(step);
  const actions = { plan: custom ? 'Chọn tài sản' : 'Tiếp tục', basket: 'Tiếp tục', risk: 'Xem lại hồ sơ', review: 'Xác nhận & tạo danh mục' };
  useEffect(() => { onStepChange?.(step); }, [step, onStepChange]);
  const [chosen, setChosen] = useState('');
  const [planAttempted, setPlanAttempted] = useState(false);
  const [riskAttempted, setRiskAttempted] = useState(false);
  const riskAlert = useRef<HTMLDivElement>(null);
  const assessment = quantifiedAnswers(answers);
  const missingRisk = riskKeys.filter(key => !answers[key]);
  const focusRiskError = () => requestAnimationFrame(() => riskAlert.current?.focus());
  const heading = useRef<HTMLLIElement>(null);
  const selectedUniverse = universes.find(u => u.universe_id === chosen) ?? universes.find(u => u.provenance?.data_origin === 'real') ?? universes[0];
  const missingBasket = custom ? !assetIds.length : !selectedUniverse;
  const needsAssetsHere = missingBasket && (custom ? step === 'basket' : step === 'plan');
  const selectedSummary = assetIds.length ? `Đã chọn ${assetIds.length} mã · ${assetIds.slice(0, 4).join(', ')}${assetIds.length > 4 ? '…' : ''}` : '';
  const hint = step === 'basket' ? assetIds.length ? 'Mã đã chọn có thể nhận tỷ trọng 0%.' : 'Chọn ít nhất một mã để tiếp tục.'
    : step === 'plan' ? custom ? selectedSummary || 'Bạn sẽ tự chọn các mã ở bước kế tiếp.' : needsAssetsHere ? 'Cần bộ tài sản sẵn sàng để tiếp tục.' : 'Dùng bộ tài sản có sẵn.'
    : custom ? selectedSummary : undefined;
  const nameError = planAttempted && !answers.name.trim();
  const horizonError = planAttempted && (!Number.isInteger(Number(answers.horizon)) || Number(answers.horizon) < 1 || Number(answers.horizon) > 600);
  function changeStep(next: WizardStep) {
    setStep(next);
    requestAnimationFrame(() => {
      const title = heading.current?.closest('main')?.querySelector('h1');
      (title ?? heading.current)?.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    });
  }
  function update(key: keyof typeof initialAnswers, value: string) { setAnswers(current => ({ ...current, [key]: value })); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (needsAssetsHere) return;
    if (missingBasket && step !== 'plan') { changeStep(custom ? 'basket' : 'plan'); return; }
    if ((step === 'risk' || step === 'review') && missingRisk.length) { setRiskAttempted(true); if (step !== 'risk') changeStep('risk'); focusRiskError(); return; }
    if (step !== 'review') { changeStep(steps[position + 1]); return; }
    if (!assessment) return;
    const done = await onCreate({ name: answers.name.trim(), capital_vnd: answers.capital.replaceAll('.', ''), ...(custom ? { asset_ids: assetIds } : { universe_id: selectedUniverse!.universe_id }), answers: assessment });
    if (done) { setAssetIds([]); setAnswers(initialAnswers); setPlanAttempted(false); setRiskAttempted(false); changeStep('plan'); }
  }
  return <form className="risk-wizard" data-step={step} data-custom-basket={custom || undefined} onSubmit={submit} aria-busy={busy} onInvalidCapture={event => {
    if (step === 'plan') {
      event.preventDefault(); setPlanAttempted(true);
      const firstInvalid = event.currentTarget.querySelector<HTMLInputElement>('input:invalid, select:invalid');
      if (event.target === firstInvalid) requestAnimationFrame(() => firstInvalid?.focus());
      return;
    }
    if (step !== 'risk') return;
    event.preventDefault(); setRiskAttempted(true);
    if (event.target === event.currentTarget.querySelector(`input[name="${missingRisk[0]}"]`)) focusRiskError();
  }}>
    <section className="panel wizard-card">
      <ol className="step-progress" aria-label="Tiến trình tạo danh mục">{steps.map((item, index) => <li key={item} ref={item === step ? heading : undefined} tabIndex={item === step ? -1 : undefined} className={index <= position ? 'complete' : ''} aria-current={item === step ? 'step' : undefined}><span>{index + 1}. {labels[item]}</span>{index < position && <span className="sr-only"> · Đã hoàn thành</span>}</li>)}</ol>
      <fieldset className="wizard-plan" hidden={step !== 'plan'} disabled={busy || step !== 'plan'}><legend className="sr-only">Thông tin kế hoạch</legend><div className="form-grid wizard-goals">
        <label><span id="wizard-name-label">Tên danh mục</span><input aria-labelledby="wizard-name-label" name="name" required pattern={'.*\\S.*'} maxLength={120} aria-invalid={nameError || undefined} aria-describedby={nameError ? 'wizard-name-error' : undefined} placeholder="Tên danh mục" autoComplete="off" value={answers.name} onChange={e => update('name', e.target.value)}/>{nameError && <small id="wizard-name-error" className="field-error">Nhập tên danh mục để tiếp tục.</small>}</label>
        <CapitalInput attempted={planAttempted} value={answers.capital} onChange={value => update('capital', value)}/>
        <label><span id="wizard-horizon-label">Thời gian đầu tư (tháng)</span><input aria-labelledby="wizard-horizon-label" name="horizon" aria-invalid={horizonError || undefined} aria-describedby={horizonError ? 'wizard-horizon-error' : undefined} type="number" required min="1" max="600" step="1" value={answers.horizon} onChange={e => update('horizon', e.target.value)}/>{horizonError && <small id="wizard-horizon-error" className="field-error">Nhập thời gian đầu tư từ 1 đến 600 tháng, bằng số nguyên.</small>}</label>
        {!custom && <label>Bộ tài sản<select name="universe" required value={selectedUniverse?.universe_id ?? ''} onChange={e => setChosen(e.target.value)} disabled={!universes.length}>
          {!universes.length && <option value="">Chưa có bộ dữ liệu sẵn sàng</option>}
          {universes.map(u => <option key={u.universe_id} value={u.universe_id}>{u.universe_id === 'VN_PHASE1_FULL' ? 'Danh sách tài sản Việt Nam (32 mã)' : u.asset_ids.join(' · ')} · {u.demo ? 'minh họa' : u.provenance?.data_origin === 'real' ? 'giá thị trường' : 'nguồn chưa xác minh'} · {u.as_of_date}</option>)}
        </select><small>{selectedUniverse ? `${selectedUniverse.universe_id === 'VN_PHASE1_FULL' ? '30 cổ phiếu, vàng và quỹ trái phiếu VFF' : selectedUniverse.asset_ids.join(', ')} · Ngày dữ liệu ${selectedUniverse.as_of_date}` : 'Cần bộ dữ liệu sẵn sàng để tạo danh mục.'}</small></label>}
        {!custom && selectedUniverse?.universe_id === 'VN_PHASE1_FULL' && <p className="muted small">Quỹ trái phiếu VFF thuộc nhóm tài sản phòng thủ.</p>}
      </div><aside className="wizard-capital-note"><h2>Vốn kế hoạch</h2><p>Số tiền bạn dự định phân bổ. Bạn có thể xem lại các thông tin này ở bước xác nhận.</p></aside></fieldset>
      {custom && step === 'basket' && <section className="wizard-basket-picker">
        <p className="wizard-basket-title" role="status">{answers.name} · {assetIds.length} mã đã chọn</p>
        <AssetPicker assets={catalog!.assets} selected={assetIds} onChange={setAssetIds} disabled={busy}/>
      </section>}
      <fieldset hidden={step !== 'risk'} disabled={busy || step !== 'risk'}><legend className="sr-only">Khả năng chấp nhận rủi ro</legend>
        <p className="muted small">Chọn một câu trả lời cho mỗi nhóm theo khả năng thực tế của bạn.</p>
        {riskAttempted && missingRisk.length > 0 && <div ref={riskAlert} className="error risk-error-summary" role="alert" tabIndex={-1}><strong>Hãy trả lời đủ các nhóm trước khi xem lại.</strong><ul>{missingRisk.map(key => <li key={key}><a href={`#risk-${key}`} onClick={event => { event.preventDefault(); event.currentTarget.closest('form')?.querySelector<HTMLInputElement>(`input[name="${key}"]`)?.focus(); }}>{shortLabels[key]}</a></li>)}</ul></div>}
        <RiskQuestions idPrefix="risk" draft={answers} capital={answers.capital.replaceAll('.', '')} onChange={update} attempted={riskAttempted}/>
      </fieldset>
      {step === 'review' && <div className="wizard-review"><dl className="review-list">
        <div><dt>Danh mục</dt><dd>{answers.name}</dd></div>
        <div><dt>Vốn kế hoạch</dt><dd>{answers.capital} ₫</dd></div>
        {assessment && <AnswerRows answers={assessment}/>}
        <div><dt>Tài sản được cân nhắc</dt><dd>{custom ? `${assetIds.length} mã: ${assetIds.join(', ')}` : selectedUniverse?.asset_ids.join(', ')}{!custom && <> · {selectedUniverse?.demo ? 'Dữ liệu minh họa' : selectedUniverse?.provenance?.data_origin === 'real' ? 'Giá thị trường' : 'Nguồn chưa xác minh'}</>}</dd></div>
        <div><dt>Hồ sơ rủi ro</dt><dd>Hệ thống xác định sau khi bạn xác nhận.</dd></div>
      </dl>{custom && !assetIds.includes('VFF') && <p className="muted">Bạn có thể lưu kế hoạch với rổ này. Khi tính đề xuất, rổ cần có quỹ trái phiếu VFF.</p>}{custom && <details className="allocation-details"><summary>Giới hạn áp dụng khi tính phân bổ</summary><p>Mã đã chọn vẫn có thể nhận tỷ trọng 0%. Khi tính đề xuất, hệ thống kiểm tra dữ liệu của từng mã.</p><p>Quỹ trái phiếu VFF chiếm tối thiểu 15%. Nhóm tài sản còn lại chiếm tối đa 70%. Mỗi tài sản chiếm tối đa 50%.</p></details>}<p className="muted small">Bạn sẽ xem lại từng đề xuất trước khi quyết định lưu tỷ trọng mục tiêu.</p></div>}
    </section>
    <TaskActions hint={hint}>
      {position > 0 ? <button type="button" className="quiet" disabled={busy} onClick={() => changeStep(steps[position - 1])}>{step === 'review' ? 'Sửa câu trả lời' : 'Quay lại'}</button> : onCancel && <button type="button" className="quiet" disabled={busy} onClick={onCancel}>Quay lại</button>}
      <button data-testid={step === 'review' ? 'create-portfolio-submit' : undefined} type="submit" disabled={busy || needsAssetsHere}>
        {busy ? 'Đang xử lý…' : actions[step]}
        {!busy && step !== 'review' && <ArrowRight size={16} aria-hidden="true"/>}
      </button>
    </TaskActions>
  </form>;
}
