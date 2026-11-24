import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { ComparisonTable } from '../src/components/portfolio-lifecycle';
import type { Recommendation } from '../src/lib/portfolio-types';

const a: Recommendation = { id: 'a', portfolio_id: 'p', portfolio_version: 1, capital_vnd: '100000000', asset_ids: ['FPT', 'VCB'], weights: ['0.4', '0.6'], strategy: 'MVO', data_snapshot_id: 'snapshot-a' };
const b: Recommendation = { ...a, id: 'b', asset_ids: ['VCB', 'FPT', 'MWG'], weights: ['0.5', '0.3', '0.2'], strategy: 'EW', data_snapshot_id: 'snapshot-b' };

describe('V2 comparison decisions', () => {
  it('aligns reordered and missing assets and renders signed B minus A percentage points', () => {
    const html = renderToStaticMarkup(<ComparisonTable items={[a, b]}/>);
    expect(html).toContain('Δ B − A');
    expect(html).toContain('−10,0 điểm %');
    expect(html).toContain('+20,0 điểm %');
    expect(html).toContain('0,0%');
    const [chart, table] = html.split('<table class="comparison-table">');
    expect(chart.indexOf('MWG')).toBeLessThan(chart.indexOf('FPT'));
    expect(table.indexOf('FPT')).toBeLessThan(table.indexOf('VCB'));
    expect(table.indexOf('VCB')).toBeLessThan(table.indexOf('MWG'));
    expect(html).toContain('20.000.000');
  });
  it('keeps unchanged assets in the comparison table and labels a tiny change without rounding it to zero', () => {
    const html = renderToStaticMarkup(<ComparisonTable items={[a, { ...a, id: 'tiny', weights: [.40003, .6] }]}/>);
    const [chart, table] = html.split('<table class="comparison-table">');
    expect(chart).toContain('Tăng &lt;0,01 điểm %');
    expect(chart).not.toContain('VCB');
    expect(table).toContain('VCB');
  });
  it('puts allocations before profile and data details with links to both proposals', () => {
    const html = renderToStaticMarkup(<ComparisonTable items={[a, b]}/>);
    expect(html.indexOf('FPT')).toBeLessThan(html.indexOf('Xem hồ sơ và ngày dữ liệu'));
    expect(html).toContain('<details');
    expect(html).toContain('khác cơ sở đầu vào');
    expect(html).toContain('#proposal?portfolio=p&amp;proposal=a');
    expect(html).toContain('#proposal?portfolio=p&amp;proposal=b');
    expect(html).not.toContain('tốt nhất');
  });
});

// State-gated decisions must remain separate even when layout changes.
import { PausedProposal, ProposalReview, ProposalRequest, PortfolioOverview } from '../src/components/portfolio-workspace';
import type { Portfolio } from '../src/lib/portfolio-types';
const portfolio: Portfolio = { id: 'p', name: 'Kế hoạch', capital_vnd: '100000000', universe_id: 'VN', version: 1, constraints: { risk_aversion: 3, max_position_weight: .5 }, risk_profile: { profile: 'balanced' }, policy_version_id: 'v1' };
it('never offers an enabled accept for a stale proposal', () => {
  const html = renderToStaticMarkup(<ProposalReview portfolio={portfolio} recommendation={a} accepted={false} stale conflict={false} busy={false} onAccept={() => {}} viewerBase={null}/>);
  expect(html).toMatch(/data-testid="accept-proposal" disabled=""/);
  expect(html).toContain('Phân bổ của lần tính cũ');
  expect(html).not.toContain('Xem lại đầu vào');
});
it('starts with input review, not a mutation confirmation or a preaccepted target', () => {
  const html = renderToStaticMarkup(<ProposalRequest portfolio={portfolio} readiness={null} busy={false} onSubmit={() => {}}/>);
  expect(html).toContain('Xem lại yêu cầu');
  expect(html).not.toContain('data-testid="confirm-proposal"');
  expect(html).not.toContain('type="radio"');
  expect(html).not.toContain('type="checkbox"');
});
it('prioritizes the accepted allocation over the number of proposals', () => {
  const html = renderToStaticMarkup(<PortfolioOverview portfolio={portfolio} dashboard={{ portfolio, accepted_target: { id: 't', recommendation_id: 'a', accepted_at: '2026-11-05T00:00:00Z', portfolio_version: 1, allocation: a }, proposal_count: 9281, target_matches_portfolio: true }}/>);
  expect(html).toContain('Mục tiêu đã chấp nhận');
  expect(html).not.toContain('9281');
  expect(html).toContain('chưa theo dõi');
});
it('does not assign a risk profile to a legacy portfolio without confirmed answers', () => {
  const html = renderToStaticMarkup(<PortfolioOverview portfolio={{ ...portfolio, risk_profile: null }} dashboard={null}/>);
  expect(html).toContain('Chưa xác nhận');
  expect(html).not.toContain('Hồ sơ đã được xác nhận');
  expect(html).toContain('#risk-assessment?portfolio=p');
});

