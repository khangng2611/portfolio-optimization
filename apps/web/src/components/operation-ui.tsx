'use client';
import { IconButton } from './action-controls';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, type Api, type Page, type PageApi } from '../lib/portfolio-types';
import { marketStatus } from '../lib/market-types';

export function OperationError({ error }: { error: string }) { const ref = useRef<HTMLDivElement>(null); useEffect(() => { if (error) ref.current?.focus(); }, [error]); return error ? <div className="error" role="alert" tabIndex={-1} ref={ref}><strong>Chưa thể hoàn tất yêu cầu</strong><p>{error}</p></div> : null; }
export function JobStatus({ value }: { value: string }) { const labels: Record<string, string> = { CANDIDATE: 'Chờ review', APPROVED: 'Đã duyệt', REJECTED: 'Đã từ chối' }; return <span className={`badge ${['SUCCEEDED', 'APPROVED', 'PASS'].includes(value) ? 'success' : ['FAILED', 'REJECTED', 'QUARANTINED'].includes(value) ? 'danger' : ''}`}>{labels[value] ?? marketStatus(value)}</span>; }
export function ResourceState({ loading, error, empty, children }: { loading: boolean; error: string; empty: boolean; children: ReactNode }) { return error ? <OperationError error={error}/> : loading ? <p className="muted" role="status">Đang tải dữ liệu…</p> : empty ? <div className="empty-state compact"><h3>Chưa có bản ghi</h3><p>Các yêu cầu và kết quả đã lưu sẽ xuất hiện tại đây.</p></div> : children; }
export function PageControls({ page, offset, onPage }: { page: Page<unknown> | null; offset: number; onPage: (offset: number) => void }) { return <div className="pagination"><IconButton icon="previous" label="Trang trước" disabled={!page || !offset} onClick={() => onPage(Math.max(0, offset - page!.limit))}/><span>{page ? `${offset + (page.items.length ? 1 : 0)}–${offset + page.items.length} / ${page.total} kết quả` : 'Đang tải…'}</span><IconButton icon="next" label="Trang sau" disabled={!page || offset + page.limit >= page.total} onClick={() => onPage(offset + page!.limit)}/></div>; }
export function usePagedResource<T>(fetchPage: PageApi, path: string, revision: number) {
  const [page, setPage] = useState<Page<T> | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState(''); const previous = useRef(path);
  useEffect(() => { let active = true; if (previous.current !== path) { previous.current = path; setPage(null); } setLoading(true); setError(''); fetchPage<T>(path).then(data => { if (active) setPage(data); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [fetchPage, path, revision]);
  return { page, loading, error };
}
export function useResource<T>(api: Api, path: string | null, revision: number) {
  const [value, setValue] = useState<T | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false); const previous = useRef(path);
  useEffect(() => { let active = true; if (previous.current !== path || !path) { previous.current = path; setValue(null); } setError(''); if (!path) return; setLoading(true); api<T>(path).then(data => { if (active) setValue(data); }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [api, path, revision]);
  return { value, error, loading };
}
export function useOperation(api: Api) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [revision, setRevision] = useState(0); const intents = useRef(new Map<string, string>());
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  const run = useCallback(async <T,>(path: string, body: unknown, options: { method?: 'POST' | 'PATCH'; version?: number } = {}): Promise<T | null> => {
    const digest = JSON.stringify({ path, body, ...options }); let key = intents.current.get(digest); if (!key) { key = crypto.randomUUID(); intents.current.set(digest, key); }
    setBusy(true); setError(''); try { const result = await api<T>(path, { method: options.method ?? 'POST', headers: { 'idempotency-key': key, ...(options.version !== undefined ? { 'if-match': `"${options.version}"` } : {}) }, body: JSON.stringify(body) }); intents.current.delete(digest); refresh(); return result; } catch (err) { if (err instanceof ApiError && err.status === 412) setError('Thông tin đã thay đổi. Tải lại phiên bản mới trước khi xác nhận.'); else setError((err as Error).message); return null; } finally { setBusy(false); }
  }, [api, refresh]);
  return { busy, error, revision, refresh, run };
}
export function usePolling(enabled: boolean, refresh: () => void) { useEffect(() => { if (!enabled) return; const timer = setInterval(refresh, 2000); return () => clearInterval(timer); }, [enabled, refresh]); }
