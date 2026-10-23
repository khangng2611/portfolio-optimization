import { context, ROOT_CONTEXT, SpanKind, SpanStatusCode, trace, type Attributes, type Context, type SpanContext } from '@opentelemetry/api';
import { AsyncLocalStorageContextManager } from '@opentelemetry/context-async-hooks';
import { W3CTraceContextPropagator } from '@opentelemetry/core';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { AlwaysOnSampler, BatchSpanProcessor, type ReadableSpan, type Span, type SpanExporter, type SpanProcessor } from '@opentelemetry/sdk-trace-base';
import { NodeTracerProvider } from '@opentelemetry/sdk-trace-node';

const SCOPE = 'portfolio-bff';
const routeTemplates = new Set(['/api/v1/portfolios', '/api/v1/portfolios/{portfolio_id}', '/api/v1/portfolios/{portfolio_id}/recommendations', '/api/v1/recommendations/{recommendation_id}', '/api/v1/jobs/portfolio/{job_id}']);
const propagator = new W3CTraceContextPropagator();
const getter = { keys: (carrier: Record<string, string>) => Object.keys(carrier), get: (carrier: Record<string, string>, key: string) => carrier[key] };
const setter = { set: (carrier: Record<string, string>, key: string, value: string) => { carrier[key] = value; } };

const safeService = (value?: string) => value && /^[A-Za-z0-9_.-]{1,64}$/.test(value) ? value : 'web-bff';
const safeContext = ({ traceId, spanId, traceFlags, isRemote }: SpanContext): SpanContext => ({ traceId, spanId, traceFlags, isRemote });

/** Reject Next/framework spans before they reach a queue or exporter. */
export class ManualSpanProcessor implements SpanProcessor {
  constructor(private readonly delegate: SpanProcessor, private readonly serviceName = 'web-bff') {}
  onStart(_span: Span, _parent: Context): void {}
  onEnd(span: ReadableSpan): void {
    if (span.instrumentationScope.name !== SCOPE) return;
    const method = span.attributes['http.request.method'];
    const route = span.attributes['http.route'];
    if (typeof method !== 'string' || !['GET', 'POST', 'PATCH'].includes(method) || typeof route !== 'string' || !routeTemplates.has(route)) return;
    const attributes: Attributes = { 'http.request.method': method, 'http.route': route };
    const status = span.attributes['http.response.status_code'];
    if (typeof status === 'number' && Number.isInteger(status) && status >= 100 && status <= 599) attributes['http.response.status_code'] = status;
    const sanitized: ReadableSpan = {
      name: `${method} ${route}`, kind: SpanKind.SERVER,
      spanContext: () => safeContext(span.spanContext()),
      parentSpanContext: span.parentSpanContext ? safeContext(span.parentSpanContext) : undefined,
      startTime: span.startTime, endTime: span.endTime, duration: span.duration,
      ended: span.ended, status: { code: span.status.code }, attributes,
      links: [], events: [], resource: resourceFromAttributes({ 'service.name': safeService(this.serviceName) }),
      instrumentationScope: { name: SCOPE, version: '0.1.0' },
      droppedAttributesCount: span.droppedAttributesCount,
      droppedEventsCount: span.droppedEventsCount, droppedLinksCount: span.droppedLinksCount,
    };
    try { this.delegate.onEnd(sanitized); } catch { /* Telemetry cannot fail a business request. */ }
  }
  async forceFlush(): Promise<void> { try { await this.delegate.forceFlush(); } catch {} }
  async shutdown(): Promise<void> { try { await this.delegate.shutdown(); } catch {} }
}

export function createTracingProvider(exporter: SpanExporter, serviceName = 'web-bff'): NodeTracerProvider {
  const processor = new BatchSpanProcessor(exporter, { maxQueueSize: 256, maxExportBatchSize: 32, scheduledDelayMillis: 200, exportTimeoutMillis: 1000 });
  return new NodeTracerProvider({
    resource: resourceFromAttributes({ 'service.name': safeService(serviceName) }),
    sampler: new AlwaysOnSampler(), spanProcessors: [new ManualSpanProcessor(processor, serviceName)],
    spanLimits: { attributeCountLimit: 8, attributeValueLengthLimit: 160, eventCountLimit: 0, linkCountLimit: 0 },
  });
}

