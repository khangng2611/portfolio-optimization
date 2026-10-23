import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { JobTrace } from '../src/components/job-trace';
import { safeTraceReference, traceViewerBase } from '../src/lib/job-trace';

const id = 'a'.repeat(32);
describe('job trace reference presentation', () => {
  it('renders a trusted job link with its origin ID and an isolated new tab', () => {
    const html = renderToStaticMarkup(<JobTrace reference={{ job_trace_id: id, job_trace_url: `http://localhost:16686/trace/${id}` }} viewerBase="http://localhost:16686"/>);
    expect(html).toContain(`href="http://localhost:16686/trace/${id}"`);
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('Xem trace trong Jaeger');
    expect(html).toContain(id);
  });
  it('shows no fabricated link or ID for legacy jobs', () => {
    expect(renderToStaticMarkup(<JobTrace reference={{ job_trace_id: null, job_trace_url: null }} viewerBase="http://localhost:16686"/>)).toBe('');
  });
  it.each(['javascript:alert(1)', `https://evil.test/trace/${id}`, `http://localhost:16686/trace/${'b'.repeat(32)}`, `http://localhost:16686/trace/${id}?token=private`, `http://localhost:16686/trace/${id}#secret`])('keeps an untrusted returned URL inert: %s', url => {
    const html = renderToStaticMarkup(<JobTrace reference={{ job_trace_id: id, job_trace_url: url }} viewerBase="http://localhost:16686"/>);
    expect(html).not.toContain('<a');
    expect(html).toContain(id);
    expect(html).not.toContain('private');
  });
  it('permits HTTPS only against the configured server viewer and preserves path prefixes', () => {
    expect(safeTraceReference({ job_trace_id: id, job_trace_url: `https://traces.example.test/jaeger/trace/${id}` }, 'https://traces.example.test/jaeger')).toEqual({ id, url: `https://traces.example.test/jaeger/trace/${id}` });
    expect(safeTraceReference({ job_trace_id: id, job_trace_url: `https://evil.test/trace/${id}` }, 'https://traces.example.test')).toEqual({ id, url: null });
    for (const value of ['http://public.test:16686', 'http://localhost:3000', 'https://user:secret@traces.test', 'https://traces.test/?token=secret']) expect(traceViewerBase(value)).toBeNull();
  });
});
