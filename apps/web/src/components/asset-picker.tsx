'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { ChartNoAxesCombined, Check, ChevronDown, Minus, Plus } from 'lucide-react';
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

export function AssetPicker(props: PickerProps) {
  const { assets, selected, onChange, disabled } = props;
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('');
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    const media = window.matchMedia('(min-width: 960px)');
    const sync = () => setDesktop(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);
  const search = query.trim().toLocaleLowerCase('vi');
  const matches = assets.filter(asset => (!kind || asset.kind === kind) && `${asset.asset_id} ${asset.display_name} ${asset.description ?? ''}`.toLocaleLowerCase('vi').includes(search));
  const ordered = matches.sort((a, b) =>
    Number(b.asset_id === 'VFF') - Number(a.asset_id === 'VFF') ||
    Number(selected.includes(b.asset_id)) - Number(selected.includes(a.asset_id)));
  const chosenAssets = assets.filter(item => selected.includes(item.asset_id)).sort((a, b) => Number(b.asset_id === 'VFF') - Number(a.asset_id === 'VFF'));
  const chosenIds = chosenAssets.map(item => item.asset_id);
  const available = desktop ? ordered.filter(item => !selected.includes(item.asset_id)) : ordered;
  const canExpand = !kind && !search && ordered.some((asset, index) => index >= 2 && !selected.includes(asset.asset_id));
  function assetRow(asset: AssetCatalogItem, index: number) {
    const chosen = selected.includes(asset.asset_id);
    return <li key={asset.asset_id} className="wizard-asset" data-preview-hidden={!expanded && !kind && !search && !chosen && index >= 2 || undefined} data-selected={chosen || undefined}>
      <div className="wizard-asset-id"><i data-asset-kind={asset.kind} aria-hidden="true"/><strong>{asset.asset_id}</strong><span>{kinds[asset.kind]}</span></div>
      {asset.description ? <details className="wizard-asset-info">
        <summary>{asset.display_name !== asset.asset_id ? asset.display_name : 'Mô tả tài sản'}<span className="sr-only"> · Xem mô tả {asset.asset_id}</span> <ChevronDown size={14} aria-hidden="true"/></summary><p>{asset.description}</p>
      </details> : asset.display_name !== asset.asset_id && <p className="wizard-asset-name">{asset.display_name}</p>}
      {asset.asset_id === 'VFF' && <p className="wizard-asset-reason">Cần VFF khi tính đề xuất.</p>}
      <button type="button" className="quiet wizard-asset-toggle" data-asset-id={asset.asset_id} aria-pressed={chosen}
        aria-label={chosen ? `Bỏ ${asset.asset_id} khỏi rổ tài sản` : `Thêm ${asset.asset_id} vào rổ tài sản`}
        onClick={event => {
          if (desktop && event.currentTarget === document.activeElement) {
            const row = event.currentTarget.closest('li');
            const nextRow = row?.nextElementSibling ?? row?.previousElementSibling;
            const focusTarget = nextRow?.querySelector<HTMLButtonElement>('button[data-asset-id]') ?? event.currentTarget.closest('fieldset')?.querySelector<HTMLInputElement>('input[type=search]');
            focusTarget?.focus({ preventScroll: true });
          }
          onChange(toggleAsset(assets, selected, asset.asset_id));
        }}>
        {chosen && desktop ? <Minus size={16} aria-hidden="true"/> : chosen ? <Check size={16} aria-hidden="true"/> : <Plus size={16} aria-hidden="true"/>}{chosen ? (desktop ? 'Bỏ' : 'Đã chọn') : 'Thêm'}
      </button>
    </li>;
  }
  const FilterPanel = desktop ? 'div' : 'details';
  return <fieldset className="wizard-asset-picker" disabled={disabled}>
    <legend className="sr-only">Rổ tài sản tự chọn</legend>
    <div className="wizard-search-tools">
      <label htmlFor="wizard-asset-search">Tìm tài sản</label>
      {canExpand && <button type="button" className="wizard-mode-switch" aria-expanded={expanded} aria-controls={listId} onClick={() => setExpanded(!expanded)}>{expanded ? 'Thu gọn' : `Xem tất cả ${assets.length} mã`}</button>}
    </div>
      <input id="wizard-asset-search" type="search" value={query} placeholder="Mã hoặc tên tài sản" onChange={event => setQuery(event.target.value)}/>
      <FilterPanel className="wizard-bulk-tools">
        {!desktop && <summary>Lọc và chọn nhiều mã</summary>}
        <label>Loại tài sản<select value={kind} onChange={event => setKind(event.target.value)}><option value="">Tất cả</option>{Object.entries(kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <button type="button" className="quiet" disabled={!matches.some(item => !selected.includes(item.asset_id))} onClick={() => {
          const ids = new Set([...selected, ...matches.map(item => item.asset_id)]);
          onChange(assets.filter(item => ids.has(item.asset_id)).map(item => item.asset_id));
        }}>{search || kind ? 'Thêm tất cả kết quả' : 'Thêm tất cả'}</button>
        <button type="button" className="quiet" disabled={!selected.length} onClick={() => onChange([])}>Bỏ tất cả</button>
      </FilterPanel>
      <div className="wizard-candidates">
        {desktop && <h2>Tài sản có thể thêm · {available.length}</h2>}
        <ul id={listId} className="wizard-asset-list" aria-label={search ? 'Kết quả tìm tài sản' : 'Tài sản đang xem'}>
          {available.map(assetRow)}
          {!available.length && <li><p role="status">{!assets.length ? 'Chưa có tài sản được hỗ trợ.' : !ordered.length ? 'Không tìm thấy tài sản khớp với từ khóa.' : 'Các mã phù hợp đều đã có trong rổ.'}</p></li>}
        </ul>
      </div>
      <aside className="wizard-basket-summary">
        <h2>Rổ của bạn{desktop && ` · ${chosenIds.length}`}</h2>
        {desktop ? <ul className="wizard-asset-list" aria-label="Tài sản đã chọn">
          {chosenAssets.length ? chosenAssets.map(assetRow) : <li>Chưa chọn mã</li>}
        </ul> : <strong>{chosenIds.length ? chosenIds.join(' · ') : 'Chưa chọn mã'}</strong>}
        {!desktop && <p>Mã đã chọn có thể nhận tỷ trọng 0%.</p>}
      </aside>
      {desktop && <p className="wizard-selection-note muted small">Mã đã chọn có thể nhận tỷ trọng 0%.</p>}
  </fieldset>;
}

function AssetData({assets, portfolioId}: {assets: AssetCatalogItem[]; portfolioId: string}) {
  return (
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
  );
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
  return <section className="panel asset-selection-editor"><h2>Lựa chọn tài sản</h2>{error && <p className="error" role="alert">{error}</p>}{catalog ? <AssetPicker assets={catalog.assets} selected={ids} onChange={setIds} disabled={busy || !catalog.selection_enabled}/> : <p>Chưa tải được danh sách tài sản. Lựa chọn đã lưu: {revision.candidate_asset_ids.join(', ')}.</p>}
    <p className="muted small">Cần có quỹ trái phiếu VFF để tính đề xuất. Sau khi đổi tài sản, hãy tạo đề xuất mới để dùng danh sách vừa lưu.</p>
    <button type="button" disabled={busy || !catalog?.selection_enabled || !ids.length || JSON.stringify(ids) === JSON.stringify(revision.candidate_asset_ids)} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu lựa chọn tài sản'}</button>
    <p className="muted small asset-save-scope">Chỉ lưu rổ tài sản. Tên và vốn kế hoạch được lưu riêng ở phần Thông tin kế hoạch.</p>
    {catalog && <AssetData assets={catalog.assets} portfolioId={portfolio.id}/>}
    <details><summary>Lịch sử lựa chọn · {history.length} phiên bản</summary><ol>{history.map(item => <li key={item.revision_id}>Phiên bản {item.portfolio_version} · {item.candidate_asset_ids.join(', ')} · {dateTime(item.created_at)}</li>)}</ol></details>
  </section>;
}
