import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AllocationView } from '../src/components/allocation-view';

describe('allocation presentation', () => {
  it('keeps the historical table sortable and labels uncatalogued assets without guessing their class', () => {
    const allocation = { asset_ids: ['ZERO', 'SMALL', 'LARGE'], weights: ['0', '0.09', '0.6'], capital_vnd: '1000000', strategy: 'MVO' };
    const html = renderToStaticMarkup(<AllocationView allocation={allocation} metadata={false}/>);
    expect(html).not.toContain('ZERO');
    expect(html).toContain('69,0%');
    expect(html).toContain('data-asset-kind="unknown"');
    const body = html.split('<tbody>')[1].split('</tbody>')[0];
    expect(body.indexOf('LARGE')).toBeLessThan(body.indexOf('SMALL'));
    expect(html).toContain('690.000');
    expect(html).toContain('aria-sort="descending"');
    expect(html.match(/class="allocation-sort"/g)).toHaveLength(3);
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
  it('keeps the 0–100% scale and uses the actual weight for a very small bar', () => {
    const html = renderToStaticMarkup(<AllocationView presentation="chart" allocation={{ asset_ids: ['FPT', 'VCB', 'VFF'], weights: [.5, .00005, 0], capital_vnd: '1000000', strategy: 'MVO' }}/>);
    expect(html).toContain('>100%<');
    expect(html).toContain('width:50%');
    expect(html).toContain('width:0.005%');
    expect(html).toContain('&lt;0,01%');
    expect(html).not.toContain('VFF');
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
  it('keeps the demo label without exposing stored strategy codes', () => {
    const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['AAA', 'BBB'], weights: ['0.5', '0.5'], capital_vnd: '100', strategy: 'EW', requested_strategy: 'BL_ML', fallback_reason: 'MODEL_UNAVAILABLE', demo: true }}/>);
    expect(html).not.toMatch(/BL \+ ML|BL_ML|→ EW/);
    expect(html).toContain('Dữ liệu minh họa');
  });
});

it('shows the assets, data availability and allocation limits without internal pins', () => {
  const html = renderToStaticMarkup(<AllocationView allocation={{ asset_ids: ['FPT', 'GOLD', 'VFF', 'VCB'], weights: [.3, .3, .4, 0], capital_vnd: '1000000', strategy: 'BL_ML', constraints: { risk_aversion: 5, max_position_weight: .5, min_defensive_weight: .15, max_non_defensive_weight: .7 }, requested_constraints: { risk_aversion: 3, max_position_weight: .5 }, inputs_provenance: { phase1_full: { active_asset_ids: ['FPT', 'GOLD', 'VFF'], selected_equity_ids: ['FPT'], selection_id: 'selection-hash', selection_epoch: '2026-11-01', fit_epoch: '2026-11-02', regime: { regime: 'crisis' }, availability: { VFF: { observation_date: '2026-11-03', age_days: 8, policy_available_at: '2026-11-11T18:00:00+07:00' } } } } }}/>);
  expect(html).toContain('Tài sản dùng trong lần tính: FPT · GOLD · VFF');
  expect(html).toContain('NAV VFF');
  expect(html).toContain('Dữ liệu chậm 8 ngày');
  expect(html).toContain('11/11/2026');
  expect(html).toContain('Nhóm phòng thủ tối thiểu 15,0%');
  expect(html).not.toContain('selection-hash');
});

it('uses the displayed record for capital, groups equal kinds, and keeps exact zero rows visible in the overview', () => {
  const assets = ['FPT', 'VCB'].map(asset_id => ({ asset_id, display_name: asset_id, kind: 'stock' as const, unit: 'VND/share', currency: 'VND', catalog_version: '1', data_status: 'FRESH' as const, ml_status: 'UNKNOWN' as const }));
  for (const [capital, amount] of [['100000000', '35.000.000'], ['120000000', '42.000.000']]) {
    const html = renderToStaticMarkup(<AllocationView assets={assets} pricePortfolioId="p" priceProposalId="r" priceReturnView="overview" presentation="summary" allocation={{ asset_ids: ['FPT', 'VCB', 'VFF'], weights: [.35, .65, 0], capital_vnd: capital, strategy: 'EW' }}/>);
    expect(html.match(/<li data-asset-kind="stock"/g)).toHaveLength(1);
    expect(html).toContain('100%');
    expect(html).toContain('asset=FPT');
    expect(html).toContain('from=overview');
    expect(html).toContain(amount);
    expect(html).toContain('VFF');
    expect(html).toContain('>0%</td>');
    expect(html).not.toContain('Xem giá VFF');
  }
});

it('keeps missing recorded amounts and weights distinct from a genuine zero', () => {
  const allocation = { asset_ids: ['FPT'], weights: [1], capital_vnd: '', strategy: 'EW' };
  const html = renderToStaticMarkup(<AllocationView allocation={allocation} presentation="summary"/>);
  expect(html).toContain('Chưa có số tiền');
  expect(html).toContain('100%');
  expect(renderToStaticMarkup(<AllocationView allocation={{ ...allocation, weights: [] }}/>)).toContain('chưa có đủ dữ liệu tỷ trọng');
});
