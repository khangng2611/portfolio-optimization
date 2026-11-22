import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PortfolioOverview } from '../src/components/portfolio-workspace';
import { AssetPicker } from '../src/components/asset-picker';
import { ChatRecommendation } from '../src/components/chat-workspace';
import type { Portfolio, Recommendation } from '../src/lib/portfolio-types';
import type { RecommendationCard } from '../src/lib/chat-types';
import type { AssetCatalogItem } from '../src/lib/selection-types';

const portfolio: Portfolio = { id: 'p', name: 'Kế hoạch hiện tại', capital_vnd: '120000000', universe_id: 'USER_SELECTED', version: 2, constraints: { risk_aversion: 3, max_position_weight: .5 }, risk_profile: { profile: 'balanced' }, policy_version_id: 'current-policy', asset_selection: { revision_id: 'current', portfolio_id: 'p', portfolio_version: 2, candidate_asset_ids: ['FPT', 'GOLD', 'VFF'], candidate_hash: 'current-hash', selection_policy_id: 'selection', risk_policy_id: 'risk', created_at: '2026-11-20T00:00:00Z' } };
const canonical: Recommendation = { id: 'r', portfolio_id: 'p', portfolio_version: 1, asset_ids: ['ZERO', 'FPT', 'VFF'], weights: [0, .5, .5], capital_vnd: '100000000', strategy: 'MVO', as_of_date: '2026-11-17', constraints: { risk_aversion: 3, max_position_weight: .5 } };
const card: RecommendationCard = { type: 'recommendation', recommendation_id: 'r', facts: { ...canonical }, facts_hash: 'a'.repeat(64), explanation_status: 'TEMPLATE', explanation_requested: true, provider: { reason: 'DISABLED' }, schema_version: 'fact-plan-v1', prompt_version: 'v1' };

it('discloses current candidates without replacing the accepted result with current capital', () => {
  const html = renderToStaticMarkup(<PortfolioOverview portfolio={portfolio} dashboard={{ portfolio, accepted_target: { id: 't', recommendation_id: 'r', accepted_at: '2026-11-18T00:00:00Z', portfolio_version: 1, allocation: canonical }, proposal_count: 1, target_matches_portfolio: false }}/>);
  expect(html).toContain('3 tài sản được cân nhắc');
  expect(html.indexOf('<details')).toBeLessThan(html.indexOf('FPT · GOLD · VFF'));
  expect(html).toContain('120.000.000');
  expect(html).toContain('100.000.000');
  expect(html).toContain('Vốn đã ghim khi chấp nhận');
  expect(html).toContain('Danh mục đã thay đổi');
  expect(html).toContain('#proposal?portfolio=p&amp;proposal=r');
  expect(html.indexOf('allocation-stack')).toBeLessThan(html.indexOf('allocation-details'));
});

it('keeps technical asset metadata in a disclosure and does not collapse data/ML status into readiness', () => {
  const asset: AssetCatalogItem = { asset_id: 'GOLD', display_name: 'Vàng SJC', description: null, kind: 'gold', data_status: 'STALE', ml_status: 'NOT_COVERED', currency: 'VND', unit: 'VND/tael', catalog_version: 'v1', checked_at: '2026-11-20T00:00:00Z' };
  const html = renderToStaticMarkup(<AssetPicker assets={[asset]} selected={[]} onChange={() => {}}/>);
  expect(html).toContain('Tài sản hỗ trợ · 1');
  expect(html).toContain('Rổ của bạn · 0');
  expect(html).toContain('asset-transfer-empty-panel');
  const row = html.split('class="asset-transfer-row"')[1]?.split('</button>')[0] ?? '';
  expect(row).toContain('Dữ liệu đã cũ');
  expect(row).not.toContain('ML');
  expect(html).toContain('Xem dữ liệu và xác minh từng mã');
  expect(html).toContain('ML chưa phủ');
  expect(html).not.toContain('Sẵn sàng');
});

it('summarizes verified allocation while keeping long server prose and zero rows in original-result details', () => {
  const html = renderToStaticMarkup(<ChatRecommendation card={card} canonical={canonical} content="ZERO 0%; giải thích nguyên văn từ backend."/>);
  expect(html).toContain('Đã tạo đề xuất');
  expect(html).not.toContain('Đề xuất đã lưu');
  expect(html).toContain('Kết quả đang được giải thích');
  expect(html).toContain('Phân bổ chính');
  expect(html).toContain('Cơ sở đã được xác minh');
  expect(html).toContain('Giới hạn và điều cần lưu ý');
  expect(html).toContain('Chưa có nguồn tham khảo phù hợp');
  expect(html).toContain('Nội dung giải thích đã lưu');
  expect(html).toContain('ZERO 0%; giải thích nguyên văn từ backend.');
  expect(html.split('Nội dung giải thích đã lưu')[0]).not.toContain('ZERO 0%');
  expect(html).toContain('Xem đề xuất và quyết định');
});

it('does not invent a constraints section or citations for an older result without them', () => {
  const old = { ...canonical, constraints: undefined };
  const html = renderToStaticMarkup(<ChatRecommendation card={{ ...card, facts: { ...old } }} canonical={old} content=""/>);
  expect(html).not.toContain('Giới hạn và điều cần lưu ý');
  expect(html).not.toContain('Nguồn tham khảo ·');
  expect(html).not.toContain('Nội dung giải thích đã lưu');
});

it('only labels current-target acceptance when it is explicitly confirmed by the dashboard', () => {
  const ordinary = renderToStaticMarkup(<ChatRecommendation card={card} canonical={canonical} content=""/>);
  expect(ordinary).not.toContain('Chưa chấp nhận');
  expect(ordinary).not.toContain('Đã chấp nhận làm mục tiêu hiện tại');
  const accepted = renderToStaticMarkup(<ChatRecommendation card={card} canonical={canonical} content="" isCurrentTarget/>);
  expect(accepted).toContain('Đã chấp nhận làm mục tiêu hiện tại');
});

it('renders every data status independently from ML coverage', () => {
  for (const [data_status, label] of [['UNKNOWN', 'Chưa xác minh dữ liệu'], ['MISSING', 'Thiếu dữ liệu'], ['QUARANTINED', 'Dữ liệu đang cách ly'], ['FRESH', 'Dữ liệu trong hạn'], ['STALE', 'Dữ liệu đã cũ']] as const) {
    const asset: AssetCatalogItem = { asset_id: 'FPT', display_name: 'FPT', kind: 'stock', data_status, ml_status: 'COVERED', currency: 'VND', unit: 'VND/share', catalog_version: 'v1' };
    const html = renderToStaticMarkup(<AssetPicker assets={[asset]} selected={[]} onChange={() => {}}/>);
    const row = html.split('class="asset-transfer-row"')[1]?.split('</button>')[0] ?? '';
    expect(row).toContain(label);
    expect(row).not.toContain('Sẵn sàng');
    expect(html).toContain('ML đã phủ');
  }
});
