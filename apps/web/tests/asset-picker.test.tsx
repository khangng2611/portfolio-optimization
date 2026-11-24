import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AssetPicker, WizardAssetPicker } from '../src/components/asset-picker';
import type { AssetCatalogItem } from '../src/lib/selection-types';
const asset = (id: string, kind: AssetCatalogItem['kind'], data_status: AssetCatalogItem['data_status']): AssetCatalogItem => ({ asset_id: id, kind, display_name: id, description: id === 'FPT' ? 'Công nghệ thông tin và viễn thông.' : 'Quỹ mở đầu tư trái phiếu.', data_status, currency: 'VND', unit: 'VND/unit', catalog_version: 'supported-assets-v1', ml_status: 'UNKNOWN' });
it('keeps stale catalog choices selectable without preselecting assets', () => {
  const html = renderToStaticMarkup(<AssetPicker assets={[asset('FPT', 'stock', 'FRESH'), asset('VFF', 'fund', 'STALE')]} selected={['FPT']} onChange={() => {}}/>);
  expect(html).toContain('Tìm tài sản');
  expect(html).toContain('Quỹ trái phiếu');
  expect(html).toContain('Dữ liệu đã cũ');
  expect(html).toContain('kiểm tra lại dữ liệu của từng mã');
  const available = html.split('data-testid="available-assets"')[1]?.split('</section>')[0] ?? '';
  const selected = html.split('data-testid="selected-assets"')[1]?.split('</section>')[0] ?? '';
  expect(available).toContain('aria-label="Thêm VFF vào rổ tài sản"');
  expect(available).toContain('href="#asset-prices?asset=VFF" target="_blank"');
  expect(selected).toContain('href="#asset-prices?asset=FPT" target="_blank"');
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

it('skips description markup when an asset has no description', () => {
  const item = { ...asset('FPT', 'stock', 'UNKNOWN'), description: null };
  const html = renderToStaticMarkup(<AssetPicker assets={[item]} selected={[]} onChange={() => {}}/>);
  expect(html).not.toContain('Chưa có mô tả từ nguồn dữ liệu.');
  expect(html).not.toContain('aria-describedby');
});

it('shows the eligible price date even when a newer observation is recorded', () => {
  const item = { ...asset('ACB', 'stock', 'FRESH'), eligible_observation_date: '2026-11-17', latest_observation_date: '2026-11-20' };
  const html = renderToStaticMarkup(<AssetPicker assets={[item]} selected={[]} onChange={() => {}}/>);
  expect(html).toContain('Giá ngày 17/11/2026');
  expect(html).not.toContain('Giá ngày 20/11/2026');
  expect(html).toContain('Ngày ghi nhận gần nhất</dt><dd>20/11/2026');
});

it('opens onboarding with individual selection states, the basket summary and the defensive fund requirement', () => {
  const html = renderToStaticMarkup(<WizardAssetPicker assets={[{ ...asset('FPT', 'stock', 'FRESH'), display_name: 'Tập đoàn FPT' }, asset('VFF', 'fund', 'STALE')]} selected={['FPT']} onChange={() => {}}/>);
  expect(html.indexOf('Thêm VFF vào rổ tài sản')).toBeLessThan(html.indexOf('Bỏ FPT khỏi rổ tài sản'));
  expect(html).toContain('Cần VFF khi tính đề xuất.');
  expect(html).toContain('Tập đoàn FPT');
  expect(html).toContain('aria-pressed="true" aria-label="Bỏ FPT khỏi rổ tài sản"');
  expect(html).toContain('aria-pressed="false" aria-label="Thêm VFF vào rổ tài sản"');
  expect(html).toContain('<strong>FPT</strong><p>Mã đã chọn có thể nhận tỷ trọng 0%.</p>');
  expect(html).toContain('Xem tất cả 2 mã');
  expect(html).not.toContain('<details open');
});
