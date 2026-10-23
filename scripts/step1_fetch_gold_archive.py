"""Freeze a single, explicitly attributed SJC-HCM archival provider for the full period."""
from pathlib import Path
from datetime import datetime,timezone
import requests,json,hashlib,time
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/readiness_20261012';RAW=OUT/'gold_archive_raw';RAW.mkdir(exist_ok=True)
urls=json.loads((OUT/'gold_archive_month_urls.json').read_text());rows=[]
for i,url in enumerate(urls):
 name=url.rstrip('/').replace('https://giavang.tv/lich-su/','').replace('/','_')+'.html';p=RAW/name
 time.sleep(1.0)
 r=requests.get(url,timeout=(5,20));p.write_bytes(r.content)
 rows.append(dict(file=name,url=url,status=r.status_code,received_at_utc=datetime.now(timezone.utc).isoformat(),http_date=r.headers.get('Date'),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content)))
 (OUT/'gold_archive_manifest.json').write_text(json.dumps(dict(status='running',provider='GiaVang.TV archival series attributed to SJC / historical GiaVang.org',pacing_seconds=1,records=rows),indent=2))
 if r.status_code!=200:raise RuntimeError('Stop on provider error; never silently fill failed retrieval')
 if (i+1)%12==0:print(f'Archived {i+1}/{len(urls)} months',flush=True)
(OUT/'gold_archive_manifest.json').write_text(json.dumps(dict(status='SUCCESS',provider='GiaVang.TV archival series attributed to SJC / historical GiaVang.org',pacing_seconds=1,records=rows),indent=2));print('COMPLETE',len(rows))
