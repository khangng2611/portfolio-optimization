import { expect, it } from 'vitest';
import { login, request } from './helpers';
const pid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
it('forwards validated list filters and pagination counts through the owner boundary', async () => {
  let seen = '';
  const { bff, cookie } = await login({ fetch: async url => {
    seen = String(url);
    return Response.json([], { headers: { 'x-total-count': '42', 'x-limit': '10', 'x-offset': '20' } });
  } });
  const response = await bff.proxy(request('/api/v1/portfolios?limit=10&offset=20&q=M%E1%BB%A5c&risk_profile=balanced&sort=name_asc', { cookie }));
  expect(response.status).toBe(200);
  expect(new URL(seen).searchParams.get('q')).toBe('Mục');
  expect(response.headers.get('x-total-count')).toBe('42');
  expect(response.headers.get('x-limit')).toBe('10');
  expect(response.headers.get('x-offset')).toBe('20');
  for (const query of ['limit=0', 'limit=101', 'offset=-1', 'sort=arbitrary', 'risk_profile=admin', 'limit=1&limit=2']) {
    expect((await bff.proxy(request('/api/v1/portfolios?' + query, { cookie }))).status).toBe(400);
  }
});
it('allows readiness reads without granting any publication mutation', async () => {
  const { bff, cookie } = await login({ fetch: async () => Response.json({ status: 'EXPIRED' }) });
  expect((await bff.proxy(request(`/api/v1/portfolios/${pid}/readiness`, { cookie }))).status).toBe(200);
  expect((await bff.proxy(request('/api/v1/universes/readiness', { cookie }))).status).toBe(200);
  expect((await bff.proxy(request('/internal/v1/publications', { cookie }))).status).toBe(404);
});
