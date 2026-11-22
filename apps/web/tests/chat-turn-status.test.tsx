import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ChatTurnStatus } from '../src/components/chat-workspace';
import { chatStage, type ChatJob } from '../src/lib/chat-types';
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
