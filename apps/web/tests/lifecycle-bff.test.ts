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

it('forwards paper reads and explicit owner decisions with the session and CSRF boundary', async () => {
  const seen: { path: string; method: string; body: unknown }[] = [];
  const { bff, cookie, csrf } = await login({ fetch: async (url, init) => {
    expect(new Headers(init?.headers).get('authorization')).toBe('Bearer access-alice');
    seen.push({ path: new URL(String(url)).pathname, method: init!.method!, body: init?.body && JSON.parse(String(init.body)) });
    return Response.json({});
  } });
  const base = `/api/v1/portfolios/${pid}/paper`;
  const headers = { origin: 'https://app.test', 'x-csrf-token': csrf, 'content-type': 'application/json' };
  expect((await bff.proxy(request(base, { cookie }))).status).toBe(200);
  for (const [path, body] of [
    ['/initialize', { capital_vnd: '10000000' }], ['/preview', {}],
    ['/decisions', { preview_id: pid, action: 'CONFIRM' }], ['/reviews/2026-11-25/skip', {}],
  ] as const) {
    expect((await bff.proxy(request(base + path, { cookie, headers, method: 'POST', body: JSON.stringify(body) }))).status).toBe(200);
    expect(seen.at(-1)).toEqual({ path: base + path, method: 'POST', body });
  }
  expect((await bff.proxy(request(base + '/decisions', { cookie, method: 'POST', body: '{}' }))).status).toBe(403);
  expect((await bff.proxy(request(base + '/reviews/latest/skip', { cookie, headers, method: 'POST', body: '{}' }))).status).toBe(404);
  expect(seen).toHaveLength(5);
});
