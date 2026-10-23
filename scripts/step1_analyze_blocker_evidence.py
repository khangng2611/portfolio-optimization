"""Summarize recovered evidence and produce unactivated GOLD candidate series."""
from pathlib import Path
import json,hashlib,re
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/blocker_evidence_20261012';RAW=OUT/'raw'
quotes=[];daily=[];errors=[]
fetch_records=json.loads((OUT/'source_manifest.json').read_text())+json.loads((OUT/'extended_source_manifest.json').read_text())
status_by_file={r['file']:r.get('status') for r in fetch_records}
saved=pd.read_csv(ROOT/'trusted_baseline/datasets/gold/gold_full.csv').set_index('date')
for p in sorted(RAW.glob('pnj_history_*.json')):
 day=p.stem[-8:];date=f'{day[:4]}-{day[4:6]}-{day[6:]}'
 try:
  obj=json.loads(p.read_text());groups=[g for loc in obj['locations'] if loc.get('name')=='TPHCM' for g in loc.get('gold_type',[]) if g.get('name')=='SJC'];data=groups[0].get('data',[]) if groups else []
 except Exception as e:
  errors.append(dict(date=date,file=p.name,http_status=status_by_file.get(p.name),error=str(e)))
  daily.append(dict(date=date,n_quotes=None,baseline_sjc_sell=float(saved.loc[date,'sjc_sell']) if date in saved.index else None,first_sell=None,last_sell=None,cutoff_1500_sell=None,cutoff_quote_timestamp=None,baseline_matches_any_quote=None,raw_quote_missing=None,source_file=p.name,http_status=status_by_file.get(p.name),retrieval_state='FAILED_NOT_A_MISSING_QUOTE'))
  continue
 current=[]
 for j,q in enumerate(data):
  try:
   stamp=pd.to_datetime(q['updated_at'],format='%d/%m/%Y %H:%M:%S');sell=int(q['gia_ban'].replace('.',''));buy=int(q['gia_mua'].replace('.',''))
  except Exception as e:errors.append(dict(date=date,file=p.name,error=str(e)));continue
  row=dict(requested_date=date,quote_timestamp_local=str(stamp),quote_date=stamp.strftime('%Y-%m-%d'),buy_thousand_vnd_per_luong=buy,sell_thousand_vnd_per_luong=sell,source_file=p.name,source_row=j,location='TPHCM',product='SJC',timezone_assumption='Asia/Ho_Chi_Minh; provider timestamp has no timezone',matches_requested_date=stamp.strftime('%Y-%m-%d')==date)
  quotes.append(row)
  if row['matches_requested_date']:current.append(row)
 current.sort(key=lambda q:q['quote_timestamp_local'])
 eligible=[q for q in current if q['quote_timestamp_local']<=date+' 15:00:00']
 value=float(saved.loc[date,'sjc_sell']) if date in saved.index else None
 daily.append(dict(date=date,n_quotes=len(current),baseline_sjc_sell=value,first_sell=current[0]['sell_thousand_vnd_per_luong'] if current else None,last_sell=current[-1]['sell_thousand_vnd_per_luong'] if current else None,cutoff_1500_sell=eligible[-1]['sell_thousand_vnd_per_luong'] if eligible else None,cutoff_quote_timestamp=eligible[-1]['quote_timestamp_local'] if eligible else None,baseline_matches_any_quote=(any(value==q['sell_thousand_vnd_per_luong'] for q in current) if current and value is not None else None),raw_quote_missing=not current,source_file=p.name,http_status=status_by_file.get(p.name),retrieval_state='OBSERVED_QUOTES' if current else 'SUCCESS_NO_QUOTES'))
