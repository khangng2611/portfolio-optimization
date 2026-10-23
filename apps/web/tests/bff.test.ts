import { describe, it, expect } from 'vitest';
import { createBff } from '../src/server/bff';
import { EncryptedStore } from '../src/server/store';
import { readConfig } from '../src/server/config';
import { MemoryBackend, provider, config, login, request } from './helpers';

// Each case crosses the actual BFF/session boundary. Only Redis and the IdP network are replaced.
describe('browser authentication boundary', () => {
  it('requires explicit local HTTP opt-in and refuses insecure public origins', () => {
    expect(() => readConfig({ APP_ORIGIN: 'http://example.com', ALLOW_INSECURE_HTTP: 'true' })).toThrow();
    expect(() => readConfig({ APP_ORIGIN: 'http://localhost:3000' })).toThrow();
  });
  it('encrypts tokens at rest and authenticates stored ciphertext', async () => {
    const backend = new MemoryBackend();
    const store = new EncryptedStore(backend, config.key);
    await store.put('session:test', { refreshToken: 'private-refresh' }, 60);
    const raw = backend.data.get('session:test')!.value;
    expect(raw).not.toContain('private-refresh');
    expect(await store.get('session:test')).toEqual({ refreshToken: 'private-refresh' });
    backend.data.set('session:test', { value: raw.slice(0, -3) + 'aaa', until: Infinity });
    await expect(store.get('session:test')).rejects.toThrow();
  });
  it('sets an opaque Secure HttpOnly SameSite cookie and returns only user and CSRF', async () => {
    const { bff, cookie, csrf } = await login();
    expect(cookie).toMatch(/__Host-portfolio_session=[\w-]{43}/);
    expect(cookie).toContain('HttpOnly');
    expect(cookie).toContain('Secure');
    expect(cookie).toContain('SameSite=Lax');
    const response = await bff.session(request('/auth/session', { cookie }));
    expect(response.headers.get('cache-control')).toContain('no-store');
    expect(await response.json()).toEqual({ authenticated: true, user: { sub: 'alice', name: 'Alice', roles: ['investor'] }, csrfToken: csrf });
  });
  it('rejects missing or mismatched state and consumes the transaction once', async () => {
    const backend = new MemoryBackend();
    const bff = createBff(config, new EncryptedStore(backend, config.key), provider());
    const start = await bff.login(request('/auth/login'));
    const flowCookie = start.headers.get('set-cookie')!;
    const state = new URL(start.headers.get('location')!).searchParams.get('state')!;
    expect((await bff.callback(request('/auth/callback?code=code&state=wrong', { cookie: flowCookie }))).status).toBe(400);
    expect((await bff.callback(request(`/auth/callback?code=code&state=${state}`, { cookie: flowCookie }))).status).toBe(400);
    expect((await bff.callback(request(`/auth/callback?code=code&state=${state}`))).status).toBe(400);
  });
  it('rejects a cross-origin mutation, missing CSRF, and arbitrary proxy paths', async () => {
    const { bff, cookie, csrf } = await login();
    for (const headers of [{ origin: 'https://evil.test', 'x-csrf-token': csrf }, { origin: config.origin }] as Record<string, string>[]) {
      const response = await bff.proxy(request('/api/v1/portfolios', { method: 'POST', cookie, headers, body: '{}' }));
      expect(response.status).toBe(403);
    }
    for (const path of ['/api/v1/internal/secrets', '/api/v1/portfolios/https%3A%2F%2Fevil.test', '/api/v1/portfolios?url=http://evil.test']) {
      expect((await bff.proxy(request(path, { cookie }))).status).toBe(404);
    }
  });
  it('returns forbidden for a non-ASCII CSRF value instead of treating it as dependency failure', async () => {
    const { bff, cookie, csrf } = await login();
    const response = await bff.proxy(request('/api/v1/portfolios', { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': 'é'.repeat(csrf.length) }, body: '{}' }));
    expect(response.status).toBe(403);
  });
  it('forwards only authenticated bearer and allowed headers to the fixed backend', async () => {
    let captured: Request | undefined;
    const { bff, cookie, csrf } = await login({ fetch: async (url, init) => {
      captured = new Request(url, init);
      return Response.json({ id: 'portfolio-one' }, { status: 201, headers: { 'set-cookie': 'injected=yes', location: 'https://evil.test' } });
    } });
    const response = await bff.proxy(request('/api/v1/portfolios', { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, authorization: 'Bearer attacker', 'x-user-id': 'mallory', 'content-type': 'application/json' }, body: '{"name":"Example"}' }));
    expect(response.status).toBe(201);
    expect(captured!.url).toBe('http://portfolio-api:8000/api/v1/portfolios');
    expect(captured!.headers.get('authorization')).toBe('Bearer access-alice');
    expect(captured!.headers.get('cookie')).toBeNull();
    expect(captured!.headers.get('x-user-id')).toBeNull();
    expect(response.headers.get('set-cookie')).toBeNull();
    expect(response.headers.get('location')).toBeNull();
  });
  it('preserves version preconditions and returns backend ETag without forwarding other headers', async () => {
    let captured: Request | undefined;
    const { bff, cookie, csrf } = await login({ fetch: async (url, init) => {
      captured = new Request(url, init);
      return Response.json({ version: 2 }, { headers: { ETag: '\"2\"', 'set-cookie': 'untrusted=yes', 'x-internal-key': 'private' } });
    } });
    const response = await bff.proxy(request('/api/v1/portfolios/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', { method: 'PATCH', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json', 'if-match': '\"1\"' }, body: '{"name":"Renamed"}' }));
    expect(response.status).toBe(200);
    expect(captured!.headers.get('if-match')).toBe('"1"');
    expect(response.headers.get('etag')).toBe('"2"');
    expect(response.headers.get('set-cookie')).toBeNull();
    expect(response.headers.get('x-internal-key')).toBeNull();
  });
  it('rejects redirect responses instead of forwarding credentials to another origin', async () => {
    const { bff, cookie } = await login({ fetch: async (_url, init) => {
      expect(init?.redirect).toBe('manual');
      return new Response(null, { status: 307, headers: { location: 'https://evil.test' } });
    } });
    expect((await bff.proxy(request('/api/v1/portfolios', { cookie }))).status).toBe(502);
  });
  it('serializes refresh across BFF replicas and uses the rotated token', async () => {
    let refreshes = 0;
    const oidc = provider();
    oidc.exchange = async () => ({ ...await provider().exchange(), accessExpiresAt: Date.now() + 100 });
    oidc.refresh = async () => {
      refreshes++;
      await new Promise(resolve => setTimeout(resolve, 30));
      return { ...await provider().exchange(), accessToken: 'rotated-access', refreshToken: 'rotated-refresh' };
    };
    const { bff, cookie, store } = await login({ oidc });
    const replica = createBff(config, store, oidc);
    const responses = await Promise.all([bff.session(request('/auth/session', { cookie })), replica.session(request('/auth/session', { cookie }))]);
    expect(responses.map(r => r.status)).toEqual([200, 200]);
    expect(refreshes).toBe(1);
  });
  it('deletes expired sessions and fails closed if Redis is unavailable', async () => {
    const { bff, cookie, store, backend } = await login();
    const id = cookie.match(/portfolio_session=([^;]+)/)![1];
    const session = await store.get<Record<string, unknown>>(`session:${id}`);
    await store.put(`session:${id}`, { ...session, expiresAt: Date.now() - 1 }, 60);
    expect((await bff.session(request('/auth/session', { cookie }))).status).toBe(401);
    backend.get = async () => { throw new Error('Redis unavailable'); };
    expect((await bff.session(request('/auth/session', { cookie }))).status).toBe(503);
  });
  it('revokes on logout and prevents refresh from restoring a deleted session', async () => {
    let resolveRefresh: (value: Awaited<ReturnType<ReturnType<typeof provider>['exchange']>>) => void = () => {};
    let started: () => void = () => {};
    const ready = new Promise<void>(resolve => { started = resolve; });
    const oidc = provider();
    let revoked = false;
    oidc.revoke = async () => { revoked = true; };
    const { bff, cookie, csrf, store } = await login({ oidc });
    const id = cookie.match(/portfolio_session=([^;]+)/)![1];
    const session = await store.get<Record<string, unknown>>(`session:${id}`);
    await store.put(`session:${id}`, { ...session, accessExpiresAt: Date.now() - 1 }, 60);
    oidc.refresh = async () => { started(); return new Promise(resolve => { resolveRefresh = resolve; }); };
    const pending = bff.session(request('/auth/session', { cookie }));
    await ready;
    const result = await bff.logout(request('/auth/logout', { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf } }));
    resolveRefresh(await provider().exchange());
    expect((await pending).status).toBe(401);
    expect(result.status).toBe(200);
    expect(result.headers.get('set-cookie')).toContain('Max-Age=0');
    expect(revoked).toBe(true);
    expect(await store.get(`session:${id}`)).toBeNull();
  });
});
