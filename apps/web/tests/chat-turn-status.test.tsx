import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AllocationStatusAnswer, ChatTurnStatus } from '../src/components/chat-workspace';
import { chatStage, type AllocationStatusCard, type ChatDashboard, type ChatJob } from '../src/lib/chat-types';
const base = { job_id: 'j', conversation_id: 'c', message_id: 'm', status_url: '', events_url: '', stage: 'COMPLETE', error: null, recommendation_id: null, result_message_id: 'reply', last_event_id: 1, attempts: 1 };
function render(status: string, resultVisible = false) {
  return renderToStaticMarkup(<ChatTurnStatus job={{...base, status} as ChatJob} resultVisible={resultVisible} connection="connected" disabled={false} onResume={() => {}}/>);
}
it('does not add a completion receipt after an already visible answer', () => {
  expect(render('SUCCEEDED', true)).toBe('');
  expect(render('WAITING_INPUT', true)).toBe('');
});
it('never labels a generic chat completion as saving a portfolio result', () => {
  expect(chatStage('COMPLETE')).not.toContain('đã được lưu');
  const html = render('SUCCEEDED');
  expect(html).toContain('Đã xử lý lượt trao đổi');
  expect(html).not.toContain('panel');
  expect(html).not.toContain('Kết quả đã được lưu');
});
it('keeps in-progress, failure and authorization recovery visible', () => {
  expect(render('RUNNING')).toContain('Đang xử lý');
  expect(render('FAILED', true)).toContain('Yêu cầu chưa hoàn tất');
  expect(render('FAILED', true)).not.toContain('Câu trả lời đã sẵn sàng');
  expect(render('AUTHORIZATION_REQUIRED', true)).toContain('Cấp lại quyền và tiếp tục');
});

it('explains expired inputs and directs the user through refresh and a new review', () => {
  const html=renderToStaticMarkup(<ChatTurnStatus job={{...base,status:'FAILED',error:'INPUT_EXPIRED'} as ChatJob} resultVisible={false} connection="saved" disabled={false} onResume={()=>{}}/>);
  expect(html).toContain('Dữ liệu đầu vào đã hết hạn');
  expect(html).toContain('người vận hành');
  expect(html).toContain('xác nhận lại');
  expect(html).not.toContain('Xem lại dữ liệu và đầu vào trước');
});

it('identifies stale VFF separately from an expired published input', () => {
  const html=renderToStaticMarkup(<ChatTurnStatus job={{...base,status:'FAILED',error:'VFF_STALE'} as ChatJob} resultVisible={false} connection="saved" disabled={false} onResume={()=>{}}/>);
  expect(html).toContain('NAV của quỹ VFF');
  expect(html).toContain('7 ngày');
  expect(html).toContain('xác nhận lại');
  expect(html).not.toContain('Dữ liệu đầu vào đã hết hạn');
});

it('shows a legacy pause as the business answer without a failure heading or an inferred destination', () => {
  const job = { ...base, status: 'FAILED', error: 'SYSTEM_PAUSED', result_message_id: null };
  const html = renderToStaticMarkup(<ChatTurnStatus job={job} resultVisible={false} connection="saved" disabled={false} onResume={() => {}}/>);
  expect(html).toContain('Tính năng tạo đề xuất mới đang tạm dừng. Bạn vẫn có thể xem các đề xuất đã lưu.');
  expect(html).not.toMatch(/Chưa thể hoàn tất|gửi lại|href=/);
});

const statusCard: AllocationStatusCard = {
  type: 'allocation_status', reason_code: 'SYSTEM_PAUSED', status: 'BLOCKED',
  checked_at: '2026-11-23T10:00:00Z', scope: 'system', portfolio_id: 'p',
};
function answer(card: AllocationStatusCard, selected: string, dashboardId: string, count: number) {
  const dashboard = { portfolio: { id: dashboardId }, proposal_count: count } as ChatDashboard;
  return renderToStaticMarkup(<AllocationStatusAnswer card={card} content="Nội dung đã lưu" dashboard={dashboard} portfolioId={selected} onRecheck={() => {}}/>);
}
it('shows the original answer and source time, with a history link only for the matching authorized dashboard', () => {
  const html = answer(statusCard, 'p', 'p', 1);
  expect(html).toContain('Nội dung đã lưu');
  expect(html).toContain(statusCard.checked_at);
  expect(html).toContain('#proposal?focus=history&amp;portfolio=p');
  for (const other of [answer(statusCard, 'other', 'p', 1), answer(statusCard, 'p', 'other', 1), answer(statusCard, 'p', 'p', 0)]) {
    expect(other).not.toContain('href=');
  }
});
it('allows a fresh check after an unknown status without borrowing the message timestamp', () => {
  const card = { ...statusCard, status: 'UNKNOWN' as const, checked_at: null };
  expect(answer(card, 'p', 'p', 0)).toContain('Kiểm tra lại trạng thái');
  expect(answer(card, 'p', 'p', 0)).not.toContain('<time');
  expect(answer(card, 'other', 'other', 1)).not.toContain('Kiểm tra lại trạng thái');
});
