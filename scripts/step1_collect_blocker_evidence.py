"""Read-only public-source collection; never modifies scientific inputs."""
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import json,hashlib,requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/step1/blocker_evidence_20261012'
RAW=OUT/'raw';RAW.mkdir(parents=True,exist_ok=True)
sources={
 'vff_official_page.html':'https://wm.vinacapital.com/vi/investment-solutions/onshore-funds/vff/',
 'vff_prospectus_202603.pdf':'https://wm.vinacapital.com/wp-content/uploads/2026/03/20260326_VFF-BCB-sua-doi-bo-sung-03.2026.pdf',
 'vff_prospectus_202507.pdf':'https://wm.vinacapital.com/wp-content/uploads/2025/07/20250725_VFF-Ban-cao-bach-sua-doi-bo-sung-07.2025-1.pdf',
 'vff_prospectus_202307.pdf':'https://vinacapital.com/wp-content/uploads/2023/07/20230713_VFF-Ban-cao-bach-sua-doi-bo-sung-Jul-2023-002.pdf',
 'vff_basic_definitions.html':'https://vinacapital.com/vi/investment-education/basic-definitions-when-investing-in-oefs/',
 'pnj_official_page.html':'https://giavang.pnj.com.vn/',
 'vnstock_source_policy.html':'https://vnstocks.com/docs/vnstock/tham-khao/data-sources',
 'vnstock_migration_policy.html':'https://vnstocks.com/docs/vnstock/v5/chuyen-doi/tu-vnstock-data-3x',
 'vsdc_acb_2025_dividend.html':'https://vsdc.vn/en/ad/182839',
 'fpts_acb_2024_events.pdf':'https://file.fpts.com.vn/FileStore2/File/2024/05/31/FIA20240531_8c0c8a23.pdf',
}
for day in ['20200101','20200102','20200323','20210601','20220613','20231002','20240531','20250523','20260129','20260227','20260429']:
 sources[f'pnj_history_{day}.json']=f'https://edge-cf-api.pnj.io/ecom-frontend/v1/get-gold-price-history?date={day}'
for sym in ['ACB','FPT','VNM']:
 sources[f'kbs_{sym}_2024_2025.json']=f'https://kbbuddywts.kbsec.com.vn/iis-server/investment/stocks/{sym}/data_day?sdate=01-01-2024&edate=30-06-2025'
def fetch(item):
 name,url=item;row=dict(file=name,url=url,requested_at_utc=datetime.now(timezone.utc).isoformat())
 try:
  r=requests.get(url,timeout=(10,25),headers={'User-Agent':'Mozilla/5.0'});(RAW/name).write_bytes(r.content)
  row.update(status=r.status_code,final_url=r.url,received_at_utc=datetime.now(timezone.utc).isoformat(),http_date=r.headers.get('Date'),content_type=r.headers.get('Content-Type'),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content))
 except Exception as e:row.update(status=None,error=f'{type(e).__name__}: {e}')
 return row
with ThreadPoolExecutor(max_workers=5) as pool:records=list(pool.map(fetch,sources.items()))
(OUT/'source_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print(json.dumps([{k:r.get(k) for k in ['file','status','bytes','error']} for r in records]))
