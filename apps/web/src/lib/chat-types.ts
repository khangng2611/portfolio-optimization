import type { Dashboard, Portfolio, Recommendation } from './portfolio-types';

export type ChatPortfolio = Omit<Portfolio, 'constraints' | 'risk_profile'> & {
  constraints: Portfolio['constraints'] & { defensive_asset_ids?: string[]; min_defensive_weight?: number; max_non_defensive_weight?: number };
  risk_profile: { profile: string; version_id?: string; mapping_version?: string; answers?: Record<string, string | number> } | null;
};
export type ChatDashboard = Omit<Dashboard, 'portfolio'> & { portfolio: ChatPortfolio; holdings_status?: string };
export type Conversation = { id: string; title: string; portfolio_id: string | null; active_job_id: string | null; created_at: string; llm_consent?: boolean };
export type ProviderMetadata = { reason: string; provider?: string; model?: string; input_tokens?: number; output_tokens?: number; estimated_cost_usd?: number; prompt_version?: string };
export type ConfirmationCard = { type: 'confirmation'; reason: string; confirmation_message_id: string; facts_hash: string; input: { portfolio: ChatPortfolio; strategy: string } };
export type RecommendationCard = { type: 'recommendation'; recommendation_id: string; facts: Recommendation & Record<string, unknown>; facts_hash: string; explanation_status: string; provider: ProviderMetadata; schema_version: string; prompt_version: string };
export type FactCard = { type: 'portfolio' | 'profile' | 'market'; facts: Record<string, unknown>; facts_hash: string };
export type InputCard = { type: 'input_required'; fields: string[]; portfolio_id?: string };
export type ChatMessage = { id: string; conversation_id: string; role: string; content: string; client_message_id: string | null; created_at: string; structured: ((ConfirmationCard | RecommendationCard | FactCard | InputCard | { type: 'help' }) & { dialogue?: ProviderMetadata }) | null };
export type ChatReceipt = { message_id: string; job_id: string; conversation_id: string; status_url: string; events_url: string };
export type ChatJob = ChatReceipt & { status: string; stage: string; error: string | null; recommendation_id: string | null; result_message_id: string | null; last_event_id: number; attempts: number };
export type SendMessage = { content: string; client_message_id: string; portfolio_id?: string; strategy?: 'EW' | 'MVO' | 'BL_ML'; intent?: 'allocation' | 'profile' | 'portfolio' | 'market' | 'explain' | 'help'; recommendation_id?: string; confirmation?: { message_id: string; facts_hash: string } };
export type ChatEvent = { id: number | null; event: string; data: Record<string, unknown> };

export const chatStopped = (status?: string) => !!status && ['SUCCEEDED', 'FAILED', 'WAITING_INPUT', 'AUTHORIZATION_REQUIRED', 'CANCELLED'].includes(status);
export const chatStatus = (status?: string) => ({ QUEUED: 'Đã tiếp nhận', RUNNING: 'Đang xử lý', RETRY: 'Đang thử lại kết nối', WAITING_DEPENDENCY: 'Đang chờ kết quả định lượng', WAITING_INPUT: 'Cần bạn xác nhận thông tin', AUTHORIZATION_REQUIRED: 'Cần cấp lại quyền', SUCCEEDED: 'Đã hoàn tất', FAILED: 'Chưa thể hoàn tất', CANCELLED: 'Đã dừng' }[status ?? ''] ?? 'Đang kết nối');
export const chatStage = (stage?: string) => ({ COLLECT: 'Kiểm tra thông tin danh mục', CONFIRMATION: 'Chờ xem lại và xác nhận', SUBMIT: 'Gửi yêu cầu đã xác nhận', TOOL_AUTHORIZED: 'Đã xác nhận đầu vào', WAIT_ALLOCATION: 'Đang tính phương án phân bổ', COMPLETE: 'Câu trả lời đã sẵn sàng' }[stage ?? ''] ?? 'Đang kiểm tra yêu cầu');
export function chatError(status?: number): string {
  if (status === 401) return 'Phiên đã hết hạn. Đăng nhập lại rồi chủ động gửi hoặc xác nhận yêu cầu.';
  if (status === 403) return 'Tài khoản chưa có quyền thực hiện yêu cầu này.';
  if (status === 404) return 'Không tìm thấy hội thoại hoặc dữ liệu thuộc tài khoản này. Về danh sách để chọn lại.';
  if (status === 409 || status === 412) return 'Thông tin hoặc lượt hội thoại đã thay đổi. Tải lại lịch sử và xem thẻ xác nhận mới nhất.';
  if (status === 429) return 'Có nhiều yêu cầu đang xử lý. Chờ một lúc rồi thử lại cùng yêu cầu.';
  if (status === 400 || status === 422) return 'Kiểm tra nội dung, danh mục và lựa chọn trước khi gửi lại.';
  return 'Kết nối chưa ổn định. Tải lại trạng thái; nếu chưa được tiếp nhận, thử lại cùng yêu cầu.';
}

