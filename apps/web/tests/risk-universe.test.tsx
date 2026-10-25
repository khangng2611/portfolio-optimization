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
  expect(html).toContain('giá thật');
  expect(html).toContain('minh họa');
  expect(html).toMatch(/<option[^>]*value="REAL_STOCKS"[^>]*selected=""/);
});
