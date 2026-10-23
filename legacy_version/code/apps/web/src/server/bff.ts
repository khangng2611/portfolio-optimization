import { randomBytes, timingSafeEqual } from 'node:crypto';
import type { Config } from './config';
import { EncryptedStore } from './store';
import type { Flow, IdentityProvider, Tokens } from './oidc';
interface Session extends Tokens { csrfToken: string; expiresAt: number }
class HttpError extends Error { constructor(public status: number, message: string) { super(message); } }
const opaque = () => randomBytes(32).toString('base64url');
const equal = (a: string, b: string) => { const left = Buffer.from(a); const right = Buffer.from(b); return left.length === right.length && timingSafeEqual(left, right); };
const json = (value: unknown, status = 200) => Response.json(value, { status, headers: { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', 'referrer-policy': 'no-referrer' } });
const uuid = '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';
const routes = [
  { path: /^\/api\/v1\/portfolios$/, methods: ['GET', 'POST'], query: ['limit', 'offset'] },
  { path: new RegExp(`^/api/v1/portfolios/${uuid}$`), methods: ['GET', 'PATCH'], query: [] },
  { path: new RegExp(`^/api/v1/portfolios/${uuid}/recommendations$`), methods: ['GET', 'POST'], query: ['limit', 'offset'] },
  { path: new RegExp(`^/api/v1/recommendations/${uuid}$`), methods: ['GET'], query: [] },
  { path: new RegExp(`^/api/v1/jobs/portfolio/${uuid}$`), methods: ['GET'], query: [] },
];
async function readBounded(request: Request, max: number) {
  if (Number(request.headers.get('content-length') ?? 0) > max) throw new HttpError(413, 'Request too large');
  if (!request.body) return '';
  const reader = request.body.getReader();
  let size = 0;
  const parts: Uint8Array[] = [];
  try { while (true) { const { value, done } = await reader.read(); if (done) break; size += value.length; if (size > max) throw new HttpError(413, 'Request too large'); parts.push(value); } }
  finally { await reader.cancel(); }
  return Buffer.concat(parts).toString('utf8');
}
export function createBff(config: Config, store: EncryptedStore, identity: IdentityProvider, fetcher: typeof fetch = fetch) {
  const prefix = config.secureCookies ? '__Host-' : '';
  const sessionName = `${prefix}portfolio_session`;
  const flowName = `${prefix}portfolio_login`;
  const cookie = (name: string, value: string, seconds: number) => `${name}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${seconds}${config.secureCookies ? '; Secure' : ''}`;
  function cookieValue(request: Request, name: string) {
    const found = (request.headers.get('cookie') ?? '').split(';').map(part => part.trim()).filter(part => part.startsWith(`${name}=`));
    if (found.length !== 1) return null;
    const value = found[0].slice(name.length + 1);
    return /^[A-Za-z0-9_-]{43}$/.test(value) ? value : null;
  }
  function mutation(request: Request, session: Session) {
    const token = request.headers.get('x-csrf-token') ?? '';
    if (request.headers.get('origin') !== config.origin || !equal(token, session.csrfToken)) throw new HttpError(403, 'Origin or CSRF validation failed');
  }
  async function load(request: Request) {
    const id = cookieValue(request, sessionName);
    if (!id) throw new HttpError(401, 'Authentication required');
    const session = await store.get<Session>(`session:${id}`);
    if (!session) throw new HttpError(401, 'Authentication required');
    if (session.expiresAt <= Date.now()) { await store.del(`session:${id}`); throw new HttpError(401, 'Session expired'); }
    return { id, session };
  }
  async function fresh(id: string, initial: Session): Promise<Session> {
    if (initial.accessExpiresAt > Date.now() + 30_000) return initial;
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      const owner = opaque();
      if (await store.lock(id, owner)) {
        try {
          const latest = await store.get<Session>(`session:${id}`);
          if (!latest || latest.expiresAt <= Date.now()) throw new HttpError(401, 'Session expired');
          if (latest.accessExpiresAt > Date.now() + 30_000) return latest;
          let tokens: Tokens;
          try { tokens = await identity.refresh(latest.refreshToken, latest.user.sub); }
          catch { await store.del(`session:${id}`); throw new HttpError(401, 'Please sign in again'); }
          const next: Session = { ...latest, ...tokens };
          const remaining = Math.floor((latest.expiresAt - Date.now()) / 1000);
          if (remaining <= 0 || !await store.saveRefreshed(id, next, remaining, owner)) {
            await identity.revoke(tokens.refreshToken).catch(() => {});
            throw new HttpError(401, 'Session expired');
          }
          return next;
        } finally { await store.unlock(id, owner); }
      }
      await new Promise(resolve => setTimeout(resolve, 50));
      const latest = await store.get<Session>(`session:${id}`);
      if (!latest || latest.expiresAt <= Date.now()) throw new HttpError(401, 'Session expired');
      if (latest.accessExpiresAt > Date.now() + 30_000) return latest;
    }
    throw new HttpError(503, 'Session refresh busy');
  }
  function guarded(handler: (request: Request) => Promise<Response>) {
    return async (request: Request) => {
      try { return await handler(request); }
      catch (error) { return error instanceof HttpError ? json({ error: error.message }, error.status) : json({ error: 'Authentication service unavailable' }, 503); }
    };
  }
  return {
    login: guarded(async () => {
      const id = opaque();
      const flow: Flow = { state: opaque(), nonce: opaque(), verifier: opaque(), expiresAt: Date.now() + 300_000 };
      const url = await identity.authorize(flow);
      await store.put(`flow:${id}`, flow, 300);
      return new Response(null, { status: 302, headers: { location: url.href, 'set-cookie': cookie(flowName, id, 300), 'cache-control': 'no-store', 'referrer-policy': 'no-referrer' } });
    }),
    callback: guarded(async request => {
      const id = cookieValue(request, flowName);
      const flow = id ? await store.take<Flow>(`flow:${id}`) : null;
      const received = new URL(request.url);
      const state = received.searchParams.get('state') ?? '';
      if (!flow || flow.expiresAt <= Date.now() || !equal(state, flow.state) || received.searchParams.getAll('state').length !== 1) throw new HttpError(400, 'Invalid or expired login transaction');
      // Never derive redirect_uri from an untrusted Host/X-Forwarded-Host header.
      const callback = new URL('/auth/callback', config.origin);
      callback.search = received.search;
      let tokens: Tokens;
      try { tokens = await identity.exchange(callback, flow); }
      catch { throw new HttpError(400, 'Login could not be verified'); }
      const old = cookieValue(request, sessionName);
      if (old) await store.del(`session:${old}`);
      const next = opaque();
      const session: Session = { ...tokens, csrfToken: opaque(), expiresAt: Date.now() + config.sessionSeconds * 1000 };
      await store.put(`session:${next}`, session, config.sessionSeconds);
      const headers = new Headers({ location: config.origin + '/', 'cache-control': 'no-store', 'referrer-policy': 'no-referrer' });
      headers.append('set-cookie', cookie(flowName, '', 0));
      headers.append('set-cookie', cookie(sessionName, next, config.sessionSeconds));
      return new Response(null, { status: 303, headers });
    }),
    session: guarded(async request => {
      const { id, session } = await load(request);
      const active = await fresh(id, session);
      return json({ authenticated: true, user: active.user, csrfToken: active.csrfToken });
    }),
    logout: guarded(async request => {
      const { id, session } = await load(request);
      mutation(request, session);
      await store.del(`session:${id}`);
      let providerRevoked = true;
      try { await identity.revoke(session.refreshToken); } catch { providerRevoked = false; }
      const response = json({ loggedOut: true, providerRevoked });
      response.headers.append('set-cookie', cookie(sessionName, '', 0));
      response.headers.append('set-cookie', cookie(flowName, '', 0));
      return response;
    }),
    proxy: guarded(async request => {
      const url = new URL(request.url);
      const route = routes.find(route => route.path.test(url.pathname) && route.methods.includes(request.method));
      if (!route || [...url.searchParams.keys()].some(key => !route.query.includes(key))) throw new HttpError(404, 'Route not found');
      for (const value of url.searchParams.values()) if (!/^\d{1,6}$/.test(value)) throw new HttpError(400, 'Invalid pagination');
      const { id, session } = await load(request);
      const mutates = !['GET', 'HEAD'].includes(request.method);
      if (mutates) mutation(request, session);
      const headers = new Headers({ accept: 'application/json' });
      let body: string | undefined;
      if (mutates) {
        if (request.headers.get('content-type')?.split(';')[0] !== 'application/json') throw new HttpError(415, 'JSON required');
        body = await readBounded(request, 64 * 1024);
        try { JSON.parse(body); } catch { throw new HttpError(400, 'Invalid JSON'); }
        headers.set('content-type', 'application/json');
        const precondition = request.headers.get('if-match');
        if (precondition) headers.set('if-match', precondition);
        const idempotency = request.headers.get('idempotency-key');
        if (url.pathname.endsWith('/recommendations') && !idempotency) throw new HttpError(400, 'Idempotency-Key required');
        if (idempotency) { if (!/^[A-Za-z0-9_-]{8,128}$/.test(idempotency)) throw new HttpError(400, 'Invalid Idempotency-Key'); headers.set('idempotency-key', idempotency); }
      }
      const active = await fresh(id, session);
      headers.set('authorization', `Bearer ${active.accessToken}`);
      let upstream: Response;
      try { upstream = await fetcher(config.portfolioUrl + url.pathname + url.search, { method: request.method, headers, body, redirect: 'manual', cache: 'no-store', signal: AbortSignal.timeout(10_000) }); }
      catch { throw new HttpError(502, 'Portfolio service unavailable'); }
      if (upstream.status >= 300 && upstream.status < 400) throw new HttpError(502, 'Unexpected backend redirect');
      if (upstream.status === 204) return new Response(null, { status: 204, headers: { 'cache-control': 'no-store' } });
      if (!upstream.headers.get('content-type')?.includes('application/json')) throw new HttpError(502, 'Unexpected backend response');
      let data: unknown;
      try { data = await upstream.json(); } catch { throw new HttpError(502, 'Invalid backend response'); }
      const response = json(data, upstream.status);
      const etag = upstream.headers.get('etag');
      if (etag) response.headers.set('etag', etag);
      return response;
    }),
  };
}
