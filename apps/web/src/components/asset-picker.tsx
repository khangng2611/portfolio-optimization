'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { ChartNoAxesCombined, Check, ChevronDown, Funnel, Plus } from 'lucide-react';
import { SearchField, SelectField } from './list-fields';
import { assetKindName, type AssetCatalog, type AssetCatalogItem, type SelectionRevision } from '../lib/selection-types';
import type { Api, Portfolio } from '../lib/portfolio-types';
import { dateTime } from '../lib/portfolio-types';
import { shortDate } from '../lib/p1-types';
import { workspaceHash } from '../lib/workspace-state';

const kinds = assetKindName;
const statuses = { UNKNOWN: 'Chưa xác minh dữ liệu', MISSING: 'Thiếu dữ liệu', QUARANTINED: 'Dữ liệu đang cách ly', FRESH: 'Giá cách ngày kiểm tra tối đa 7 ngày', STALE: 'Dữ liệu đã cũ' };
const mlStatuses = { COVERED: 'Mô hình đã hỗ trợ', REVIEW_PENDING: 'Mô hình đang chờ duyệt', NOT_COVERED: 'Mô hình chưa hỗ trợ', UNKNOWN: 'Chưa xác minh hỗ trợ' };
function priceStatus(asset: AssetCatalogItem) {
  if (asset.eligible_observation_date) {
    const date = shortDate(asset.eligible_observation_date);
    if (asset.data_status === 'FRESH') return `Giá ngày ${date}`;
    if (asset.data_status === 'STALE') return `Dữ liệu đã cũ · Giá ngày ${date}`;
  }
  return statuses[asset.data_status];
}

function PriceHistoryLink({ assetId, portfolioId }: { assetId: string; portfolioId?: string }) {
  return <a className="asset-history-link" href={workspaceHash({ view: 'asset-prices', assetId, portfolioId })} target="_blank" rel="noopener" aria-label={`Lịch sử giá ${assetId} (mở thẻ mới)`} title="Mở lịch sử giá trong thẻ mới"><ChartNoAxesCombined className="action-icon" aria-hidden="true"/>Lịch sử giá</a>;
}

type PickerProps = { assets: AssetCatalogItem[]; selected: string[]; onChange: (ids: string[]) => void; disabled?: boolean; portfolioId?: string };

function toggleAsset(assets: AssetCatalogItem[], selected: string[], id: string) {
  if (selected.includes(id)) return selected.filter(item => item !== id);
  return assets.filter(item => item.asset_id === id || selected.includes(item.asset_id)).map(item => item.asset_id);
}

