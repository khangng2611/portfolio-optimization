import type { AllocationConstraints } from './p1-types';
export type AssetCatalogItem = { asset_id: string; kind: 'stock' | 'gold' | 'fund'; display_name: string; description?: string | null; unit: string; currency: string; catalog_version: string; data_status: 'UNKNOWN' | 'MISSING' | 'QUARANTINED' | 'FRESH' | 'STALE'; eligible_observation_date?: string | null; latest_observation_date?: string | null; available_at?: string | null; age_days?: number | null; checked_at?: string | null; ml_status: 'UNKNOWN' | 'NOT_COVERED' | 'REVIEW_PENDING' | 'COVERED' };
export type AssetCatalog = { catalog_version: string; selection_enabled: boolean; assets: AssetCatalogItem[] };
export const assetKindName = { stock: 'Cổ phiếu', gold: 'Vàng', fund: 'Quỹ trái phiếu' };
export type AssetMetadata = { asset_id: string; display_name: string; description: string | null; metadata_source?: string | null; metadata_source_symbol?: string | null; metadata_fetched_at?: string | null };
export function mergeAssetMetadata(catalog: AssetCatalog, metadata: AssetMetadata[]): AssetCatalog {
  return { ...catalog, assets: catalog.assets.map(asset => {
    const record = metadata.find(item => item.asset_id === asset.asset_id);
    return { ...asset, display_name: record?.display_name || asset.asset_id, description: record?.description ?? null };
  }) };
}
export type SelectionRevision = { revision_id: string; portfolio_id: string; portfolio_version: number; candidate_asset_ids: string[]; candidate_hash: string; selection_policy_id: string; risk_policy_id: string; created_at: string };
export type SelectionProof = { candidate_hash: string; active_asset_ids: string[]; selected_equity_ids: string[]; rejected_equity_ids: string[]; selection_hash: string; applied_selection: string; decision_session: string; selection_price_end_date: string };
export type SelectionReadiness = { readiness_kind: 'user-selection-v1'; portfolio_version?: number; revision_id?: string; candidate_hash?: string; candidate_asset_ids: string[]; can_submit: boolean; reason_code: string; strategies: { strategy: string; can_submit: boolean; reason_code: string }[]; asset_status: Record<string, unknown>[]; regime?: { regime: string } | null; selection_valid_until?: string | null; decision_session?: string | null; checked_at?: string | null; effective_constraints?: AllocationConstraints | null };
export const isSelectionReadiness = (value: unknown): value is SelectionReadiness => !!value && typeof value === 'object' && 'readiness_kind' in value && value.readiness_kind === 'user-selection-v1';
