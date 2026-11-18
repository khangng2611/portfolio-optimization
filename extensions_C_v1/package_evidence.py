"""Package admitted derived evidence only; raw vendor snapshots are deliberately excluded."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil,zipfile,csv
from .C1_fixed_rule import HERE
from experiments_core.src.frozen import ROOT,sha,write_json


def main():
    out=HERE/'submission';out.mkdir(exist_ok=True)
    shutil.copy2(HERE/'qa/render_final/Additional_Experiments_C_Report.pdf',out/'Additional_Experiments_C_Report.pdf')
    source=list(HERE.glob('*.py'))+list((HERE/'tests').glob('*.py'))
    root_files=list(HERE.glob('*.md'))+list(HERE.glob('*.csv'))+[HERE/x for x in ['baseline_manifest.json','C2_source_audit.json','reproduction_check.json','verification.json']]
    selected={str(p.relative_to(ROOT)):p for p in source+root_files if p.name!='implementation_plan.md'}
    for p in (HERE/'figures').glob('*.png'):selected[str(p.relative_to(ROOT))]=p
    for name in ['Additional_Experiments_C_Report.docx','Additional_Experiments_C_Report.pdf']:
        p=out/name;selected[str(p.relative_to(ROOT))]=p
    for name in ['tests.log','independent_review.md']:
        p=HERE/'qa'/name;selected[str(p.relative_to(ROOT))]=p
    for run_id in ['extensions-C-20261104T210906','extensions-C-20261104T211105']:
        run=HERE/'runs'/run_id
        for p in [run/x for x in ['manifest.json','validation.json','requirements_frozen.txt','stdout.log','stderr.log']]+list((run/'source_snapshot').rglob('*')):
            if p.is_file():selected[str(p.relative_to(ROOT))]=p
    for name in ['core.py','frozen.py']:
        p=ROOT/'experiments_core/src'/name;selected[str(p.relative_to(ROOT))]=p
    p=ROOT/'experiments_core/tests/test_core.py';selected[str(p.relative_to(ROOT))]=p
    assert not any('/inputs/' in name or '/private_inputs/' in name for name in selected)
    manifest={'created_at':datetime.now(timezone.utc).isoformat(),'status':{'C1':'COMPLETED','C2':'NOT_RUN_SOURCE_GATE_NOT_MET','C3_C6':'DESIGN_ONLY'},
              'raw_vendor_inputs_included':False,'replication_scope':'Derived evidence and exact C1 run source snapshots; fresh simulation needs licensed private frozen input pack and existing repository layout.',
              'report_pages':6,'files':[{'path':name,'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in sorted(selected.items())]}
    write_json(HERE/'publication_manifest.json',manifest);selected['extensions_C_v1/publication_manifest.json']=HERE/'publication_manifest.json'
    archive=out/'Additional_Experiments_C_Evidence_20261104.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(selected.items()):z.write(p,name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        import hashlib
        for item in manifest['files']:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
        assert not any('/inputs/' in name or name.endswith('prices_valuation.csv') for name in z.namelist())
    # Individually visible files, plus archive for complete source/daily/event evidence.
    visible=['C1_results.csv','comparisons.csv','paired_uncertainty.csv','C1_event_trades.csv','target_L1_distances.csv',
             'C2_results.csv','C2_source_feasibility.md','C2_source_and_alignment.md','issues_to_supervisor.md','optional_proposals.md','validations.md','data_dictionary.md','input_dictionary.csv','publication_manifest.json']
    for name in visible:shutil.copy2(HERE/name,out/name)
    (out/'00_README_First.txt').write_text('''THÍ NGHIỆM BỔ SUNG C — 04/11/2026\n\nĐọc báo cáo DOCX/PDF 6 trang trước. C1 đã hoàn tất và kiểm tra hai lần; C2 chưa chạy số liệu vì thiếu bộ daily total-return với vintage/quyền nghiên cứu; C3–C6 mới là đề cương.\n\nCác CSV ngoài ZIP là bảng chính để xem ngay. C1_results: fractions cho CAGR/vol/MDD; paired_uncertainty/comparisons: chênh lệch CAGR theo điểm phần trăm. C1_event_trades: một dòng mỗi sự kiện; không có tổng lặp theo tài sản.\n\nZIP chứa source, snapshot source lúc chạy, daily/trades/holdings, figures, manifests/hash, protocol, tests/logs và hướng dẫn tái lập. Có thể giải nén thành thư mục để đọc. Không có raw vendor prices/private input pack trong ZIP; người tái chạy cần dữ liệu được cấp quyền riêng.\n\nC2_results chỉ có status/null, không phải chỉ số return=0. Đọc C2_source_feasibility và issues_to_supervisor để quyết định nguồn hoặc phạm vi tiếp theo.\n''')
    with (out/'SHA256SUMS.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['file','bytes','sha256'])
        for p in sorted(out.iterdir()):
            if p.is_file() and p.name!='SHA256SUMS.csv' and not '.draft.' in p.name:w.writerow([p.name,p.stat().st_size,sha(p)])
    print(json.dumps({'archive':str(archive),'files_inside':len(selected),'bytes':archive.stat().st_size,'raw_input_files':0,'status':'VERIFIED'}))

if __name__=='__main__':main()
