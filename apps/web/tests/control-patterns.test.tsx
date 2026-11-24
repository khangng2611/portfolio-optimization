import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { IconButton } from '../src/components/action-controls';
it('gives an icon button an accessible name, tooltip and safe non-submit default', () => {
 const html=renderToStaticMarkup(<IconButton icon="refresh" label="Làm mới"/>);
 expect(html).toContain('type="button"');expect(html).toContain('aria-label="Làm mới"');expect(html).toContain('control-tooltip');expect(html).toContain('aria-hidden="true"');
});
