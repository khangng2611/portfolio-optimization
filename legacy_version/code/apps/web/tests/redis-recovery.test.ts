import { afterEach, describe, expect, it, vi } from 'vitest';
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { createClient, type RedisClientType } from 'redis';
import { handler } from '../src/server/runtime';
import { createBff } from '../src/server/bff';
import { connectStore } from '../src/server/store';
import { config, provider, request } from './helpers';

// Keep the actual Redis client/network behavior; retain clients only for test cleanup.
const clients = vi.hoisted(() => [] as RedisClientType[]);
vi.mock('redis', async importOriginal => {
  const redis = await importOriginal<typeof import('redis')>();
  return { ...redis, createClient: (...args: Parameters<typeof redis.createClient>) => { const client = redis.createClient(...args); clients.push(client as RedisClientType); return client; } };
});
const binary = process.env.REDIS_TEST_BINARY ?? 'redis-server';
const redisAvailable = spawnSync(binary, ['--version'], { stdio: 'ignore' }).status === 0;
let child: ChildProcess | undefined;
afterEach(async () => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  for (const client of clients.splice(0)) if (client.isOpen) client.destroy();
  if (child && child.exitCode === null) { const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited; }
  child = undefined;
});
async function startRedis(port: number) {
  child = spawn(binary, ['--bind', '127.0.0.1', '--port', String(port), '--save', '', '--appendonly', 'no', '--protected-mode', 'yes'], { stdio: ['ignore', 'pipe', 'pipe'] });
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Redis did not become ready')), 3000);
    child!.stdout!.on('data', data => { if (data.toString().includes('Ready to accept connections')) { clearTimeout(timeout); resolve(); } });
    child!.once('error', error => { clearTimeout(timeout); reject(error); });
    child!.once('exit', () => { clearTimeout(timeout); reject(new Error('Redis exited before ready')); });
  });
}
async function stopRedis() { const exited = once(child!, 'exit'); child!.kill('SIGTERM'); await exited; child = undefined; }
async function portNumber() { const server = createServer(); server.listen(0, '127.0.0.1'); await once(server, 'listening'); const address = server.address(); const port = typeof address === 'object' && address ? address.port : 0; await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); return port; }
async function eventually<T>(action: () => Promise<T>, accept: (value: T) => boolean) {
  let result: T | undefined;
  for (let attempt = 0; attempt < 50; attempt++) { result = await action(); if (accept(result)) return result; await new Promise(resolve => setTimeout(resolve, 100)); }
  return result;
}
describe.skipIf(!redisAvailable)('real Redis outage recovery', () => {
  it('does not leak Redis connections when identity discovery fails', async () => {
    const port = await portNumber();
    await startRedis(port);
    const observer = createClient({ url: `redis://127.0.0.1:${port}/0` });
    await observer.connect();
    for (const [key, value] of Object.entries({ APP_ORIGIN: config.origin, OIDC_ISSUER: config.issuer, OIDC_CLIENT_SECRET: config.clientSecret, PORTFOLIO_API_URL: config.portfolioUrl, SESSION_ENCRYPTION_KEY: config.key.toString('base64'), REDIS_URL: `redis://127.0.0.1:${port}/0` })) vi.stubEnv(key, value);
    vi.stubGlobal('fetch', async () => { throw new Error('Identity discovery unavailable'); });
    const response = await handler('login')(request('/auth/login'));
    expect(response.status).toBe(503);
    // Let any accidentally allocated real connection finish before counting on the server.
    for (const client of clients) if (!client.isReady) await once(client, 'ready');
    const info = await observer.info('clients');
    expect(info.match(/connected_clients:(\d+)/)?.[1]).toBe('1');
  });
  it('fails closed during outage and reauthenticates after restart without restarting the BFF', async () => {
    const port = await portNumber();
    await startRedis(port);
    const store = await connectStore(`redis://127.0.0.1:${port}/0`, config.key);
    const bff = createBff(config, store, provider());
    async function signIn() {
      const login = await bff.login(request('/auth/login'));
      expect(login.status).toBe(302);
      const state = new URL(login.headers.get('location')!).searchParams.get('state')!;
      const callback = await bff.callback(request(`/auth/callback?code=test&state=${state}`, { cookie: login.headers.get('set-cookie')! }));
      expect(callback.status).toBe(303);
      return callback.headers.get('set-cookie')!.match(/__Host-portfolio_session=[^,]+/)![0];
    }
    const cookie = await signIn();
    expect((await bff.session(request('/auth/session', { cookie }))).status).toBe(200);
    await stopRedis();
    expect(await eventually(async () => (await bff.session(request('/auth/session', { cookie }))).status, status => status === 503)).toBe(503);
    const started = Date.now();
    expect((await bff.login(request('/auth/login'))).status).toBe(503);
    expect(Date.now() - started).toBeLessThan(1000);
    await startRedis(port);
    // Session was lost with the nonpersistent server, never trust the old cookie.
    expect(await eventually(async () => (await bff.session(request('/auth/session', { cookie }))).status, status => status === 401)).toBe(401);
    const newCookie = await signIn();
    expect(newCookie).not.toBe(cookie);
    expect((await bff.session(request('/auth/session', { cookie: newCookie }))).status).toBe(200);
    expect((await bff.session(request('/auth/session', { cookie }))).status).toBe(401);
  }, 15_000);
});
