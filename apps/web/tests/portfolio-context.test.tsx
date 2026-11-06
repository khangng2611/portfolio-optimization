import { expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PortfolioList } from '../src/components/portfolio-lifecycle';
import type { PageApi } from '../src/lib/portfolio-types';
const fetchPage: PageApi = async () => ({ items: [], total: 0, limit: 10, offset: 0 });
it('keeps portfolio management filters in the management view', () => {
  const html = renderToStaticMarkup(<PortfolioList fetchPage={fetchPage}/>);
  expect(html).toContain('Lọc theo hồ sơ');
  expect(html).toContain('Sắp xếp danh mục');
  expect(html).toContain('Tạo danh mục');
});
it('does not repeat management filters when another tab only needs a portfolio context', () => {
  const html = renderToStaticMarkup(<PortfolioList mode="choose" destination="proposal" fetchPage={fetchPage}/>);
  expect(html).toContain('Tìm trong danh sách');
  expect(html).not.toContain('Lọc theo hồ sơ');
  expect(html).not.toContain('Sắp xếp danh mục');
  expect(html).toContain('Quản lý danh mục');
});
