import { isSelectionReadiness, type SelectionReadiness } from './selection-types';
import type { Phase1Full } from './p1-types';
export type WorkspaceView = (typeof views)[number];
export type WorkspaceRoute = { view: WorkspaceView; focus?: 'history' | 'request'; conversationId?: string; portfolioId?: string; proposalId?: string; compareIds?: [string, string]; invalid?: boolean; jobId?: string; snapshotId?: string; modelId?: string; assetId?: string; returnView?: 'overview' };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const assetIdPattern = /^[A-Z0-9_-]{1,64}$/;
const views = ['overview', 'portfolios', 'create', 'proposal', 'profile', 'history', 'edit', 'compare', 'market', 'market-ingestion', 'market-quality', 'market-snapshots', 'market-publications', 'market-refresh', 'market-revisions', 'models', 'model-training', 'model-review', 'risk-assessment', 'chat', 'asset-prices', 'settings', 'holdings', 'rebalance', 'views', 'research', 'knowledge'] as const;
export const allocationPriceKey = (owner: string, portfolio: string, proposal: string) => `portfolio.price-focus:${owner}:${portfolio}:${proposal}`;
export function parseWorkspaceHash(hash: string): WorkspaceRoute {
  const [name, query] = hash.replace(/^#/, '').split('?');
  const view = views.includes(name as WorkspaceView) ? name as WorkspaceView : 'overview';
  const params = new URLSearchParams(query);
  const route: WorkspaceRoute = { view };
  for (const [key, field] of [['conversation', 'conversationId'], ['portfolio', 'portfolioId'], ['proposal', 'proposalId'], ['job', 'jobId'], ['snapshot', 'snapshotId'], ['model', 'modelId']] as const) {
    const value = params.get(key);
    if (value && uuid.test(value) && params.getAll(key).length === 1) route[field] = value;
    else if (value) route.invalid = true;
  }
  const focus = params.get('focus');
  const asset = params.get('asset');
  if (asset !== null) {
    if (view === 'asset-prices' && assetIdPattern.test(asset) && params.getAll('asset').length === 1) route.assetId = asset;
    else route.invalid = true;
  }
  const origin = params.get('from');
  if (origin !== null) {
    if (view === 'asset-prices' && origin === 'overview' && route.portfolioId && params.getAll('from').length === 1) route.returnView = origin;
    else route.invalid = true;
  }
  if (focus) { if ((focus === 'history' || focus === 'request' && !route.proposalId && !route.jobId) && view === 'proposal' && params.getAll('focus').length === 1) route.focus = focus; else route.invalid = true; }
  const a = params.get('a'), b = params.get('b');
  if (a || b) {
    if (a && b && a !== b && uuid.test(a) && uuid.test(b) && params.getAll('a').length === 1 && params.getAll('b').length === 1) route.compareIds = [a, b];
    else route.invalid = true;
  }
  if (route.proposalId && !route.portfolioId || route.compareIds && !route.portfolioId) route.invalid = true;
  return route;
}
export function workspaceHash(route: WorkspaceRoute): string {
  const params = new URLSearchParams();
  if (route.focus) params.set('focus', route.focus);
  if (route.conversationId) params.set('conversation', route.conversationId);
  if (route.portfolioId) params.set('portfolio', route.portfolioId);
  if (route.proposalId) params.set('proposal', route.proposalId);
  if (route.jobId) params.set('job', route.jobId);
  if (route.snapshotId) params.set('snapshot', route.snapshotId);
  if (route.modelId) params.set('model', route.modelId);
  if (route.returnView) params.set('from', route.returnView);
  if (route.assetId) params.set('asset', route.assetId);
  if (route.compareIds) { params.set('a', route.compareIds[0]); params.set('b', route.compareIds[1]); }
  return '#' + route.view + (params.size ? '?' + params.toString() : '');
}
export function proposalCompletionRoute(current: WorkspaceRoute, portfolioId: string, proposalId: string): WorkspaceRoute | null {
  return current.view === 'proposal' && current.portfolioId === portfolioId && !current.proposalId
    ? { view: 'proposal', portfolioId, proposalId } : null;
}
export function assetUniverseName(id: string): string {
  if (id === 'USER_SELECTED') return 'Tài sản bạn chọn';
  if (id === 'DEMO') return 'Bộ tài sản minh họa';
  if (id === 'VN_PHASE1_FULL') return 'Danh sách tài sản Việt Nam';
  return 'Bộ tài sản có sẵn';
}

export type StrategyReadiness = { strategy: string; available: boolean; reason_code: string };
export type LegacyReadiness = { provenance?: { phase1_full?: Phase1Full } | null; universe_id: string; asset_ids: string[]; as_of_date: string | null; valid_until: string | null; demo: boolean; data_origin: string; status: string; reason_code: string; strategies: StrategyReadiness[]; next_action: string; checked_at: string; bundle_id?: string | null; bundle_hash?: string | null; snapshot_id?: string | null; approved_model_id?: string | null; model_manifest_hash?: string | null };
export type Readiness = LegacyReadiness | SelectionReadiness;
export function readinessAllows(value: Readiness | (Pick<LegacyReadiness, 'status' | 'strategies'> & Partial<Pick<LegacyReadiness, 'valid_until'>>) | null, strategy: string, fallback: boolean, now = Date.now()): boolean {
  if (isSelectionReadiness(value)) {
    if (value.reason_code === 'SYSTEM_PAUSED' || !(Date.parse(value.selection_valid_until ?? '') > now)) return false;
    // The custom API reports its default strategy at the top level and each alternative separately.
    if (strategy === 'HYBRID' && !value.can_submit) return false;
    const current = value.strategies.find(item => item.strategy === strategy);
    if (current?.can_submit) return true;
    return strategy === 'BL_ML' && fallback && !!current && ['MODEL_UNAVAILABLE', 'MODEL_REVIEW_PENDING', 'MODEL_COVERAGE_MISSING', 'MODEL_EPOCH_MISMATCH', 'NO_VALID_ML_VIEWS'].includes(current.reason_code) && value.strategies.some(item => item.strategy === 'EW' && item.can_submit);
  }
  if (!value || value.status !== 'READY' || ('reason_code' in value && value.reason_code === 'SYSTEM_PAUSED')) return false;
  if ('valid_until' in value && !(Date.parse(value.valid_until ?? '') > now)) return false;
  const current = value.strategies.find(s => s.strategy === strategy);
  if (current?.available) return true;
  return strategy === 'BL_ML' && fallback && current?.reason_code === 'MODEL_UNAVAILABLE' && value.strategies.some(s => s.strategy === 'EW' && s.available);
}
export function modelServingReady(value: Pick<LegacyReadiness, 'status' | 'strategies' | 'valid_until'>, now: number): boolean {
  return !!value.valid_until && Date.parse(value.valid_until) > now && readinessAllows(value, 'BL_ML', false, now);
}
type ComparisonPins = { data_snapshot_id?: string; bundle_hash?: string; policy_version_id?: string; portfolio_version?: number; capital_vnd: string; core_version?: string; as_of_date?: string; model_bundle_id?: string | null };
export function comparisonDifferences(a: ComparisonPins, b: ComparisonPins): string[] {
  return [...new Set(([['data_snapshot_id', 'bộ dữ liệu'], ['bundle_hash', 'dữ liệu đầu vào'], ['as_of_date', 'ngày dữ liệu'], ['policy_version_id', 'quy tắc phân bổ'], ['portfolio_version', 'phiên bản danh mục'], ['capital_vnd', 'vốn kế hoạch'], ['core_version', 'cách tính'], ['model_bundle_id', 'cách tính']] as const)
    .filter(([key]) => a[key] !== b[key]).map(([, label]) => label))];
}

export const allocationPausedTitle = 'Tính năng tạo đề xuất mới đang tạm dừng.';
export const savedProposalsHint = 'Bạn vẫn có thể xem các đề xuất đã lưu.';
export const readinessReason: Record<string, string> = {
  ASSET_SELECTION_REQUIRED: 'Tạo danh mục có rổ tài sản được chọn để nhận đề xuất hệ thống. Bạn vẫn có thể mở lịch sử danh mục này.',
  INSUFFICIENT_ASSETS: 'Cần ít nhất 2 tài sản để tính phân bổ; bạn vẫn có thể lưu lựa chọn.',
  RISK_PROFILE_REQUIRED: 'Cần xác nhận hồ sơ rủi ro của danh mục trước khi tính.',
  DEFENSIVE_ASSET_REQUIRED: 'Rổ cần có quỹ trái phiếu VFF để đáp ứng giới hạn phòng thủ.',
  CONSTRAINTS_INFEASIBLE: 'Lựa chọn chưa đủ sức chứa để thỏa giới hạn vị thế và nhóm phòng thủ.',
  ASSET_DATA_MISSING: 'Một tài sản đã chọn còn thiếu dữ liệu; cần cập nhật nguồn.',
  ASSET_DATA_STALE: 'Dữ liệu đủ điều kiện của tài sản đã chọn đã quá 7 ngày.',
  HISTORY_INSUFFICIENT: 'Lịch sử của tài sản đã chọn chưa đủ để tính toán.',
  MODEL_COVERAGE_MISSING: 'Hệ thống chưa thể tính đề xuất cho tất cả cổ phiếu đã chọn.',
  MODEL_EPOCH_MISMATCH: 'Hệ thống đang chờ đầu vào phù hợp với kỳ dữ liệu hiện tại.',
  NO_VALID_ML_VIEWS: 'Chưa đủ tín hiệu dự báo để tính đề xuất cho rổ tài sản này.',

  VFF_STALE: 'NAV VFF đủ điều kiện đã quá 7 ngày; cần dữ liệu khả dụng mới.',
  GOLD_STALE: 'Giá GOLD đủ điều kiện đã quá 7 ngày; cần dữ liệu khả dụng mới.',
  MODEL_REVIEW_PENDING: 'Đầu vào tính đề xuất đang chờ phê duyệt.',
  MODEL_UNAVAILABLE: 'Chưa có mô hình đã duyệt phù hợp với dữ liệu hiện tại.',
  INPUT_EXPIRED: 'Dữ liệu đã hết hạn. Cần làm mới trước khi tính đề xuất.',
  INPUT_UNAVAILABLE: 'Dữ liệu hoặc mô hình chưa sẵn sàng để tính đề xuất.',
  SYSTEM_PAUSED: allocationPausedTitle + ' ' + savedProposalsHint,
  INPUT_INVALID: 'Dữ liệu hoặc mô hình chưa qua kiểm tra tính toàn vẹn.',
  SELECTION_MISMATCH: 'Hệ thống đang chờ đầu vào tương thích để tính đề xuất.',
};
