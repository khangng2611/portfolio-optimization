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
    expect(html.indexOf('FPT')).toBeLessThan(html.indexOf('VCB'));
    expect(html.indexOf('VCB')).toBeLessThan(html.indexOf('MWG'));
    expect(html).toContain('20.000.000');
  });
  it('puts allocations before expandable pins and links to each canonical proposal', () => {
    const html = renderToStaticMarkup(<ComparisonTable items={[a, b]}/>);
    expect(html.indexOf('FPT')).toBeLessThan(html.lastIndexOf('Snapshot dữ liệu'));
    expect(html).toContain('<details');
    expect(html).toContain('khác cơ sở đầu vào');
    expect(html).toContain('#proposal?portfolio=p&amp;proposal=a');
    expect(html).toContain('#proposal?portfolio=p&amp;proposal=b');
    expect(html).not.toContain('tốt nhất');
  });
});

// State-gated decisions must remain separate even when layout changes.
import { ProposalReview, ProposalRequest, PortfolioOverview } from '../src/components/portfolio-workspace';
import type { Portfolio } from '../src/lib/portfolio-types';
const portfolio: Portfolio = { id: 'p', name: 'Kế hoạch', capital_vnd: '100000000', universe_id: 'VN', version: 1, constraints: { risk_aversion: 3, max_position_weight: .5 }, risk_profile: { profile: 'balanced' }, policy_version_id: 'v1' };
it('never offers an enabled accept for a stale proposal', () => {
  const html = renderToStaticMarkup(<ProposalReview portfolio={portfolio} recommendation={a} accepted={false} stale conflict={false} busy={false} onAccept={() => {}} viewerBase={null}/>);
  expect(html).toMatch(/data-testid="accept-proposal" disabled=""/);
  expect(html).toContain('Cần tính lại');
});
it('starts with input review, not a mutation confirmation or a preaccepted target', () => {
  const html = renderToStaticMarkup(<ProposalRequest portfolio={portfolio} readiness={null} strategy="MVO" fallback={false} busy={false} onStrategy={() => {}} onFallback={() => {}} onSubmit={() => {}}/>);
  expect(html).toContain('Xem lại yêu cầu');
  expect(html).not.toContain('data-testid="confirm-proposal"');
  expect(html).toContain('EW');
  expect(html).toContain('BL + ML');
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
