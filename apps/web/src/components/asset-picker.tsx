'use client';
import { useEffect, useRef, useState } from 'react';
import type { AssetCatalog, AssetCatalogItem, SelectionRevision } from '../lib/selection-types';
import type { Api, Portfolio } from '../lib/portfolio-types';
import { dateTime } from '../lib/portfolio-types';

const kinds = { stock: 'Cổ phiếu', gold: 'Vàng', fund: 'Quỹ trái phiếu' };
const statuses = { UNKNOWN: 'Chưa xác minh dữ liệu', MISSING: 'Thiếu dữ liệu', QUARANTINED: 'Dữ liệu đang cách ly', FRESH: 'Dữ liệu trong hạn', STALE: 'Dữ liệu đã cũ' };
export function AssetPicker({ assets, selected, onChange, disabled = false }: { assets: AssetCatalogItem[]; selected: string[]; onChange: (ids: string[]) => void; disabled?: boolean }) {
  const [query, setQuery] = useState(''), [kind, setKind] = useState('');
  const rows = assets.filter(asset => (!kind || asset.kind === kind) && `${asset.asset_id} ${asset.display_name}`.toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')));
  const filtered = Boolean(query.trim() || kind);
  const selectedRows = rows.filter(asset => selected.includes(asset.asset_id)).length;
  return <fieldset className="asset-picker" disabled={disabled}><legend>Tài sản được phép cân nhắc</legend>
    <p className="muted small">Hệ thống có thể phân bổ 0% vào tài sản đã chọn. Dữ liệu cũ vẫn có thể lưu; điều kiện tính toán được kiểm tra riêng.</p>
    <div className="form-grid"><label>Tìm tài sản<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Mã hoặc tên tài sản"/></label><label>Loại tài sản<select value={kind} onChange={event => setKind(event.target.value)}><option value="">Tất cả</option>{Object.entries(kinds).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>
    <div className="asset-picker-toolbar">
      <div role="status" aria-live="polite"><strong>Đã chọn {selected.length}/{assets.length}</strong><span className="muted small">{filtered ? `${selectedRows}/${rows.length} kết quả đang hiển thị đã chọn · Thao tác chỉ áp dụng cho kết quả lọc.` : `${assets.length} tài sản có thể cân nhắc`}</span></div>
      <div className="asset-picker-actions">
        <button type="button" className="quiet" disabled={!rows.length || selectedRows === rows.length} onClick={() => onChange(assets.filter(asset => selected.includes(asset.asset_id) || rows.includes(asset)).map(asset => asset.asset_id))}>{filtered ? 'Chọn tất cả kết quả' : 'Chọn tất cả'}</button>
        <button type="button" className="quiet" disabled={!selectedRows} onClick={() => onChange(selected.filter(id => !rows.some(asset => asset.asset_id === id)))}>{filtered ? 'Bỏ chọn kết quả' : 'Bỏ chọn tất cả'}</button>
      </div>
    </div>
    <div className="risk-options asset-picker-options">{rows.map(asset => <label className="risk-choice" key={asset.asset_id}><input type="checkbox" value={asset.asset_id} checked={selected.includes(asset.asset_id)} onChange={event => onChange(assets.filter(item => event.target.checked ? selected.includes(item.asset_id) || item.asset_id === asset.asset_id : selected.includes(item.asset_id) && item.asset_id !== asset.asset_id).map(item => item.asset_id))}/><span><strong>{asset.asset_id}{asset.display_name !== asset.asset_id && <span className="asset-picker-name">{asset.display_name}</span>}</strong><small>{kinds[asset.kind]} · {statuses[asset.data_status]}</small><small>{asset.eligible_observation_date ? `Dữ liệu đến ${asset.eligible_observation_date} · ` : ''}{asset.age_days != null ? `${asset.age_days} ngày · ` : ''}ML {asset.ml_status === 'COVERED' ? 'đã phủ' : asset.ml_status === 'REVIEW_PENDING' ? 'chờ duyệt' : asset.ml_status === 'NOT_COVERED' ? 'chưa phủ' : 'chưa xác minh'}</small></span></label>)}</div>
    {!rows.length && <p role="status">Không có tài sản khớp bộ lọc.</p>}
  </fieldset>;
}

export function AssetSelectionEditor({ portfolio, catalog, api, onSaved }: { portfolio: Portfolio; catalog: AssetCatalog | null; api: Api; onSaved: () => void }) {
  const revision = portfolio.asset_selection;
  const [ids, setIds] = useState(revision?.candidate_asset_ids ?? []), [history, setHistory] = useState<SelectionRevision[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const intent = useRef({ body: '', key: '' });
  useEffect(() => { setIds(revision?.candidate_asset_ids ?? []); }, [revision]);
  useEffect(() => {
    let active = true;
    api<SelectionRevision[]>(`/api/v1/portfolios/${portfolio.id}/asset-selections`).then(rows => { if (active) setHistory(rows); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [api, portfolio.id, revision?.revision_id]);
  if (!revision) return null;
  async function save() {
    const body = JSON.stringify({ candidate_asset_ids: ids });
    if (intent.current.body !== body) intent.current = { body, key: crypto.randomUUID() };
    setBusy(true); setError('');
    try {
      await api(`/api/v1/portfolios/${portfolio.id}/asset-selections`, { method: 'POST', headers: { 'If-Match': `"${portfolio.version}"`, 'Idempotency-Key': intent.current.key }, body });
      intent.current = { body: '', key: '' }; onSaved();
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <section className="panel"><h2>Lựa chọn tài sản của danh mục</h2>{error && <p className="error" role="alert">{error}</p>}{catalog ? <AssetPicker assets={catalog.assets} selected={ids} onChange={setIds} disabled={busy || !catalog.selection_enabled}/> : <p>Chưa tải được catalog. Lựa chọn đã lưu: {revision.candidate_asset_ids.join(', ')}.</p>}
    <p className="muted small">Policy custom mixed cần VFF để đủ nhóm phòng thủ; không tự thêm tài sản. Sửa lựa chọn sẽ tăng phiên bản danh mục, các đề xuất cũ giữ dữ liệu đã ghim.</p>
    <button type="button" disabled={busy || !catalog?.selection_enabled || !ids.length || JSON.stringify(ids) === JSON.stringify(revision.candidate_asset_ids)} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu lựa chọn tài sản'}</button>
    <details><summary>Lịch sử lựa chọn · {history.length} phiên bản</summary><ol>{history.map(item => <li key={item.revision_id}>Phiên bản {item.portfolio_version} · {item.candidate_asset_ids.join(', ')} · {dateTime(item.created_at)}</li>)}</ol></details>
  </section>;
}