it('routes a paused empty plan to its own chat and a paused plan with proposals to its history', () => {
  const dashboard = { portfolio, accepted_target: null, proposal_count: 0, target_matches_portfolio: false };
  for (const proposal_count of [0, 2]) {
    const html = renderToStaticMarkup(<PausedProposal portfolio={portfolio} dashboard={{ ...dashboard, proposal_count }}/>);
    const primary = html.split('<aside class="plan-status"')[1].split('</aside>')[0];
    expect(primary).toContain('Tạm dừng tạo đề xuất');
    expect(primary).toContain(proposal_count ? '#proposal?focus=history&amp;portfolio=p' : '#chat?portfolio=p');
    expect(html).toContain('id="methodology"');
    expect(html).not.toContain('data-testid="confirm-proposal"');
  }
});

it('keeps expiry and permission to calculate separate from permission to accept a current proposal', () => {
  const props = { portfolio, recommendation: { ...a, valid_until: '2020-01-01' }, accepted: false, conflict: false, busy: false, onAccept: () => {}, viewerBase: null };
  const ready = { readiness_kind: 'user-selection-v1' as const, candidate_asset_ids: ['VFF', 'FPT'], can_submit: true, reason_code: 'READY', selection_valid_until: '2099-01-01', strategies: [{ strategy: 'HYBRID', can_submit: true, reason_code: 'READY' }], asset_status: [] };
  const paused = { ...ready, can_submit: false, reason_code: 'SYSTEM_PAUSED', strategies: [] };
  const locked = renderToStaticMarkup(<ProposalReview {...props} stale readiness={paused}/>);
  expect(locked).toContain('Hết hạn · Tính mới tạm dừng');
  expect(locked).not.toContain('focus=request');
  expect(locked).toContain('focus=history');
  const expired = renderToStaticMarkup(<ProposalReview {...props} stale readiness={ready}/>);
  expect(expired).toContain('Xem lại đầu vào');
  expect(expired).toContain('focus=request');
  expect(expired).not.toContain('data-testid="confirm-proposal"');
  const current = renderToStaticMarkup(<ProposalReview {...props} recommendation={{ ...a, valid_until: '2099-01-01' }} stale={false} readiness={paused}/>);
  expect(current).toContain('Chấp nhận làm mục tiêu');
  expect(current).not.toContain('disabled=""');
});

it('keeps the paused history action and saved allocation together after capital changes', () => {
  const html = renderToStaticMarkup(<PortfolioOverview portfolio={{ ...portfolio, capital_vnd: '120000000' }}
    dashboard={{ portfolio, accepted_target: { id: 't', recommendation_id: a.id, accepted_at: '2026-11-05', portfolio_version: 1, allocation: a }, proposal_count: 1, target_matches_portfolio: false }}
    readiness={{ readiness_kind: 'user-selection-v1', candidate_asset_ids: a.asset_ids, can_submit: false, reason_code: 'SYSTEM_PAUSED', strategies: [], asset_status: [] }}/>);
  expect(html.match(/class="plan-status"/g)).toHaveLength(1);
  expect(html).toContain('Tạm dừng tạo đề xuất');
  expect(html).toContain('Xem lịch sử đề xuất');
  expect(html).toContain('Phân bổ đã lưu');
  const primary = html.split('aria-label="Mục tiêu đã chấp nhận"')[1].split('</section>')[0];
  expect(primary).toContain('100.000.000');
  expect(primary).not.toContain('120.000.000');
  expect(html).toContain('120.000.000');
});
