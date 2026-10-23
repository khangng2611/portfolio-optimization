"""Update local reports, retain numeric tables and package additional evidence."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import json,hashlib,csv,re,shutil
ROOT=Path(__file__).resolve().parents[1];STEP=ROOT/'outputs/step1';OUT=STEP/'blocker_evidence_20261012';section=(OUT/'report_section13.md').read_text()
report=STEP/'step1_report.md';backup=OUT/'step1_report_before_evidence.md'
if not backup.exists():shutil.copy2(report,backup)
original=backup.read_text();updated=original[:original.index('## 13. ')]+section
updated=updated.replace('**Ngày biên tập:** 07/10/2026.','**Ngày biên tập:** 12/10/2026.')
updated=updated.replace('còn nhật ký tái dựng được số công bố kết thúc **27/02/2026**','còn hồ sơ lịch sử khôi phục có ngày OOS cuối **27/02/2026** và tái dựng được NAV công bố')
warning='**Cập nhật 12/10/2026:** bảng này giữ kết quả lượt chạy 04/10/2026 để đối chiếu. Chứng cứ mới về GOLD, thời điểm dữ liệu và điều chỉnh cổ phiếu được nêu tại mục 13; chưa kích hoạt nguồn/giả định mới hoặc chạy lại baseline tháng 4.\n\n'
updated=updated.replace('### 12.1. Kết quả IS và OOS sau hiệu chỉnh\n\n','### 12.1. Kết quả IS và OOS sau hiệu chỉnh\n\n'+warning)
# The report's six empirical result tables remain byte-identical.
start='### 12.1.';end='## 13.'
def tables(s):return re.findall(r'(?m)^\|[^\n]+\n(?:\|[^\n]*\n)+',s[s.index(start):s.index(end)])
assert tables(original)==tables(updated)
assert len(re.findall(r'^## \d+\.',updated,re.M))==13
report.write_text(updated)
rootreport=ROOT/'report.md';rootbackup=OUT/'report_summary_before_evidence.md'
if not rootbackup.exists():shutil.copy2(rootreport,rootbackup)
short=rootbackup.read_text().replace('Cập nhật: **04/10/2026**.','Cập nhật chứng cứ: **12/10/2026**. Số liệu baseline giữ lượt chạy **04/10/2026**.')
where=short.index('## 3. Vấn đề hiện trạng')
short=short[:where]+'''## 3. Chứng cứ mới và vấn đề hiện trạng

Đã kiểm tra cả bốn vấn đề trước Step 2. NAV VFF tải lại khớp **552/552** ngày, nhưng record timestamp chưa xác nhận thời điểm công bố. Bản cáo bạch 2023/2025/2026 ghi đóng sổ **14:40 ngày T−1**, khác mô phỏng close phiên kế tiếp của baseline.

Đã xác định nguồn dự kiến GOLD là **PNJ, SJC tại TPHCM, ngàn đồng/lượng**. Trong **38 ngày có quote tải thành công**, **31 giá snapshot không khớp bất kỳ quote cùng ngày**; đây là kiểm tra mẫu, không ước lượng lỗi toàn kỳ. Thu hồi đủ kỳ bị HTTP429; ngày tải lỗi không được coi là ngày không đổi giá hoặc tự điền. Chuỗi ứng viên chưa kích hoạt.

Đối chiếu KBS **30 mã, 47.243 hàng ngày/mã chung**: **22 mã khớp**, **8 mã có giá thay đổi**. Chưa có ledger sự kiện và công thức factor đầy đủ; chưa chứng nhận lợi nhuận kinh tế/total return.

'''+(OUT/'blocker_evidence_summary.md').read_text().split('## Tái lập và phạm vi\n\n')[1].split('\n\nManifest')[0]+'''

## 4. Kết luận và việc cần xác nhận

Bảng IS/OOS phía trên giữ kết quả 04/10; 33 input vẫn khớp hash. Chưa chạy lại baseline tháng 4 với nguồn/giả định mới. Cần thống nhất **C1: phạm vi VFF và cutoff; C2: nguồn/quy tắc quote GOLD; C3: adjusted-close return hay total return; C4: điều kiện chuyển Step 2 khi vintage chưa đủ**. Kỳ baseline tháng 4 đã được chốt, không cần xác nhận lại.

[Báo cáo kỹ thuật cập nhật](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/step1_report.md) · [Chứng cứ chi tiết](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/blocker_evidence_20261012/blocker_evidence_summary.md) · [Các lựa chọn cần xác nhận](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/blocker_evidence_20261012/16_Decisions_To_Confirm.md).

NOT READY FOR STEP 2
'''
rootreport.write_text(short)
oldsubmission=STEP/'Step1_Submission_20261007';submission=STEP/'Step1_Submission_20261012';submission.mkdir(exist_ok=True)
for p in oldsubmission.iterdir():
 if p.is_file() and not p.name.startswith('.') and p.name not in ['00_Step1_Report.md','00_Attachment_Index.csv']:shutil.copy2(p,submission/p.name)
submit=(oldsubmission/'00_Step1_Report.md').read_text();submit=submit[:submit.index('## 13. ')]+section;submit=submit.replace('**Ngày biên tập:** 07/10/2026.','**Ngày biên tập:** 12/10/2026.')
submit=submit.replace('còn nhật ký tái dựng được số công bố kết thúc **27/02/2026**','còn hồ sơ lịch sử khôi phục có ngày OOS cuối **27/02/2026** và tái dựng được NAV công bố')
submit=submit.replace('### 12.1. Kết quả IS và OOS sau hiệu chỉnh\n\n','### 12.1. Kết quả IS và OOS sau hiệu chỉnh\n\n'+warning)
insert='| `15_Blocker_Evidence_20261012.zip` | Chứng cứ mới cho bốn vấn đề trước Step 2: nguồn công bố, raw API, đối chiếu dữ liệu và thử tái lập lịch sử. | 13 |\n| `16_Decisions_To_Confirm.md` | Bốn lựa chọn C1–C4 cần thống nhất, ảnh hưởng và hồ sơ còn cần cung cấp. | 13 |\n'
submit=submit.replace('| `00_Attachment_Index.csv`',insert+'| `00_Attachment_Index.csv`')
(submission/'00_Step1_Report.md').write_text(submit)
evidence_zip=submission/'15_Blocker_Evidence_20261012.zip';archived=[]
with ZipFile(evidence_zip,'w',ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(OUT.rglob('*')):
  if not p.is_file():continue
  rel=p.relative_to(OUT)
  if any(part.startswith('.') for part in rel.parts) or 'google_doc_update' in rel.parts or 'workspace' in rel.parts or 'mpl' in rel.parts or p.name.startswith('google_doc_before') or p.name.endswith('_before_evidence.md') or p.name=='report_update_verification.json':continue
  z.write(p,str(rel));archived.append(dict(path=str(rel),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
 for p in sorted((OUT/'historical_fresh_refit/workspace/logs').glob('*.json')):
  member='historical_fresh_refit/generated_logs/'+p.name;z.write(p,member);archived.append(dict(path=member,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
 for n in ['step1_collect_blocker_evidence.py','step1_collect_gold_and_actions.py','step1_analyze_blocker_evidence.py','step1_refit_historical_candidate.py','step1_verify_historical_refit.py','step1_write_blocker_findings.py']:
  p=ROOT/'scripts'/n;z.write(p,'scripts/'+n);archived.append(dict(path='scripts/'+n,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
 z.writestr('evidence_member_hashes.json',json.dumps(archived,indent=2))
with ZipFile(evidence_zip) as z:
 assert z.testzip() is None
 assert all(hashlib.sha256(z.read(r['path'])).hexdigest()==r['sha256'] for r in archived)
shutil.copy2(OUT/'16_Decisions_To_Confirm.md',submission/'16_Decisions_To_Confirm.md')
with (oldsubmission/'00_Attachment_Index.csv').open(encoding='utf-8-sig',newline='') as f:
 old_index={r['filename']:r for r in csv.DictReader(f)}
extra_descriptions={'15_Blocker_Evidence_20261012.zip':'Chứng cứ mới cho bốn vấn đề trước Step 2','16_Decisions_To_Confirm.md':'Bốn lựa chọn C1–C4 cần thống nhất'}
index=[]
for p in sorted(submission.iterdir()):
 if p.name=='00_Attachment_Index.csv' or p.name.startswith('.'):continue
 previous=old_index.get(p.name,{})
 index.append(dict(filename=p.name,description=previous.get('description',extra_descriptions.get(p.name,'')),report_sections=previous.get('report_sections','13'),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
with (submission/'00_Attachment_Index.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
outer=STEP/'Step1_Submission_20261012.zip'
with ZipFile(outer,'w',ZIP_DEFLATED) as z:
 for p in sorted(submission.iterdir()):
  if p.is_file() and not p.name.startswith('.'):z.write(p,f'{submission.name}/{p.name}')
record=dict(status='REPORT_AND_PACKAGE_VERIFIED',empirical_tables_unchanged=True,main_sections=13,new_attachment_count=2,total_submission_files=len([p for p in submission.iterdir() if p.is_file() and not p.name.startswith('.')]),evidence_members_verified=len(archived),zip_bytes=outer.stat().st_size,active_baseline_replaced=False,readiness='NOT READY FOR STEP 2')
(OUT/'report_update_verification.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
