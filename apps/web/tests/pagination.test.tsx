import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Pagination } from '../src/components/portfolio-lifecycle';
it('does not offer disabled page navigation for an empty or single-page result', () => {
  expect(renderToStaticMarkup(<Pagination total={0} offset={0} onChange={() => {}}/>)).toBe('');
  const html = renderToStaticMarkup(<Pagination total={2} offset={0} onChange={() => {}}/>);
  expect(html).toContain('2 kết quả');
  expect(html).not.toContain('<button');
});
it('preserves navigation back from an offset even when the result count shrinks', () => {
  const html = renderToStaticMarkup(<Pagination total={0} offset={10} onChange={() => {}}/>);
  expect(html).toContain('Trang trước');
  expect(html).not.toMatch(/<button[^>]*disabled=""[^>]*>Trang trước/);
});
