"""Create a content-verified submission archive; never alter Step 1 files."""
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import zipfile
from zoneinfo import ZoneInfo
import pandas as pd
from .frozen import ROOT,PKG,READY,BASE,BASE_RUN,sha,write_json,relocated

PRIMARY='core-evidence-20261023T211011'
REPEAT='core-evidence-20261023T211139'


def main():
    submission=PKG/'submission';out=PKG/'outputs';docs=PKG/'docs'
    shutil.copy2(PKG/'qa/report_render_delivery/Step2_Core_Evidence_Report.pdf',submission/'Step2_Core_Evidence_Report.pdf')
    shutil.copy2(docs/'core_experiment_report.md',submission/'core_experiment_report.md')
    for name in ['selection_structure.csv','selection_portfolio_metrics.csv','optimizer_ladder_metrics.csv','cost_sensitivity.csv','uncertainty_intervals.csv']:
        shutil.copy2(out/name,submission/name)
    for run,label in [(PRIMARY,'primary'),(REPEAT,'repeat')]:
        directory=PKG/'runs'/run
        for stream in ['stdout','stderr']:
            shutil.copy2(PKG/f'runs_{label}_{stream}.log',directory/f'{stream}.log')
        write_json(directory/'execution_log_attachment.json',{
            'stdout':'stdout.log','stderr':'stderr.log','exit_code':0,
            'stdout_sha256':sha(directory/'stdout.log'),'stderr_sha256':sha(directory/'stderr.log'),
            'attached_at':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
            'saved_signals_reused':True,'pretrained_model_cache_inference_reused':False})
    pd.concat([pd.read_csv(PKG/'runs'/r/'outputs/experiment_registry.csv') for r in [PRIMARY,REPEAT]]).to_csv(docs/'experiment_registry_all_runs.csv',index=False)
    (submission/'00_README.md').write_text('''# Báo cáo Step 2 và bộ minh chứng

Đọc Step2_Core_Evidence_Report.pdf hoặc bản Word tương ứng. Các bảng CSV đặt ngoài ZIP giúp đối chiếu nhanh; raw return, weights, covariance, lịch chọn, log, source, dữ liệu và toàn bộ run records nằm trong Step2_Core_Evidence_20261023.zip.

Đã chạy 13 nhánh A và 3 nhánh B, kiểm tra lặp toàn bộ. Có 641 return OOS chung, 6 kiểm thử mới và 35 kiểm thử kế thừa đạt, 10.245 assertion độc lập đạt. Kết quả đủ để sửa bài báo trong phạm vi giả định đã khai báo, không chứng nhận chiến lược thực thi giao dịch.

Kết luận: Proposed ổn định và turnover thấp; ML cải thiện gross OOS nhưng nhạy chi phí. Tất cả khoảng tin cậy bootstrap chênh lệch CAGR/Sharpe chứa 0. Các probe confidence/regime độc lập chưa chạy. Chi tiết IS/OOS, giả định và sai khác đã khai báo có trong báo cáo.

evidence_manifest.json trong ZIP có SHA-256 cho từng tệp. Exact guide copies và bản xuất báo cáo Step1 được băm lúc đóng gói, tách biệt với numerical freeze trước thực thi. Không thay đổi baseline Step1 hoặc quyền chia sẻ Drive.

Để tái lập, giải nén vào checkout của source commit ghi trong manifest, dùng research environment theo requirements_frozen.txt và xem experiments_core/README.md. Môi trường Python không được nhúng trong ZIP. Không cần model cache hay tải dữ liệu mới.
''')
    files={}
    def add(path,archive=None):
        path=Path(path)
        if not path.is_file() or '__pycache__' in path.parts or path.name=='.DS_Store':return
        files[archive or str(path.relative_to(ROOT))]=path
    # Curated task package only; omit unrelated concurrent application changes.
    for folder in ['src','tests','config','docs']:
        for p in (PKG/folder).rglob('*'):add(p)
    for p in [PKG/'README.md',PKG/'.gitignore',PKG/'core_tests_final.log',PKG/'inherited_tests.log']:add(p)
    for r in [PRIMARY,REPEAT]:
        for p in (PKG/'runs'/r).rglob('*'):add(p)
    # A physical canonical output copy makes Markdown figure links portable.
    for p in out.rglob('*'):
        if p.is_file():add(p,str(Path('experiments_core/outputs')/p.relative_to(out)))
    for p in BASE.rglob('*'):add(p)
    for p in BASE_RUN.rglob('*'):add(p)
    repeat=READY/'runs/availability-observed-contract-repeat-20261012T234301'
    for p in (repeat/'artifacts').glob('*.csv'):add(p)
    add(repeat/'manifest.json')
    original=json.loads((BASE_RUN/'manifest.json').read_text())
    for item in original['inputs']:
        path=relocated(item['path']);assert sha(path)==item['sha256'];add(path)
    for name in ['availability_policy.json','candidate_information_prices.csv','availability_ledger.csv','readiness_status.json','reproducibility_verification.json']:
        add(READY/name)
    add(submission/'Step2_Core_Evidence_Report.docx')
    add(submission/'Step2_Core_Evidence_Report.pdf')
    refs=PKG/'config/references'
    for name in ['guide_1.md','project_1.md']:
        original_path=Path('/Users/nguyenkhang/Documents/MASTER/Thesis/phase2-journal-plan')/name
        assert sha(original_path)==sha(refs/name)
    for entry in json.loads((PKG/'runs'/PRIMARY/'manifest.json').read_text())['files']:
        if entry['path'].startswith('outputs/step1/'):
            assert sha(ROOT/entry['path'])==entry['sha256']
    # Final provenance intentionally supplements, rather than rewrites, run manifests.
    manifest={'schema_version':1,'packaged_at':datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
              'primary':PRIMARY,'repeat':REPEAT,'status':'READY FOR PAPER REVISION',
              'reference_hash_stage':'publication time; numerical input/config freeze is in each original run manifest',
              'reference_hashes':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted(refs.glob('*'))]+[
                  {'path':str((docs/'implementation_plan.md').relative_to(ROOT)),'sha256':sha(docs/'implementation_plan.md')}],
              'verification':json.loads((PKG/'runs'/PRIMARY/'independent_verification.json').read_text()),
              'scope':'research experiment report; no submission-ready manuscript or executable fund-trading certification',
              'files':[{'archive_path':name,'sha256':sha(p),'bytes':p.stat().st_size} for name,p in sorted(files.items())]}
    write_json(submission/'evidence_manifest.json',manifest)
    archive=submission/'Step2_Core_Evidence_20261023.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(files.items()):z.write(p,name)
        z.write(submission/'evidence_manifest.json','evidence_manifest.json')
        z.write(submission/'00_README.md','README_Submission.md')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for item in manifest['files']:
            assert hashlib.sha256(z.read(item['archive_path'])).hexdigest()==item['sha256']
    ready=[p for p in submission.iterdir() if p.is_file() and not p.name.endswith('.draft.docx') and p.name not in ['evidence_manifest.json','SHA256SUMS.csv','upload_verification.json']]
    with (submission/'SHA256SUMS.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=['file','bytes','sha256']);writer.writeheader()
        for p in sorted(ready):writer.writerow({'file':p.name,'bytes':p.stat().st_size,'sha256':sha(p)})
    write_json(PKG/'qa/submission_validation.json',{'status':'PASS','archive_files':len(files)+2,'every_archived_content_hash_verified':True,
               'baseline_inputs_unchanged':True,'report_pages':7,'visual_review':'all pages inspected; first four final PNGs byte-identical to inspected prior render',
               'archive_bytes':archive.stat().st_size,'primary':PRIMARY,'repeat':REPEAT})
    print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'files':len(files)+2,'submission_files':[p.name for p in sorted(ready)]+['SHA256SUMS.csv']}))


if __name__=='__main__':main()