export function WizardAssetPicker(props: PickerProps) {
  const { assets, selected, onChange, disabled } = props;
  const [query, setQuery] = useState('');
  const [bulk, setBulk] = useState(false);
  const search = query.trim().toLocaleLowerCase('vi');
  const matches = assets.filter(asset => `${asset.asset_id} ${asset.display_name} ${asset.description ?? ''}`.toLocaleLowerCase('vi').includes(search));
  const ordered = matches.sort((a, b) =>
    Number(b.asset_id === 'VFF') - Number(a.asset_id === 'VFF') ||
    Number(selected.includes(b.asset_id)) - Number(selected.includes(a.asset_id)));
  const chosenIds = assets.filter(item => selected.includes(item.asset_id)).sort((a, b) => Number(b.asset_id === 'VFF') - Number(a.asset_id === 'VFF')).map(item => item.asset_id);
  // The opening view puts the defensive fund and current choices first. Search and bulk mode use the full catalog.
  const preview = ordered.filter((asset, index) => index < 2 || selected.includes(asset.asset_id));
  const visible = search ? ordered : preview;
  return <fieldset className="wizard-asset-picker" disabled={disabled}>
    <legend className="sr-only">Rổ tài sản tự chọn</legend>
    <div className="wizard-search-tools">
      {bulk ? <span className="muted small">Cần VFF cho phần phòng thủ khi tính đề xuất.</span> : <label htmlFor="wizard-asset-search">Tìm tài sản</label>}
      <button type="button" className="wizard-mode-switch" onClick={() => setBulk(!bulk)}>{bulk ? 'Xem danh sách đơn' : `Xem tất cả ${assets.length} mã`}</button>
    </div>
    {bulk ? <AssetPicker {...props}/> : <>
      <input id="wizard-asset-search" type="search" value={query} placeholder="Mã hoặc tên tài sản" onChange={event => setQuery(event.target.value)}/>
      <ul className="wizard-asset-list" aria-label={search ? 'Kết quả tìm tài sản' : 'Tài sản đang xem'}>{visible.map(asset => {
        const chosen = selected.includes(asset.asset_id);
        return <li key={asset.asset_id} className="wizard-asset" data-selected={chosen || undefined}>
          <div className="wizard-asset-id"><i data-asset-kind={asset.kind} aria-hidden="true"/><strong>{asset.asset_id}</strong><span>{kinds[asset.kind]}</span></div>
          {asset.description ? <details className="wizard-asset-info">
            <summary>{asset.display_name !== asset.asset_id ? asset.display_name : 'Mô tả tài sản'}<span className="sr-only"> · Xem mô tả {asset.asset_id}</span> <ChevronDown size={14} aria-hidden="true"/></summary><p>{asset.description}</p>
          </details> : asset.display_name !== asset.asset_id && <p className="wizard-asset-name">{asset.display_name}</p>}
          {asset.asset_id === 'VFF' && <p className="wizard-asset-reason">Cần VFF khi tính đề xuất.</p>}
          <button type="button" className="quiet wizard-asset-toggle" data-asset-id={asset.asset_id} aria-pressed={chosen}
            aria-label={chosen ? `Bỏ ${asset.asset_id} khỏi rổ tài sản` : `Thêm ${asset.asset_id} vào rổ tài sản`}
            onClick={() => onChange(toggleAsset(assets, selected, asset.asset_id))}>
            {chosen ? <Check size={16} aria-hidden="true"/> : <Plus size={16} aria-hidden="true"/>}{chosen ? 'Đã chọn' : 'Thêm'}
          </button>
        </li>;
      })}</ul>
      {!ordered.length && <p role="status">{assets.length ? 'Không tìm thấy tài sản khớp với từ khóa.' : 'Chưa có tài sản được hỗ trợ.'}</p>}
      <aside className="wizard-basket-summary">
        <h2>Rổ của bạn</h2><strong>{chosenIds.length ? chosenIds.join(' · ') : 'Chưa chọn mã'}</strong>
        <p>Mã đã chọn có thể nhận tỷ trọng 0%.</p>
      </aside>
    </>}
  </fieldset>;
}

