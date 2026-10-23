import { createBff } from '../src/server/bff';
import { EncryptedStore, type Backend } from '../src/server/store';
import type { Config } from '../src/server/config';
import type { IdentityProvider } from '../src/server/oidc';
export const config: Config = { origin: 'https://app.test', issuer: 'https://identity.test/realms/portfolio', clientId: 'portfolio-web', clientSecret: 'secret', audience: 'portfolio-api', scope: 'openid profile email portfolio:read portfolio:write', redisUrl: 'redis://localhost:6379', key: Buffer.alloc(32, 7), portfolioUrl: 'http://portfolio-api:8000', allowHttp: false, sessionSeconds: 3600, secureCookies: true };
export class MemoryBackend implements Backend {
  data = new Map<string, { value: string; until: number }>();
  async get(key: string) { const item = this.data.get(key); if (!item || item.until <= Date.now()) return null; return item.value; }
  async set(key: string, value: string, seconds: number, nx = false) { if (nx && this.data.has(key) && this.data.get(key)!.until > Date.now()) return false; this.data.set(key, { value, until: Date.now() + seconds * 1000 }); return true; }
  async take(key: string) { const value = await this.get(key); this.data.delete(key); return value; }
  async del(key: string) { this.data.delete(key); }
  async unlock(key: string, owner: string) { if (await this.get(key) === owner) this.data.delete(key); }
  async guardedSet(key: string, value: string, seconds: number, lock: string, owner: string) { if (await this.get(lock) !== owner || !(await this.get(key))) return false; return this.set(key, value, seconds); }
}
export function provider() {
  const tokens = () => ({ accessToken: 'access-alice', refreshToken: 'refresh-alice', accessExpiresAt: Date.now() + 300_000, user: { sub: 'alice', name: 'Alice', roles: ['investor'] } });
  return { authorize: async (flow: import("../src/server/oidc").Flow) => { const url = new URL('https://identity.test/auth'); url.searchParams.set('state', flow.state); url.searchParams.set('nonce', flow.nonce); url.searchParams.set('code_challenge_method', 'S256'); return url; }, exchange: async () => tokens(), refresh: async () => tokens(), revoke: async () => {} };
}
export function request(path: string, options: { method?: string; cookie?: string; headers?: Record<string, string>; body?: string } = {}) {
  return new Request(config.origin + path, { method: options.method, headers: { ...(options.cookie ? { cookie: options.cookie.split(';')[0] } : {}), ...options.headers }, body: options.body });
}
export async function login(options: { oidc?: IdentityProvider; fetch?: typeof fetch } = {}) {
  const backend = new MemoryBackend();
  const store = new EncryptedStore(backend, config.key);
  const bff = createBff(config, store, options.oidc ?? provider(), options.fetch);
  const start = await bff.login(request('/auth/login'));
  const state = new URL(start.headers.get('location')!).searchParams.get('state')!;
  const callback = await bff.callback(request(`/auth/callback?code=code&state=${state}`, { cookie: start.headers.get('set-cookie')! }));
  const cookie = callback.headers.get('set-cookie')!.match(/__Host-portfolio_session=[^,]+/)![0];
  // Read directly so near-expiry tests can trigger refresh themselves.
  const id = cookie.match(/portfolio_session=([^;]+)/)![1];
  const session = await store.get<{ csrfToken: string }>(`session:${id}`);
  return { bff, cookie, csrf: session!.csrfToken, store, backend };
}