export function configureTracing(env: Record<string, string | undefined> = process.env): void {
  const runtime = globalThis as typeof globalThis & { __portfolioBffTracing?: boolean };
  if (env.OTEL_TRACES_ENABLED !== 'true' || runtime.__portfolioBffTracing) return;
  try {
    const endpoint = new URL(env.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT ?? 'http://jaeger:4318/v1/traces');
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash || endpoint.pathname !== '/v1/traces') return;
    if (endpoint.protocol !== 'https:' && !(endpoint.protocol === 'http:' && ['jaeger', 'localhost', '127.0.0.1', '[::1]'].includes(endpoint.hostname))) return;
    const exporter = new OTLPTraceExporter({ url: endpoint.href, timeoutMillis: 1000, concurrencyLimit: 1, headers: {} });
    createTracingProvider(exporter, safeService(env.OTEL_SERVICE_NAME)).register({ contextManager: new AsyncLocalStorageContextManager(), propagator });
    runtime.__portfolioBffTracing = true;
  } catch { /* Invalid config/exporter initialization leaves business operations available. */ }
}

function validTracestate(value: string): boolean {
  if (value.length > 512) return false;
  const members = value.split(',');
  if (members.length > 32) return false;
  const seen = new Set<string>();
  for (const member of members) {
    const pair = member.trim().split('=');
    if (pair.length !== 2) return false;
    const [key, state] = pair;
    if (!/^(?:[a-z][a-z0-9_*/-]{0,255}|[a-z0-9][a-z0-9_*/-]{0,240}@[a-z][a-z0-9_*/-]{0,13})$/.test(key) || seen.has(key)) return false;
    if (!/^[\x20-\x7e]{1,256}$/.test(state) || state.includes(',') || state.includes('=') || state.trim() !== state) return false;
    seen.add(key);
  }
  return true;
}

export function injectTraceHeaders(headers: Headers): void {
  if (process.env.OTEL_TRACES_ENABLED !== 'true') return;
  const carrier: Record<string, string> = {};
  propagator.inject(context.active(), carrier, setter);
  for (const [key, value] of Object.entries(carrier)) headers.set(key, value);
}

export async function traceProxy(request: Request, route: string, action: () => Promise<Response>): Promise<Response> {
  if (process.env.OTEL_TRACES_ENABLED !== 'true') return action();
  const carrier: Record<string, string> = {};
  const incoming = request.headers.get('traceparent');
  if (incoming && /^00-(?!0{32})[a-f0-9]{32}-(?!0{16})[a-f0-9]{16}-0[01]$/.test(incoming)) {
    carrier.traceparent = incoming;
    const state = request.headers.get('tracestate');
    if (state && validTracestate(state)) carrier.tracestate = state;
  }
  const parent = propagator.extract(ROOT_CONTEXT, carrier, getter);
  const started = performance.now();
  return trace.getTracer(SCOPE, '0.1.0').startActiveSpan(`${request.method} ${route}`, {
    kind: SpanKind.SERVER,
    attributes: { 'http.request.method': request.method, 'http.route': route },
  }, parent, async span => {
    try {
      const response = await action();
      span.setAttribute('http.response.status_code', response.status);
      if (response.status >= 500) span.setStatus({ code: SpanStatusCode.ERROR });
      if (span.isRecording()) {
        const current = span.spanContext();
        response.headers.set('X-Trace-ID', current.traceId);
        try { console.log(JSON.stringify({ service: safeService(process.env.OTEL_SERVICE_NAME), trace_id: current.traceId, span_id: current.spanId, stage: 'bff.proxy', status: response.status, duration_ms: Math.round((performance.now() - started) * 100) / 100 })); } catch {}
      }
      return response;
    } finally { span.end(); }
  });
}
