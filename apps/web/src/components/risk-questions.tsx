import { useState } from 'react';
import { CircleHelp } from 'lucide-react';
import type { QuantifiedAnswers, RiskAnswers, RiskProfile } from '../lib/portfolio-types';

export const riskKeys = ['loss', 'liquidity', 'reserve'] as const;
type Question = typeof riskKeys[number];
export const shortLabels = { loss: 'Mức giảm chấp nhận', liquidity: 'Nhu cầu rút vốn', reserve: 'Quỹ dự phòng' };
const options = {
  loss: { low: 'Thấp · Dưới 5%', medium: 'Vừa · Từ 5% đến dưới 15%', high: 'Cao · Từ 15% trở lên' },
  liquidity: { low: 'Tối đa 10%', medium: 'Trên 10% đến 30%', high: 'Trên 30%' },
  reserve: { under_3: 'Dưới 3 tháng', '3_to_under_6': 'Từ 3 đến dưới 6 tháng', at_least_6: 'Từ 6 tháng trở lên' },
};
const questions = {
  loss: 'Trong 12 tháng tới, mức giảm lớn nhất so với vốn ban đầu mà bạn vẫn sẵn lòng giữ kế hoạch là bao nhiêu?',
  liquidity: 'Trong 12 tháng tới, bạn dự kiến cần rút bao nhiêu phần vốn ban đầu?',
  reserve: 'Nếu thu nhập tạm dừng, khoản dự phòng ngoài danh mục đủ trang trải chi phí thiết yếu trong bao lâu?',
};
export const emptyRiskDraft = { horizon: '', loss: '', liquidity: '', reserve: '', experience: '' };
export type RiskDraft = typeof emptyRiskDraft;
export function quantifiedAnswers(draft: RiskDraft): QuantifiedAnswers | null {
  const loss = draft.loss as QuantifiedAnswers['loss_tolerance'];
  const liquidity = draft.liquidity as QuantifiedAnswers['liquidity_need'];
  const reserve = draft.reserve as QuantifiedAnswers['reserve_months'];
  if (!Object.hasOwn(options.loss, loss) || !Object.hasOwn(options.liquidity, liquidity) || !Object.hasOwn(options.reserve, reserve)) return null;
  return { questionnaire_version: 'risk-v2', horizon_months: Number(draft.horizon), loss_tolerance: loss, liquidity_need: liquidity, reserve_months: reserve,
    ...(draft.experience === 'beginner' || draft.experience === 'experienced' ? { experience: draft.experience } : {}) };
}
function amount(capital: string, percent: number) {
  if (!/^\d+(\.\d+)?$/.test(capital)) return '';
  const [whole, fraction = ''] = capital.split('.');
  const scale = 100n * 10n ** BigInt(fraction.length);
  const value = BigInt(whole + fraction) * BigInt(percent);
  const part = (value % scale).toString().padStart(fraction.length + 2, '0').replace(/0+$/, '');
  return (value / scale).toLocaleString('vi-VN') + (part ? ',' + part : '') + ' ₫';
}

