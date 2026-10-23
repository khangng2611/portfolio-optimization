export type TraceReference = { job_trace_id?: string | null; job_trace_url?: string | null };
const validId = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value) && value !== '0'.repeat(32);

export function traceViewerBase(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 512) return null;
  try {
    const url = new URL(value);
    if (url.username || url.password || url.search || url.hash || !/^\/[A-Za-z0-9_/-]*$/.test(url.pathname)) return null;
    const local = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) && url.port === '16686';
    if (!local && url.protocol !== 'https:') return null;
    return url.href.replace(/\/+$/, '');
  } catch { return null; }
}

export function safeTraceReference(value: TraceReference, trustedBase: string | null): { id: string; url: string | null } | null {
  if (!validId(value.job_trace_id)) return null;
  const base = traceViewerBase(trustedBase);
  const expected = base ? `${base}/trace/${value.job_trace_id}` : null;
  let url: string | null = null;
  try { if (expected && typeof value.job_trace_url === 'string' && new URL(value.job_trace_url).href === expected) url = expected; } catch { /* Invalid upstream URL remains inert. */ }
  return { id: value.job_trace_id, url };
}

export function sanitizeTraceFields(value: unknown, trustedBase: string | null): unknown {
  if (Array.isArray(value)) return value.map(item => sanitizeTraceFields(item, trustedBase));
  if (!value || typeof value !== 'object') return value;
  const data = value as Record<string, unknown>;
  if (!('job_trace_id' in data) && !('job_trace_url' in data)) return value;
  const reference = safeTraceReference(data as TraceReference, trustedBase);
  return { ...data, job_trace_id: reference?.id ?? null, job_trace_url: reference?.url ?? null };
}
