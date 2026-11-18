import { beforeAll, expect, it } from 'vitest';
import { exportJWK, generateKeyPair, SignJWT } from 'jose';
import { createIdentityProvider } from '../src/server/identity';
import { config } from './helpers';

let keys: Awaited<ReturnType<typeof generateKeyPair>>;
beforeAll(async () => { keys = await generateKeyPair('RS256'); });
const credentials = { username: 'alice', password: 'private-test-value' };

async function identity(options: { aud?: string; issuer?: string; expired?: boolean; forged?: boolean } = {}) {
  const publicKey = await exportJWK(keys.publicKey);
  const signer = options.forged ? (await generateKeyPair('RS256')).privateKey : keys.privateKey;
  const token = await new SignJWT({ realm_access: { roles: ['investor'] }, azp: 'portfolio-web' })
    .setProtectedHeader({ alg: 'RS256', kid: 'test-key' })
    .setIssuer(options.issuer ?? config.issuer).setAudience(options.aud ?? 'portfolio-api')
    .setSubject('alice').setIssuedAt().setExpirationTime(options.expired ? 1 : '5m').sign(signer);
  return createIdentityProvider(config, async (input, init) => {
    const url = new URL(String(input));
    expect(url.origin).toBe(config.authUrl);
    expect(init?.redirect).toBe('error');
    if (url.pathname === '/.well-known/jwks.json') return Response.json({ keys: [{ ...publicKey, kid: 'test-key' }] });
    expect(url.pathname).toBe('/internal/v1/login');
    expect(new Headers(init?.headers).get('authorization')).toBe('Bearer ' + config.authWebSecret);
    expect(JSON.parse(String(init?.body))).toEqual(credentials);
    return Response.json({ accessToken: token, refreshToken: 'refresh', sessionId: 'session',
      sessionExpiresAt: Date.now() + 3600_000, user: { sub: 'alice', name: 'Alice', roles: ['system-admin'] } });
  });
}

it('authenticates over the private API and uses roles from the signed token', async () => {
  const auth = await identity();
  expect((await auth.login(credentials)).user).toEqual({ sub: 'alice', name: 'Alice', roles: ['investor'] });
});

it.each([{ aud: 'another-api' }, { issuer: 'https://evil.test' }, { expired: true }, { forged: true }])(
  'rejects invalid access tokens (%j)', async options => {
    const auth = await identity(options);
    await expect(auth.login(credentials)).rejects.toThrow();
  },
);
