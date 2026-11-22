import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AllocationView } from '../src/components/allocation-view';

describe('allocation presentation', () => {
  it('hides exact zero weights in the table, chart and compact legend without changing totals or colors', () => {
    const allocation = { asset_ids: ['ZERO', 'SMALL', 'LARGE'], weights: ['0', '0.09', '0.6'], capital_vnd: '1000000', strategy: 'MVO' };
    for (const compact of [false, true]) {
      const html = renderToStaticMarkup(<AllocationView allocation={allocation} compact={compact} metadata={false}/>);
      expect(html).not.toContain('ZERO');
      expect(html).toContain('69,0%');
      expect(html).toContain('var(--chart-2)');
      expect(html).toContain('var(--chart-3)');
      if (!compact) {
        const body = html.split('<tbody>')[1].split('</tbody>')[0];
        expect(body.indexOf('LARGE')).toBeLessThan(body.indexOf('SMALL'));
        expect(html).toContain('690.000');
        expect(html).toContain('aria-sort="descending"');
        expect(html.match(/class="allocation-sort"/g)).toHaveLength(3);
      }
    }
  });

  it('shows an empty allocation message when every weight is zero', () => {
    const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['ZERO'], weights: [0], capital_vnd: '100', strategy: 'EW' }}/>);
    expect(html).not.toContain('ZERO');
    expect(html).toContain('Chưa có tài sản được phân bổ.');
    expect(html).toContain('0,0%');
  });
  it('derives the chart total from API weights instead of assuming a complete allocation', () => {
    const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['FPT', 'VCB'], weights: ['0.2', '0.3'], capital_vnd: '1000000', strategy: 'MVO' }}/>);
    expect(html).toContain('50,0%');
    expect(html).toContain('Tổng tỷ trọng');
    expect(html).toContain('500.000');
  });
  it('distinguishes attested real snapshot provenance from an unspecified non-demo bundle', () => {
    const base = { asset_ids: ['FPT', 'VCB'], weights: ['0.5', '0.5'], capital_vnd: '100', strategy: 'MVO', demo: false };
    expect(renderToStaticMarkup(<AllocationView allocation={base}/>)).not.toContain('Giá thị trường');
    expect(renderToStaticMarkup(<AllocationView allocation={{ ...base, inputs_provenance: { data_origin: 'real' } }}/>)).toContain('Giá thị trường');
  });
  it('maps decimal weights to the ordered asset IDs and planned capital without claiming holdings', () => {
    const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['AAA', 'BBB'], weights: ['0.6', '0.4'], capital_vnd: '1000000', strategy: 'MVO' }}/>);
    expect(html).toContain('AAA');
    expect(html).toContain('60,0%');
    expect(html).toContain('600.000');
    expect(html).toContain('Vốn mục tiêu');
    expect(html).not.toContain('NAV');
  });
  it('shows the explicit effective fallback strategy and demo label', () => {
    const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['AAA', 'BBB'], weights: ['0.5', '0.5'], capital_vnd: '100', strategy: 'EW', requested_strategy: 'BL_ML', fallback_reason: 'MODEL_UNAVAILABLE', demo: true }}/>);
    expect(html).toContain('BL + ML → EW');
    expect(html).toContain('chưa có model ML được duyệt');
    expect(html).toContain('Dữ liệu minh họa');
  });
});

it('discloses full-universe active assets, availability and effective risk against profile', () => {
  const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['FPT', 'GOLD', 'VFF', 'VCB'], weights: [.3, .3, .4, 0], capital_vnd: '1000000', strategy: 'BL_ML', constraints: { risk_aversion: 5, max_position_weight: .5, min_defensive_weight: .15, max_non_defensive_weight: .7 }, requested_constraints: { risk_aversion: 3, max_position_weight: .5 }, inputs_provenance: { phase1_full: { active_asset_ids: ['FPT', 'GOLD', 'VFF'], selected_equity_ids: ['FPT'], selection_id: 'selection-hash', selection_epoch: '2026-11-01', fit_epoch: '2026-11-02', regime: { regime: 'crisis' }, availability: { VFF: { observation_date: '2026-11-03', age_days: 8, policy_available_at: '2026-11-11T18:00:00+07:00' } } } } }}/>);
  expect(html).toContain('Tài sản ngoài K5 có tỷ trọng 0%');
  expect(html).toContain('NAV VFF');
  expect(html).toContain('tuổi 8 ngày');
  expect(html).toContain('khả dụng từ 2026-11-11');
  expect(html).toContain('5 (hồ sơ: 3)');
  expect(html).toContain('selection-hash');
});
