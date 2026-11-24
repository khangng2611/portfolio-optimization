import { expect, it } from 'vitest';
import { login, request, config, provider } from './helpers';
const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
it('allows authenticated investors to read only the fixed Market metadata endpoint', async () => {
  const seen: string[] = [];
  config.marketUrl = 'http://market-api:8000';
  const { bff, cookie } = await login({ fetch: async url => { seen.push(String(url)); return Response.json([]); } });
  expect((await bff.proxy(request('/api/v1/market/assets', { cookie }))).status).toBe(200);
  expect(seen).toEqual(['http://market-api:8000/api/v1/market/assets']);
  expect((await bff.proxy(request('/api/v1/market/assets?source=http://evil.test', { cookie }))).status).toBe(404);
  expect((await bff.proxy(request('/api/v1/market/assets', { method: 'POST', cookie }))).status).toBe(404);
  expect((await bff.proxy(request('/api/v1/market/assets'))).status).toBe(401);
});
const operator = () => { const p = provider(); return { ...p, login: async () => ({ ...await p.login(), user: { sub: 'operator', name: 'Operator', roles: ['data-operator'] } }) }; };
it('blocks investors from operator reads and writes before contacting a backend', async () => {
  let calls = 0;
  const { bff, cookie, csrf } = await login({ fetch: async () => { calls++; return Response.json([]); } });
  expect((await bff.proxy(request('/api/v1/market/datasets', { cookie }))).status).toBe(403);
  expect((await bff.proxy(request('/api/v1/market/publications', { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json' }, body: '{}' }))).status).toBe(403);
  expect(calls).toBe(0);
});
it('routes fixed operator endpoints to their owning service with CSRF and bounded query validation', async () => {
  const seen: string[] = [];
  config.marketUrl = 'http://market-api:8000'; config.quantUrl = 'http://quant-api:8000';
  const { bff, cookie, csrf } = await login({ identity: operator(), fetch: async url => { seen.push(String(url)); return Response.json([], { headers: { 'x-total-count': '4' } }); } });
  expect((await bff.proxy(request('/api/v1/market/datasets?limit=20&offset=0', { cookie }))).status).toBe(200);
  expect((await bff.proxy(request(`/api/v1/market/ingestions/${id}/quality`, { cookie }))).status).toBe(200);
  expect((await bff.proxy(request('/api/v1/market/publications', { cookie }))).status).toBe(200);
  expect(seen[0]).toBe('http://market-api:8000/api/v1/market/datasets?limit=20&offset=0');
  expect(seen[2]).toBe('http://quant-api:8000/api/v1/market/publications');
  expect((await bff.proxy(request('/api/v1/market/datasets?url=http://evil.test', { cookie }))).status).toBe(404);
  expect((await bff.proxy(request('/api/v1/market/ingestions', { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json' }, body: '{}' }))).status).toBe(400);
  expect((await bff.proxy(request('/api/v1/market/snapshots', { method: 'POST', cookie, headers: { 'content-type': 'application/json' }, body: '{}' }))).status).toBe(403);
});

it('forwards a bounded investor price series read and restricts raw prices to operators', async () => {
  config.marketUrl = 'http://market-api:8000';
  const received: string[] = [];
  const { bff, cookie } = await login({ fetch: async url => { received.push(String(url)); return Response.json({ series: [] }); } });
  const query = '?asset_id=FPT&start_date=2026-11-01&end_date=2026-11-22';
  expect((await bff.proxy(request('/api/v1/market/price-series' + query, { cookie }))).status).toBe(200);
  expect(received).toEqual(['http://market-api:8000/api/v1/market/price-series' + query]);
  expect((await bff.proxy(request('/api/v1/market/price-series' + query + '&asset_id=VFF', { cookie }))).status).toBe(400);
  expect((await bff.proxy(request('/api/v1/market/prices' + query, { cookie }))).status).toBe(403);
});

it('keeps knowledge lifecycle under the operator role, CSRF, version and idempotency gates', async () => {
  config.knowledgeUrl = 'http://knowledge-api:8000';
  const path = `/api/v1/knowledge/corpora/${id}/activate`;
  const investor = await login();
  expect((await investor.bff.proxy(request('/api/v1/knowledge/corpora', { cookie: investor.cookie }))).status).toBe(403);
  const seen: string[] = [];
  const { bff, cookie, csrf } = await login({ identity: operator(), fetch: async (url, init) => {
    const h = new Headers(init?.headers);
    seen.push(`${url} ${h.get('if-match')} ${h.get('idempotency-key')}`);
    return Response.json({ active: true });
  } });
  const options = { method: 'POST', cookie, body: '{ "reason": "verified corpus" }' };
  const headers = { origin: config.origin, 'content-type': 'application/json', 'x-csrf-token': csrf };
  expect((await bff.proxy(request(path, options))).status).toBe(403);
  expect((await bff.proxy(request(path, { ...options, headers }))).status).toBe(428);
  expect((await bff.proxy(request(path, { ...options, headers: { ...headers, 'if-match': '"5"' } }))).status).toBe(400);
  expect((await bff.proxy(request(path, { ...options, headers: { ...headers, 'if-match': '"5"', 'idempotency-key': 'activate-fixture' } }))).status).toBe(200);
  expect(seen).toEqual([`http://knowledge-api:8000${path} "5" activate-fixture`]);
});
