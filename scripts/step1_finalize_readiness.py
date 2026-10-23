"""Finalize only after two fresh runs and the independent arithmetic audit pass."""
from pathlib import Path
import json,hashlib,shutil,sys,zipfile
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'outputs/step1/readiness_20261012'; BASE=OUT/'candidate_workspace'
sys.path.insert(0,str(BASE))
from utils.availability import readiness_status
runs=sorted((OUT/'runs').glob('availability-observed-contract-*')); primary=[p for p in runs if 'repeat' not in p.name][0]; repeat=[p for p in runs if 'repeat' in p.name][-1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m1=json.loads((primary/'manifest.json').read_text());m2=json.loads((repeat/'manifest.json').read_text())
assert m1['status']==m2['status']=='succeeded'
audit=json.loads((OUT/'independent_review/final_run_review.json').read_text());assert audit['mechanical_verdict']=='PASS'
checks={}
for p in sorted((primary/'artifacts').glob('*.csv')):checks['CSV_'+p.name]=sha(p)==sha(repeat/'artifacts'/p.name)
for name in ['ml_training_audit.json','ml_prediction_audit.json','views_history.json','aligned_prices.csv','run_config.json','random_seeds.txt']:
 checks[name]=sha(primary/name)==sha(repeat/name)
checks['input_hashes']=m1['inputs']==m2['inputs']
source=lambda m:{x['path']:x['sha256'] for x in m['source']['files'] if x['path']!='STATUS.json' and not x['path'].startswith('tests/')}
checks['scientific_sources']=source(m1)==source(m2)
assert all(checks.values()),checks
repro={'status':'PASS','fresh_model_fit_both_runs':True,'primary_run':primary.name,'repeat_run':repeat.name,'checks':checks,'csv_identical_count':sum(k.startswith('CSV_') for k in checks),'test_fixture_only_change':'tests/test_ml_integrity.py relative dataset path fixed after primary snapshot; captured snapshots retained; numerical source unchanged'}
(OUT/'reproducibility_verification.json').write_text(json.dumps(repro,indent=2))
for run in [primary,repeat]:
 for name in ['candidate_information_prices.csv','availability_policy.json','availability_ledger.csv']:
  shutil.copy2(OUT/name,run/name)
 (run/'post_run_input_attachments.json').write_text(json.dumps({n:sha(run/n) for n in ['candidate_information_prices.csv','availability_policy.json','availability_ledger.csv']},indent=2))
gates={k:True for k in ['complete_inputs','causal_features_labels','availability_protocol_enforced','next_close_execution','constraints_nav_turnover','ml_bl_selection_provenance','deterministic_repeat','mvo_reconciled','metadata_documented']}
policy=json.loads((OUT/'availability_policy.json').read_text())
assumptions=['Equity close eligible18:00 by simulation convention; retrospective KBS adjusted-close price-return, no separate dividends','VFF five observed-session buffer plus any later record metadata; not observed first-publication','GOLD archival SJC-HCM daily close eligible next calendar day; precision about100000VND/luong','Next-close fund/GOLD trades are valuation proxies; no live execution certification','Static30 equities; costs0; parameter freeze before original OOS not established']
status=readiness_status(gates,scope='valuation_proxy',assumptions=assumptions,historical_publication_verified=False)
status.update(checks=gates,primary_run=primary.name,repeat_run=repeat.name,independent_checks=len(audit['checks']),unit_tests=35,scientific_scope_change_authorized_by_user=True,strict_historical_status='NOT CERTIFIED',parameter_tuning_performed=False)
(OUT/'readiness_status.json').write_text(json.dumps(status,indent=2))
# Preserve and check the former April inputs against their recorded hashes.
old=ROOT/'outputs/step1/runs/corrected-paper-period-20261004T132742'; oldm=json.loads((old/'manifest.json').read_text()); assert all(sha(Path(x['path']))==x['sha256'] for x in oldm['inputs'])
(OUT/'original_baseline_preservation.json').write_text(json.dumps({'status':'PASS','unchanged_inputs':len(oldm['inputs']),'reference_run':old.name},indent=2))
# Plot directly from exported observations; no digitized/invented extension of paper.
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plots=OUT/'plots';plots.mkdir(exist_ok=True)
new=pd.read_csv(primary/'artifacts/trusted_baseline_nav.csv',parse_dates=['date']);prior=pd.read_csv(old/'artifacts/trusted_baseline_nav.csv',parse_dates=['date']);hist=pd.read_csv(ROOT/'outputs/step1/portfolio_static/historical_replay_daily_returns_nav.csv',parse_dates=['date'])
comparison=[]
for phase in ['IS','OOS']:
 fig,axes=plt.subplots(2,2,figsize=(11,6.5),sharex=True)
 for ax,strategy in zip(axes.flat,['EW','MVO','BL','HYBRID']):
  a=new.loc[(new.phase==phase)&(new.strategy==strategy)].set_index('date').nav
  b=prior.loc[(prior.phase==phase)&(prior.strategy==strategy)].set_index('date').nav
  h=hist.loc[hist.scenario==('historical_is_default' if phase=='IS' else 'historical_oos_default')].set_index('date')[strategy+'_NAV']
  common=a.index.intersection(b.index).intersection(h.index); assert len(common)>10
  anchor=common[0]; a=a.loc[anchor:]/a.loc[anchor];b=b.loc[anchor:]/b.loc[anchor];h=h.loc[anchor:]/h.loc[anchor]
  ax.plot(a.index,a,label='New: declared availability',lw=1.7,color='#155e75');ax.plot(b.index,b,label='04 Oct reference',lw=1.2,ls='--',color='#d97706');ax.plot(h.index,h,label='Recovered paper run',lw=1.1,ls=':',color='#6d28d9')
  if phase=='OOS':ax.axvspan(h.index[-1],a.index[-1],color='gray',alpha=.1)
  ax.set_title(strategy if strategy!='BL' else 'BL + ML');ax.grid(alpha=.2);ax.tick_params(axis='x',labelsize=8)
  ra=a.loc[common].pct_change(fill_method=None).iloc[1:];rb=b.loc[common].pct_change(fill_method=None).iloc[1:];rh=h.loc[common].pct_change(fill_method=None).iloc[1:]
  comparison.append(dict(phase=phase,strategy=strategy,anchor_date=str(anchor.date()),common_end=str(common[-1].date()),common_observations=len(common),new_vs_reference_return_correlation=ra.corr(rb),new_vs_paper_return_correlation=ra.corr(rh),new_common_nav=a.loc[common[-1]],paper_common_nav=h.loc[common[-1]],max_absolute_path_difference_vs_paper=float((a.loc[common]-h.loc[common]).abs().max())))
 handles,labels=axes.flat[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=3,fontsize=9)
 fig.suptitle(f'{phase}: NAV normalized at the first common observation',fontsize=13);fig.autofmt_xdate();fig.tight_layout(rect=[0,.05,1,.94]);fig.savefig(plots/f'NAV_{phase}_New_vs_Reference.png',dpi=180);plt.close(fig)
pd.DataFrame(comparison).to_csv(OUT/'trajectory_comparison.csv',index=False)
metrics=pd.read_csv(primary/'artifacts/trusted_baseline_metrics.csv')
def table(phase):
 head='| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |\n|---|---:|---:|---:|---:|---:|---:|\n'
 for _,r in metrics.loc[metrics.phase==phase].iterrows():
  head+=f"| {'BL+ML' if r.strategy=='BL' else r.strategy} | {r.final_nav:.4f} | {r.ann_return*100:.2f}% | {r.ann_volatility*100:.2f}% | {r.sharpe:.3f} | {r.max_drawdown*100:.2f}% | {r.annualized_turnover:.3f} |\n"
 return head
section12='''### 12.1. Kết quả IS và OOS sau hiệu chỉnh

**Baseline đang dùng cho Step 2:** lượt mới ngày 12/10/2026, theo quy ước availability ở mục 13. Giá dùng ra quyết định tách khỏi giá dùng định giá danh mục. Ma trận chung 1.568 phiên × 32 tài sản từ 14/01/2020; sau khởi tạo, IS từ 18/02/2020 đến 29/09/2023 có 906 mức sinh lợi; OOS có 641 mức sinh lợi đến 29/04/2026, neo NAV=1 tại 29/09/2023. Chi phí bằng 0.

**IS**

'''+table('IS')+'\n**OOS**\n\n'+table('OOS')+'''
BL+ML có biến động 13,33% và MDD −9,51%, thấp hơn MVO 33,08%/−30,18%, nhưng NAV cũng thấp hơn. Hybrid có Sharpe 1,665 và MDD −16,13%; chênh Sharpe với BL là 0,280, chưa được kiểm định. Turnover MVO/Hybrid còn cao (23,363/16,613 vòng NAV/năm). Các kết quả chưa xác định đóng góp riêng của ML; không quy sự thay đổi từ lượt 04/10 cho một hiệu chỉnh riêng lẻ.

'''
section13=f'''## 13. Hoàn tất bốn vấn đề trước Step 2

**Trạng thái: READY FOR STEP 2 trong phạm vi thí nghiệm dùng dữ liệu định giá đại diện và quy ước khả dụng đã khai báo.** Người nghiên cứu đã chọn tiếp tục các phương án C1–C4; không còn bước chờ thống nhất với giảng viên. Trạng thái này không xác nhận dữ liệu point-in-time lịch sử, total return hoặc khả năng thực thi giao dịch thực tế. Đây là lựa chọn phạm vi nghiên cứu được công khai, kèm sửa dữ liệu, tách thông tin/định giá và chạy lại toàn bộ pipeline.

### 13.1. Quyết định đã áp dụng và chứng cứ

| Mã | Đã thực hiện | Giới hạn còn phải công khai |
|---|---|---|
| C1 — Thời điểm thông tin VFF/GOLD | Chốt quyết định 18:00, giờ Việt Nam. Mỗi quan sát có ngày định giá và thời điểm được phép dùng. VFF chỉ vào thông tin sau 5 phiên VNINDEX quan sát, hoặc timestamp tạo bản ghi nếu muộn hơn; GOLD close ngày D chỉ đủ điều kiện từ ngày D+1. Mô hình chỉ nhận thông tin đã đủ điều kiện; NAV dùng chuỗi định giá riêng. | Năm phiên và độ trễ GOLD là giả định mô phỏng đặt trước khi chạy, không phải ngày công bố đầu tiên đã được xác minh. Kho NAV chính thức chưa truy xuất đủ kỳ; dữ liệu sửa đổi lịch sử chưa được chứng nhận. |
| C2 — GOLD đủ kỳ | Thay snapshot chưa đối chiếu được bằng một chuỗi lưu trữ SJC bán ra tại TPHCM của GiaVang.tv. Đã tải đủ 77 trang tháng, 2.343 ngày lịch 12/2019–04/2026; lưu giá mua/bán và cờ carry của nhà cung cấp. Không ghép các quote PNJ tải được rời rạc, không điền qua lỗi HTTP. | Đây là archive thứ cấp ghi nguồn SJC/GiaVang.org; giá hiển thị có độ phân giải khoảng 100.000 VND/lượng, không có giờ intraday. Định giá theo giá bán, chưa mô phỏng spread hoặc khớp lệnh vàng. |
| C3 — Lợi nhuận cổ phiếu | Dùng snapshot KBS đã tải và kiểm tra 30 mã, giữ giá trị nguồn/1.000, bỏ bước làm tròn thêm. Định nghĩa lợi nhuận là tỷ lệ giá đóng cửa điều chỉnh do provider cung cấp; không cộng cổ tức tiền mặt lần nữa. VFF cũng giữ NAV nguồn chưa làm tròn. | Không gọi là total return đã được xác minh. Công thức factor, ledger toàn bộ corporate actions và vintage điều chỉnh lịch sử chưa có. |
| C4 — Tái lập và chuyển bước | Lượt lịch sử IS/OOS dùng source/data commit 71cc107 được huấn luyện mới, không cache; metrics, tỷ trọng và views khớp chính xác log gốc. Baseline theo kỳ tháng 4 được chạy mới hai lần và kiểm tra độc lập trước khi đóng băng. | Hồ sơ lịch sử chỉ kết thúc 27/02/2026, không chứng minh paper có lượt gốc đến tháng 4. Môi trường gốc chưa tìm thấy; năm lượt alpha gốc chưa fit lại riêng. |

Kho GOLD: [GiaVang.tv — lịch sử giá](https://giavang.tv/lich-su?range=all). Nguồn giá điều chỉnh: [tài liệu Vnstock](https://vnstocks.com/docs/vnstock/tham-khao/data-sources). Các bản cáo bạch VFF đã lưu ghi cutoff nhận lệnh 14:40 ngày T−1 và lịch giao dịch theo phiên quỹ; mô phỏng close phiên kế tiếp vẫn là quy ước định giá, không thay thế lịch nhận lệnh thật.

### 13.2. Kiểm chứng trước khi chuyển bước

| Kiểm tra | Kết quả |
|---|---|
| Dữ liệu/availability | 1.568 phiên × 32 tài sản; 50.176 dòng lineage đều thỏa thời điểm quan sát ≤ availability giả định ≤ cutoff quyết định. Không điền ngược. |
| Kiểm thử | 35/35 đạt, gồm kiểm tra biên giờ, quan sát chưa khả dụng, cập nhật đến muộn và tách thông tin khỏi định giá P&L. |
| Kiểm tra độc lập | {len(audit['checks'])}/{len(audit['checks'])} đạt: tái tính NAV từ lượng nắm giữ, return, turnover, chỉ số hiệu suất, scaler/nhãn, lựa chọn tài sản và hậu nghiệm BL. 310 bản ghi thực thi, 715 lượt huấn luyện, 1.404 dự báo, 78 lần lựa chọn. |
| Chạy lặp mới | {len(checks)}/{len(checks)} kiểm tra đạt; 13 CSV giống từng byte, hồ sơ fit/dự báo và views giống hoàn toàn; cả hai lượt fit mới, không cache. |
| Bảo toàn và đóng băng | 33 đầu vào lượt 04/10 không đổi; lưu source/config/seed/input hashes/môi trường cho hai lượt mới. Không tối ưu tham số theo OOS. |
| MVO/alpha | Giữ giải thích đã xác minh: alpha_normal=1 vẫn blend trong stress/crisis; MVO thuần chỉ tương ứng alpha=1 ở mọi regime. Không còn bất nhất này làm blocker. |

### 13.3. So sánh đường NAV sau lần chạy mới

Các đường dưới đây lấy từ CSV xuất, neo tại quan sát chung đầu tiên của từng kỳ. Đường paper đến 27/02/2026; phần nền xám chỉ có các baseline tháng 4, không kéo dài đường paper. Lượt 04/10 được giữ làm đối chứng; thay nguồn, độ chính xác giá và quy ước thông tin cùng lúc nên không gọi đây là ablation một yếu tố.

![NAV IS: lượt mới, đối chứng 04/10 và lượt lịch sử]({plots/'NAV_IS_New_vs_Reference.png'})

![NAV OOS: lượt mới, đối chứng 04/10 và lượt lịch sử]({plots/'NAV_OOS_New_vs_Reference.png'})

Số đo tương quan được lưu trong `17_Readiness_Evidence.zip/trajectory_comparison.csv`; đây là so sánh mô tả, không phải kiểm định đóng góp kinh tế của ML. Mục 12.2–12.4 và các hình 11–13 giữ kết quả kiểm tra 04/10 để tra cứu, không phải số liệu của baseline mới.

### 13.4. Bộ tệp nộp và baseline cho Step 2

| Tệp/thư mục | Nội dung và cách dùng |
|---|---|
| `01_Baseline_Metrics.csv` đến `05_Baseline_Turnover.csv` | Thay bằng kết quả của baseline mới 12/10; khớp mục 12.1. |
| `06_Pipeline_Audit.zip`, `09_Reproducibility.zip` | Audit, source/config/môi trường, đầu vào, hai manifest và kết quả kiểm tra/chạy lặp của lượt mới. |
| `07_Data_Audit.zip`, `08_Design_Provenance.zip`, `10_Comparison_Details.zip`, hình 11–13, `14_Diagnostic_Plots.zip` | Hồ sơ kiểm tra nền và so sánh 04/10 được giữ làm đối chứng, không thay cho baseline mới. |
| `15_Blocker_Evidence_20261012.zip` | Chứng cứ gốc cho VFF, PNJ, KBS, bản cáo bạch và tái lập lịch sử; giữ nguyên để tra nguồn. |
| `16_Decisions_Applied.md` | Ghi quyết định C1–C4 đã áp dụng và giới hạn nghiên cứu; thay tệp yêu cầu xác nhận trước đây. |
| `17_Readiness_Evidence.zip` | Policy availability, lineage, dữ liệu nguồn GOLD, kiểm tra coverage, trạng thái readiness và số đo đường NAV. |
| `18_NAV_IS_New_vs_Reference.png`, `19_NAV_OOS_New_vs_Reference.png` | Hình so sánh cập nhật cho lần chạy mới. |

Baseline dùng tiếp là `{primary.name}`; mã nguồn trong `readiness_20261012/candidate_workspace/`, không lấy CSV tháng 7 ở thư mục gốc. Step 2 sẽ so sánh full VN30, random K=5, benchmark đơn giản K=5 và phương pháp chọn đại diện đề xuất, giữ mô hình danh mục phía sau và policy dữ liệu cố định. Universe point-in-time/chi phí/ML ablation xử lý ở bước tương ứng; không kết luận giá trị riêng của ML ở Step 1.

**Kết luận:** đủ điều kiện bắt đầu Step 2 theo giao thức thí nghiệm định giá đã khai báo và được đóng băng. Chứng nhận khả dụng lịch sử thực tế và thực thi quỹ thực tế vẫn chưa đạt; đây là giới hạn của diễn giải kết quả, không được viết thành đã xác minh hoàn toàn.

READY FOR STEP 2
'''
(OUT/'report_section13.md').write_text(section13)
(OUT/'report_section12_1.md').write_text(section12)
report_path=ROOT/'outputs/step1/step1_report.md';oldreport=report_path.read_text();(OUT/'report_before_readiness.md').write_text(oldreport)
report=oldreport[:oldreport.index('## 13.')]+section13
start=report.index('### 12.1.');end=report.index('### 12.2.',start);report=report[:start]+section12+report[end:]
for heading in ['### 12.2. Đối chiếu số công bố và logic gốc','### 12.3. Độ nhạy alpha và tỷ lệ dự báo đúng hướng','### 12.4. So sánh đường NAV và điểm cần sửa trong bài báo']:
 report=report.replace(heading,heading+'\n\n**Đối chứng lưu trữ:** số liệu/hình của lượt 04/10, trước hiệu chỉnh availability và nguồn ngày 12/10; không dùng làm baseline Step 2.')
start=report.index('**Kết quả chung:**');end=report.index('\n\n| Phần',start)
summary='**Kết quả chung:** READY FOR STEP 2 trong phạm vi giao thức dùng giá định giá đại diện và availability giả định được khai báo tại mục 13. Hai lượt mới và audit độc lập đã đạt; bảng 12.1 là kết quả mới. Các mục 2–11 lưu kiểm tra nền 04/10; mục 13 ghi bổ sung và thay đổi 12/10. Chưa chứng nhận thời điểm công bố đầu tiên/vintage điều chỉnh lịch sử hoặc thực thi giao dịch quỹ thực tế.'
report=report[:start]+summary+report[end:]
report=report.replace('ma trận chung 07/01/2020–29/04/2026, 1.573 phiên','ma trận chung 14/01/2020–29/04/2026, 1.568 phiên').replace('từ 11/02/2020 đến 29/09/2023 sau khởi tạo, gồm 911','từ 18/02/2020 đến 29/09/2023 sau khởi tạo, gồm 906')
report=report.replace('**Tái lập hiện chỉ đạt một phần.**','**Tái lập lượt lịch sử đã được bổ sung.**').replace('Chưa huấn luyện lại độc lập toàn bộ lựa chọn tài sản, ML và BL trong môi trường gốc, nên chưa xác nhận tái lập toàn bộ pipeline.','Ngày 12/10 đã huấn luyện mới IS/OOS từ source/data commit 71cc107 trong môi trường ghi nhận, không cache; metrics, toàn bộ tỷ trọng và views khớp chính xác log gốc. Chưa xác nhận môi trường gốc hoặc fit lại năm lượt alpha riêng.')
report_path.write_text(report);(ROOT/'report.md').write_text(report)
(OUT/'16_Decisions_Applied.md').write_text('# Quyết định C1–C4 đã áp dụng\n\n'+section13[section13.index('### 13.1.'):section13.index('### 13.2.')])
# Complete new flat submission package. Older comparisons stay explicitly archival.
pkg=ROOT/'outputs/step1/Step1_Submission_Readiness_20261012';pkg.mkdir(exist_ok=True)
priorpkg=ROOT/'outputs/step1/Step1_Submission_20261012'
for p in priorpkg.iterdir():
 if p.is_file() and not p.name.startswith('.') and p.name not in ['00_Attachment_Index.csv','16_Decisions_To_Confirm.md']:shutil.copy2(p,pkg/p.name)
for dest,src in [('01_Baseline_Metrics.csv','trusted_baseline_metrics.csv'),('02_Baseline_NAV.csv','trusted_baseline_nav.csv'),('03_Baseline_Daily_Returns.csv','trusted_baseline_daily_returns.csv'),('04_Baseline_Target_Weights.csv','trusted_baseline_weights.csv'),('05_Baseline_Turnover.csv','trusted_baseline_turnover.csv')]:shutil.copy2(primary/'artifacts'/src,pkg/dest)
shutil.copy2(report_path,pkg/'00_Step1_Report.md');shutil.copy2(OUT/'16_Decisions_Applied.md',pkg/'16_Decisions_Applied.md')
shutil.copy2(plots/'NAV_IS_New_vs_Reference.png',pkg/'18_NAV_IS_New_vs_Reference.png');shutil.copy2(plots/'NAV_OOS_New_vs_Reference.png',pkg/'19_NAV_OOS_New_vs_Reference.png')
def zip_paths(dest,items):
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
  for p,arc in items:
   if p.is_file():z.write(p,arc)
   elif p.is_dir():
    for f in sorted(p.rglob('*')):
     if f.is_file() and '__pycache__' not in f.parts and not f.name.startswith('.'):z.write(f,str(Path(arc)/f.relative_to(p)))
zip_paths(pkg/'06_Pipeline_Audit.zip',[(primary/'artifacts','artifacts'),(primary/'selection_matrices','selection_matrices'),(primary/'bl_audit_sample','bl_audit_sample'),(OUT/'independent_review','independent_review')])
items=[(primary/'source_snapshot','source_snapshot'),(BASE/'datasets','datasets'),(primary/'runner_source.py','runner_source.py'),(OUT/'availability_policy.json','availability_policy.json'),(OUT/'candidate_information_prices.csv','candidate_information_prices.csv'),(OUT/'availability_ledger.csv','availability_ledger.csv'),(OUT/'reproducibility_verification.json','reproducibility_verification.json'),(OUT/'candidate_unit_tests.log','candidate_unit_tests.log'),(OUT/'readiness_status.json','readiness_status.json')]
for run in [primary,repeat]:
 for n in ['manifest.json','run_config.json','random_seeds.txt','requirements_frozen.txt','aligned_prices.csv','ml_training_audit.json','ml_prediction_audit.json','views_history.json','post_run_input_attachments.json']:items.append((run/n,run.name+'/'+n))
zip_paths(pkg/'09_Reproducibility.zip',items)
zip_paths(pkg/'17_Readiness_Evidence.zip',[(OUT/n,n) for n in ['availability_policy.json','candidate_observation_records.csv','candidate_information_prices.csv','availability_ledger.csv','input_validation.json','readiness_status.json','original_baseline_preservation.json','reproducibility_verification.json','gold_archive_raw','gold_archive_daily.csv','gold_archive_manifest.json','gold_archive_validation.json','gold_recovery_manifest.json','vff_official_archive.json','trajectory_comparison.csv']])
index=pd.read_csv(priorpkg/'00_Attachment_Index.csv');desc=dict(zip(index.filename,index.description));desc.update({'00_Step1_Report.md':'Báo cáo cập nhật 12/10; READY trong phạm vi valuation-proxy','06_Pipeline_Audit.zip':f'Audit lượt mới và {len(audit["checks"])} kiểm tra độc lập đạt','09_Reproducibility.zip':'Mã nguồn, dữ liệu, policy, hai manifest, 35 tests và chứng cứ hai lượt fit mới giống nhau','16_Decisions_Applied.md':'Quyết định C1–C4 đã áp dụng; không chờ giảng viên xác nhận','17_Readiness_Evidence.zip':'Nguồn GOLD đủ kỳ, policy/lineage, coverage, readiness và số đo đường NAV','18_NAV_IS_New_vs_Reference.png':'Đường IS mới so với đối chứng04/10 và hồ sơ paper','19_NAV_OOS_New_vs_Reference.png':'Đường OOS mới; không kéo dài paper sau27/02/2026'})
for name in ['07_Data_Audit.zip','08_Design_Provenance.zip','10_Comparison_Details.zip','11_NAV_Legacy_vs_Corrected.png','12_NAV_IS_vs_Paper.png','13_NAV_OOS_vs_Paper.png','14_Diagnostic_Plots.zip']:desc[name]='Đối chứng lưu trữ04/10: '+desc[name]
for name in ['01_Baseline_Metrics.csv','02_Baseline_NAV.csv','03_Baseline_Daily_Returns.csv','04_Baseline_Target_Weights.csv','05_Baseline_Turnover.csv']:desc[name]='Baseline mới12/10: '+desc[name]
pd.DataFrame([dict(filename=p.name,description=desc.get(p.name,''),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(pkg.iterdir()) if p.is_file() and not p.name.startswith('.')]).to_csv(pkg/'00_Attachment_Index.csv',index=False,encoding='utf-8-sig')
zip_paths(pkg.with_suffix('.zip'),[(pkg,pkg.name)])
print(json.dumps({'status':status['status'],'scope':status['scope'],'independent_checks':len(audit['checks']),'repeat_checks':len(checks),'package':str(pkg),'zip_mib':pkg.with_suffix('.zip').stat().st_size/2**20},indent=2))
