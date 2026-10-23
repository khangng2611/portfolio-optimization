"""PNJ history recovery with bounded pacing and explicit stop on rate limiting."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,time,requests,sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/readiness_20261012';RAW=OUT/'gold_raw';RAW.mkdir(parents=True,exist_ok=True)
calendar=pd.read_csv(ROOT/'trusted_baseline/datasets/indices/full/VNINDEX.csv');dates=pd.to_datetime(calendar.date);dates=dates[(dates>='2020-01-01')&(dates<='2026-04-30')].sort_values().drop_duplicates()
dates=sorted(set(dates.dt.strftime('%Y%m%d'))|{'20191231','20200101'})
old=ROOT/'outputs/step1/blocker_evidence_20261012/raw';records=[];fetched=0
def valid(p):
 try:return isinstance(json.loads(p.read_text()).get('locations'),list)
 except:return False
for day in dates:
 name=f'pnj_history_{day}.json';target=RAW/name
 if target.exists() and valid(target):records.append(dict(date=day,file=name,status=200,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source='retained_current_recovery'));continue
 src=old/name
 if src.exists() and valid(src):
  target.write_bytes(src.read_bytes());records.append(dict(date=day,file=name,status=200,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source='retained_prior_verified_response'));continue
 url=f'https://edge-cf-api.pnj.io/ecom-frontend/v1/get-gold-price-history?date={day}'
 time.sleep(2.1)
 row=dict(date=day,file=name,url=url,requested_at_utc=datetime.now(timezone.utc).isoformat())
 try:
  response=requests.get(url,timeout=(5,20),headers={'User-Agent':'Mozilla/5.0'});target.write_bytes(response.content);row.update(status=response.status_code,received_at_utc=datetime.now(timezone.utc).isoformat(),retry_after=response.headers.get('Retry-After'),http_date=response.headers.get('Date'),sha256=hashlib.sha256(response.content).hexdigest(),bytes=len(response.content),source='new_primary_response')
 except Exception as e:row.update(status=None,error=str(e))
 records.append(row);fetched+=1
 (OUT/'gold_recovery_manifest.json').write_text(json.dumps(dict(status='running',pacing_seconds=2.1,total_requested_dates=len(dates),records=records),indent=2))
 if row.get('status')!=200 or not valid(target):
  (OUT/'gold_recovery_manifest.json').write_text(json.dumps(dict(status='STOPPED_PROVIDER_ERROR',pacing_seconds=2.1,total_requested_dates=len(dates),records=records),indent=2));print(json.dumps(row),flush=True);sys.exit(2)
 if fetched%25==0:print(f'Validated {len(records)}/{len(dates)} dates ({fetched} new requests)',flush=True)
(OUT/'gold_recovery_manifest.json').write_text(json.dumps(dict(status='SUCCESS',pacing_seconds=2.1,total_requested_dates=len(dates),records=records),indent=2));print('GOLD RECOVERY COMPLETE',len(records),flush=True)
