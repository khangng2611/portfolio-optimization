"""Package immutable April-run evidence and adapt report references for submission."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib, json, csv, re, shutil

ROOT=Path(__file__).resolve().parents[1]
STEP=ROOT/'outputs/step1'
PERIOD=STEP/'paper_period'
COR=PERIOD/'corrected'
RUN=STEP/'runs/corrected-paper-period-20261004T132742'
LEG=PERIOD/'legacy_on_canonical_inputs/legacy-canonical-20261004T133015'
OUT=STEP/'Step1_Submission_20261007'
PUB=PERIOD/'google_doc_submission_20261007'
OUT.mkdir(exist_ok=True); PUB.mkdir(exist_ok=True)
records=[]; mappings={}; inventory=[]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def record(src, dest, member=''):
    records.append(dict(source=str(src.relative_to(ROOT)),attachment=dest,member=member,sha256=digest(src),bytes=src.stat().st_size))
    mappings[str(src)]=(dest,member)
def copy(src,name,desc,section):
    shutil.copy2(src,OUT/name); assert digest(src)==digest(OUT/name)
    record(src,name); inventory.append((name,desc,section))
def archive(name,entries,desc,section):
    seen=set()
    with ZipFile(OUT/name,'w',ZIP_DEFLATED,compresslevel=9) as z:
        for src,member in entries:
            assert src.is_file(),src
            if member in seen:continue
            z.write(src,member); seen.add(member); record(src,name,member)
    inventory.append((name,desc,section))
def tree(path,prefix):return [(p,f'{prefix}/{p.relative_to(path)}') for p in sorted(path.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
for n,(base,label,desc) in enumerate([
 ('metrics','Metrics','Hiệu suất IS/OOS của EW, MVO, BL+ML và Hybrid: NAV, lợi nhuận, biến động, Sharpe, drawdown và turnover.'),
 ('nav','NAV','Chuỗi NAV hằng ngày để đối chiếu diễn biến và số cuối kỳ.'),
 ('daily_returns','Daily_Returns','Lợi nhuận hằng ngày dùng tính lại các chỉ số hiệu suất.'),
 ('weights','Target_Weights','Tỷ trọng mục tiêu tại mỗi lần tái cân bằng; không phải tỷ trọng trôi theo giá hằng ngày.'),
 ('turnover','Turnover','Chi tiết giao dịch và turnover của từng chiến lược; kết quả chưa trừ chi phí.')],1):
    copy(COR/f'trusted_baseline_{base}.csv',f'{n:02d}_Baseline_{label}.csv',desc,'8, 12')
audit_names=['training_window_audit.csv','ml_training_audit.csv','ml_prediction_audit.csv','selection_history.csv','execution_ledger.csv','constraint_violations.csv','constraint_diagnostics.csv','turnover_summary.csv','forecast_origin_diagnostics.csv','forecast_origin_summary.csv']
entries=[(COR/n,n) for n in audit_names]+tree(RUN/'selection_matrices','selection_matrices')+tree(COR/'bl_audit_sample/corrected','bl_audit_sample/corrected')
archive('06_Pipeline_Audit.zip',entries,'Nhật ký thời điểm thực thi, huấn luyện/dự báo ML, chọn tài sản, ma trận lựa chọn, BL và ràng buộc. CSV vi phạm chỉ có tiêu đề vì không phát hiện vi phạm ở ngưỡng 1e-8.','4–8')
mappings[str(COR/'bl_audit_sample/corrected')]=('06_Pipeline_Audit.zip','bl_audit_sample/corrected/')
entries=[(STEP/n,n) for n in ['data_manifest.csv','audit_data.md']]+[(PERIOD/n,n) for n in ['april_run_data_diagnostics.json','april_run_data_diagnostics.md','input_coverage.md','input_coverage.json','active_run.json']]
archive('07_Data_Audit.zip',entries,'Danh mục nguồn dữ liệu, xác minh VFF, chẩn đoán dữ liệu và độ bao phủ của kỳ chạy tháng 4. Nhật ký lịch sử có đề cập kỳ tháng 7; active_run.json xác định kỳ nộp hiện tại.','1–3')
entries=[(STEP/n,n) for n in ['universe_provenance.md','parameter_provenance.csv','mvo_reconciliation.md','change_log.md']]+[(PERIOD/'step1_report_before_selection_20261007.md','reference_full_report.md')]
archive('08_Design_Provenance.zip',entries,'Nguồn gốc tập tài sản, tham số, nhật ký sửa lỗi và báo cáo chi tiết để tra cứu. Báo cáo chính cập nhật cách hiểu nhãn MVO component trong PDF.','3, 9–11')
entries=[(RUN/n,f'primary_run/{n}') for n in ['manifest.json','run_config.json','random_seeds.txt','requirements_frozen.txt','runner_source.py','aligned_prices.csv','stdout.log','stderr.log']]+tree(RUN/'source_snapshot','primary_run/source_snapshot')
entries += [(STEP/'runs/corrected-paper-period-repeat-20261004T133908/manifest.json','repeat_run/manifest.json'),(ROOT/'legacy_version/snapshot_manifest.json','legacy_snapshot/snapshot_manifest.json')]
entries += [(PERIOD/n,n) for n in ['reproducibility_verification.json','reproducibility_verification.md','final_trusted_tests.log']]+tree(PERIOD/'independent_review','independent_review')
entries += [(p,str(p.relative_to(STEP))) for p in sorted((STEP/'legacy_results').rglob('*')) if p.is_file() and 'workspace' not in p.parts and 'matplotlib-cache' not in p.parts]
archive('09_Reproducibility.zip',entries,'Manifest, cấu hình/seed/môi trường, mã nguồn baseline, ma trận giá, snapshot manifest gốc và kết quả 27 kiểm thử, 52 kiểm tra độc lập, 40 kiểm tra tái lập.','1, 8, 11')
mappings[str(STEP/'legacy_results')]=('09_Reproducibility.zip','legacy_results/')
entries=[(PERIOD/n,n) for n in ['paper_vs_corrected_metrics.csv','legacy_vs_corrected_metrics.csv','corrected_alpha_sensitivity.csv','corrected_alpha_nav.csv','paper_vs_corrected_alpha.csv','alpha_grid_method.json','corrected_hitrate_summary.csv','corrected_hitrate_details.csv'] if (PERIOD/n).is_file()]
entries += [(LEG/n,f'legacy_canonical/{n}') for n in ['common_oos_window_comparison.csv','controlled_comparison.json','legacy_constraint_summary.json','manifest.json']]
entries += [(LEG/'artifacts'/n,f'legacy_canonical/artifacts/{n}') for n in ['legacy_nav.csv','legacy_metrics.csv','legacy_daily_returns.csv']]
entries += [(STEP/'portfolio_static'/n,f'historical_replay/{n}') for n in ['historical_replay_report.json','historical_replay_metrics.csv','historical_replay_daily_returns_nav.csv']]
entries += [(PERIOD/'google_doc_20261006'/n,f'trajectory/{n}') for n in ['trajectory_comparison.csv','trajectory_common_dates.csv','comparison_provenance.json']]
entries += [(p,f'printed_paper_tables/{p.name}') for p in (PERIOD/'pdf_audit').glob('printed*.csv')]
archive('10_Comparison_Details.zip',entries,'Bảng đối chiếu paper/logic gốc/baseline, cửa sổ OOS chung, alpha, hit rate và chuỗi NAV tái dựng lịch sử để kiểm tra các hình.','9, 12')
copy(PERIOD/'google_doc_20261007/legacy_vs_corrected_readable.png','11_NAV_Legacy_vs_Corrected.png','Đường NAV logic gốc và baseline trên cùng đầu vào tháng 4, cho MVO, BL+ML và Hybrid.','12.2')
copy(PERIOD/'google_doc_20261006/paper_vs_rerun_is.png','12_NAV_IS_vs_Paper.png','Đối chiếu đường NAV IS sau chuẩn hóa tại cùng mốc.','12.4')
copy(PERIOD/'google_doc_20261006/paper_vs_rerun_oos.png','13_NAV_OOS_vs_Paper.png','Đối chiếu NAV OOS; vùng sau 27/02/2026 chỉ có baseline, không có đường paper kéo dài giả định.','12.4')
archive('14_Diagnostic_Plots.zip',tree(COR/'plots','plots'),'Sơ đồ walk-forward và hình ràng buộc, turnover, NAV, drawdown; có cả PNG và PDF.','4, 8, 11')
mappings[str(COR)]=('01_Baseline_Metrics.csv','')
source=STEP/'step1_report.md'; original=source.read_text(); md=original
def ref(m):
    label,src=m.group(1),m.group(2)
    assert src in mappings,src
    name,member=mappings[src]
    if m.group(0).startswith('!'):return f'![{label}]({OUT/name})'
    detail=f' → `{member}`' if member else ''
    return f'[{name}]({name}){detail}'
md=re.sub(r'!?\[([^\]]+)\]\((/[^)]+)\)',ref,md)
md=md.replace('Ma trận `.npz` được tham chiếu tương đối với thư mục lượt chạy chính tại mục 11.','Ma trận `.npz` được lưu trong `06_Pipeline_Audit.zip`; sau giải nén, giữ cùng cấu trúc `selection_matrices/` như đường dẫn trong CSV.')
start=md.index('| Nhóm hồ sơ cần lưu/nộp kèm |'); end=md.index('\n\n**Minh chứng:**',start)
table='### Danh mục tệp đính kèm\n\nCác tệp dưới đây được đặt cùng thư mục với Google Doc. Tên nộp được chuẩn hóa; nội dung CSV và hình giữ nguyên từ lượt chạy tháng 4/2026. Các gói ZIP giữ tên gốc của hồ sơ bên trong. Ký hiệu “ZIP → tệp” trong các mục minh chứng chỉ vị trí sau giải nén.\n\n| Tên tệp trong thư mục nộp | Nội dung và mục đích | Mục báo cáo |\n|---|---|---|\n'
for name,desc,sec in inventory:table+=f'| `{name}` | {desc} | {sec} |\n'
table+='| `00_Attachment_Index.csv` | Danh mục tất cả tệp, dung lượng và SHA-256 để kiểm tra việc sao chép. | 11 |\n| `00_Step1_Report.md` | Bản văn bản tương ứng với Google Doc để lưu trữ. | 1–13 |\n'
table+='\n**Phạm vi bộ minh chứng:** các gói chứa hồ sơ kiểm tra và cấu hình của nghiên cứu, không phải toàn bộ dự án, môi trường thực thi hoặc 631 tệp của phiên bản gốc. Đường dẫn trong manifest phản ánh nơi tạo lượt chạy; bảng ánh xạ `attachment_source_map.csv` trong gói tái lập liên kết chúng với tệp nộp. Các tài liệu audit lịch sử được giữ nguyên và phải đọc cùng kỳ chạy ghi tại đầu báo cáo. Hai hồ sơ `training_window_audit.csv` và `ml_training_audit.csv` có nội dung giống nhau, được giữ cả hai theo tên đầu ra hướng dẫn.'
md=md[:start]+table+md[end:]
assert len(re.findall(r'^## \d+\.',md,re.M))==13
# Tables of empirical results must be unchanged; only the attachment table changes.
old_tables=re.findall(r'(?m)^\|[^\n]+\n(?:\|[^\n]*\n)+',original)
new_tables=re.findall(r'(?m)^\|[^\n]+\n(?:\|[^\n]*\n)+',md)
assert [t for t in old_tables if 'Nhóm hồ sơ' not in t]==[t for t in new_tables if 'Tên tệp trong' not in t]
(OUT/'00_Step1_Report.md').write_text(md)
mapping_file=PUB/'attachment_source_map.csv'
with mapping_file.open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
with ZipFile(OUT/'09_Reproducibility.zip','a',ZIP_DEFLATED) as z:z.write(mapping_file,'attachment_source_map.csv')
index_rows=[dict(filename=n,description=d,report_sections=s,bytes=(OUT/n).stat().st_size,sha256=digest(OUT/n)) for n,d,s in inventory]
index_rows.append(dict(filename='00_Step1_Report.md',description='Bản báo cáo tương ứng Google Doc',report_sections='1–13',bytes=(OUT/'00_Step1_Report.md').stat().st_size,sha256=digest(OUT/'00_Step1_Report.md')))
with (OUT/'00_Attachment_Index.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(index_rows[0]));w.writeheader();w.writerows(index_rows)
# Verify every archive member against its original source.
for r in records:
    if r['member']:
        with ZipFile(OUT/r['attachment']) as z:assert hashlib.sha256(z.read(r['member'])).hexdigest()==r['sha256']
    else:assert digest(OUT/r['attachment'])==r['sha256']
assert digest(source)==hashlib.sha256(original.encode()).hexdigest()
outer=STEP/'Step1_Submission_20261007.zip'
with ZipFile(outer,'w',ZIP_DEFLATED) as z:
    for p in sorted(OUT.iterdir()):z.write(p,f'{OUT.name}/{p.name}')
status=dict(status='PASS',canonical_report_sha256=digest(source),submission_report_sha256=digest(OUT/'00_Step1_Report.md'),attachment_count=len(list(OUT.iterdir())),source_files_verified=len(records),empirical_tables_unchanged=True,all_references_mapped=True,zip_bytes=outer.stat().st_size,not_uploaded_to_drive=True)
(PUB/'package_verification.json').write_text(json.dumps(status,indent=2))
print(json.dumps(status))
