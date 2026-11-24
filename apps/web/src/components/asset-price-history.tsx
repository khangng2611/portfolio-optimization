'use client';

import { useEffect, useState, type Ref } from 'react';
import { ApiError, dateTime, type Api } from '../lib/portfolio-types';
import { marketCutoffDate, marketPrice } from '../lib/market-types';
import { assetKindName, type AssetCatalogItem } from '../lib/selection-types';
import { allocationPriceKey, assetIdPattern, workspaceHash } from '../lib/workspace-state';
import { PriceChart, type PriceObservation } from './price-chart';

type PriceSeries = { provider: string; price_type: string; price_basis: string; unit: string; source_unit: string; observations: PriceObservation[] };
type PriceHistory = { asset_id: string; as_of: string; series: PriceSeries[] };
const unitName: Record<string, string> = { 'VND/share': '₫/cổ phiếu', 'VND/tael': '₫/lượng', 'VND/unit': '₫/chứng chỉ quỹ' };
const sourceName = (series: PriceSeries) => [series.provider, series.price_type, series.price_basis, series.unit, series.source_unit].join(' · ');

const priceTypes: Record<string, string> = { close: 'Giá đóng cửa', nav: 'NAV', bid: 'Giá mua', ask: 'Giá bán', midpoint: 'Giá trung điểm' };
const priceBases: Record<string, string> = { provider_adjusted: 'Đã điều chỉnh', raw_close: 'Chưa điều chỉnh', nav: 'Giá trị tài sản ròng' };
const displaySource = (series: PriceSeries) => [series.provider === 'kbs-direct-v1' ? 'KBS' : series.provider, priceTypes[series.price_type] ?? series.price_type, priceBases[series.price_basis] ?? series.price_basis].join(' · ');
const periods = [[30, '30 ngày'], [90, '90 ngày'], [180, '180 ngày'], [365, '1 năm']] as const;
const defaultAsset = 'FPT';

