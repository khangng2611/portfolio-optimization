import { createRemoteJWKSet, customFetch, jwtVerify } from 'jose';
import type { Config } from './config';

export interface User { sub: string; name: string; roles: string[] }
export interface Tokens {
  accessToken: string; refreshToken: string; accessExpiresAt: number;
  sessionId: string; sessionExpiresAt: number; user: User;
}
export interface Credentials { username: string; password: string }
export interface Registration extends Credentials { name: string }
export interface IdentityProvider {
  register(body: Registration): Promise<void>;
  login(body: Credentials): Promise<Tokens>;
  refresh(sessionId: string, refreshToken: string, subject: string): Promise<Tokens>;
  revoke(sessionId: string): Promise<void>;
}
export class AuthError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export function createIdentityProvider(config: Config, fetcher: typeof fetch = fetch): IdentityProvider {
  const keys = createRemoteJWKSet(new URL('/.well-known/jwks.json', config.authUrl), {
    [customFetch]: (url, init) => fetcher(url, { ...init, redirect: 'error' }),
    timeoutDuration: 5000,
  });
  async function post(action: string, body: unknown) {
    const response = await fetcher(config.authUrl + '/internal/v1/' + action, {
      method: 'POST', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(5000),
      headers: { 'content-type': 'application/json', authorization: 'Bearer ' + config.authWebSecret },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const message = response.status === 401 ? 'Thông tin đăng nhập không hợp lệ.'
        : response.status === 409 ? 'Tên đăng nhập đã được sử dụng.'
        : 'Thông tin tài khoản không hợp lệ.';
      throw new AuthError(response.status, message);
    }
    return response;
  }
  async function normalize(response: Response, subject?: string, sessionId?: string): Promise<Tokens> {
    const tokens = await response.json() as Tokens;
    const { payload } = await jwtVerify(tokens.accessToken, keys, {
      issuer: config.issuer, audience: 'portfolio-api', algorithms: ['RS256'],
      requiredClaims: ['sub', 'exp', 'iat'],
    });
    const roles = (payload.realm_access as { roles?: unknown } | undefined)?.roles;
    if (!payload.sub || payload.sub !== tokens.user.sub || (subject && subject !== payload.sub)
        || (sessionId && sessionId !== tokens.sessionId) || payload.azp !== 'portfolio-web'
        || !Array.isArray(roles) || !roles.every(role => typeof role === 'string')
        || typeof tokens.user.name !== 'string' || !tokens.sessionId || !tokens.refreshToken
        || !Number.isSafeInteger(tokens.sessionExpiresAt) || tokens.sessionExpiresAt <= Date.now()
        || !payload.exp || payload.exp * 1000 > tokens.sessionExpiresAt) {
      throw new Error('Invalid identity response');
    }
    return { ...tokens, accessExpiresAt: payload.exp * 1000, user: { sub: payload.sub, name: tokens.user.name, roles } };
  }
  return {
    register: async body => { await post('register', body); },
    login: async body => normalize(await post('login', body)),
    refresh: async (sessionId, refreshToken, subject) => normalize(await post('refresh', { sessionId, refreshToken }), subject, sessionId),
    revoke: async sessionId => { await post('revoke', { sessionId }); },
  };
}
