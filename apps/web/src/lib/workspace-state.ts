export type WorkspaceView = 'overview' | 'portfolios' | 'create' | 'proposal' | 'profile' | 'history' | 'edit' | 'compare' | 'market' | 'market-ingestion' | 'market-quality' | 'market-snapshots' | 'market-publications' | 'market-refresh' | 'models' | 'model-training' | 'model-review' | 'risk-assessment' | 'chat';
export type WorkspaceRoute = { view: WorkspaceView; focus?: 'history'; conversationId?: string; portfolioId?: string; proposalId?: string; compareIds?: [string, string]; invalid?: boolean; jobId?: string; snapshotId?: string; modelId?: string };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const views: WorkspaceView[] = ['overview', 'portfolios', 'create', 'proposal', 'profile', 'history', 'edit', 'compare', 'market', 'market-ingestion', 'market-quality', 'market-snapshots', 'market-publications', 'market-refresh', 'models', 'model-training', 'model-review', 'risk-assessment', 'chat'];
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
  if (focus) { if (focus === 'history' && view === 'proposal' && params.getAll('focus').length === 1) route.focus = 'history'; else route.invalid = true; }
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
  if (route.compareIds) { params.set('a', route.compareIds[0]); params.set('b', route.compareIds[1]); }
  return '#' + route.view + (params.size ? '?' + params.toString() : '');
}
export function proposalCompletionRoute(current: WorkspaceRoute, portfolioId: string, proposalId: string): WorkspaceRoute | null {
  return current.view === 'proposal' && current.portfolioId === portfolioId && !current.proposalId
    ? { view: 'proposal', portfolioId, proposalId } : null;
}
export type StrategyReadiness = { strategy: string; available: boolean; reason_code: string };
export type Readiness = { universe_id: string; asset_ids: string[]; as_of_date: string | null; valid_until: string | null; demo: boolean; data_origin: string; status: string; reason_code: string; strategies: StrategyReadiness[]; next_action: string; checked_at: string; bundle_id?: string | null; bundle_hash?: string | null; snapshot_id?: string | null; approved_model_id?: string | null; model_manifest_hash?: string | null };
export function readinessAllows(value: Pick<Readiness, 'status' | 'strategies'> | null, strategy: string, fallback: boolean): boolean {
  if (!value || value.status !== 'READY') return false;
  const current = value.strategies.find(s => s.strategy === strategy);
  if (current?.available) return true;
  return strategy === 'BL_ML' && fallback && current?.reason_code === 'MODEL_UNAVAILABLE' && value.strategies.some(s => s.strategy === 'EW' && s.available);
}
export function modelServingReady(value: Pick<Readiness, 'status' | 'strategies' | 'valid_until'>, now: number): boolean {
  return !!value.valid_until && Date.parse(value.valid_until) > now && readinessAllows(value, 'BL_ML', false);
}
type ComparisonPins = { data_snapshot_id?: string; bundle_hash?: string; policy_version_id?: string; portfolio_version?: number; capital_vnd: string; core_version?: string; as_of_date?: string; model_bundle_id?: string | null };
export function comparisonDifferences(a: ComparisonPins, b: ComparisonPins): string[] {
  return ([['data_snapshot_id', 'Snapshot dữ liệu'], ['bundle_hash', 'Bộ input'], ['as_of_date', 'Ngày dữ liệu'], ['policy_version_id', 'Policy'], ['portfolio_version', 'Phiên bản danh mục'], ['capital_vnd', 'Vốn kế hoạch'], ['core_version', 'Core'], ['model_bundle_id', 'Model']] as const)
    .filter(([key]) => a[key] !== b[key]).map(([, label]) => label);
}
