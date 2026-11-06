import { describe, it, expect } from 'vitest';
import { createBff } from '../src/server/bff';
import { config, login, provider, request } from './helpers';

const cid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const chatConfig = { ...config, chatUrl: 'http://chat-api:8000' };

describe('Chat BFF authorization and streaming', () => {
  it('changes owner conversation consent only with authenticated CSRF protection', async () => {
    const { store, cookie, csrf } = await login();
    let calls = 0;
    const bff = createBff(chatConfig, store, provider(), async (url, init) => {
      calls++;
      expect(String(url)).toBe(`http://chat-api:8000/api/v1/conversations/${cid}/preferences`);
      expect(new Headers(init?.headers).get('authorization')).toBe('Bearer access-alice');
      return Response.json({ llm_consent: false });
    });
    const path = `/api/v1/conversations/${cid}/preferences`;
    expect((await bff.proxy(request(path, { method: 'POST', cookie, headers: { origin: config.origin, 'content-type': 'application/json' }, body: '{"llm_consent":false}' }))).status).toBe(403);
    expect((await bff.proxy(request(path, { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json' }, body: '{"llm_consent":false}' }))).status).toBe(200);
    expect(calls).toBe(1);
  });
  it('routes investor chat to a fixed owner and isolates replay/auth headers', async () => {
    const { store, cookie, csrf } = await login();
    const seen: Request[] = [];
    const bff = createBff(chatConfig, store, provider(), async (url, init) => {
      seen.push(new Request(url, init));
      return Response.json({ job_id: cid }, { status: 202, headers: { 'set-cookie': 'evil=yes' } });
    });
    const response = await bff.proxy(request(`/api/v1/conversations/${cid}/messages`, { method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json', 'idempotency-key': 'message-key-01', 'x-service-authorization': 'Bearer evil', 'x-delegation-grant': 'evil' }, body: '{}' }));
    expect(response.status).toBe(202);
    expect(seen[0].url).toBe(`http://chat-api:8000/api/v1/conversations/${cid}/messages`);
    expect(seen[0].headers.get('authorization')).toBe('Bearer access-alice');
    expect(seen[0].headers.get('x-service-authorization')).toBeNull();
    expect(seen[0].headers.get('x-delegation-grant')).toBeNull();
    expect(response.headers.get('set-cookie')).toBeNull();
  });

  it('relays SSE replay and rejects malformed sequence without forwarding cookies', async () => {
    const { store, cookie } = await login();
    let calls = 0;
    const bff = createBff(chatConfig, store, provider(), async (_url, init) => {
      calls++;
      const h = new Headers(init?.headers);
      expect(h.get('last-event-id')).toBe('17');
      expect(h.get('accept')).toBe('text/event-stream');
      expect(h.get('cookie')).toBeNull();
      expect(h.get('authorization')).toBe('Bearer access-alice');
      return new Response('id: 18\nevent: completed\ndata: {}\n\n', { headers: { 'content-type': 'text/event-stream', 'x-private': 'secret', 'set-cookie': 'evil=yes' } });
    });
    const response = await bff.proxy(request(`/api/v1/jobs/chat/${cid}/events`, { cookie, headers: { 'last-event-id': '17' } }));
    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toContain('text/event-stream');
    expect(response.headers.get('x-private')).toBeNull();
    expect(response.headers.get('set-cookie')).toBeNull();
    expect(await response.text()).toContain('id: 18');
    expect((await bff.proxy(request(`/api/v1/jobs/chat/${cid}/events`, { cookie, headers: { 'last-event-id': 'bad' } }))).status).toBe(400);
    expect(calls).toBe(1);
  });

  it('denies absent session and closes an existing stream when the session is revoked', async () => {
    const { store, cookie } = await login();
    const bff = createBff(chatConfig, store, provider(), async () => new Response(new ReadableStream({ start(c) { c.enqueue(new TextEncoder().encode(': connected\n\n')); } }), { headers: { 'content-type': 'text/event-stream' } }));
    expect((await bff.proxy(request(`/api/v1/jobs/chat/${cid}/events`))).status).toBe(401);
    const r = await bff.proxy(request(`/api/v1/jobs/chat/${cid}/events`, { cookie }));
    const reader = r.body!.getReader();
    expect((await reader.read()).done).toBe(false);
    const id = cookie.match(/portfolio_session=([^;]+)/)![1];
    await store.del(`session:${id}`);
    const chunk = await reader.read();
    expect(new TextDecoder().decode(chunk.value)).toContain('session_expired');
    expect((await reader.read()).done).toBe(true);
  });
  it('reads only on downstream demand and cancels the upstream reader', async () => {
    const { store, cookie } = await login();
    let pulls = 0;
    let cancelled = false;
    const upstream = new ReadableStream<Uint8Array>({
      pull(controller) {
        pulls++;
        if (pulls <= 100) controller.enqueue(new TextEncoder().encode(`id: ${pulls}\ndata: {}\n\n`));
      },
      cancel() { cancelled = true; },
    }, { highWaterMark: 0 });
    const bff = createBff(chatConfig, store, provider(), async () => new Response(upstream, { headers: { 'content-type': 'text/event-stream' } }));
    const response = await bff.proxy(request(`/api/v1/jobs/chat/${cid}/events`, { cookie }));
    const reader = response.body!.getReader();
    try {
      await new Promise(resolve => setTimeout(resolve, 20));
      expect(pulls).toBe(0);
      expect((await reader.read()).done).toBe(false);
      await new Promise(resolve => setTimeout(resolve, 20));
      expect(pulls).toBe(1);
    } finally { await reader.cancel(); }
    expect(cancelled).toBe(true);
  });

  it('closes a silent stream immediately on request abort', async () => {
    const { store, cookie } = await login();
    let cancelled = false;
    const bff = createBff(chatConfig, store, provider(), async () => new Response(new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } }), { headers: { 'content-type': 'text/event-stream' } }));
    const abort = new AbortController();
    const response = await bff.proxy(new Request(config.origin + `/api/v1/jobs/chat/${cid}/events`, { headers: { cookie: cookie.split(';')[0] }, signal: abort.signal }));
    const reader = response.body!.getReader();
    const pending = reader.read();
    await new Promise(resolve => setTimeout(resolve, 20));
    abort.abort();
    try {
      expect(await Promise.race([pending.then(part => part.done), new Promise(resolve => setTimeout(() => resolve('timed out'), 150))])).toBe(true);
      expect(cancelled).toBe(true);
    } finally { await reader.cancel(); }
  });

  it('closes before forwarding an oversized upstream stream chunk', async () => {
    const { store, cookie } = await login();
    const bff = createBff(chatConfig, store, provider(), async () => new Response(new Uint8Array(256 * 1024 + 1), { headers: { 'content-type': 'text/event-stream' } }));
    const response = await bff.proxy(request(`/api/v1/jobs/chat/${cid}/events`, { cookie }));
    const reader = response.body!.getReader();
    try { expect((await reader.read()).done).toBe(true); }
    finally { await reader.cancel(); }
  });

});