export function RiskQuestions({ draft, capital, onChange, idPrefix, attempted = false }: {
  draft: RiskDraft; capital: string; idPrefix: string; onChange: (key: keyof RiskDraft, value: string) => void; attempted?: boolean;
}) {
  const [unsure, setUnsure] = useState<Partial<Record<Question, boolean>>>({});
  const examples = {
    loss: 'Nếu khoản đầu tư giảm 15% và chưa biết khi nào hồi phục, bạn có còn muốn giữ kế hoạch? Hãy chọn khoảng giảm phù hợp ở trên.',
    liquidity: 'Cộng các khoản bạn dự kiến lấy từ danh mục để chi tiêu trong năm tới, rồi chọn khoảng tương ứng.',
    reserve: 'Lấy số tiền dự phòng ngoài danh mục chia cho chi phí thiết yếu mỗi tháng. Ví dụ, 40 triệu chia cho 10 triệu/tháng là 4 tháng.',
  };
  return <><div className="risk-questions">{riskKeys.map(key => {
    const invalid = attempted && !draft[key];
    const id = idPrefix + '-' + key;
    return <fieldset id={id} className="risk-question" key={key} aria-labelledby={id + '-title ' + id + '-prompt'}>
      <legend className="sr-only" id={id + '-title'}>{shortLabels[key]}</legend>
      <div className="risk-question-row">
        <div className="risk-prompt">
          <strong aria-hidden="true">{shortLabels[key]}</strong>
          <p id={id + '-prompt'}>{questions[key]}</p>
        </div>
        <div className="risk-answer">
          <div className="risk-options">{Object.entries(options[key]).map(([value, label]) => <label className="risk-choice" key={value}><input type="radio" name={key} value={value} required checked={draft[key] === value}
            aria-invalid={invalid || undefined} aria-describedby={invalid ? id + '-error' : undefined} onChange={() => { setUnsure(last => ({ ...last, [key]: false })); onChange(key, value); }}/><span>{label}</span></label>)}</div>
          <div className="risk-answer-tools">
            {capital && key !== 'reserve' && <p className="muted small">{key === 'loss' ? `5% = ${amount(capital, 5)} · 15% = ${amount(capital, 15)}` : `10% = ${amount(capital, 10)} · 30% = ${amount(capital, 30)}`}</p>}
            <button type="button" className="risk-help" aria-expanded={!!unsure[key]} onClick={() => { setUnsure(last => ({ ...last, [key]: true })); onChange(key, ''); }}><CircleHelp size={16} aria-hidden="true"/>Tôi chưa chắc</button>
          </div>
          {unsure[key] && <p className="risk-example" role="status">{examples[key]}</p>}
          {invalid && <p className="field-error" id={id + '-error'}>Chọn một câu trả lời.</p>}
        </div>
      </div>
    </fieldset>;
  })}</div>
    <label className="risk-experience">Kinh nghiệm đầu tư (tùy chọn)<select value={draft.experience} onChange={event => onChange('experience', event.target.value)}>
      <option value="">Bỏ qua</option><option value="beginner">Mới bắt đầu</option><option value="experienced">Đã có kinh nghiệm</option>
    </select></label>
    {draft.experience === 'beginner' && <p className="muted small">Bạn có thể sẵn lòng chờ khi danh mục giảm giá nhưng vẫn cần rút tiền để chi tiêu. Vì vậy, hãy cân nhắc riêng từng câu.</p>}
  </>;
}

const legacyLevels = { low: 'Thấp', medium: 'Vừa', high: 'Cao' };
export function AnswerRows({ answers }: { answers: RiskAnswers }) {
  const v2 = answers.questionnaire_version === 'risk-v2';
  return <><div><dt>Thời gian đầu tư</dt><dd>{answers.horizon_months} tháng</dd></div>
    <div><dt>Nhu cầu rút vốn sớm</dt><dd>{(v2 ? options.liquidity : legacyLevels)[answers.liquidity_need]}</dd></div>
    <div><dt>{v2 ? 'Mức giảm chấp nhận trong 12 tháng' : 'Khả năng chịu biến động'}</dt><dd>{(v2 ? options.loss : legacyLevels)[answers.loss_tolerance]}</dd></div>
    {v2 && <div><dt>Quỹ dự phòng ngoài danh mục</dt><dd>{options.reserve[answers.reserve_months]}</dd></div>}
    {answers.experience && <div><dt>Kinh nghiệm</dt><dd>{answers.experience === 'experienced' ? 'Đã có kinh nghiệm' : 'Mới bắt đầu'}</dd></div>}</>;
}

export function RiskReason({ profile }: { profile?: RiskProfile | null }) {
  const a = profile?.answers;
  if (a?.questionnaire_version !== 'risk-v2' || !profile?.determining_factors?.length) return null;
  const reasons = { horizon_months: `thời hạn ${a.horizon_months} tháng`, liquidity_need: `dự kiến rút ${options.liquidity[a.liquidity_need].toLowerCase()} vốn trong 12 tháng`,
    loss_tolerance: `mức giảm bạn chấp nhận ${options.loss[a.loss_tolerance].split(' · ')[1].toLowerCase()}`, reserve_months: `quỹ dự phòng đủ cho ${options.reserve[a.reserve_months].toLowerCase()}` };
  return <p>Hồ sơ được xác định theo {profile.determining_factors.map(key => reasons[key]).join(', ')}.</p>;
}
