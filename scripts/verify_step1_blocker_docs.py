"""Verify a section-only Google Doc update, preserving the user's prior edits."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree,html
import argparse,json,re,hashlib,shutil
import pdfplumber
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/step1/blocker_evidence_20261012';PUB=OUT/'google_doc_update'
p=argparse.ArgumentParser();p.add_argument('--docx',required=True);p.add_argument('--pdf',required=True);args=p.parse_args()
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
def clean(t):return re.sub(r'\s+',' ',t.replace('\u200b','').replace('\ufeff','')).strip()
def read(path):
 with ZipFile(path) as z:
  tree=etree.fromstring(z.read('word/document.xml'));media=sorted(hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('word/media/'))
 paras=[clean(''.join(x.xpath('.//w:t/text()',namespaces=ns))) for x in tree.xpath('//w:p',namespaces=ns)]
 return tree,paras,media
before,bp,bm=read(OUT/'google_doc_before_update.docx');after,ap,am=read(args.docx)
heading='13. Các vấn đề cần giải quyết trước Step 2 (Blocking issues)'
assert bp[:bp.index(heading)]==ap[:ap.index(heading)],'Content before section13 changed'
assert bm==am,'Images changed';assert ap.count(heading)==1;assert '\n'.join(ap).strip().endswith('NOT READY FOR STEP 2')
src=html.fromstring((PUB/'full_report.html').read_text());expected_tables=[[clean(''.join(c.itertext())) for c in t.xpath('.//th|.//td')] for t in src.xpath('//table')]
actual_tables=[[clean(''.join(c.xpath('.//w:t/text()',namespaces=ns))) for c in t.xpath('.//w:tc',namespaces=ns)] for t in after.xpath('//w:tbl',namespaces=ns)]
assert actual_tables[-len(expected_tables):]==expected_tables
expected_paras=[clean(''.join(p.itertext())) for p in src.xpath('//body/p')]
assert all(x in ap for x in expected_paras if x)
for suffix,value in [('docx',args.docx),('pdf',args.pdf)]:shutil.copy2(value,PUB/f'verified_google_doc.{suffix}')
(PUB/'verified_text.txt').write_text('\n'.join(ap))
with pdfplumber.open(args.pdf) as pdf:pages=[dict(page=i+1,characters=len(page.extract_text() or ''),images=len(page.images)) for i,page in enumerate(pdf.pages)]
record=dict(status='CONTENT_VERIFIED',user_content_before_section13_preserved=True,original_media_unchanged=True,new_tables_exact=True,source_body_paragraphs_present=True,readiness_retained=True,section13_sha256=hashlib.sha256((OUT/'report_section13.md').read_bytes()).hexdigest(),pages=pages)
(PUB/'publication_verification.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
