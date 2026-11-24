import { expect, it } from 'vitest';
import { parseWorkspaceHash, workspaceHash } from '../src/lib/workspace-state';
import { renderToStaticMarkup } from 'react-dom/server';
import { RiskReassessment } from '../src/components/risk-reassessment';
import { RiskWizard } from '../src/components/risk-wizard';
import { PortfolioEmptyState } from '../src/components/portfolio-lifecycle';
import { PortfolioOverview, RiskProfileView } from '../src/components/portfolio-workspace';
import type { Portfolio } from '../src/lib/portfolio-types';

const portfolio: Portfolio = { id: 'p', name: 'Kế hoạch', capital_vnd: '100000000', universe_id: 'VN', version: 1, constraints: { risk_aversion: 3, max_position_weight: .5 }, risk_profile: { profile: 'balanced' }, policy_version_id: 'v1' };
it('requires deliberate risk answers instead of promoting preselected assumptions', () => {
  const html = renderToStaticMarkup(<RiskWizard busy={false} onCreate={async () => true}/>);
  const radios = html.match(/<input[^>]*type="radio"[^>]*>/g) ?? [];
  expect(radios).toHaveLength(9);
  expect(radios.some(input => input.includes('checked=""'))).toBe(false);
  for (const name of ['loss', 'reserve', 'liquidity']) expect(radios.some(input => input.includes(`name="${name}"`) && input.includes('required=""'))).toBe(true);
});
it('gives a first account a direct creation action, while search-empty offers recovery', () => {
  const first = renderToStaticMarkup(<PortfolioEmptyState firstUse onClear={() => {}}/>);
  expect(first).toContain('href="#create"');
  expect(first).toContain('Tạo danh mục đầu tiên');
  expect(first).not.toContain('bộ lọc');
  const filtered = renderToStaticMarkup(<PortfolioEmptyState firstUse={false} onClear={() => {}}/>);
  expect(filtered).toContain('Xóa bộ lọc');
  expect(filtered).not.toContain('Tạo danh mục đầu tiên');
});
it('directs an unaccepted portfolio with existing proposals to review instead of first creation', () => {
  const html = renderToStaticMarkup(<PortfolioOverview portfolio={portfolio} dashboard={{ portfolio, accepted_target: null, proposal_count: 2, target_matches_portfolio: true }}/>);
  expect(html).toContain('Xem lịch sử đề xuất');
  expect(html).not.toContain('Tạo đề xuất đầu tiên');
  expect(html).not.toContain('2 đề xuất chưa chấp nhận');
  expect(html).toContain('focus=history');
});
it('offers the first proposal after confirming the profile and method readiness', () => {
  const html = renderToStaticMarkup(<PortfolioOverview portfolio={portfolio} readiness={{ readiness_kind: 'user-selection-v1', reason_code: 'READY', can_submit: true, strategies: [{ strategy: 'HYBRID', can_submit: true, reason_code: 'READY' }], candidate_asset_ids: ['FPT', 'VFF'], asset_status: [], selection_valid_until: '2099-01-01' }} dashboard={{ portfolio, accepted_target: null, proposal_count: 0, target_matches_portfolio: true }}/>);
  expect(html).toContain('Tạo đề xuất đầu tiên');
});
it('never invents questionnaire answers for a legacy profile', () => {
  const html = renderToStaticMarkup(<RiskProfileView portfolio={portfolio}/>);
  expect(html).toContain('Chưa có câu trả lời đã lưu');
  expect(html).not.toContain('36 tháng');
  expect(html).toContain('Đánh giá lại hồ sơ');
});
it('shows saved answers and usable limits without internal profile metadata', () => {
  const html = renderToStaticMarkup(<RiskProfileView portfolio={{ ...portfolio, risk_profile: { profile: 'balanced', answers: { questionnaire_version: 'risk-v1', horizon_months: 60, liquidity_need: 'high', loss_tolerance: 'low', experience: 'experienced' } } }}/>);
  expect(html).toContain('60 tháng');
  expect(html).toContain('Đã có kinh nghiệm');
  expect(html).not.toContain('Chưa có câu trả lời đã lưu');
  expect(html).toContain('Tối đa 50% mỗi tài sản');
  expect(html).not.toContain('Thông số và phiên bản hồ sơ');
  expect(html).not.toContain('v1');
});

it('retains an explicit proposal-history destination across URL serialization', () => {
  const route = { view: 'proposal' as const, portfolioId: '11111111-1111-4111-8111-111111111111', focus: 'history' as const };
  expect(parseWorkspaceHash(workspaceHash(route))).toEqual(route);
  expect(parseWorkspaceHash('#proposal?focus=other').invalid).toBe(true);
  expect(parseWorkspaceHash('#proposal?focus=history&focus=history').invalid).toBe(true);
});

it('does not fabricate answers when reassessing a legacy profile', () => {
  const html = renderToStaticMarkup(<RiskReassessment portfolio={portfolio} api={async () => { throw new Error('not called during render'); }} fetchPage={async () => ({ items: [], total: 0, limit: 10, offset: 0 })} onSaved={() => {}} onReload={() => {}}/>);
  expect(html).toContain('name="reserve"');
  expect(html).not.toMatch(/type="radio"[^>]*checked/);
  expect(html).not.toContain('value="36"');
});

it('shows exact planned-capital examples and preserves the survey interpretation', () => {
  const answers = { questionnaire_version: 'risk-v2' as const, horizon_months: 60, liquidity_need: 'high' as const,
    loss_tolerance: 'high' as const, reserve_months: 'at_least_6' as const };
  const saved: Portfolio = { ...portfolio, capital_vnd: '10000000000000000000.0000',
    risk_profile: { profile: 'conservative', answers, determining_factors: ['liquidity_need'] } };
  const html = renderToStaticMarkup(<RiskReassessment portfolio={saved} api={async () => { throw Error(); }} fetchPage={async () => ({ items: [], total: 0, limit: 10, offset: 0 })} onSaved={() => {}} onReload={() => {}}/>);
  expect(html).toContain('5% = 500.000.000.000.000.000 ₫');
  expect(html.match(/type="radio"[^>]*checked/g)).toHaveLength(3);
  const profile = renderToStaticMarkup(<RiskProfileView portfolio={saved}/>);
  expect(profile).toContain('dự kiến rút trên 30% vốn trong 12 tháng');
  expect(profile).toContain('Từ 6 tháng trở lên');
  expect(profile).not.toContain('Đã có kinh nghiệm');
});
