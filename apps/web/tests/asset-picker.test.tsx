import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AssetPicker } from '../src/components/asset-picker';
import type { AssetCatalogItem } from '../src/lib/selection-types';
const asset = (id: string, kind: AssetCatalogItem['kind'], data_status: AssetCatalogItem['data_status']): AssetCatalogItem => ({ asset_id: id, kind, display_name: id, description: id === 'FPT' ? 'Công nghệ thông tin và viễn thông.' : 'Quỹ mở đầu tư trái phiếu.', data_status, currency: 'VND', unit: 'VND/unit', catalog_version: 'supported-assets-v1', ml_status: 'UNKNOWN' });
it('keeps stale catalog choices selectable and explains zero weights without preselecting assets', () => {
  const html = renderToStaticMarkup(<AssetPicker assets={[asset('FPT', 'stock', 'FRESH'), asset('VFF', 'fund', 'STALE')]} selected={['FPT']} onChange={() => {}}/>);
  expect(html).toContain('Tìm tài sản');
  expect(html).toContain('Quỹ trái phiếu');
  expect(html).toContain('Dữ liệu đã cũ');
  expect(html).toContain('Hệ thống có thể phân bổ 0% vào tài sản đã chọn');
  const available = html.split('data-testid="available-assets"')[1]?.split('</section>')[0] ?? '';
  const selected = html.split('data-testid="selected-assets"')[1]?.split('</section>')[0] ?? '';
  expect(available).toContain('aria-label="Thêm VFF vào rổ tài sản"');
  expect(available).not.toContain('data-asset-id="FPT"');
  expect(selected).toContain('aria-label="Bỏ FPT khỏi rổ tài sản"');
  expect(selected).toContain('Công nghệ thông tin và viễn thông.');
  expect(selected).not.toContain('data-asset-id="VFF"');
  expect(html).not.toContain('K5:');
});

it('shows bulk actions and counts from the supplied catalog', () => {
  const html = renderToStaticMarkup(<AssetPicker assets={[asset('FPT', 'stock', 'FRESH'), asset('VFF', 'fund', 'STALE')]} selected={['FPT']} onChange={() => {}}/>);
  expect(html).toContain('Đã chọn 1/2');
  expect(html).toMatch(/<button(?=[^>]*type="button")(?![^>]*disabled)[^>]*>Thêm tất cả<\/button>/);
  expect(html).toMatch(/<button(?=[^>]*type="button")(?![^>]*disabled)[^>]*>Bỏ tất cả<\/button>/);
});

it('disables bulk actions when there is nothing to select or clear', () => {
  const empty = renderToStaticMarkup(<AssetPicker assets={[]} selected={[]} onChange={() => {}}/>);
  expect(empty).toMatch(/<button[^>]*disabled[^>]*>Thêm tất cả<\/button>/);
  expect(empty).toMatch(/<button[^>]*disabled[^>]*>Bỏ tất cả<\/button>/);
  expect(empty).toContain('Rổ tài sản đang trống');
  const full = renderToStaticMarkup(<AssetPicker assets={[asset('FPT', 'stock', 'FRESH')]} selected={['FPT']} onChange={() => {}} disabled/>);
  expect(full).toContain('<fieldset class="asset-picker" disabled="">');
  expect(full).toMatch(/<button[^>]*disabled[^>]*>Thêm tất cả<\/button>/);
});

it('uses an explicit fallback when an older catalog has no description', () => {
  const item = { ...asset('FPT', 'stock', 'UNKNOWN'), description: null };
  const html = renderToStaticMarkup(<AssetPicker assets={[item]} selected={[]} onChange={() => {}}/>);
  expect(html).toContain('Chưa có mô tả từ nguồn dữ liệu.');
});
