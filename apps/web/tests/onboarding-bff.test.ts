import { describe, expect, it } from 'vitest';
import { login, request, config } from './helpers';

const pid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const rid = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
describe('G2 authenticated routes', () => {
  it('proxies onboarding, dashboard and targets through the existing identity boundary', async () => {
    const seen: string[] = [];
    const { bff, cookie, csrf } = await login({ fetch: async (url, init) => {
      seen.push(String(url));
      expect(new Headers(init?.headers).get('authorization')).toBe('Bearer access-alice');
      return Response.json({ ok: true });
    } });
    const headers = { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json' };
    expect((await bff.proxy(request('/api/v1/universes', { cookie }))).status).toBe(200);
    expect((await bff.proxy(request('/api/v1/onboarding/portfolios', { method: 'POST', cookie, headers, body: '{}' }))).status).toBe(200);
    for (const suffix of ['dashboard', 'targets']) expect((await bff.proxy(request(`/api/v1/portfolios/${pid}/${suffix}`, { cookie }))).status).toBe(200);
    expect(seen).toHaveLength(4);
  });
  it('requires CSRF for accept and preserves If-Match without widening proxy access', async () => {
    let captured: Request | undefined;
    const { bff, cookie, csrf } = await login({ fetch: async (url, init) => {
      captured = new Request(url, init);
      return Response.json({ portfolio_version: 2 }, { headers: { etag: '"2"' } });
    } });
    const path = `/api/v1/recommendations/${rid}/accept`;
    expect((await bff.proxy(request(path, { method: 'POST', cookie, body: '{}' }))).status).toBe(403);
    const response = await bff.proxy(request(path, { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json', 'if-match': '"1"' }, body: '{}' }));
    expect(response.status).toBe(200);
    expect(captured?.headers.get('if-match')).toBe('"1"');
    expect(response.headers.get('etag')).toBe('"2"');
    expect((await bff.proxy(request(path.replace('/accept', '/execute'), { method: 'POST', cookie, body: '{}' }))).status).toBe(404);
  });
});

it('proxies catalog and guarded selection revisions through Portfolio only', async () => {
  let captured: Request | undefined;
  const { bff, cookie, csrf } = await login({ fetch: async (url, init) => { captured = new Request(url, init); return Response.json({ ok: true }); } });
  expect((await bff.proxy(request('/api/v1/assets/catalog', { cookie }))).status).toBe(200);
  const path = `/api/v1/portfolios/${pid}/asset-selections`;
  expect((await bff.proxy(request(path, { cookie }))).status).toBe(200);
  const headers = { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json', 'idempotency-key': 'selection-revision-1' };
  expect((await bff.proxy(request(path, { method: 'POST', cookie, headers, body: '{}' }))).status).toBe(428);
  expect((await bff.proxy(request(path, { method: 'POST', cookie, headers: { ...headers, 'if-match': '"3"' }, body: '{"candidate_asset_ids":["FPT"]}' }))).status).toBe(200);
  expect(captured?.url).toBe('http://portfolio-api:8000' + path);
  expect(captured?.headers.get('if-match')).toBe('"3"');
  expect(captured?.headers.get('idempotency-key')).toBe('selection-revision-1');
});
