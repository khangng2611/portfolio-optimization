'use client';

import { useState, type FormEvent } from 'react';
import { IconButton } from './action-controls';
import { JobStatus, OperationError, PageControls, ResourceState, useOperation, usePagedResource, usePolling, useResource } from './operation-ui';
import type { Api, PageApi } from '../lib/portfolio-types';
import { workspaceHash, type WorkspaceRoute } from '../lib/workspace-state';

const apiBase = '/api/v1/knowledge';
type Corpus = { id: string; name: string; status: string; version: number; hash: string; active: boolean; chunks: number; embedded_chunks: number };
type IndexJob = { id: string; corpus_id: string; status: string; error?: string; chunks?: number; embedded_chunks?: number };
type Manifest = { name: string; review: string; documents: { key: string; title: string; version: number; content_hash: string }[] };
type Decision = { corpus: Corpus; action: 'activate' | 'deactivate'; reason: string };

export function KnowledgeOperations({ route, api, fetchPage }: { route: WorkspaceRoute; api: Api; fetchPage: PageApi }) {
  const op = useOperation(api);
  const [offset, setOffset] = useState(0), [text, setText] = useState(''), [manifest, setManifest] = useState<Manifest | null>(null);
  const [validation, setValidation] = useState(''), [decision, setDecision] = useState<Decision | null>(null);
  const corpora = usePagedResource<Corpus>(fetchPage, `${apiBase}/corpora?limit=20&offset=${offset}`, op.revision);
  const job = useResource<IndexJob>(api, route.jobId ? `${apiBase}/indexing-jobs/${route.jobId}` : null, op.revision);
  usePolling(!!route.jobId && !!job.value && ['QUEUED', 'RUNNING', 'RETRY'].includes(job.value.status), op.refresh);

  function preview(event: FormEvent) {
    event.preventDefault();
    try {
      if (new TextEncoder().encode(text).length > 1_048_576) throw new Error('size');
      const value = JSON.parse(text) as Manifest;
      if (typeof value?.name !== 'string' || !value.name.trim() || typeof value.review !== 'string' ||
        !Array.isArray(value.documents) || !value.documents.length || !value.documents.every(doc => typeof doc?.title === 'string' && typeof doc.key === 'string' && Number.isInteger(doc.version) && typeof doc.content_hash === 'string')) throw new Error('manifest');
      setManifest(value); setValidation('');
    } catch {
      setValidation('Dán manifest JSON đã duyệt, có tên corpus, ghi chú review và danh sách tài liệu kèm phiên bản, checksum. Kích thước tối đa 1 MiB.');
    }
  }

  async function enqueue() {
    if (!manifest || op.busy) return;
    const receipt = await op.run<IndexJob>(`${apiBase}/indexing-jobs`, manifest);
    if (!receipt) return;
    setManifest(null); setText('');
    window.location.hash = workspaceHash({ view: 'knowledge', jobId: receipt.id });
  }

  async function applyDecision() {
    if (!decision || op.busy) return;
    if (await op.run(`${apiBase}/corpora/${decision.corpus.id}/${decision.action}`, { reason: decision.reason.trim() }, { version: decision.corpus.version })) setDecision(null);
  }

  return <div className="p1-operations">
    <div className="section-heading"><p className="muted">Theo dõi phiên bản nguồn phương pháp và trạng thái lập chỉ mục.</p><IconButton icon="refresh" label="Tải lại kho tri thức" onClick={op.refresh} disabled={op.busy}/></div>
    <OperationError error={op.error}/>
    {route.jobId && <section className="panel p1-section"><h2>Trạng thái lập chỉ mục</h2><ResourceState loading={!job.value && !job.error} error={job.error} empty={!job.value}>{job.value && <div role="status"><JobStatus value={job.value.status}/><p className="market-code">Tác vụ {job.value.id}</p><p>{job.value.chunks ?? 0} đoạn · {job.value.embedded_chunks ?? 0} đoạn có chỉ mục ngữ nghĩa</p>{job.value.error && <p className="notice warning">{job.value.error}</p>}</div>}</ResourceState></section>}
    <section className="panel p1-section"><h2>Phiên bản corpus</h2>
      <ResourceState loading={corpora.loading && !corpora.page} error={corpora.error} empty={!corpora.page?.items.length}>
        <div className="table-wrap mobile-cards"><table><caption className="sr-only">Các phiên bản nguồn đã lưu</caption><thead><tr><th scope="col">Corpus</th><th scope="col">Trạng thái</th><th scope="col">Lập chỉ mục</th><th scope="col">Quyết định</th></tr></thead><tbody>{corpora.page?.items.map(corpus => <tr key={corpus.id}>
          <th scope="row">{corpus.name}<small>v{corpus.version}</small><details><summary>Mã đối chiếu</summary><p className="market-code">{corpus.hash}</p></details></th>
          <td data-label="Trạng thái">{corpus.active ? <span className="badge success">Đang phục vụ</span> : <JobStatus value={corpus.status}/>}</td>
          <td data-label="Lập chỉ mục">{corpus.chunks} đoạn · {corpus.embedded_chunks} có chỉ mục ngữ nghĩa</td>
          <td data-label="Quyết định"><button className="quiet" disabled={op.busy || corpus.status !== 'READY'} onClick={() => setDecision({ corpus, action: corpus.active ? 'deactivate' : 'activate', reason: '' })}>{corpus.active ? 'Xem lại để dừng' : 'Xem lại để kích hoạt'}</button></td>
        </tr>)}</tbody></table></div>
      </ResourceState>
      <PageControls page={corpora.page} offset={offset} onPage={setOffset}/>
      {decision && <form className="p1-section" onSubmit={event => { event.preventDefault(); void applyDecision(); }}>
        <h3>{decision.action === 'activate' ? 'Xem lại kích hoạt nguồn' : 'Xem lại dừng phục vụ'}</h3>
        <p>{decision.corpus.name} · Phiên bản {decision.corpus.version}. Quyết định áp dụng cho lượt tra cứu tiếp theo.</p>
        <label>Lý do<textarea required minLength={3} maxLength={300} rows={2} value={decision.reason} onChange={event => setDecision({ ...decision, reason: event.target.value })}/></label>
        <div className="actions"><button disabled={op.busy || decision.reason.trim().length < 3}>Xác nhận {decision.action === 'activate' ? 'kích hoạt' : 'dừng'}</button><button type="button" className="quiet" onClick={() => setDecision(null)}>Quay lại</button></div>
      </form>}
    </section>
    <section className="panel p1-section"><h2>Nhập tài liệu đã duyệt</h2>{manifest ? <>
      <h3>{manifest.name}</h3><p>{manifest.review}</p><ul>{manifest.documents.map((doc, index) => <li key={index}><strong>{doc.title}</strong> · {doc.key} v{doc.version}<small className="price-revision">{doc.content_hash}</small></li>)}</ul>
      <p className="muted">Gửi yêu cầu lập chỉ mục. Corpus chỉ phục vụ sau khi hoàn tất và được kích hoạt.</p>
      <div className="actions"><button type="button" disabled={op.busy} onClick={() => void enqueue()}>Xác nhận nhập tài liệu</button><button type="button" className="quiet" disabled={op.busy} onClick={() => setManifest(null)}>Sửa manifest</button></div>
    </> : <form onSubmit={preview}>
      <label>Manifest JSON<textarea rows={6} required maxLength={1_048_576} value={text} onChange={event => setText(event.target.value)} aria-describedby={validation ? 'manifest-error' : 'manifest-help'}/></label>
      <p id="manifest-help" className="muted small">Dùng manifest có nội dung tiếng Việt công khai và nguồn HTTPS đã duyệt. Dịch vụ Kho tri thức kiểm tra nội dung, phiên bản và checksum khi nhận yêu cầu.</p>
      {validation && <p id="manifest-error" role="alert" className="error">{validation}</p>}
      <div className="actions"><button disabled={op.busy}>Xem lại yêu cầu nhập</button></div>
    </form>}</section>
  </div>;
}
