import { safeTraceReference, type TraceReference } from '../lib/job-trace';

export function JobTrace({ reference, viewerBase }: { reference: TraceReference; viewerBase: string | null }) {
  const current = safeTraceReference(reference, viewerBase);
  if (!current) return null;
  return <div className="job-trace"><small>Trace của công việc: <code>{current.id}</code></small>{current.url && <a href={current.url} target="_blank" rel="noopener noreferrer">Xem trace trong Jaeger ↗</a>}</div>;
}
