"""Check the exported Google Doc against the prepared source content."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree,html
import argparse,shutil,json,re,hashlib
import pdfplumber

root=Path(__file__).resolve().parents[1]
out=root/'outputs/step1/paper_period/google_doc_20261007'
parser=argparse.ArgumentParser()
parser.add_argument('--docx',required=True)
parser.add_argument('--pdf',required=True)
args=parser.parse_args()
shutil.copy2(args.docx,out/'verified_google_doc.docx')
shutil.copy2(args.pdf,out/'verified_google_doc.pdf')
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with ZipFile(args.docx) as z:x=etree.fromstring(z.read('word/document.xml'))
def clean(t):return re.sub(r'\s+',' ',t.replace('\u200b','').replace('\ufeff','')).strip()
elements=x.xpath('//w:p',namespaces=ns)
paras=[clean(''.join(p.xpath('.//w:t/text()',namespaces=ns))) for p in elements]
text='\n'.join(paras)
assert 'STEP1FIGURE' not in text
assert text.strip().endswith('NOT READY FOR STEP 2')
assert len(x.xpath('//a:blip',namespaces=ns))==3
expected=html.fromstring((out/'full_report.html').read_text())
expected_tables=[[clean(''.join(c.itertext())) for c in t.xpath('.//th|.//td')] for t in expected.xpath('//table')]
actual_tables=[[clean(''.join(c.xpath('.//w:t/text()',namespaces=ns))) for c in t.xpath('.//w:tc',namespaces=ns)] for t in x.xpath('//w:tbl',namespaces=ns)]
assert expected_tables==actual_tables
headings=re.findall(r'^## (.+)$',(root/'outputs/step1/step1_report.md').read_text(),re.M)
assert len(headings)==13 and all(h in paras for h in headings)
expected_paras=[clean(''.join(p.itertext())) for p in expected.xpath('//body/p') if 'STEP1FIGURE' not in ''.join(p.itertext())]
missing=[p for p in expected_paras if p and p not in paras]
assert not missing,missing[:3]
positions=[i for i,p in enumerate(elements) if p.xpath('.//a:blip',namespaces=ns)]
assert len(positions)==3
assert paras[positions[1]-1].startswith('Hình so sánh IS.')
assert paras[positions[2]-1].startswith('Hình so sánh OOS.')
(out/'verified_text.txt').write_text(text)
with pdfplumber.open(out/'verified_google_doc.pdf') as p:
    pages=[{'page':i+1,'text_length':len(q.extract_text() or ''),'images':len(q.images),'tables':len(q.find_tables())} for i,q in enumerate(p.pages)]
record={'status':'CONTENT_VERIFIED','source_sha256':hashlib.sha256((root/'outputs/step1/step1_report.md').read_bytes()).hexdigest(),
    'all_source_body_paragraphs_present':True,'main_sections':13,'all_13_tables_exact':True,'table_cells_verified':sum(map(len,actual_tables)),
    'images':3,'image_positions_verified':True,'placeholders_removed':True,'readiness_retained':True,'pdf_pages':pages,'source_date':'2026-10-07'}
(out/'publication_verification.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record))
