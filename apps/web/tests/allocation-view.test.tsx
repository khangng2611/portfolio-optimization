import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { AllocationView } from '../src/components/allocation-view';

describe('allocation presentation', () => {
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
