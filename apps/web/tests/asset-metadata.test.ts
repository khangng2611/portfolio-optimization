import { expect, it } from 'vitest';
import { mergeAssetMetadata, type AssetCatalog } from '../src/lib/selection-types';

const catalog: AssetCatalog = { selection_enabled: true, catalog_version: 'supported-assets-v1', assets: [{ asset_id: 'FPT', kind: 'stock', unit: 'VND/share', currency: 'VND', catalog_version: 'supported-assets-v1', display_name: 'Old hardcoded name', description: 'Old description', data_status: 'FRESH', ml_status: 'COVERED' }] };

it('reads Market metadata without expanding the model universe or replacing readiness', () => {
  const result = mergeAssetMetadata(catalog, [{ asset_id: 'FPT', display_name: 'Database company name', description: 'Database business profile' }, { asset_id: 'UNSUPPORTED', display_name: 'Other', description: 'Other' }]);
  expect(result.assets).toHaveLength(1);
  expect(result.assets[0]).toMatchObject({ asset_id: 'FPT', display_name: 'Database company name', description: 'Database business profile', data_status: 'FRESH', ml_status: 'COVERED' });
});

it('uses explicit missing metadata rather than old hardcoded descriptions during an outage', () => {
  expect(mergeAssetMetadata(catalog, []).assets[0]).toMatchObject({ display_name: 'FPT', description: null, data_status: 'FRESH' });
});