q=pd.DataFrame(quotes);d=pd.DataFrame(daily)
q.to_csv(OUT/'gold_raw_quotes.csv',index=False);d.to_csv(OUT/'gold_snapshot_daily_comparison.csv',index=False)
# A proposed convention, not an activated replacement or a known historical public-release clock.
c=d[['date','cutoff_1500_sell','cutoff_quote_timestamp','raw_quote_missing','source_file']].copy().rename(columns={'cutoff_1500_sell':'price'})
c['source_quote_date']=c.date.where(c.price.notna());c['active_baseline']=False;c['coverage_status']=d.retrieval_state
c.to_csv(OUT/'gold_candidate_1500_NOT_ACTIVATED.csv',index=False)
period=d[d.date.between('2020-01-01','2026-04-29')];observed=period[period.n_quotes.gt(0)];known=observed[observed.baseline_sjc_sell.notna()]
gold=dict(calendar_dates_attempted=len(period),http_success_dates=int(period.http_status.eq(200).sum()),http_429_dates=int(period.http_status.eq(429).sum()),dates_with_quotes=len(observed),successful_dates_without_quotes=int(period.n_quotes.eq(0).sum()),raw_quotes=int(len(q)),retrieval_errors=len(errors),comparison_dates=len(known),baseline_matches_any_quote=int(known.baseline_matches_any_quote.eq(True).sum()),baseline_matches_no_quote=int(known.baseline_matches_any_quote.eq(False).sum()),baseline_matches_first=int((known.baseline_sjc_sell==known.first_sell).sum()),baseline_matches_1500=int((known.baseline_sjc_sell==known.cutoff_1500_sell).sum()),baseline_matches_last=int((known.baseline_sjc_sell==known.last_sell).sum()),candidate_status='INCOMPLETE_NOT_ACTIVATED_NO_IMPUTATION_OVER_FAILURES',primary_source='PNJ edge API; SJC quote, TPHCM, thousand VND/luong',point_in_time_revision_history_verified=False)
v=pd.read_csv(ROOT/'outputs/step1/data_static/canonical_vff.csv');v=v[v.date.between('2020-01-01','2026-04-30')].copy();created=pd.to_datetime(v.provider_record_created_at_utc,utc=True).dt.tz_convert('Asia/Ho_Chi_Minh');date=pd.to_datetime(v.date)
v['metadata_created_local']=created.astype(str);v['metadata_after_1500']=created.dt.tz_localize(None)>date+pd.Timedelta(hours=15);v['metadata_next_or_later_day']=created.dt.tz_localize(None).dt.normalize()>date;v.to_csv(OUT/'vff_metadata_april_check.csv',index=False)
vff=dict(observations=len(v),metadata_present=int(created.notna().sum()),metadata_missing=int(created.isna().sum()),metadata_after_valuation_1500=int(v.metadata_after_1500.sum()),metadata_after_valuation_day=int(v.metadata_next_or_later_day.sum()),metadata_is_not_verified_public_release=True)
stock=[]
for p in sorted(RAW.glob('kbs_verified_full_*.json')):
 try:a=pd.DataFrame(json.loads(p.read_text())['data_day']);a['date']=a.t.str[:10];a['provider_close']=(a.c/1000).round(2)
 except:continue
 sym=p.stem.split('_')[-1];b=pd.read_csv(ROOT/f'trusted_baseline/datasets/stocks/full/{sym}.csv');m=b.merge(a[['date','provider_close']],on='date').sort_values('date');m['snapshot_return']=m.close.pct_change();m['new_provider_return']=m.provider_close.pct_change();m.to_csv(OUT/f'stock_overlap_{sym}.csv',index=False)
 stock.append(dict(symbol=sym,n_overlap=len(m),n_exact=int((m.close==m.provider_close).sum()),n_price_different=int((m.close!=m.provider_close).sum()),max_abs_price_diff=float((m.close-m.provider_close).abs().max()),max_abs_return_diff=float((m.snapshot_return-m.new_provider_return).abs().max()),price_ratio_min=float((m.provider_close/m.close).min()),price_ratio_max=float((m.provider_close/m.close).max())))
s=pd.DataFrame(stock);s.to_csv(OUT/'stock_snapshot_comparison.csv',index=False)
stocks=dict(symbols_checked=len(s),fully_matching_symbols=int(s.n_price_different.eq(0).sum()),symbols_with_revision=s.loc[s.n_price_different.gt(0),'symbol'].tolist(),full_corporate_action_ledger_verified=False,return_type='provider-adjusted close returns; not yet certified as economic total return')
summary=dict(audit_date='2026-10-12',gold=gold,vff=vff,stocks=stocks,active_april_baseline_replaced=False)
(OUT/'evidence_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(OUT/'gold_parse_errors.json').write_text(json.dumps(errors,indent=2));print(json.dumps(summary,ensure_ascii=False))
