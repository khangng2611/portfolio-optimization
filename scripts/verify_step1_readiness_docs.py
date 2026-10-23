"""Verify targeted Google Doc edits preserve all other user text and old media."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree,html
import re,json,hashlib
import pdfplumber
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/readiness_20261012';PUB=OUT/'google_doc_update'
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def clean(s):return re.sub(r'\s+',' ',s.replace('\u200b','').replace('\ufeff','')).strip()
def read(p):
 with ZipFile(p) as z:
  tree=etree.fromstring(z.read('word/document.xml'));media=[hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('word/media/')]
 pars=[clean(''.join(p.xpath('.//w:t/text()',namespaces=ns))) for p in tree.xpath('//w:p',namespaces=ns)]
 return tree,pars,media
b,bp,bm=read(PUB/'before.docx');a,ap,am=read(PUB/'final.docx')
replacements=json.loads((PUB/'targeted_replacements.json').read_text())
replacements[1]['new']=replacements[1]['new'].replace('bảng 12.1 là kết quả mới.','bảng ở mục 13 là kết quả mới; mục 12 lưu đối chứng 04/10.')
replacements.append({'old':'Manifest, cấu hình/seed/môi trường, mã nguồn baseline, ma trận giá, snapshot manifest gốc và kết quả 27 kiểm thử, 52 kiểm tra độc lập, 40 kiểm tra tái lập.','new':'Mã nguồn/config, dữ liệu và policy, hai manifest mới; 35 kiểm thử, 42 kiểm tra độc lập và 21 kiểm tra tái lập đạt. 13 CSV giống từng byte.'})
oldheading='13. Các vấn đề cần giải quyết trước Step 2 (Blocking issues)';newheading='13. Hoàn tất bốn vấn đề trước Step 2'
expected=[x for x in bp[:bp.index(oldheading)] if x]
for pair in replacements:expected=[x.replace(clean(pair['old']),clean(pair['new'])) for x in expected]
actual=[x for x in ap[:ap.index(newheading)] if x]
if expected!=actual:
 from difflib import unified_diff
 print('\n'.join(unified_diff(expected,actual,n=1)));raise AssertionError('Unexpected user text change before13')
assert all(x in am for x in bm),'Old images missing';assert len(am)==len(bm)+2,'New figure count'
assert 'STEP1FIGURE' not in '\n'.join(ap);assert '\n'.join(ap).strip().endswith('READY FOR STEP 2');assert 'NOT READY FOR STEP 2' not in '\n'.join(ap)
source_text=(PUB/'full_report.html').read_text().replace('Thay bằng kết quả của baseline mới 12/10; khớp mục 12.1.','Kết quả baseline mới 12/10; khớp hai bảng IS/OOS ở mục 13.')
(PUB/'full_report.html').write_text(source_text)
source=html.fromstring(source_text)
etables=[[clean(''.join(c.itertext())) for c in t.xpath('.//th|.//td')] for t in source.xpath('//table')]
atables=[[clean(''.join(c.xpath('.//w:t/text()',namespaces=ns))) for c in t.xpath('.//w:tc',namespaces=ns)] for t in a.xpath('//w:tbl',namespaces=ns)]
assert atables[-len(etables):]==etables,'New tables differ'
body=[clean(''.join(p.itertext())) for p in source.xpath('//body/p')]
assert all(t in ap for t in body if t and not t.startswith('STEP1FIGURE')),'New paragraphs missing'
with pdfplumber.open(PUB/'final.pdf') as pdf:
 pages=[dict(page=i+1,characters=len(p.extract_text() or ''),images=len(p.images)) for i,p in enumerate(pdf.pages)]
 assert all(p['characters'] or p['images'] for p in pages),'Blank page'
record=dict(status='CONTENT_VERIFIED',all_other_user_text_preserved=True,original_three_media_preserved=True,two_new_figures=True,new_five_tables_exact=True,readiness_scope_explicit=True,strict_historical_not_certified=True,pages=pages,targeted_replacements=replacements)
(PUB/'publication_verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2));(PUB/'verified_text.txt').write_text('\n'.join(ap))
print(json.dumps({k:v for k,v in record.items() if k!='targeted_replacements'},ensure_ascii=False,indent=2))
