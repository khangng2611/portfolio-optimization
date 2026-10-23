import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import { exportJWK, generateKeyPair, SignJWT } from 'jose';
import { createIdentityProvider, type Flow } from '../src/server/oidc';
import { config } from './helpers';
let keys: Awaited<ReturnType<typeof generateKeyPair>>;
beforeAll(async () => { keys = await generateKeyPair('RS256'); });
afterEach(() => vi.unstubAllGlobals());
const flow: Flow = { state: 'test-state', nonce: 'test-nonce', verifier: 'a'.repeat(43), expiresAt: Date.now() + 300000 };
async function mockIdentity(options: { nonce?: string; aud?: string; issuer?: string; expired?: boolean; forged?: boolean } = {}) {
  const jwk = await exportJWK(keys.publicKey);
  const signer = options.forged ? (await generateKeyPair('RS256')).privateKey : keys.privateKey;
  const idToken = await new SignJWT({ nonce: options.nonce ?? flow.nonce, name: 'Alice' }).setProtectedHeader({ alg: 'RS256', kid: 'test-key' }).setIssuer(config.issuer).setAudience(config.clientId).setSubject('alice').setIssuedAt().setExpirationTime('5m').sign(keys.privateKey);
  const access = await new SignJWT({ realm_access: { roles: ['investor', 'offline_access'] }, scope: 'portfolio:read portfolio:write' }).setProtectedHeader({ alg: 'RS256', kid: 'test-key' }).setIssuer(options.issuer ?? config.issuer).setAudience(options.aud ?? config.audience).setSubject('alice').setIssuedAt().setExpirationTime(options.expired ? Math.floor(Date.now() / 1000) - 1 : '5m').sign(signer);
  let grant: URLSearchParams | undefined;
  const paths: string[] = [];
  vi.stubGlobal('fetch', async (input: string | URL, init: RequestInit) => {
    const url = new URL(input); paths.push(url.origin);
    if (url.pathname.endsWith('/.well-known/openid-configuration')) return Response.json({ issuer: config.issuer, authorization_endpoint: config.issuer + '/auth', token_endpoint: config.issuer + '/token', jwks_uri: config.issuer + '/certs', revocation_endpoint: config.issuer + '/revoke', response_types_supported: ['code'], subject_types_supported: ['public'], id_token_signing_alg_values_supported: ['RS256'], token_endpoint_auth_methods_supported: ['client_secret_basic'], code_challenge_methods_supported: ['S256'] });
    if (url.pathname.endsWith('/certs')) return Response.json({ keys: [{ ...jwk, kid: 'test-key', alg: 'RS256', use: 'sig' }] });
    if (url.pathname.endsWith('/token')) { grant = new URLSearchParams(init.body as string); return Response.json({ token_type: 'Bearer', access_token: access, refresh_token: 'refresh-secret', id_token: idToken, expires_in: 300 }); }
    if (url.pathname.endsWith('/revoke')) return new Response(null, { status: 200 });
    throw new Error('Unexpected URL');
  });
  const identity = await createIdentityProvider({ ...config, internalOrigin: 'https://keycloak.internal' });
  return { identity, getGrant: () => grant, paths };
}
describe('real OIDC library integration', () => {
  it('uses PKCE S256, nonce/state, fixed redirect and public issuer with internal transport', async () => {
    const { identity, getGrant, paths } = await mockIdentity();
    const authorization = await identity.authorize(flow);
    expect(authorization.origin).toBe('https://identity.test');
    expect(authorization.searchParams.get('code_challenge')).toBe(createHash('sha256').update(flow.verifier).digest('base64url'));
    expect(authorization.searchParams.get('code_challenge_method')).toBe('S256');
    expect(authorization.searchParams.get('nonce')).toBe('test-nonce');
    const result = await identity.exchange(new URL(config.origin + '/auth/callback?code=test-code&state=test-state'), flow);
    expect(result.user).toEqual({ sub: 'alice', name: 'Alice', roles: ['investor'] });
    expect(getGrant()?.get('code_verifier')).toBe(flow.verifier);
    expect(getGrant()?.get('redirect_uri')).toBe('https://app.test/auth/callback');
    expect(paths.every(path => path === 'https://keycloak.internal')).toBe(true);
  });
  it.each([{ nonce: 'attacker' }, { aud: 'another-api' }, { issuer: 'https://evil.test' }, { expired: true }, { forged: true }])('rejects invalid token claims or signatures: %j', async options => {
    const { identity } = await mockIdentity(options);
    await expect(identity.exchange(new URL(config.origin + '/auth/callback?code=test-code&state=test-state'), flow)).rejects.toThrow();
  });
  it('rejects mismatched state before a code exchange', async () => {
    const { identity, getGrant } = await mockIdentity();
    await expect(identity.exchange(new URL(config.origin + '/auth/callback?code=test-code&state=forged'), flow)).rejects.toThrow();
    expect(getGrant()).toBeUndefined();
  });
});