export function AssetPicker({ assets, selected, onChange, disabled = false, portfolioId }: PickerProps) {
  const id = useId();
  const [query, setQuery] = useState(''), [kind, setKind] = useState('');
  const [basketVisible, setBasketVisible] = useState(false);
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
    onChange(toggleAsset(assets, selected, assetId));
    focusList(adding ? availableList.current : basketList.current, index);
  }
  function addAvailable() {
    onChange(assets.filter(asset => selected.includes(asset.asset_id) || available.includes(asset)).map(asset => asset.asset_id));
    focusList(availableList.current);
  }
  return <fieldset className="asset-picker" disabled={disabled}><legend>Chọn rổ tài sản</legend>
    <p className="asset-picker-help muted">Chọn mã để thêm hoặc bỏ khỏi rổ. Mã đã chọn vẫn có thể nhận tỷ trọng 0%.</p>
    <div className="asset-pane-shortcuts" role="group" aria-label="Danh sách đang xem">{([false, true] as const).map(chosen => <button key={String(chosen)} type="button" className="quiet list-action" aria-controls={`${id}-${chosen ? 'selected' : 'available'}-panel`} aria-pressed={basketVisible === chosen} onClick={() => setBasketVisible(chosen)}>{chosen ? `Rổ của bạn · ${selected.length}` : `Tài sản hỗ trợ · ${available.length}`}</button>)}</div>
    <div className="asset-picker-filters" data-mobile-hidden={basketVisible || undefined}>
      <SearchField label="Tìm tài sản để thêm" value={query} onChange={event => setQuery(event.target.value)} placeholder="Mã, tên hoặc mô tả"/>
      <SelectField label="Loại tài sản" icon={Funnel} value={kind} onChange={event => setKind(event.target.value)}>
        <option value="">Tất cả</option>
        {Object.entries(kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </SelectField>
    </div>
    <div className="asset-transfer">
      {([false, true] as const).map(chosen => {
        const rows = chosen ? basket : available;
        const titleId = `${id}-${chosen ? 'selected' : 'available'}`;
        return <section id={`${titleId}-panel`} className={`asset-transfer-panel${chosen ? ' asset-transfer-selected' : ''}${!rows.length ? ' asset-transfer-empty-panel' : ''}`} data-testid={chosen ? 'selected-assets' : 'available-assets'} data-mobile-hidden={basketVisible !== chosen || undefined} key={String(chosen)} aria-labelledby={titleId}>
          <div className="asset-transfer-header"><div><h3 id={titleId}>{chosen ? 'Rổ tài sản của bạn' : 'Tài sản hỗ trợ'}</h3><p className="muted small" role={chosen ? 'status' : undefined} aria-live={chosen ? 'polite' : undefined} aria-atomic={chosen ? true : undefined}>{chosen ? `Đã chọn ${selected.length}/${assets.length}` : `${available.length} mã ${filtered ? 'khớp bộ lọc, chưa chọn' : 'chưa chọn'}`}</p></div>
            <button type="button" className="quiet list-action" disabled={chosen ? !selected.length : !available.length} onClick={chosen ? () => { onChange([]); focusList(basketList.current); } : addAvailable}>{chosen ? 'Bỏ tất cả' : filtered ? 'Thêm tất cả kết quả' : 'Thêm tất cả'}</button>
          </div>
          <div className="asset-transfer-list" ref={chosen ? basketList : availableList} tabIndex={-1} role="region" aria-label={chosen ? 'Danh sách đã chọn' : 'Danh sách tài sản hỗ trợ'}>
            {rows.length ? <ul>{rows.map(asset => <li key={asset.asset_id} className="asset-transfer-row">
              <div className="asset-transfer-content">
                <div className="asset-transfer-name"><strong>{asset.asset_id}</strong>{asset.display_name !== asset.asset_id && <span>{asset.display_name}</span>}</div>
                {asset.description && <span className="asset-transfer-description" id={`${id}-${asset.asset_id}-description`}>{asset.description}</span>}
                <div className="asset-transfer-meta"><span className={`asset-data-${asset.data_status.toLowerCase()}`}>{kinds[asset.kind]} · {priceStatus(asset)}</span>
                  <PriceHistoryLink assetId={asset.asset_id} portfolioId={portfolioId}/>
                </div>
              </div>
              <button type="button" className="quiet list-action asset-transfer-action" data-asset-id={asset.asset_id} aria-label={chosen ? `Bỏ ${asset.asset_id} khỏi rổ tài sản` : `Thêm ${asset.asset_id} vào rổ tài sản`} aria-describedby={asset.description ? `${id}-${asset.asset_id}-description` : undefined} onClick={() => moveAsset(asset.asset_id, !chosen)}>{chosen ? 'Bỏ' : 'Thêm'}</button>
            </li>)}</ul> : <div className="asset-transfer-empty">{chosen ? <><strong>Rổ tài sản đang trống</strong><p>Chọn mã từ tập tài sản hỗ trợ để thêm vào rổ.</p></> : <p>{!assets.length ? 'Chưa có tài sản được hỗ trợ.' : filtered ? matches.length ? 'Các mã khớp bộ lọc đã có trong rổ.' : 'Không có tài sản khớp bộ lọc.' : 'Bạn đã thêm toàn bộ tài sản vào rổ.'}</p>}</div>}
          </div>
        </section>;
      })}
    </div>
    {filtered && !available.length && <button className="quiet list-action asset-clear-filter" data-mobile-hidden={basketVisible || undefined} type="button" onClick={() => { setQuery(''); setKind(''); }}>Xóa tìm kiếm và bộ lọc</button>}
    <p className="asset-picker-footnote muted small">Bạn vẫn có thể thêm mã có dữ liệu cũ vào rổ. Khi tính đề xuất, hệ thống kiểm tra lại dữ liệu của từng mã.</p>
    <details className="asset-picker-data"><summary>Xem dữ liệu từng mã</summary>
      <p className="muted small">Giá đủ mới khi đã có thể sử dụng tại thời điểm kiểm tra và được ghi nhận cách đó tối đa 7 ngày.</p>
      {assets.map(asset => <details key={asset.asset_id} className="asset-data-detail">
        <summary>{asset.asset_id} · {kinds[asset.kind]} · {priceStatus(asset)}</summary>
        {asset.display_name !== asset.asset_id && <p>{asset.display_name}</p>}
        {asset.description && <p className="muted">{asset.description}</p>}
        <dl>
          <div><dt>Ngày giá có thể dùng để tính</dt><dd>{shortDate(asset.eligible_observation_date)}</dd></div>
          {asset.latest_observation_date && asset.latest_observation_date !== asset.eligible_observation_date && <div><dt>Ngày ghi nhận gần nhất</dt><dd>{shortDate(asset.latest_observation_date)}</dd></div>}
          {asset.age_days != null && <div><dt>Khoảng cách đến ngày kiểm tra</dt><dd>{asset.age_days} ngày</dd></div>}
          {asset.checked_at && <div><dt>Kiểm tra lúc</dt><dd>{dateTime(asset.checked_at)}</dd></div>}
          {asset.available_at && <div><dt>Giá có thể sử dụng từ</dt><dd>{dateTime(asset.available_at)}</dd></div>}
          <div><dt>Hỗ trợ từ mô hình</dt><dd>{mlStatuses[asset.ml_status]}</dd></div>
        </dl>
        <PriceHistoryLink assetId={asset.asset_id} portfolioId={portfolioId}/>
      </details>)}</details>
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
  return <section className="panel asset-selection-editor"><h2>Lựa chọn tài sản</h2>{error && <p className="error" role="alert">{error}</p>}{catalog ? <AssetPicker portfolioId={portfolio.id} assets={catalog.assets} selected={ids} onChange={setIds} disabled={busy || !catalog.selection_enabled}/> : <p>Chưa tải được danh sách tài sản. Lựa chọn đã lưu: {revision.candidate_asset_ids.join(', ')}.</p>}
    <p className="muted small">Cần có quỹ trái phiếu VFF để tính đề xuất. Sau khi đổi tài sản, hãy tạo đề xuất mới để dùng danh sách vừa lưu.</p>
    <button type="button" disabled={busy || !catalog?.selection_enabled || !ids.length || JSON.stringify(ids) === JSON.stringify(revision.candidate_asset_ids)} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu lựa chọn tài sản'}</button>
    <p className="muted small asset-save-scope">Chỉ lưu rổ tài sản. Tên và vốn kế hoạch được lưu riêng ở phần Thông tin kế hoạch.</p>
    <details><summary>Lịch sử lựa chọn · {history.length} phiên bản</summary><ol>{history.map(item => <li key={item.revision_id}>Phiên bản {item.portfolio_version} · {item.candidate_asset_ids.join(', ')} · {dateTime(item.created_at)}</li>)}</ol></details>
  </section>;
}
