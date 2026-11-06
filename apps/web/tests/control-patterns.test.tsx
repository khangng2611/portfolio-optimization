import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { IconButton } from '../src/components/action-controls';
import { ChatOptions } from '../src/components/chat-workspace';
it('gives an icon button an accessible name, tooltip and safe non-submit default', () => {
 const html=renderToStaticMarkup(<IconButton icon="refresh" label="Làm mới"/>);
 expect(html).toContain('type="button"');expect(html).toContain('aria-label="Làm mới"');expect(html).toContain('control-tooltip');expect(html).toContain('aria-hidden="true"');
});
it('keeps automatic chat choices explicit without inventing a strategy', () => {
 const html=renderToStaticMarkup(<ChatOptions intent="" strategy="" disabled={false} onIntent={()=>{}} onStrategy={()=>{}}/>);
 expect((html.match(/checked=""/g)??[]).length).toBe(2);expect(html).toContain('Tự động');expect(html).toContain('BL + ML');expect(html).not.toContain('<select');
});
it('preserves named choices and disabled state while a request is in flight', () => {
 const html=renderToStaticMarkup(<ChatOptions intent="explain" strategy="BL_ML" disabled onIntent={()=>{}} onStrategy={()=>{}}/>);
 expect(html).toMatch(/<input(?=[^>]*value="explain")(?=[^>]*checked="")[^>]*>/);expect(html).toMatch(/<input(?=[^>]*value="BL_ML")(?=[^>]*checked="")[^>]*>/);expect(html).toContain('disabled=""');
});