export function AssetPriceHistory({ api, assetId: linkedAsset, assets, ownerKey, portfolioId, proposalId, returnView, headingRef }: { headingRef?: Ref<HTMLHeadingElement>; api: Api; assetId?: string; assets?: AssetCatalogItem[]; ownerKey: string; portfolioId?: string; proposalId?: string; returnView?: 'overview' }) {
  const storageKey = `portfolio.last-price-asset:${ownerKey}`;
  const [lastAsset, setLastAsset] = useState(() => {
    try {
      const saved = window.localStorage.getItem(storageKey);
      if (saved && assetIdPattern.test(saved)) return saved;
    } catch { /* Browser storage is optional. */ }
    return defaultAsset;
  });
  const assetId = linkedAsset ?? lastAsset;
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const viewport = window.matchMedia('(min-width: 1024px)');
    const sync = () => setWide(viewport.matches);
    sync();
    viewport.addEventListener('change', sync);
    return () => viewport.removeEventListener('change', sync);
  }, []);
  const [range, setRange] = useState(90), [source, setSource] = useState(''), [retry, setRetry] = useState(0);
  const [data, setData] = useState<PriceHistory>(), [failure, setFailure] = useState(0);
  const asset = assets?.find(item => item.asset_id === assetId);
  useEffect(() => {
    if (linkedAsset && portfolioId && proposalId) {
      try { sessionStorage.setItem(allocationPriceKey(ownerKey, portfolioId, proposalId), linkedAsset); } catch { /* Optional context for chat suggestions. */ }
    }
  }, [linkedAsset, ownerKey, portfolioId, proposalId]);
  useEffect(() => {
    let active = true;
    setData(undefined); setFailure(0);
    const end = new Date(), start = new Date(end);
    start.setUTCDate(start.getUTCDate() - range);
    const query = new URLSearchParams({ asset_id: assetId, start_date: marketCutoffDate(start), end_date: marketCutoffDate(end) });
    api<PriceHistory>(`/api/v1/market/price-series?${query}`).then(result => {
      if (!active) return;
      if (result.asset_id !== assetId) { setFailure(502); return; }
      setData(result);
      setLastAsset(assetId);
      try { window.localStorage.setItem(storageKey, assetId); } catch { /* Browser storage is optional. */ }
    }).catch(error => {
      if (!active) return;
      const status = error instanceof ApiError ? error.status : 503;
      if (status === 404 && !linkedAsset && assetId !== defaultAsset) setLastAsset(defaultAsset);
      else setFailure(status);
    });
    return () => { active = false; };
  }, [api, assetId, linkedAsset, range, retry, storageKey]);

  const series = data?.asset_id === assetId ? data.series : [];
  const selected = series.find(item => sourceName(item) === source) ?? series[0];
  const unit = selected && (unitName[selected.unit] ?? selected.unit);
  const assetSelect = <label>Tài sản<select value={assetId} onChange={event => { window.location.hash = workspaceHash({ view: 'asset-prices', assetId: event.target.value, portfolioId, proposalId, returnView }); }}>
        {!asset && <option value={assetId}>{assetId}</option>}{assets?.map(item => <option key={item.asset_id} value={item.asset_id}>{item.asset_id}</option>)}
      </select></label>;
  const toolbar = <div className="price-history-toolbar">
      <div className="price-periods" role="group" aria-label="Khoảng thời gian">
        {periods.map(([days, label]) => <button type="button" key={days} className="quiet" aria-pressed={range === days} onClick={() => setRange(days)}>{label}</button>)}
      </div>
      {data && selected && data.series.length > 1 && <label>Chuỗi giá<select value={sourceName(selected)} onChange={event => setSource(event.target.value)}>{data.series.map(series => <option key={sourceName(series)} value={sourceName(series)}>{displaySource(series)} · {series.source_unit}</option>)}</select></label>}
    </div>;
  const readTime = data?.asset_id === assetId && <p className="small muted">Đọc dữ liệu lúc {dateTime(data.as_of)} (GMT+7).</p>;
  return <section className="panel asset-price-history" data-wide={wide || undefined} aria-label="Giá tài sản">
    <div className="price-history-header">
      <div><h1 ref={headingRef} tabIndex={-1}>{assetId} · Lịch sử giá</h1>{asset && <p className="muted">{asset.display_name !== assetId && `${asset.display_name} · `}{assetKindName[asset.kind]}</p>}</div>
      {wide && assetSelect}
    </div>
    {wide && toolbar}
    {failure ? <aside className="notice warning" role="alert"><p>{failure === 403 ? 'Tài khoản chưa có quyền đọc dữ liệu thị trường.' : failure === 404 ? 'Chưa có mã này trong dữ liệu thị trường.' : failure === 409 ? 'Hãy chọn khoảng thời gian ngắn hơn.' : 'Chưa tải được dữ liệu giá.'}</p>{failure >= 500 && <button type="button" className="quiet" onClick={() => setRetry(value => value + 1)}>Thử lại</button>}</aside>
    : data?.asset_id !== assetId ? <p className="price-chart-state" role="status">Đang tải giá thị trường…</p> : !selected?.observations.length ? <p className="price-chart-state" role="status">Chưa có dữ liệu giá trong khoảng đã chọn.</p> : <div className="price-series-card">
        <PriceChart key={`${range}:${sourceName(selected)}`} observations={selected.observations} unit={unit} periodDays={range} wide={wide}/>
        <p className="price-source-summary">Nguồn {displaySource(selected)} · {unit}</p>
        <p className="muted small price-source-note">Đề xuất phân bổ dùng dữ liệu tại ngày ghi trên kết quả.</p>
    </div>}
    {wide && readTime}
    {portfolioId && <p><a className="button quiet price-history-back" href={workspaceHash({ view: returnView ?? (proposalId ? 'proposal' : 'overview'), portfolioId, proposalId })}>Trở lại phân bổ</a></p>}
    {!wide && <details className="allocation-details price-filters"><summary>Đổi mã, khoảng thời gian và nguồn</summary>{assetSelect}{toolbar}{readTime}</details>}
    {selected && selected.observations.length > 0 && (
      <details className="allocation-details"><summary>Xem bảng giá theo ngày</summary><div className="table-wrap mobile-cards"><table><caption>{assetId} · {displaySource(selected)}</caption><thead><tr><th scope="col">Ngày quan sát</th><th scope="col">Giá</th><th scope="col">Khả dụng từ (GMT+7)</th></tr></thead><tbody>
        {[...selected.observations].reverse().map(row => <tr key={row.revision_id}><th scope="row">{row.date}</th><td data-label="Giá">{marketPrice(row.price_vnd)}</td><td data-label="Khả dụng từ">{dateTime(row.available_at)}</td></tr>)}
      </tbody></table></div></details>
    )}
  </section>;
}
