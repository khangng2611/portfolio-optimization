'use client';

import { useId, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { marketPrice } from '../lib/market-types';

export type PriceObservation = { date: string; price_vnd: string; revision: number; revision_id: string; available_at: string };
const day = 86_400_000;
const shortDate = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', timeZone: 'UTC' });
const axisYearDate = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: '2-digit', timeZone: 'UTC' });
const fullDate = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' });
const axisPrice = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 6 });
const compactPrice = new Intl.NumberFormat('vi-VN', { notation: 'compact', maximumFractionDigits: 2 });
const changeFormat = new Intl.NumberFormat('vi-VN', { style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2, minimumFractionDigits: 2 });

function priceTicks(min: number, max: number) {
  const rough = Math.max(.000001, (max - min || max * .04) / 4);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const multiple = [1, 2, 2.5, 5, 10].find(value => value >= rough / magnitude) ?? 10;
  const step = magnitude * multiple;
  const padding = min === max ? step * 2 : step * .08;
  const low = Math.max(0, Math.floor((min - padding) / step));
  const high = Math.ceil((max + padding) / step);
  return Array.from({ length: high - low + 1 }, (_, index) => (high - index) * step);
}

export function PriceChart({ observations, unit, periodDays, wide = false, nav = false }: { observations: (Pick<PriceObservation, 'date' | 'price_vnd'> & { note?: string })[]; unit?: string; periodDays?: number; wide?: boolean; nav?: boolean }) {
  const helpId = useId();
  const [selection, setSelection] = useState<number>(), [hover, setHover] = useState<number>();
  const end = observations.length - 1;
  const index = Math.min(hover ?? selection ?? end, end);
  const points = observations.map(row => ({ ...row, value: Number(row.price_vnd), time: Date.parse(row.date) }));
  const first = points[0], last = points[end], point = points[index];
  const min = Math.min(...points.map(item => item.value)), max = Math.max(...points.map(item => item.value));
  const ticks = priceTicks(min, max);
  const tickLabels = ticks.map(tick => (tick >= 1e9 ? compactPrice : axisPrice).format(tick));
  const scaleMax = ticks[0], scaleMin = ticks[ticks.length - 1];
  const elapsed = last.time - first.time;
  const x = (time: number) => elapsed ? (time - first.time) / elapsed * 100 : 50;
  const y = (value: number) => (scaleMax - value) / (scaleMax - scaleMin) * 100;
  const dateTicks = elapsed >= 4 * day ? [0, .25, .5, .75, 1] : elapsed ? [0, 1] : [0];
  const tickDate = first.date.slice(0, 4) === last.date.slice(0, 4) ? shortDate : axisYearDate;
  const line = points.map(item => `${x(item.time) * 10},${y(item.value) * 2.5}`).join(' ');
  const change = first.value ? (last.value - first.value) / first.value : null;

  function inspect(event: PointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const date = first.time + (event.clientX - bounds.left) / bounds.width * elapsed;
    const nearest = points.reduce((best, item, i) => Math.abs(item.time - date) < Math.abs(points[best].time - date) ? i : best, 0);
    if (event.pointerType === 'mouse' && event.type === 'pointermove') setHover(nearest);
    else { setHover(undefined); setSelection(nearest); }
  }

  function navigate(event: KeyboardEvent<HTMLDivElement>) {
    const current = index;
    const steps: Record<string, number> = { ArrowLeft: current - 1, ArrowDown: current - 1, ArrowRight: current + 1, ArrowUp: current + 1, Home: 0, End: end };
    if (!Object.hasOwn(steps, event.key)) return;
    event.preventDefault();
    setHover(undefined);
    setSelection(Math.max(0, Math.min(end, steps[event.key])));
  }

  const stats = <div className="price-chart-summary">
      <div className="price-chart-change" data-direction={change !== null && change > 0 ? 'up' : change !== null && change < 0 ? 'down' : undefined}>
        <span>Biến động trong khoảng</span><strong>{change === null ? '—' : changeFormat.format(change)}</strong>
      </div>
      <dl className="price-chart-stats">
        <div><dt>Thấp nhất</dt><dd>{marketPrice(min)}</dd></div>
        <div><dt>Cao nhất</dt><dd>{marketPrice(max)}</dd></div>
        <div><dt>{nav ? 'Số phiên định giá' : 'Số ngày có giá'}</dt><dd>{points.length}</dd></div>
      </dl>
    </div>;
  return <figure className="price-chart">
    <figcaption className="sr-only">{nav ? 'Tổng tài sản mô phỏng theo ngày' : 'Giá quan sát theo ngày'}</figcaption>
    <div className="price-chart-quote">
      <span>{nav ? 'Tổng tài sản tại phiên đang xem' : index === end ? 'Giá ghi nhận gần nhất' : 'Giá tại điểm đang xem'}</span>
      <strong>{marketPrice(point.price_vnd)}{unit?.startsWith('₫/') && <span className="price-unit">{unit.slice(1)}</span>}</strong>
      <time dateTime={point.date}>{fullDate.format(point.time)}</time>
      {point.note && <span>{point.note}</span>}
    </div>
    <p className="price-period-label">{periodDays && <>{periodDays} ngày · </>}Các phiên từ {shortDate.format(first.time)} đến {shortDate.format(last.time)}</p>
    <div className="price-chart-frame">
      <div className="price-chart-plot" role={end > 0 ? 'slider' : undefined} tabIndex={end > 0 ? 0 : undefined}
        aria-label={end > 0 ? nav ? 'Dò tổng tài sản theo phiên' : 'Dò giá theo ngày quan sát' : undefined} aria-describedby={end > 0 ? helpId : undefined}
        aria-valuemin={end > 0 ? 1 : undefined} aria-valuemax={end > 0 ? points.length : undefined}
        aria-valuenow={end > 0 ? index + 1 : undefined}
        aria-valuetext={end > 0 ? `${fullDate.format(point.time)} · ${marketPrice(point.price_vnd)}${point.note ? ` · ${point.note}` : ''}` : undefined}
        onPointerDown={end > 0 ? inspect : undefined}
        onPointerMove={end > 0 ? (event => { if (event.pointerType === 'mouse' || event.buttons) inspect(event); }) : undefined}
        onPointerLeave={() => setHover(undefined)} onKeyDown={navigate}>
        <svg viewBox="0 0 1000 250" preserveAspectRatio="none" aria-hidden="true">
          {ticks.map(tick => <line className="price-chart-grid" key={tick} x1="0" x2="1000" y1={y(tick) * 2.5} y2={y(tick) * 2.5}/>)}
          {end > 0 && <>
            <polyline className="price-chart-line" points={line}/>
            <line className="price-chart-guide" x1={x(point.time) * 10} x2={x(point.time) * 10} y1="0" y2="250"/>
          </>}
        </svg>
        <span className="price-chart-marker" style={{ left: `${x(point.time)}%`, top: `${y(point.value)}%` }} aria-hidden="true"/>
      </div>
      <div className="price-axis-y" data-width-sample={tickLabels.reduce((longest, label) => label.length > longest.length ? label : longest, '')} aria-hidden="true">
        {ticks.map((tick, i) => <span key={tick} style={{ top: `${y(tick)}%` }}>{tickLabels[i]}</span>)}
      </div>
      <div className="price-axis-x" aria-hidden="true">
        {dateTicks.map(fraction => <span key={fraction} data-minor={fraction === .25 || fraction === .75 || undefined} data-edge={elapsed && fraction === 0 ? 'start' : fraction === 1 ? 'end' : undefined} style={{ left: `${elapsed ? fraction * 100 : 50}%` }}>
          {tickDate.format(first.time + elapsed * fraction)}
        </span>)}
      </div>
    </div>
    <p className="price-chart-help" id={helpId}>{end > 0 ? 'Rê chuột, chạm hoặc dùng phím mũi tên để xem từng ngày.' : nav ? 'Mới có một phiên định giá.' : 'Chỉ có một ngày ghi nhận giá trong khoảng đã chọn.'}</p>
    {end > 0 && (wide ? stats : <details className="price-interval-details"><summary>Biến động và thống kê</summary>{stats}</details>)}
  </figure>;
}
