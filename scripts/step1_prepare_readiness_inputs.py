"""Prepare immutable information/outcome panels for a declared valuation protocol."""
from pathlib import Path
import sys,json,hashlib,shutil
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/readiness_20261012';BASE=OUT/'candidate_workspace';OLD=ROOT/'trusted_baseline';EVIDENCE=ROOT/'outputs/step1/blocker_evidence_20261012'
sys.path.insert(0,str(BASE))
from utils.availability import build_asof_panel
TZ='Asia/Ho_Chi_Minh'
raw=json.loads((BASE/'assets_1.json').read_text());names=raw['default_selection'];stocks=raw['vn30_universe'];records=[];source_rows=[]
all_calendar=pd.DatetimeIndex(pd.to_datetime(pd.read_csv(OLD/'datasets/indices/full/VNINDEX.csv').date)).sort_values().unique()
calendar=all_calendar[(all_calendar>='2020-01-01')&(all_calendar<='2026-04-30')]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stamp(day,hour=15):return (pd.Timestamp(day)+pd.Timedelta(hours=hour)).tz_localize(TZ)
def add(asset,frame,basis,availability):
    for row in frame.to_dict('records'):
        records.append(dict(asset=asset,observed_at=stamp(row['date'],23 if asset=='GOLD' else 15),available_at=availability(row),price=float(row['price']),availability_basis=basis,source=row['source']))
def save(asset,frame):
    cfg=raw['assets'][asset]
    for key in ['full_path','train_path','test_path']:
        p=BASE/cfg[key];p.parent.mkdir(parents=True,exist_ok=True)
        part=frame if key=='full_path' else frame[frame.date.lt('2023-10-01') if key=='train_path' else frame.date.ge('2023-10-01')]
        part[['date','price']].rename(columns={'date':cfg['date_col'],'price':cfg['price_col']}).to_csv(p,index=False)
for asset in stocks:
    path=EVIDENCE/f'raw/kbs_verified_full_{asset}.json';obj=json.loads(path.read_text());f=pd.DataFrame(obj['data_day']);f['date']=f.t.str[:10];f['price']=pd.to_numeric(f.c)/1000;f['source']=str(path.relative_to(ROOT));f=f.sort_values('date')
    assert not f.date.duplicated().any();assert f.price.gt(0).all()
    save(asset,f);add(asset,f,'provider_adjusted_close_available_by_18_assumption',lambda r:stamp(r['date'],18));source_rows.append(dict(asset=asset,path=str(path),sha256=sha(path),kind='KBS provider-native adjusted close; no separate dividends; unrounded source integers/1000'))
g=pd.read_csv(OUT/'gold_archive_daily.csv');g['price']=g.sjc_sell;g['source']=g.source_file.apply(lambda p:str((OUT/'gold_archive_raw'/p).relative_to(ROOT)))
save('GOLD',g);add('GOLD',g,'archival_daily_close_prior_day_assumption',lambda r:(pd.Timestamp(r['date'])+pd.Timedelta(days=1)).tz_localize(TZ));source_rows.append(dict(asset='GOLD',path=str(OUT/'gold_archive_daily.csv'),sha256=sha(OUT/'gold_archive_daily.csv'),kind='SJC-HCM archived by GiaVang.TV, historical GiaVang.org; close sell; approximate 0.1 million VND precision'))
v=pd.read_csv(ROOT/'outputs/step1/data_static/canonical_vff.csv');v=v[v.date.le('2026-04-30')].copy();v['price']=v.nav_per_unit_vnd/1000;v['source']='outputs/step1/data_static/fmarket_vff_nav_response.json'
def nav_available(row):
    i=all_calendar.searchsorted(pd.Timestamp(row['date']),side='right')+4
    if i>=len(all_calendar):raise ValueError('Calendar must cover NAV release buffer')
    assumed=stamp(all_calendar[i],18)
    metadata=pd.to_datetime(row.get('provider_record_created_at_utc'),utc=True,errors='coerce')
    return max(assumed,metadata.tz_convert(TZ)) if pd.notna(metadata) else assumed
save('VFF',v);add('VFF',v,'five_session_NAV_buffer_plus_later_record_metadata_assumption',nav_available);source_rows.append(dict(asset='VFF',path=str(ROOT/'outputs/step1/data_static/canonical_vff.csv'),sha256=sha(ROOT/'outputs/step1/data_static/canonical_vff.csv'),kind='FMarket product21 NAV; original precision; publication buffer is assumed, not observed'))
market=pd.read_csv(OLD/'datasets/indices/full/VNINDEX.csv');market['price']=market.close;market['source']='trusted_baseline/datasets/indices/full/VNINDEX.csv';save('VNINDEX',market);source_rows.append(dict(asset='VNINDEX',path=str(OLD/'datasets/indices/full/VNINDEX.csv'),sha256=sha(OLD/'datasets/indices/full/VNINDEX.csv'),kind='retained observed VNINDEX calendar and market proxy'))
pd.DataFrame(records).to_csv(OUT/'candidate_observation_records.csv',index=False)
panel,ledger=build_asof_panel(pd.DataFrame(records),calendar,cutoff_hour=18)
panel=panel[names].dropna(how='any');panel.index.name='date';panel.to_csv(OUT/'candidate_information_prices.csv')
ledger=ledger[ledger.session_date.isin(panel.index.strftime('%Y-%m-%d'))];ledger.to_csv(OUT/'availability_ledger.csv',index=False)
assert np.isfinite(panel.to_numpy()).all();assert (panel.to_numpy()>0).all();assert len(ledger)==len(panel)*len(names)
assert (pd.to_datetime(ledger.available_at,utc=True)<=pd.to_datetime(ledger.decision_at,utc=True)).all()
policy=dict(scope='valuation_proxy',decision_cutoff='18:00 Asia/Ho_Chi_Minh',execution='next observed session close valuation proxy; outcome NAV can be published later',information_panel='latest eligible observation; never backfill; late old observation cannot overwrite newer eligible one',equity_return='KBS provider-native adjusted-close price returns; no separate cash dividend',gold='single SJC-HCM archival close series; information eligible on next calendar day; source resolution about100000VND/luong',VFF='fixed5 observed-session NAV publication buffer plus any later record-created timestamp; not actual first-publication evidence',historical_publication_verified=False,physical_fund_execution_certified=False,parameter_tuning_performed=False,source_rows=source_rows,assumptions=['Provider adjusted prices are retrospective snapshots, not complete historical revision vintages','Daily GOLD archival close is known by the following day; exact historical intraday publication time unavailable','VFF availability is modelled by five sessions plus later provider metadata; first-publication history incomplete'],requested_period=['2020-01-01','2023-10-01','2026-04-30'])
(OUT/'availability_policy.json').write_text(json.dumps(policy,indent=2))
(OUT/'input_validation.json').write_text(json.dumps(dict(status='PASS_FOR_DECLARED_PROTOCOL',full_gold_calendar_rows=len(g),valuation_assets=len(names),information_rows=len(panel),information_first=panel.index[0].isoformat(),last=panel.index[-1].isoformat(),ledger_rows=len(ledger),all_selected_information_within_cutoff=True,historical_publication_verified=False,strict_historical_certification='NOT_VERIFIED'),indent=2))
for n in ['environment.json','requirements_frozen.txt']:shutil.copy2(ROOT/'outputs/step1'/n,OUT/n)
print(json.dumps(dict(information_shape=panel.shape,first=str(panel.index[0]),last=str(panel.index[-1]),ledger_rows=len(ledger),scope='valuation_proxy',historical_publication_verified=False)))
