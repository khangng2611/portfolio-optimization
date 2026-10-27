import { beforeEach, expect, it } from 'vitest';
import { readConfig } from '../src/server/config';
import { config, login, provider, request } from './helpers';
const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const identity = (roles: string[]) => {
  const p = provider();
  return { ...p, exchange: async () => ({ ...await p.exchange(), user: { sub: roles.join('-'), name: 'Operator', roles } }) };
};
beforeEach(() => {
  config.marketUrl = 'http://market-api:8000';
  config.quantUrl = 'http://quant-api:8000';
  config.mlUrl = 'http://ml-api:8000';
});
const writes: [string, string, string[]][] = [
  ['/api/v1/market/refresh-schedules', 'POST', ['data-operator']],
  [`/api/v1/market/refresh-schedules/${id}`, 'PATCH', ['data-operator']],
  ['/api/v1/market/refresh-jobs', 'POST', ['data-operator']],
  ['/api/v1/ml/training-jobs', 'POST', ['data-operator']],
  [`/api/v1/ml/models/${id}/reviews`, 'POST', ['model-reviewer']],
  [`/api/v1/portfolios/${id}/risk-assessments`, 'POST', ['investor']],
];
it.each(writes)('requires a durable idempotency key for %s %s', async (path, method, roles) => {
  let calls = 0;
  const { bff, cookie, csrf } = await login({ oidc: identity(roles), fetch: async () => { calls++; return Response.json({}); } });
  const response = await bff.proxy(request(path, { method, cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json' }, body: '{}' }));
  expect(response.status).toBe(400);
  expect(calls).toBe(0);
});
it.each(writes)('forwards authenticated %s %s to its fixed owner with optimistic preconditions', async (path, method, roles) => {
  let captured: Request | undefined;
  const { bff, cookie, csrf } = await login({ oidc: identity(roles), fetch: async (url, init) => {
    captured = new Request(url, init);
    expect(init?.redirect).toBe('manual');
    return Response.json({ version: 2 }, { headers: { etag: '"2"' } });
  } });
  const response = await bff.proxy(request(path, { method, cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json', 'idempotency-key': 'p1-receipt-123', 'if-match': '"1"', authorization: 'Bearer attacker' }, body: '{"decision":"APPROVED"}' }));
  expect(response.status).toBe(200);
  const owner = path.startsWith('/api/v1/market') ? config.marketUrl : path.startsWith('/api/v1/ml') ? config.mlUrl : config.portfolioUrl;
  expect(captured!.url).toBe(owner + path);
  expect(captured!.headers.get('authorization')).toBe('Bearer access-alice');
  expect(captured!.headers.get('if-match')).toBe('"1"');
  expect(captured!.headers.get('idempotency-key')).toBe('p1-receipt-123');
  expect(response.headers.get('etag')).toBe('"2"');
});
it('allows risk preview with CSRF and no mutation receipt while rejecting missing CSRF', async () => {
  let calls = 0;
  const { bff, cookie, csrf } = await login({ fetch: async () => { calls++; return Response.json({ risk_profile: 'balanced' }); } });
  const path = `/api/v1/portfolios/${id}/risk-assessments/preview`;
  expect((await bff.proxy(request(path, { method: 'POST', cookie, headers: { origin: config.origin, 'content-type': 'application/json' }, body: '{}' }))).status).toBe(403);
  expect((await bff.proxy(request(path, { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json' }, body: '{}' }))).status).toBe(200);
  expect(calls).toBe(1);
});
it('gates operator/reviewer routes before upstream calls', async () => {
  const blocked: [string[], string, string][] = [
    [['investor'], '/api/v1/ml/models', 'GET'],
    [['investor'], '/api/v1/market/refresh-jobs', 'GET'],
    [['model-reviewer'], '/api/v1/market/refresh-schedules', 'GET'],
    [['model-reviewer'], '/api/v1/market/publications', 'GET'],
    [['model-reviewer'], '/api/v1/ml/training-jobs', 'POST'],
    [['data-operator'], `/api/v1/ml/models/${id}/reviews`, 'POST'],
  ];
  let calls = 0;
  for (const [roles, path, method] of blocked) {
    const { bff, cookie, csrf } = await login({ oidc: identity(roles), fetch: async () => { calls++; return Response.json([]); } });
    expect((await bff.proxy(request(path, { method, cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json', 'idempotency-key': 'p1-receipt-123' }, body: method === 'GET' ? undefined : '{}' }))).status).toBe(403);
  }
  expect(calls).toBe(0);
});
it('forwards bounded reads and exact ML status/snapshot filters for both reviewer and operator', async () => {
  const seen: string[] = [];
  const { bff, cookie } = await login({ oidc: identity(['data-operator', 'model-reviewer']), fetch: async url => { seen.push(String(url)); return Response.json([], { headers: { 'x-total-count': '4', 'x-limit': '20', 'x-offset': '0' } }); } });
  const paths = [
    '/api/v1/market/refresh-schedules?limit=20&offset=0', `/api/v1/market/refresh-schedules/${id}`,
    '/api/v1/market/refresh-jobs?limit=20&offset=0', `/api/v1/market/refresh-jobs/${id}`,
    `/api/v1/ml/training-jobs?limit=20&offset=0&status=SUCCEEDED&snapshot_id=${id}`, `/api/v1/ml/training-jobs/${id}`,
    '/api/v1/ml/models?limit=20&status=CANDIDATE', `/api/v1/ml/models/${id}`,
    `/api/v1/portfolios/${id}/risk-assessments?limit=20&offset=0`,
  ];
  for (const path of paths) {
    const response = await bff.proxy(request(path, { cookie }));
    expect(response.status, path).toBe(200);
    expect(response.headers.get('x-total-count')).toBe('4');
    expect(response.headers.get('cache-control')).toBe('no-store');
  }
  expect(seen).toEqual(paths.map(path => (path.startsWith('/api/v1/market') ? config.marketUrl : path.startsWith('/api/v1/ml') ? config.mlUrl : config.portfolioUrl) + path));
  const reviewer = await login({ oidc: identity(['model-reviewer']), fetch: async () => Response.json([]) });
  expect((await reviewer.bff.proxy(request('/api/v1/ml/models?status=APPROVED', { cookie: reviewer.cookie }))).status).toBe(200);
});
it('rejects ambiguous, unsupported, invalid or internal routes without backend calls', async () => {
  let calls = 0;
  const { bff, cookie } = await login({ oidc: identity(['data-operator']), fetch: async () => { calls++; return Response.json([]); } });
  for (const path of [
    '/api/v1/ml/models?limit=0', '/api/v1/ml/models?limit=101', '/api/v1/ml/models?limit=2&limit=3',
    '/api/v1/ml/models?status=RUNNING', '/api/v1/ml/training-jobs?status=APPROVED',
    '/api/v1/ml/training-jobs?snapshot_id=latest', '/api/v1/market/refresh-jobs?offset=-1',
    '/api/v1/ml/models?url=https://evil.test', '/api/v1/ml/models/not-a-uuid',
    `/internal/v1/ml/models/${id}/manifest`, '/api/v1/ml/models/../../internal/secrets',
  ]) expect([400,404]).toContain((await bff.proxy(request(path, { cookie }))).status);
  expect(calls).toBe(0);
});
it('fails closed if optional ML origin is unavailable and refuses backend redirects', async () => {
  delete config.mlUrl;
  let calls = 0;
  const { bff, cookie } = await login({ oidc: identity(['model-reviewer']), fetch: async () => { calls++; return Response.json([]); } });
  expect((await bff.proxy(request('/api/v1/ml/models', { cookie }))).status).toBe(503);
  expect(calls).toBe(0);
  config.mlUrl = 'http://ml-api:8000';
  const redirect = await login({ oidc: identity(['model-reviewer']), fetch: async () => new Response(null, { status:307, headers:{ location:'https://evil.test' } }) });
  expect((await redirect.bff.proxy(request('/api/v1/ml/models', { cookie: redirect.cookie }))).status).toBe(502);
});
it('validates optional ML origin just like other service origins', () => {
  const env = { APP_ORIGIN: 'https://app.test', OIDC_ISSUER: 'https://identity.test/realm', PORTFOLIO_API_URL: 'https://portfolio.test', OIDC_CLIENT_SECRET: 'secret', REDIS_URL: 'redis://redis', SESSION_ENCRYPTION_KEY: Buffer.alloc(32,7).toString('base64') };
  expect(readConfig({ ...env, ML_API_URL:'https://ml.test' }).mlUrl).toBe('https://ml.test');
  for (const value of ['https://ml.test/path', 'https://user:password@ml.test', 'https://ml.test?x=1', 'https://ml.test#fragment', 'file:///private/ml']) expect(() => readConfig({ ...env, ML_API_URL:value })).toThrow();
});
