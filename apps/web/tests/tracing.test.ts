import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { context, ROOT_CONTEXT, SpanKind, trace } from '@opentelemetry/api';
import { AsyncLocalStorageContextManager } from '@opentelemetry/context-async-hooks';
import { W3CTraceContextPropagator } from '@opentelemetry/core';
import { InMemorySpanExporter } from '@opentelemetry/sdk-trace-base';
import { createTracingProvider } from '../src/server/tracing';
import { config, login, request } from './helpers';

const exporter = new InMemorySpanExporter();
const provider = createTracingProvider(exporter);
beforeAll(() => provider.register({ contextManager: new AsyncLocalStorageContextManager(), propagator: new W3CTraceContextPropagator() }));
beforeEach(() => { exporter.reset(); vi.stubEnv('OTEL_TRACES_ENABLED', 'true'); });
afterEach(async () => { await provider.forceFlush(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });
afterAll(async () => { await provider.shutdown(); context.disable(); trace.disable(); });
const parent = '00-11111111111111111111111111111111-2222222222222222-01';
async function finished() { await provider.forceFlush(); return exporter.getFinishedSpans(); }

describe('BFF trace context boundary', () => {
  it('propagates the authenticated proxy trace without forwarding caller identity or baggage', async () => {
    let upstream: Request | undefined;
    const { bff, cookie, csrf } = await login({ fetch: async (url, init) => { upstream = new Request(url, init); return Response.json({ job_id: 'job' }, { status: 202 }); } });
    const result = await bff.proxy(request('/api/v1/portfolios/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/recommendations', {
      method: 'POST', cookie, headers: { origin: config.origin, 'x-csrf-token': csrf, 'content-type': 'application/json', 'idempotency-key': 'request-one', authorization: 'Bearer caller-secret', traceparent: parent, baggage: 'password=private', 'x-user-id': 'mallory' }, body: '{"strategy":"MVO"}',
    }));
    expect(result.status).toBe(202);
    expect(result.headers.get('x-trace-id')).toBe('11111111111111111111111111111111');
    expect(upstream!.headers.get('traceparent')).toMatch(/^00-11111111111111111111111111111111-[a-f0-9]{16}-01$/);
    expect(upstream!.headers.get('traceparent')).not.toBe(parent);
    expect(upstream!.headers.get('authorization')).toBe('Bearer access-alice');
    expect(upstream!.headers.get('baggage')).toBeNull();
    expect(upstream!.headers.get('x-user-id')).toBeNull();
    expect(await finished()).toHaveLength(1);
  });
  it('exports manual route attributes only and excludes automatic auth callback spans', async () => {
    const automatic = trace.getTracer('next.js').startSpan('GET /auth/callback?code=private-code&state=private-state');
    automatic.setAttribute('http.url', 'https://app.test/auth/callback?code=private-code'); automatic.end();
    const manual = trace.getTracer('portfolio-bff').startSpan('GET /api/v1/portfolios', { kind: SpanKind.SERVER, attributes: { 'http.route': '/api/v1/portfolios', 'http.request.method': 'GET', 'http.response.status_code': 200, authorization: 'private-token', 'http.url': 'https://app.test/?password=private-password', capital_vnd: '1000000' } });
    manual.addEvent('raw failure', { body: 'financial-secret' }); manual.end();
    const spans = await finished();
    expect(spans).toHaveLength(1);
    expect(spans[0].attributes).toEqual({ 'http.route': '/api/v1/portfolios', 'http.request.method': 'GET', 'http.response.status_code': 200 });
    expect(spans[0].events).toEqual([]);
    expect(JSON.stringify(spans)).not.toMatch(/private-|financial-secret|capital_vnd/);
  });
  it('does not instrument auth/session handlers, disallowed paths or tracing-disabled proxy calls', async () => {
    let upstream: Request | undefined;
    const { bff, cookie } = await login({ fetch: async (url, init) => { upstream = new Request(url, init); return Response.json([]); } });
    await bff.session(request('/auth/session', { cookie }));
    expect((await bff.proxy(request('/api/v1/internal/secrets', { cookie }))).status).toBe(404);
    vi.stubEnv('OTEL_TRACES_ENABLED', 'false');
    const response = await bff.proxy(request('/api/v1/portfolios', { cookie, headers: { traceparent: parent } }));
    expect(response.status).toBe(200);
    expect(response.headers.get('x-trace-id')).toBeNull();
    expect(upstream!.headers.get('traceparent')).toBeNull();
    expect(await finished()).toEqual([]);
  });
  it.each(['garbage', parent + ', ' + parent, '00-' + '0'.repeat(32) + '-2222222222222222-01', parent.replace('00-', 'ff-'), parent.replace('11', 'AA')])('starts a root trace for malformed context: %s', async invalid => {
    const { bff, cookie } = await login({ fetch: async () => Response.json([]) });
    const response = await bff.proxy(request('/api/v1/portfolios', { cookie, headers: { traceparent: invalid } }));
    expect(response.headers.get('x-trace-id')).toMatch(/^[a-f0-9]{32}$/);
    expect(response.headers.get('x-trace-id')).not.toBe('11111111111111111111111111111111');
    expect((await finished())[0].parentSpanContext).toBeUndefined();
  });
  it('validates tracestate, preserves accepted members and never exports it or baggage', async () => {
    const carriers: Headers[] = [];
    const { bff, cookie } = await login({ fetch: async (_url, init) => { carriers.push(new Headers(init?.headers)); return Response.json([]); } });
    await bff.proxy(request('/api/v1/portfolios', { cookie, headers: { traceparent: parent, tracestate: 'vendor=opaque-value', baggage: 'token=private-baggage' } }));
    await bff.proxy(request('/api/v1/portfolios', { cookie, headers: { traceparent: parent, tracestate: 'vendor=one,vendor=two' } }));
    expect(carriers[0].get('tracestate')).toBe('vendor=opaque-value');
    expect(carriers[1].get('tracestate')).toBeNull();
    expect(JSON.stringify(await finished())).not.toContain('opaque-value');
  });
  it('isolates concurrent requests and removes context after upstream failures', async () => {
    const received: string[] = [];
    const { bff, cookie } = await login({ fetch: async (_url, init) => { const h = new Headers(init?.headers); await new Promise(resolve => setTimeout(resolve, 5)); received.push(h.get('traceparent')!); return Response.json([]); } });
    const responses = await Promise.all(['1', '3'].map(digit => bff.proxy(request('/api/v1/portfolios', { cookie, headers: { traceparent: `00-${digit.repeat(32)}-2222222222222222-01` } }))));
    expect(new Set(responses.map(r => r.headers.get('x-trace-id')))).toEqual(new Set(['1'.repeat(32), '3'.repeat(32)]));
    expect(received.map(h => h.split('-')[1]).sort()).toEqual(['1'.repeat(32), '3'.repeat(32)]);
    const failing = await login({ fetch: async () => { throw new Error('private backend failure'); } });
    expect((await failing.bff.proxy(request('/api/v1/portfolios', { cookie: failing.cookie }))).status).toBe(502);
    expect(trace.getSpan(context.active())).toBeUndefined();
  });
  it('uses ROOT instead of an ambient Next span and logs only allowlisted metadata', async () => {
    const output = vi.spyOn(console, 'log').mockImplementation(() => {});
    const automatic = trace.getTracer('next.js').startSpan('private auth query');
    const { bff, cookie } = await login({ fetch: async () => Response.json([]) });
    const response = await context.with(trace.setSpan(ROOT_CONTEXT, automatic), () => bff.proxy(request('/api/v1/portfolios?limit=1', { cookie })));
    automatic.end();
    expect(response.headers.get('x-trace-id')).not.toBe(automatic.spanContext().traceId);
    expect(await finished()).toHaveLength(1);
    const records = output.mock.calls.map(([value]) => JSON.parse(value as string));
    expect(records).toHaveLength(1);
    expect(records[0]).toMatchObject({ service: 'web-bff', stage: 'bff.proxy', status: 200, trace_id: response.headers.get('x-trace-id') });
    expect(Object.keys(records[0]).sort()).toEqual(['duration_ms', 'service', 'span_id', 'stage', 'status', 'trace_id']);
  });
  it('does not confuse a polling HTTP trace with the origin job trace or trust an arbitrary viewer URL', async () => {
    vi.stubEnv('TRACE_VIEWER_URL', 'http://localhost:16686');
    const jobId = 'a'.repeat(32);
    const { bff, cookie } = await login({ fetch: async () => Response.json({ job_trace_id: jobId, job_trace_url: `https://evil.test/trace/${jobId}` }) });
    const response = await bff.proxy(request('/api/v1/jobs/portfolio/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', { cookie }));
    expect(response.headers.get('x-trace-id')).not.toBe(jobId);
    expect(await response.json()).toMatchObject({ job_trace_id: jobId, job_trace_url: null });
  });
  it('returns business success even when a batch export stalls, and bounds flush waiting', async () => {
    vi.spyOn(exporter, 'export').mockImplementation(() => { /* Collector never completes. */ });
    const { bff, cookie } = await login({ fetch: async () => Response.json({ status: 'saved' }) });
    const response = await bff.proxy(request('/api/v1/portfolios', { cookie }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: 'saved' });
    const flush = provider.forceFlush();
    await expect(Promise.race([flush.then(() => 'bounded'), new Promise(resolve => setTimeout(() => resolve('unbounded'), 2500))])).resolves.toBe('bounded');
  });
  it('records local requests even when the remote parent was unsampled', async () => {
    const { bff, cookie } = await login({ fetch: async () => Response.json([]) });
    const response = await bff.proxy(request('/api/v1/portfolios', { cookie, headers: { traceparent: parent.slice(0,-2) + '00' } }));
    expect(response.headers.get('x-trace-id')).toBe('1'.repeat(32));
    expect(await finished()).toHaveLength(1);
  });
  it('rejects overlong tracestate before propagation', async () => {
    let received: Headers | undefined;
    const { bff, cookie } = await login({ fetch: async (_url, init) => { received = new Headers(init?.headers); return Response.json([]); } });
    await bff.proxy(request('/api/v1/portfolios', { cookie, headers: { traceparent: parent, tracestate: 'vendor=' + 'a'.repeat(513) } }));
    expect(received!.get('tracestate')).toBeNull();
  });
});
