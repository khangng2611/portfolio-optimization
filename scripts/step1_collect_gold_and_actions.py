"""Recover primary GOLD records and KBS event disclosures without replacing inputs."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,date,timedelta
import requests,json,hashlib,time
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/blocker_evidence_20261012';RAW=OUT/'raw'
requests_list=[]
day=date(2019,12,31)
while day<=date(2026,4,29):
 name=f'pnj_history_{day:%Y%m%d}.json'
 if not (RAW/name).exists():requests_list.append((name,f'https://edge-cf-api.pnj.io/ecom-frontend/v1/get-gold-price-history?date={day:%Y%m%d}'))
 day+=timedelta(days=1)
tickers=json.loads((ROOT/'trusted_baseline/assets_1.json').read_text())['default_selection']
for symbol in tickers:
 requests_list.append((f'kbs_events_{symbol}.json',f'https://kbbuddywts.kbsec.com.vn/iis-server/investment/stockinfo/event/{symbol}?l=1&p=1&s=500'))
def fetch(item):
 name,url=item;row=dict(file=name,url=url,requested_at_utc=datetime.now(timezone.utc).isoformat())
 try:
  r=requests.get(url,timeout=(5,15),headers={'User-Agent':'Mozilla/5.0'});(RAW/name).write_bytes(r.content)
  row.update(status=r.status_code,received_at_utc=datetime.now(timezone.utc).isoformat(),http_date=r.headers.get('Date'),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content))
 except Exception as e:row.update(status=None,error=f'{type(e).__name__}: {e}')
 return row
records=[]
with ThreadPoolExecutor(max_workers=3) as pool:
 for offset in range(0,len(requests_list),3):
  batch=list(pool.map(fetch,requests_list[offset:offset+3]));records.extend(batch)
  if any(r.get('status')==429 for r in batch):
   (OUT/'extended_source_manifest.json').write_text(json.dumps(records,indent=2))
   raise RuntimeError('Provider rate limit encountered; stop and preserve evidence, do not retry automatically')
  if offset%99==0:
   (OUT/'extended_source_manifest.json').write_text(json.dumps(records,indent=2));print(f'{len(records)}/{len(requests_list)} collected',flush=True)
(OUT/'extended_source_manifest.json').write_text(json.dumps(records,indent=2));print('DONE',len(records))
