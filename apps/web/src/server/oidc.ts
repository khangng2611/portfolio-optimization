import * as oidc from 'openid-client';
import { createRemoteJWKSet, customFetch as joseFetch, jwtVerify } from 'jose';
import type { Config } from './config';
export interface User { sub: string; name: string; roles: string[] }
export interface Flow { state: string; nonce: string; verifier: string; expiresAt: number }
export interface Tokens { accessToken: string; refreshToken: string; accessExpiresAt: number; user: User }
export interface IdentityProvider {
  authorize(flow: Flow): Promise<URL>;
  exchange(url: URL, flow: Flow): Promise<Tokens>;
  refresh(token: string, subject: string): Promise<Tokens>;
  revoke(token: string): Promise<void>;
}
// Only the configured issuer's network origin is rewritten. Metadata and token iss remain public.
export function backchannel(config: Config) {
  return async (input: string, init: RequestInit | oidc.CustomFetchOptions = {}) => {
    const url = new URL(input);
    if (url.origin !== new URL(config.issuer).origin) throw new Error('Unexpected identity endpoint');
    if (config.internalOrigin) { const internal = new URL(config.internalOrigin); url.protocol = internal.protocol; url.host = internal.host; }
    const body = init.body instanceof Uint8Array ? new Uint8Array(init.body).buffer : init.body;
    return fetch(url, { ...init, body, redirect: 'error', signal: AbortSignal.timeout(8000) });
  };
}
export async function createIdentityProvider(config: Config): Promise<IdentityProvider> {
  const transport = backchannel(config);
  const client = await oidc.discovery(new URL(config.issuer), config.clientId, { client_secret: config.clientSecret, id_token_signed_response_alg: 'RS256' }, oidc.ClientSecretBasic(config.clientSecret), { [oidc.customFetch]: transport, timeout: 8, ...(config.allowHttp ? { execute: [oidc.allowInsecureRequests] } : {}) });
  const metadata = client.serverMetadata();
  if (!metadata.jwks_uri) throw new Error('Issuer has no JWKS');
  const keys = createRemoteJWKSet(new URL(metadata.jwks_uri), { [joseFetch]: transport, timeoutDuration: 8000, cacheMaxAge: 300_000 });
  async function normalize(tokens: oidc.TokenEndpointResponse & oidc.TokenEndpointResponseHelpers, subject?: string, refreshFallback?: string): Promise<Tokens> {
    const { payload } = await jwtVerify(tokens.access_token, keys, { issuer: config.issuer, audience: config.audience, algorithms: ['RS256'], requiredClaims: ['exp', 'sub', 'iat'] });
    const claims = tokens.claims();
    if (!payload.sub || (claims && claims.sub !== payload.sub) || (subject && subject !== payload.sub)) throw new Error('Token subject mismatch');
    const refreshToken = tokens.refresh_token ?? refreshFallback;
    if (!refreshToken || !payload.exp) throw new Error('No refresh token or expiration');
    const roles = (payload.realm_access as { roles?: unknown } | undefined)?.roles;
    const allowedRoles = ['investor', 'researcher', 'data-operator', 'model-reviewer', 'system-admin'];
    return { accessToken: tokens.access_token, refreshToken, accessExpiresAt: payload.exp * 1000, user: { sub: payload.sub, name: String(claims?.name ?? payload.name ?? claims?.preferred_username ?? payload.preferred_username ?? payload.sub), roles: Array.isArray(roles) ? roles.filter((role): role is string => typeof role === 'string' && allowedRoles.includes(role)) : [] } };
  }
  return {
    authorize: async flow => oidc.buildAuthorizationUrl(client, { redirect_uri: `${config.origin}/auth/callback`, scope: config.scope, state: flow.state, nonce: flow.nonce, code_challenge: await oidc.calculatePKCECodeChallenge(flow.verifier), code_challenge_method: 'S256' }),
    exchange: async (url, flow) => normalize(await oidc.authorizationCodeGrant(client, url, { pkceCodeVerifier: flow.verifier, expectedState: flow.state, expectedNonce: flow.nonce, idTokenExpected: true })),
    refresh: async (token, subject) => { const tokens = await oidc.refreshTokenGrant(client, token); return normalize(tokens, subject, token); },
    revoke: token => oidc.tokenRevocation(client, token, { token_type_hint: 'refresh_token' }),
  };
}