// Compare every fact, including nested provenance. Rendering always uses the fresh
// canonical API object. Python's server facts_hash remains the audit authority;
// JSON numbers lose lexical precision in browsers, so do not invent a new digest.
export function sameFacts(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) || Array.isArray(b)) return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((value, i) => sameFacts(value, b[i]));
  const left = a as Record<string, unknown>, right = b as Record<string, unknown>;
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every(key => Object.hasOwn(right, key) && sameFacts(left[key], right[key]));
}

export const storageKey = (owner: string, resource: string, kind: 'sequence' | 'pending' | 'resume') => `portfolio.chat.${kind}.${encodeURIComponent(owner)}.${encodeURIComponent(resource)}`;
const uuid = /^[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}$/i;
export function readPending(raw: string | null): SendMessage | null {
  if (!raw) return null;
  try {
    const body = JSON.parse(raw) as SendMessage;
    if (!body || typeof body !== 'object' || Object.keys(body).some(key => !['content', 'client_message_id', 'portfolio_id', 'strategy', 'intent', 'recommendation_id', 'confirmation'].includes(key))) return null;
    if (typeof body.content !== 'string' || !body.content.trim() || body.content.length > 4000 || typeof body.client_message_id !== 'string' || !uuid.test(body.client_message_id)) return null;
    if (body.portfolio_id && !uuid.test(body.portfolio_id) || body.recommendation_id && !uuid.test(body.recommendation_id)) return null;
    if (body.strategy && !['EW', 'MVO', 'BL_ML'].includes(body.strategy)) return null;
    if (body.intent && !['allocation', 'profile', 'portfolio', 'market', 'explain', 'help'].includes(body.intent)) return null;
    if (body.confirmation && (!uuid.test(body.confirmation.message_id) || !/^[a-f\d]{64}$/.test(body.confirmation.facts_hash))) return null;
    return body;
  } catch { return null; }
}

export function createSseParser() {
  let buffer = '';
  return { push(chunk: string): ChatEvent[] {
    buffer += chunk;
    if (buffer.length > 262144) throw new Error('SSE budget exceeded');
    const result: ChatEvent[] = [];
    // Normalize only complete CRLF pairs; a trailing CR may belong to the next chunk.
    buffer = buffer.replace(/\r\n/g, '\n');
    let boundary: number;
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      let event = 'message', id: number | null = null;
      const data: string[] = [];
      for (const line of block.split('\n')) {
        if (!line || line.startsWith(':')) continue;
        const split = line.indexOf(':');
        const key = split < 0 ? line : line.slice(0, split);
        const value = split < 0 ? '' : line.slice(split + 1).replace(/^ /, '');
        if (key === 'event') event = value;
        if (key === 'data') data.push(value);
        if (key === 'id') { if (!/^\d{1,12}$/.test(value)) throw new Error('Invalid SSE sequence'); id = Number(value); }
      }
      if (!data.length) continue;
      const parsed: unknown = JSON.parse(data.join('\n'));
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Invalid SSE data');
      result.push({ id, event, data: parsed as Record<string, unknown> });
    }
    return result;
  } };
}
