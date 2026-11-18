import { expect, it } from 'vitest';
import { createBff } from '../src/server/bff';
import { EncryptedStore } from '../src/server/store';
import { config, MemoryBackend, provider, request } from './helpers';

it('requires same-origin JSON and registers without setting a session', async () => {
  const identity = { ...provider(), register: async () => {} };
  const bff = createBff(config, new EncryptedStore(new MemoryBackend(), config.key), identity);
  const post = (origin: string, contentType = 'application/json') => request('/auth/register', {
    method: 'POST', headers: { origin, 'content-type': contentType },
    body: JSON.stringify({ name: 'Alice', username: 'alice', password: 'long-password' }),
  });
  expect((await bff.register(post('https://evil.test'))).status).toBe(403);
  expect((await bff.register(post(config.origin, 'text/plain'))).status).toBe(415);
  const response = await bff.register(post(config.origin));
  expect(response.status).toBe(201);
  expect(response.headers.get('set-cookie')).toBeNull();
  for (let attempt = 1; attempt < 10; attempt++) await bff.register(post(config.origin));
  expect((await bff.register(post(config.origin))).status).toBe(429);
});
