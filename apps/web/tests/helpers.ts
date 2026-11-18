import { createBff } from '../src/server/bff';
import { EncryptedStore, type Backend } from '../src/server/store';
import type { Config } from '../src/server/config';
import type { IdentityProvider } from '../src/server/identity';
export const config: Config = { origin: 'https://app.test', issuer: 'https://identity.test', authUrl: 'https://identity.test', authWebSecret: 'secret', redisUrl: 'redis://localhost:6379', key: Buffer.alloc(32, 7), portfolioUrl: 'http://portfolio-api:8000', allowHttp: false, sessionSeconds: 3600, secureCookies: true };
export class MemoryBackend implements Backend {
  data = new Map<string, { value: string; until: number }>();
  async get(key: string) { const item = this.data.get(key); if (!item || item.until <= Date.now()) return null; return item.value; }
  async set(key: string, value: string, seconds: number, nx = false) { if (nx && this.data.has(key) && this.data.get(key)!.until > Date.now()) return false; this.data.set(key, { value, until: Date.now() + seconds * 1000 }); return true; }
  async increment(key: string, seconds: number) {
    const item = this.data.get(key);
    const active = item && item.until > Date.now() ? item : undefined;
    const next = Number(active?.value ?? 0) + 1;
    this.data.set(key, { value: String(next), until: active?.until ?? Date.now() + seconds * 1000 });
    return next;
  }
  async del(key: string) { this.data.delete(key); }
  async unlock(key: string, owner: string) { if (await this.get(key) === owner) this.data.delete(key); }
  async guardedSet(key: string, value: string, seconds: number, lock: string, owner: string) { if (await this.get(lock) !== owner || !(await this.get(key))) return false; return this.set(key, value, seconds); }
}
export function provider() {
  const tokens = () => ({ accessToken: 'access-alice', refreshToken: 'refresh-alice', accessExpiresAt: Date.now() + 300_000, sessionId: 'auth-session', sessionExpiresAt: Date.now() + 28_800_000, user: { sub: 'alice', name: 'Alice', roles: ['investor'] } });
  return { register: async () => {}, login: async () => tokens(), refresh: async () => tokens(), revoke: async () => {} } satisfies IdentityProvider;
}
export function request(path: string, options: { method?: string; cookie?: string; headers?: Record<string, string>; body?: string } = {}) {
  return new Request(config.origin + path, { method: options.method, headers: { ...(options.cookie ? { cookie: options.cookie.split(';')[0] } : {}), ...options.headers }, body: options.body });
}
export const loginRequest = () => request('/auth/login', {
  method: 'POST', headers: { origin: config.origin, 'content-type': 'application/json' },
  body: JSON.stringify({ username: 'alice', password: 'test-credentials' }),
});
export async function login(options: { identity?: IdentityProvider; fetch?: typeof fetch } = {}) {
  const backend = new MemoryBackend();
  const store = new EncryptedStore(backend, config.key);
  const bff = createBff(config, store, options.identity ?? provider(), options.fetch);
  const response = await bff.login(loginRequest());
  const cookie = response.headers.get('set-cookie')!;
  // Read directly so near-expiry tests can trigger refresh themselves.
  const id = cookie.match(/portfolio_session=([^;]+)/)![1];
  const session = await store.get<{ csrfToken: string }>(`session:${id}`);
  return { bff, cookie, csrf: session!.csrfToken, store, backend };
}
