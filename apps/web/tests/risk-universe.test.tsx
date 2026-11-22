import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { RiskWizard } from '../src/components/risk-wizard';

it('offers server supplied real assets and a separately labelled demo choice', () => {
  const html=renderToStaticMarkup(<RiskWizard busy={false} onCreate={async()=>true} universes={[
    {universe_id:'REAL_STOCKS',asset_ids:['FPT','VCB','HPG'],as_of_date:'2026-10-23',demo:false,provenance:{data_origin:'real'}},
    {universe_id:'DEMO',asset_ids:['AAA','BBB','VFF'],as_of_date:'2026-10-23',demo:true},
  ]}/>);
  expect(html).toContain('name="universe"');
  expect(html).toContain('FPT, VCB, HPG');
  expect(html).toContain('giá thị trường');
  expect(html).toContain('minh họa');
  expect(html).toMatch(/<option[^>]*value="REAL_STOCKS"[^>]*selected=""/);
});

it('labels the full universe with K5 and defensive assets instead of 32 option names', () => {
  const html = renderToStaticMarkup(<RiskWizard busy={false} onCreate={async () => true} universes={[
    { universe_id: 'VN_PHASE1_FULL', asset_ids: ['FPT', 'VCB', 'GOLD', 'VFF'], as_of_date: '2026-11-11', demo: false,
      provenance: { data_origin: 'real', phase1_full: { active_asset_ids: ['FPT', 'GOLD', 'VFF'], selected_equity_ids: ['FPT'], selection_id: 'hash', selection_epoch: '2026-11-01', fit_epoch: '2026-11-02' } } },
  ]}/>);
  expect(html).toContain('K5 + GOLD + VFF (32 tài sản)');
  expect(html).toContain('K5: FPT · GOLD · VFF');
  expect(html).toContain('VFF là tài sản phòng thủ');
});

it('keeps legacy creation when the server selection gate is off', () => {
  const html = renderToStaticMarkup(<RiskWizard busy={false} onCreate={async () => true} catalog={{ catalog_version: 'supported-assets-v1', selection_enabled: false, assets: [] }} universes={[{ universe_id: 'DEMO', asset_ids: ['AAA', 'BBB'], as_of_date: '2026-11-12', demo: true }]}/>);
  expect(html).toContain('name="universe"');
  expect(html).not.toContain('Tìm tài sản');
});

it('uses the asset basket directly when selection is enabled without a redundant mode chooser', () => {
  const html = renderToStaticMarkup(<RiskWizard busy={false} onCreate={async () => true} catalog={{ catalog_version: 'supported-assets-v1', selection_enabled: true, assets: [] }} universes={[{ universe_id: 'DEMO', asset_ids: ['AAA', 'BBB'], as_of_date: '2026-11-12', demo: true }]}/>);
  expect(html).toContain('Tài sản hỗ trợ');
  expect(html).toContain('Rổ tài sản của bạn');
  expect(html).not.toContain('Cách chọn tài sản');
  expect(html).not.toContain('name="universe"');
});
