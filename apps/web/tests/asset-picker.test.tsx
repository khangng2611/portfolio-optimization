import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AssetPicker } from '../src/components/asset-picker';
import type { AssetCatalogItem } from '../src/lib/selection-types';
const asset = (id: string, kind: AssetCatalogItem['kind'], data_status: AssetCatalogItem['data_status']): AssetCatalogItem => ({ asset_id: id, kind, display_name: id, data_status, currency: 'VND', unit: 'VND/unit', catalog_version: 'supported-assets-v1', ml_status: 'UNKNOWN' });
it('keeps stale catalog choices selectable and explains zero weights without preselecting assets', () => {
  const html = renderToStaticMarkup(<AssetPicker assets={[asset('FPT', 'stock', 'FRESH'), asset('VFF', 'fund', 'STALE')]} selected={['FPT']} onChange={() => {}}/>);
  expect(html).toContain('Tìm tài sản');
  expect(html).toContain('Quỹ trái phiếu');
  expect(html).toContain('Dữ liệu đã cũ');
  expect(html).toContain('Hệ thống có thể phân bổ 0% vào tài sản đã chọn');
  expect(html).toMatch(/<input(?=[^>]*value="VFF")(?![^>]*checked)(?![^>]*disabled)[^>]*>/);
  expect(html).not.toContain('K5:');
});

it('shows bulk actions and counts from the supplied catalog', () => {
  const html = renderToStaticMarkup(<AssetPicker assets={[asset('FPT', 'stock', 'FRESH'), asset('VFF', 'fund', 'STALE')]} selected={['FPT']} onChange={() => {}}/>);
  expect(html).toContain('Đã chọn 1/2');
  expect(html).toMatch(/<button(?=[^>]*type="button")(?![^>]*disabled)[^>]*>Chọn tất cả<\/button>/);
  expect(html).toMatch(/<button(?=[^>]*type="button")(?![^>]*disabled)[^>]*>Bỏ chọn tất cả<\/button>/);
});

it('disables bulk actions when there is nothing to select or clear', () => {
  const empty = renderToStaticMarkup(<AssetPicker assets={[]} selected={[]} onChange={() => {}}/>);
  expect(empty).toMatch(/<button[^>]*disabled[^>]*>Chọn tất cả<\/button>/);
  expect(empty).toMatch(/<button[^>]*disabled[^>]*>Bỏ chọn tất cả<\/button>/);
  const full = renderToStaticMarkup(<AssetPicker assets={[asset('FPT', 'stock', 'FRESH')]} selected={['FPT']} onChange={() => {}} disabled/>);
  expect(full).toContain('<fieldset class="asset-picker" disabled="">');
  expect(full).toMatch(/<button[^>]*disabled[^>]*>Chọn tất cả<\/button>/);
});
