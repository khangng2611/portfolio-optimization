'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { ActionIcon } from './action-controls';
import type { AssetCatalog, AssetCatalogItem, SelectionRevision } from '../lib/selection-types';
import type { Api, Portfolio } from '../lib/portfolio-types';
import { dateTime } from '../lib/portfolio-types';

const kinds = { stock: 'Cổ phiếu', gold: 'Vàng', fund: 'Quỹ trái phiếu' };
const statuses = { UNKNOWN: 'Chưa xác minh dữ liệu', MISSING: 'Thiếu dữ liệu', QUARANTINED: 'Dữ liệu đang cách ly', FRESH: 'Dữ liệu trong hạn', STALE: 'Dữ liệu đã cũ' };
const mlStatuses = { COVERED: 'đã phủ', REVIEW_PENDING: 'chờ duyệt', NOT_COVERED: 'chưa phủ', UNKNOWN: 'chưa xác minh' };
export function AssetPicker({ assets, selected, onChange, disabled = false }: { assets: AssetCatalogItem[]; selected: string[]; onChange: (ids: string[]) => void; disabled?: boolean }) {
  const id = useId();
  const [query, setQuery] = useState(''), [kind, setKind] = useState('');
  const availableList = useRef<HTMLDivElement>(null), basketList = useRef<HTMLDivElement>(null);
  const matches = assets.filter(asset => (!kind || asset.kind === kind) && `${asset.asset_id} ${asset.display_name} ${asset.description ?? ''}`.toLocaleLowerCase('vi').includes(query.trim().toLocaleLowerCase('vi')));
  const available = matches.filter(asset => !selected.includes(asset.asset_id));
  const basket = assets.filter(asset => selected.includes(asset.asset_id));
  const filtered = Boolean(query.trim() || kind);
  function focusList(list: HTMLDivElement | null, index = 0) {
    const previousFocus = document.activeElement;
    requestAnimationFrame(() => {
      if (document.activeElement !== previousFocus && document.activeElement !== document.body) return;
      const buttons = list?.querySelectorAll<HTMLButtonElement>('button[data-asset-id]');
      (buttons?.[Math.min(index, buttons.length - 1)] ?? list)?.focus({ preventScroll: true });
    });
  }
  function moveAsset(assetId: string, adding: boolean) {
    const rows = adding ? available : basket;
    const index = rows.findIndex(asset => asset.asset_id === assetId);
    onChange(adding ? assets.filter(asset => selected.includes(asset.asset_id) || asset.asset_id === assetId).map(asset => asset.asset_id) : selected.filter(value => value !== assetId));
    focusList(adding ? availableList.current : basketList.current, index);
  }
  function addAvailable() {
    onChange(assets.filter(asset => selected.includes(asset.asset_id) || available.includes(asset)).map(asset => asset.asset_id));
    focusList(availableList.current);
  }
  return <fieldset className="asset-picker" disabled={disabled}><legend>Chọn rổ tài sản</legend>
    <p className="asset-picker-help muted">Bấm vào mã để thêm hoặc bỏ khỏi rổ. Bạn có thể thay đổi trước khi xác nhận.</p>
    <div className="asset-pane-shortcuts" aria-label="Chuyển đến khung tài sản">{([false, true] as const).map(chosen => <button key={String(chosen)} type="button" className="quiet" aria-controls={`${id}-${chosen ? 'selected' : 'available'}-panel`} onClick={() => { const list = chosen ? basketList.current : availableList.current; list?.closest('section')?.scrollIntoView({ block: 'start' }); list?.focus({ preventScroll: true }); }}>{chosen ? `Rổ của bạn · ${selected.length}` : `Tài sản hỗ trợ · ${available.length}`}</button>)}</div>
    <div className="asset-picker-filters"><label>Tìm tài sản để thêm<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Mã, tên hoặc mô tả"/></label><label>Loại tài sản<select value={kind} onChange={event => setKind(event.target.value)}><option value="">Tất cả</option>{Object.entries(kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
    <div className="asset-transfer">
      {([false, true] as const).map(chosen => {
        const rows = chosen ? basket : available;
        const titleId = `${id}-${chosen ? 'selected' : 'available'}`;
        return <section id={`${titleId}-panel`} className={`asset-transfer-panel${chosen ? ' asset-transfer-selected' : ''}${!rows.length ? ' asset-transfer-empty-panel' : ''}`} data-testid={chosen ? 'selected-assets' : 'available-assets'} key={String(chosen)} aria-labelledby={titleId}>
          <div className="asset-transfer-header"><div><h3 id={titleId}>{chosen ? 'Rổ tài sản của bạn' : 'Tài sản hỗ trợ'}</h3><p className="muted small" role={chosen ? 'status' : undefined} aria-live={chosen ? 'polite' : undefined} aria-atomic={chosen ? true : undefined}>{chosen ? `Đã chọn ${selected.length}/${assets.length}` : `${available.length} mã ${filtered ? 'khớp bộ lọc, chưa chọn' : 'chưa chọn'}`}</p></div>
            <button type="button" className="quiet" disabled={chosen ? !selected.length : !available.length} onClick={chosen ? () => { onChange([]); focusList(basketList.current); } : addAvailable}>{chosen ? 'Bỏ tất cả' : filtered ? 'Thêm tất cả kết quả' : 'Thêm tất cả'}</button>
          </div>
          <div className="asset-transfer-list" ref={chosen ? basketList : availableList} tabIndex={-1} role="region" aria-label={chosen ? 'Danh sách đã chọn' : 'Danh sách tài sản hỗ trợ'}>
            {rows.length ? <ul>{rows.map(asset => <li key={asset.asset_id}><button type="button" className="asset-transfer-row" data-asset-id={asset.asset_id} aria-label={chosen ? `Bỏ ${asset.asset_id} khỏi rổ tài sản` : `Thêm ${asset.asset_id} vào rổ tài sản`} aria-describedby={`${id}-${asset.asset_id}-description`} onClick={() => moveAsset(asset.asset_id, !chosen)}>
              <span className="asset-transfer-content"><span className="asset-transfer-name"><strong>{asset.asset_id}</strong>{asset.display_name !== asset.asset_id && <span>{asset.display_name}</span>}</span>
                <span className="asset-transfer-description" id={`${id}-${asset.asset_id}-description`} title={asset.description || undefined}>{asset.description || 'Chưa có mô tả từ nguồn dữ liệu.'}</span>
                <span className={`asset-transfer-metadata asset-data-${asset.data_status.toLowerCase()}`}>{kinds[asset.kind]} · {statuses[asset.data_status]}</span>
              </span><span className="asset-transfer-action"><ActionIcon name={chosen ? 'previous' : 'next'}/></span>
            </button></li>)}</ul> : <div className="asset-transfer-empty">{chosen ? <><strong>Rổ tài sản đang trống</strong><p>Chọn mã từ tập tài sản hỗ trợ để thêm vào rổ.</p></> : <p>{!assets.length ? 'Chưa có tài sản được hỗ trợ.' : filtered ? matches.length ? 'Các mã khớp bộ lọc đã có trong rổ.' : 'Không có tài sản khớp bộ lọc.' : 'Bạn đã thêm toàn bộ tài sản vào rổ.'}</p>}</div>}
          </div>
        </section>;
      })}
    </div>
    {filtered && !available.length && <button className="quiet asset-clear-filter" type="button" onClick={() => { setQuery(''); setKind(''); }}>Xóa tìm kiếm và bộ lọc</button>}
    <p className="asset-picker-footnote muted small">Hệ thống có thể phân bổ 0% vào tài sản đã chọn. Dữ liệu cũ vẫn có thể lưu; điều kiện tính toán được kiểm tra riêng.</p>
    <details className="asset-picker-data"><summary>Xem dữ liệu và xác minh từng mã</summary><p className="muted small">ML coverage và điều kiện dùng tài sản là hai thông tin khác nhau. Chưa phủ ML không đồng nghĩa không dùng được; khả năng tạo đề xuất được kiểm tra riêng theo policy.</p>{assets.map(asset => <details key={asset.asset_id} className="asset-data-detail"><summary>{asset.asset_id} · {kinds[asset.kind]} · {statuses[asset.data_status]}</summary><p>{asset.display_name}</p><p className="muted">{asset.description || 'Chưa có mô tả từ nguồn dữ liệu.'}</p><dl><div><dt>Trạng thái ML</dt><dd>ML {mlStatuses[asset.ml_status]}</dd></div><div><dt>Ngày dữ liệu đủ điều kiện</dt><dd>{asset.eligible_observation_date ?? 'Chưa ghi nhận'}</dd></div>{asset.latest_observation_date && <div><dt>Ngày quan sát gần nhất</dt><dd>{asset.latest_observation_date}</dd></div>}{asset.age_days != null && <div><dt>Tuổi dữ liệu</dt><dd>{asset.age_days} ngày</dd></div>}{asset.checked_at && <div><dt>Ngày kiểm tra</dt><dd>{dateTime(asset.checked_at)}</dd></div>}{asset.available_at && <div><dt>Khả dụng từ</dt><dd>{dateTime(asset.available_at)}</dd></div>}<div><dt>Đơn vị</dt><dd>{asset.unit} · {asset.currency}</dd></div><div><dt>Phiên bản catalog</dt><dd>{asset.catalog_version}</dd></div></dl></details>)}</details>
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
  return <section className="panel asset-selection-editor"><h2>Lựa chọn tài sản</h2>{error && <p className="error" role="alert">{error}</p>}{catalog ? <AssetPicker assets={catalog.assets} selected={ids} onChange={setIds} disabled={busy || !catalog.selection_enabled}/> : <p>Chưa tải được catalog. Lựa chọn đã lưu: {revision.candidate_asset_ids.join(', ')}.</p>}
    <p className="muted small">Policy custom mixed cần VFF để đủ nhóm phòng thủ; không tự thêm tài sản. Sửa lựa chọn sẽ tăng phiên bản danh mục, các đề xuất cũ giữ dữ liệu đã ghim.</p>
    <button type="button" disabled={busy || !catalog?.selection_enabled || !ids.length || JSON.stringify(ids) === JSON.stringify(revision.candidate_asset_ids)} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu lựa chọn tài sản'}</button>
    <p className="muted small asset-save-scope">Chỉ lưu rổ tài sản. Tên và vốn kế hoạch được lưu riêng ở phần Thông tin kế hoạch.</p>
    <details><summary>Lịch sử lựa chọn · {history.length} phiên bản</summary><ol>{history.map(item => <li key={item.revision_id}>Phiên bản {item.portfolio_version} · {item.candidate_asset_ids.join(', ')} · {dateTime(item.created_at)}</li>)}</ol></details>
  </section>;
}
