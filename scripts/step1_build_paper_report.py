"""Update the Step 1 report from the verified April-period run and evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/step1"
PAPER=OUT/"paper_period"


def link(label,path):
    return f"[{label}]({ROOT/path})"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--legacy-run-id",required=True)
    args=parser.parse_args()
    run=OUT/"runs"/args.run_id
    legacy=PAPER/"legacy_on_canonical_inputs"/args.legacy_run_id
    manifest=json.loads((run/"manifest.json").read_text())
    legacy_manifest=json.loads((legacy/"manifest.json").read_text())
    assert manifest["status"]==legacy_manifest["status"]=="succeeded"
    repeated=json.loads((PAPER/"reproducibility_verification.json").read_text())
    assert repeated["status"]=="PASS"
    review=json.loads((PAPER/"independent_review/final_run_review.json").read_text())
    assert review["mechanical_verdict"]=="PASS" and not review["failures"]
    tests=(PAPER/"final_trusted_tests.log").read_text()
    assert "Ran 27 tests" in tests and tests.strip().endswith("OK")
    corrected=PAPER/"corrected"
    metrics=pd.read_csv(corrected/"trusted_baseline_metrics.csv")
    old_metrics=pd.read_csv(legacy/"artifacts/legacy_metrics.csv")
    checks=json.loads((corrected/"baseline_verification.json").read_text())
    diagnostic=json.loads((PAPER/"april_run_data_diagnostics.json").read_text())
    prior=PAPER/"prior_july_delivery/report.md"
    text=prior.read_text()

    def replace(old,new):
        nonlocal text
        assert old in text,old[:150]
        text=text.replace(old,new)

    def section(number,new):
        nonlocal text
        pattern=rf"(?ms)^## {number}\. .*?(?=^## {number+1}\. |\Z)"
        text,n=re.subn(pattern,lambda _:new.rstrip()+"\n\n",text)
        assert n==1,number

    def metrics_table(frame):
        lines=["| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |",
               "|---|---:|---:|---:|---:|---:|---:|"]
        for x in frame.itertuples():
            lines.append(f"| {x.strategy.replace('BL','BL+ML')} | {x.final_nav:.4f} | {100*x.ann_return:.2f}% | {100*x.ann_volatility:.2f}% | {x.sharpe:.3f} | {100*x.max_drawdown:.2f}% | {x.annualized_turnover:.3f} |")
        return "\n".join(lines)

    start=text.index("## 1.")
    text=f"""# Báo cáo Step 1 — Kiểm tra tính đúng đắn và tái dựng baseline

Ngày cập nhật: **04/10/2026**. Phạm vi: **Step 1** theo yêu cầu của bạn, sử dụng `guide_0.md`, `project_0.md` và PDF CSoNet làm tài liệu đối chiếu. Yêu cầu mới nhất của bạn thay lựa chọn kết thúc tháng 7 trước đó bằng **01/2020–04/2026**; không đổi tham số để khớp số công bố.

**Đã chạy lại và fit mô hình từ đầu** theo mốc **2020-01-01 / chia IS–OOS 2023-10-01 / kết thúc inclusive 2026-04-30**. PDF chỉ ghi tháng, nên ngày 30/04 là quy ước hết tháng được khai báo. Phiên cuối thực tế trong calendar VNINDEX đóng băng là **29/04/2026**. OOS gồm **641 daily returns**, từ 02/10/2023; NAV được chuẩn hóa tại phiên 29/09/2023 để không bỏ return đầu OOS.

**Kết quả chính:** OOS NAV EW **1,7149**, MVO **3,2031**, BL+ML **1,9479**, Hybrid **2,7521**. Hybrid Sharpe **1,648** và BL+ML **1,629**, nhưng chưa có kiểm định cho chênh lệch nhỏ này. **27/27 regression tests**, **52/52 kiểm tra độc lập** đạt; target constraints không có vi phạm substantive. Hai lượt April fresh-fit có output giống hoàn toàn. Phần kết quả tháng 7 và bản báo cáo trước được bảo toàn tại {link('prior_july_delivery',Path('outputs/step1/paper_period/prior_july_delivery'))}.

Đây là **baseline tính toán đã kiểm chứng dưới giả định dữ liệu sẵn có theo ngày định giá**. Chưa chứng nhận đầy đủ lịch sử công bố VFF/GOLD, nguồn quote GOLD hoặc corporate actions cổ phiếu; readiness cuối báo cáo vẫn là **NOT READY FOR STEP 2**. `trusted_baseline_*` là tên output yêu cầu trong guide, không thay thế chứng nhận này.

"""+text[start:]
    replace("### 1.2. Chạy nguyên trạng code/config/dữ liệu hiện tại","### 1.2. Lượt kiểm tra nguyên trạng trước đây — kỳ tháng 7 được bảo toàn")
    replace("Kết quả OOS hiện tại đến 01/07/2026, đọc từ stdout của runner:","Kết quả OOS của lượt kiểm tra trước đến 01/07/2026, đọc từ stdout của runner; **không phải bảng baseline tháng 4 đang hoạt động**:")
    replace("**Không tái tạo được paper bằng trạng thái hiện tại.**","**Các lượt nguyên trạng trước đây không tái tạo được số paper.**")
    paper_path=Path("csonet-paper/CSoNet2026_ML_Enhanced_Black_Litterman_Final.pdf")
    addition=f"""### 1.4. Đối chiếu PDF thực tế và chạy lại kỳ paper

{link('PDF CSoNet đã cung cấp',paper_path)} ghi **Jan2020–Apr2026** ở Abstract/trang1 và Experimental Setup/trang7. `project_0.md` §5.1 mô tả cùng kỳ gần đúng; guide yêu cầu tái lập manuscript, không ấn định ngày kết thúc cụ thể. **Figure1/trang4 lại ghi Mar2026**. Bằng chứng archived log ở §1.3 chỉ phủ đến 27/02/2026 nhưng tái dựng được số Table2/Table3/Table4. Vì vậy cần đồng bộ văn bản, hình và số liệu; không thể chỉ đổi label ngày của kết quả cũ.

| Phần | Mốc yêu cầu được chốt | Coverage / cách tính thực tế |
|---|---|---|
| Toàn mẫu | 01/01/2020–30/04/2026 | Ma trận chung 07/01/2020–29/04/2026, 1.573×32; không backfill trước quan sát đầu VFF |
| IS | Ngày <01/10/2023 | Warm-up trước performance; NAV 11/02/2020–29/09/2023, 911 returns |
| OOS | Ngày ≥01/10/2023, đến hết tháng4 | NAV anchor29/09/2023; returns02/10/2023–29/04/2026, 641 returns |

Run chính: `{args.run_id}`; fit mới, seeds42–46, không cache. Manifest trước/chốt sau chạy tại {link('manifest.json',run.relative_to(ROOT)/'manifest.json')}. Runtime date overrides được ghi trong manifest và `run_config.json` **của run**; `trusted_baseline/config.py` và generated root config cũ vẫn giữ mặc định tháng7. Lệnh tái lập phải truyền ba mốc ngày ở §11.

Đã chạy thêm **logic legacy trên cùng ma trận canonical, cùng thứ tự assets/calendar và cùng kỳ tháng4**: `{args.legacy_run_id}`, fit walk-forward mới, original scientific code không sửa. Loader gốc được bypass bằng ma trận canonical đã lưu; đây là comparator cho logic tính toán, **không phải chạy nguyên trạng input/loader gốc hoặc tái tạo đúng snapshot paper**. Legacy giữ same-close allocation/constant-mix và reset OOS gốc (anchor02/10, firstreturn03/10, 640 returns); bản sửa giữ next-close/fixed-share và 641 returns. Các khác biệt ML purge/features/constraints vẫn đồng thời tồn tại, nên không gọi đây là single-component ablation.

{link('Legacy run manifest',legacy.relative_to(ROOT)/'manifest.json')} và {link('legacy_metrics.csv',legacy.relative_to(ROOT)/'artifacts/legacy_metrics.csv')} lưu kết quả; NAV legacy/corrected cùng kỳ được vẽ ở §11. Bảng đối chiếu số PDF ở §12 là số công bố làm reference, không là benchmark fresh-fit trên identical inputs.

Historical input bundle71cc107 không đủ GOLD (cuối01/03/2026) và VFF (cuối24/03/2026) để phủ trọn tháng4, không có VNINDEX; 29/30 cổ phiếu khác close giữa snapshot lịch sử và hiện tại trên ngày chung, nguyên nhân điều chỉnh/revision chưa xác minh. Do đó dùng **snapshot canonical đã xác minh từ Step1**, chỉ giới hạn lại ngày. {link('input_coverage.md',Path('outputs/step1/paper_period/input_coverage.md'))} ghi coverage, overlap và cả hai cách hiểu Apr1/Apr30; bảng chính sử dụng **Apr30** theo yêu cầu hết tháng.

"""
    replace("## 2. Data audit — Dữ liệu và lịch",addition+"## 2. Data audit — Dữ liệu và lịch")
    # Dynamic April data values are separately audited by the data reviewer.
    dated=diagnostic["vff_distinct_canonical_nav_valuation_dates"]
    alignment=diagnostic["vff_alignment"]
    vff={"raw_observations":dated["full"],"IS_observations":dated["IS"],"OOS_observations":dated["OOS"],
         "carried_sessions":alignment["carried_exchange_session_rows"],
         "max_valuation_age_calendar_days":alignment["max_valuation_or_stored_record_age_calendar_days"],
         "zero_returns":alignment["zero_aligned_return_rows"]}
    replace("baseline **chỉ dùng 569 observation ≤01/07/2026**, gồm 295 IS và 274 OOS. Giá cuối đến kỳ yêu cầu: NAV ngày **30/06/2026 = 26.380,73 VND**, normalized legacy price **26,38**.",
        f"baseline tháng4 **chỉ dùng {vff['raw_observations']} observation ≤30/04/2026**, gồm {vff['IS_observations']} IS và {vff['OOS_observations']} OOS. Giá cuối: NAV ngày **28/04/2026 = 26.064,61 VND**, normalized legacy price **26,06**.")
    replace("Bảng chung có **1.616 ngày × 32 tài sản**, 07/01/2020–01/07/2026, exact matrix hash `a409eefecb89c8009a8c8e958d6a135a7f62302c320a391d09b4a3964ccd87cc`.",
        f"Bảng chung tháng4 có **1.573 ngày × 32 tài sản**, 07/01/2020–29/04/2026, exact matrix hash `{manifest['aligned_inputs']['price_matrix_sha256']}`.")
    replace("Independent as-of reconstruction khớp toàn bộ 32 cột; **19 kiểm tra dữ liệu đạt**, 33 input và 45 source/config hashes khớp tại lúc review. Trên calendar mới, VFF có **1.047 phiên carried**, max age **13 calendar days**, **1.102 zero returns**. GOLD có **1.426 zero returns**, nhưng tuổi quote thật vẫn UNKNOWN.",
        f"Independent as-of reconstruction tháng4 khớp toàn bộ32cột; review kiểm lại **33 input hashes**, matrix prefix và captured source/runner hashes, đều đạt. Trên calendar tháng4, VFF có **{vff['carried_sessions']:,} phiên carried**, max age **{vff['max_valuation_age_calendar_days']} calendar days**, **{vff['zero_returns']:,} zero returns**. GOLD có **{diagnostic['gold_alignment']['zero_aligned_return_rows']:,} zero returns**, nhưng tuổi quote thật vẫn UNKNOWN. Các số này được kiểm riêng tại {link('april_run_data_diagnostics.json',Path('outputs/step1/paper_period/april_run_data_diagnostics.json'))}.")
    # Active audit links point to April artifacts; persistent registers remain unchanged.
    for name in ["training_window_audit.csv","ml_training_audit.csv","ml_prediction_audit.csv","execution_ledger.csv","selection_history.csv"]:
        replace(f"/outputs/step1/{name}",f"/outputs/step1/paper_period/corrected/{name}")
    replace("lưu **319 quyết định/thực thi**","lưu **311 quyết định/thực thi**")
    replace("**735 asset-training events**, **1.449 predictions**","**715 asset-training events**, **1.409 predictions**")
    replace("Các baseline CSV và dự báo actual của hai lượt fit mới giống hệt nhau.","Các baseline CSV và dự báo actual của hai lượt April fit mới giống hệt nhau; đồng thời khớp prefix tháng7.")
    replace("cho OOS **340/680 = 50,0%**; IS **376/769 = 48,895%**. Không so trực tiếp tỷ lệ này với 51,9% của paper: paper dùng view đã threshold/transform và ngày outcome khác, kỳ dữ liệu khác.",
        "cho OOS **324/635 = 51,0236%** (640 issued, 5 chưa đủ5phiên outcome nên không chấm); IS **376/769 = 48,895%**. Riêng các ML view sau transform/threshold: OOS **175/347 = 50,4323%** (351 issued, 4 chưa mature). Không so trực tiếp raw rate với 51,9% của paper: paper tính view đã threshold/transform, alignment ngày và snapshot/kỳ thực thi lịch sử khác. Không lấy giá tháng5 để chấm dự báo cuối tháng4.")
    replace("Đã lưu **80 selection events**","Đã lưu **78 selection events**")
    replace("Lượt cuối 10/06/2026 dùng prefix đến 09/06, chọn MBB/PLX/SAB/VHM/VJC, objective **10,240579482**.","Lượt cuối 10/04/2026 dùng prefix đến 09/04, chọn MBB/PLX/SAB/VHM/VJC, objective **10,188801798**.")
    replace("runs/corrected-20261004T085654/",f"runs/{args.run_id}/")
    replace("**302 posterior thực tế**","**294 posterior thực tế**")
    replace("Samples lịch sử ở parent folder được giữ riêng với các samples mới.","Samples lịch sử tại `outputs/step1/bl_audit_sample/` được giữ riêng với samples tháng4.")
    replace("Tổng **319 decision snapshots** trong [bl_audit_sample/corrected](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/bl_audit_sample/corrected): 302 posterior-applied",
        "Tổng **311 decision snapshots** trong [bl_audit_sample/corrected](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/bl_audit_sample/corrected): 294 posterior-applied")
    replace("end **01/07/2026**, **684 return**","end **29/04/2026**, **641 return**")
    replace("Max direct NAV error **6,22e-15**, physical-share replay error **1,20e-14**. Đã kiểm **547 nontrade transitions/strategy**, holdings drift và pre-trade/turnover đều khớp trong numerical precision. Chi tiết: [portfolio_static/final_run_review.md](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/portfolio_static/final_run_review.md).",
        "Physical-share replay error tháng4 **1,42e-13**; daily-return error **7,03e-16**, pre-return-weight error **3,33e-16**, turnover error **5,00e-16**. Review kiểm mọi transition và metric của cả IS/OOS; chi tiết: [independent_review/final_run_review.md](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/independent_review/final_run_review.md).")
    replace("**1.276 strategy-trades** = 319 executions × 4 strategies","**1.244 strategy-trades** = 311 executions × 4 strategies")
    replace("Có **136 OOS trades/strategy**","Có **128 OOS trades/strategy**")
    section(9,f"""## 9. MVO reconciliation — Vì sao 3,73 và 3,57

Trong **PDF thực tế**, Table2 ghi MVO NAV3,73; Table3 ghi dòng `alpha_normal=1` NAV3,57 với nhãn **“MVO component”**, không viết “pure MVO”. `project_0.md` §6.12 mô tả nó như pure-MVO setting; báo cáo tháng7 cũng đã dùng cách gọi đó. Sau khi đọc PDF, cần sửa cách diễn giải trong báo cáo này cho đúng tài liệu bạn cung cấp.

Archived code/log cho MVO **3,7257457727** và Hybrid alpha_normal1 **3,5697514342**. Chỉ alpha ở **normal** đổi thành1; stress/crisis vẫn0,3/0,1 nên Hybrid tiếp tục pha BL. Ngày phân kỳ đầu **20/10/2023**, stress. Câu giải thích trong PDF/trang10 gán chênh lệch cho universe/constraints không phù hợp với actual loop: Hybrid dùng cùng full32 MVO leg đã cleanup như standalone MVO. Nguyên nhân đo được là blend còn hoạt động ngoài normal regime.

Kỳ April chạy mới: standalone MVO NAV **3,2030589963**; Hybrid alpha_normal1 NAV **3,3184305868**. Hybrid này vẫn **không phải all-regime pure MVO**, nên có thể cao hơn hoặc thấp hơn standalone tùy return stream. Bảng alpha mới ở §12.

Gọi dòng sensitivity là **Hybrid với alpha_normal=1, alpha_stress=0,3, alpha_crisis=0,1**. Nếu định nghĩa pureMVO, đặt alpha1 ở mọi regime; smoke test cùng leg/cleanup/return stream cho identity đã đạt. Không đổi số alpha1 thành số standalone mà vẫn giữ stress/crisis cũ. {link('mvo_reconciliation.md',Path('outputs/step1/mvo_reconciliation.md'))} là evidence code/log lịch sử, cần đọc cùng correction về nhãn PDF ở đây.
""")
    # Replace the active delivery section rather than mixing July and April identities.
    items=["training_window_audit.csv","selection_history.csv","ml_training_audit.csv","ml_prediction_audit.csv",
        "execution_ledger.csv","constraint_violations.csv","trusted_baseline_nav.csv","trusted_baseline_daily_returns.csv",
        "trusted_baseline_weights.csv","trusted_baseline_metrics.csv","trusted_baseline_turnover.csv"]
    registry=["data_manifest.csv","universe_provenance.md","parameter_provenance.csv","mvo_reconciliation.md","change_log.md"]
    inventory=[]
    for name,path in [(x,corrected/x) for x in items]+[(x,OUT/x) for x in registry]:
        assert path.is_file(),path
        inventory.append({"requested_artifact":name,"absolute_path":str(path),"bytes":path.stat().st_size,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"active_period":"2020-01-01/2023-10-01/2026-04-30"})
    pd.DataFrame(inventory).to_csv(PAPER/"deliverable_inventory.csv",index=False)
    table="\n".join(f"| {x['requested_artifact']} | {link('Mở file',Path(x['absolute_path']).relative_to(ROOT))} |" for x in inventory)
    section(11,f"""## 11. Corrections — Checks, outputs và cách tái lập kỳ tháng4

Code sửa nằm trong {link('trusted_baseline',Path('trusted_baseline'))}; original scientific source giữ nguyên. Các integrity corrections đã có trong Step1 trước: VFF identity, GOLD source consistency, observed calendar/causal fill, internal label purge, inference causal prefix, next-close execution, fixed-share drift, OOS boundary, final feasibility và provenance/turnover exports. Lần cập nhật này **chỉ đổi kỳ qua CLI runtime**, bổ sung đối chiếu PDF và diagnostics, không tune hệ thống hoặc chạy Step2.

**27/27 regression tests đạt**, đúng cwd `trusted_baseline`; log mới {link('final_trusted_tests.log',Path('outputs/step1/paper_period/final_trusted_tests.log'))}. Review actual April độc lập **52/52 checks PASS**:715fits,1.409predictions,311executions,78global selection optima,294BLposteriors; share/turnover/metric replay errors ở numerical precision. Review còn xác nhận April prices/training/forecasts/selection/BL/targets/NAV/holdings **khớp hoàn toàn phần tương ứng của lượt July fresh-fit**, hỗ trợ kiểm tra dữ liệu tương lai không làm đổi quá khứ.

Hai lượt April fresh-fit: `{args.run_id}` và `{repeated['repeat_run_id']}`. Kiểm tra repeat độc lập **40/40 PASS**: **13 CSV byte-identical**, actual prediction JSON giống hoàn toàn, cùng scientific source/input/config/seeds/env, không cache. {link('reproducibility_verification.json',Path('outputs/step1/paper_period/reproducibility_verification.json'))} lưu hashes và scope; đây là hai run thực thi riêng, tách biệt với review52checks và common-July-prefix comparison. Không suy rằng môi trường paper gốc giống môi trường hiện tại.

Ma trận, full audit JSON, model/scaler/member parameters, selection matrices, BL snapshots, configs/seeds/env/stdout/stderr và captured source nằm trong run folder. Native ML metadata JSON có XGBoost `missing=NaN`, là hạn chế interoperability với parser JSON strict, không phải số prediction bị mất. `STATUS.json`/README được cập nhật **sau chạy**; bản metadata dùng lúc chạy đã giữ trong `source_snapshot/` của từng run. Manifest chụp runner source/digest và scientific code/config, không chỉ commit Git.

Các CSV active April nằm dưới **`outputs/step1/paper_period/corrected/`**. Root `outputs/step1/trusted_baseline_*.csv` và hai July run được bảo toàn là kết quả kỳ trước; **không dùng chúng làm bảng April**. Bản report mới được ghi giống hệt tại `report.md` và `outputs/step1/step1_report.md`. {link('active_run.json',Path('outputs/step1/paper_period/active_run.json'))} xác định run chính; {link('deliverable_inventory.csv',Path('outputs/step1/paper_period/deliverable_inventory.csv'))} ghi paths/hashes:

| Artifact | Đường dẫn |
|---|---|
{table}

Đủ bốn nhóm figure yêu cầu, cộng corrected NAV/drawdown, dưới {link('plots/',Path('outputs/step1/paper_period/corrected/plots'))}, cả PNG/PDF: `walk_forward_timing`, `legacy_vs_corrected_nav`, `constraint_diagnostics`, `turnover_history`, `corrected_nav`, `corrected_drawdown`. Legacy comparison dùng **same canonical inputs, same April period**, nhiều integrity differences đồng thời; không là ML ablation.

![Legacy logic và bản sửa, cùng kỳ tháng4]({ROOT}/outputs/step1/paper_period/corrected/plots/legacy_vs_corrected_nav.png)

Lệnh chạy lại từ project root, tạo folder mới và fit lại toàn bộ:

```sh
MPLCONFIGDIR=/private/tmp/portfolio-step1-mpl XDG_CACHE_HOME=/private/tmp/portfolio-step1-cache venv/bin/python scripts/step1_run_baseline.py --verification-run --run-label paper-period --start-date 2020-01-01 --split-date 2023-10-01 --end-date 2026-04-30
```

Lệnh regression, từ `trusted_baseline/`:

```sh
MPLCONFIGDIR=/private/tmp/portfolio-step1-mpl XDG_CACHE_HOME=/private/tmp/portfolio-step1-cache ../venv/bin/python -B -m unittest discover -s tests -v
```

`--verification-run` không ghi đè primary outputs hoặc root generated config. Không tải lại dữ liệu. CLI override đầu tiên từng lỗi shadow tên biến Python trước khi fit/tạo manifest; đã sửa alias trong wrapper, ghi rõ ở `request.json`. Hai run dùng trong báo cáo đều **succeeded / exit0**. Frozen-original hash check và PDF hash được kiểm lại khi chốt delivery.
""")
    printed=pd.read_csv(PAPER/"pdf_audit/printed_table2.csv")
    printed["strategy"]=printed.strategy.replace({"BL+ML":"BL"})
    joined=metrics.merge(printed,left_on=["phase","strategy"],right_on=["period","strategy"],validate="one_to_one")
    reference=["| Kỳ | Strategy | NAV PDF | NAV mới | Sharpe PDF | Sharpe mới | MDD PDF | MDD mới |",
               "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in joined.itertuples():
        reference.append(f"| {x.phase} | {x.strategy.replace('BL','BL+ML')} | {x.nav:.2f} | {x.final_nav:.4f} | {x.sharpe_y:.2f} | {x.sharpe_x:.3f} | {x.max_drawdown_fraction*100:.1f}% | {x.max_drawdown*100:.2f}% |")
    controlled=metrics.merge(old_metrics,on=["phase","strategy"],suffixes=("_corrected","_legacy"),validate="one_to_one")
    controlled.to_csv(PAPER/"legacy_vs_corrected_metrics.csv",index=False)
    control=["| Kỳ | Strategy | NAV legacy | NAV corrected | Sharpe legacy | Sharpe corrected |",
             "|---|---|---:|---:|---:|---:|"]
    for x in controlled.itertuples():
        control.append(f"| {x.phase} | {x.strategy.replace('BL','BL+ML')} | {x.final_nav_legacy:.4f} | {x.final_nav_corrected:.4f} | {x.sharpe_legacy:.3f} | {x.sharpe_corrected:.3f} |")
    alpha=pd.read_csv(PAPER/"paper_vs_corrected_alpha.csv")
    alpha_table=["| alpha_normal | NAV PDF | NAV mới | Sharpe PDF | Sharpe mới | MDD mới |",
                 "|---:|---:|---:|---:|---:|---:|"]
    for x in alpha.itertuples():
        alpha_table.append(f"| {x.alpha_normal:.1f} | {x.nav:.2f} | {x.final_nav:.4f} | {x.sharpe_y:.2f} | {x.sharpe_x:.3f} | {100*x.max_drawdown:.2f}% |")
    hits=pd.read_csv(PAPER/"corrected_hitrate_summary.csv")
    views=hits[(hits.kind=="emitted_ML_views")&(hits.phase=="OOS")]
    pdf_hits=pd.read_csv(PAPER/"pdf_audit/printed_table4.csv")
    # Keep comparison definitions visible even if printed per-asset counts differ.
    hit_table=["| Asset | View mới đúng/tổng matured | Hit rate mới |",
               "|---|---:|---:|"]
    for x in views.itertuples():
        hit_table.append(f"| {x.asset} | {x.n_correct}/{x.n_scored} | {100*x.hit_rate:.2f}% |")
    section(12,f"""## 12. Impact on empirical conclusions — Kết quả kỳ paper và đối chiếu

### 12.1. Baseline sau sửa, IS

NAV11/02/2020–29/09/2023,911returns:

{metrics_table(metrics[metrics.phase=='IS'])}

### 12.2. Baseline sau sửa, OOS

Anchor29/09/2023; returns02/10/2023–29/04/2026,641returns, costs0:

{metrics_table(metrics[metrics.phase=='OOS'])}

BL+ML vẫn có volatility **13,04%** / MDD **−9,64%**, thấp hơn MVO **32,84%** / **−26,86%**, với NAV thấp hơn. Hybrid tăng NAV so với BL+ML nhưng volatility/MDD tăng. Trong bốn strategy mặc định, Hybrid Sharpe **1,648** > BL+ML **1,629**; mức chênh **0,019** chưa có CI/significance. Kết luận tháng7 từng BL Sharpe cao nhất không áp dụng nguyên trạng cho kỳ April này.

OOS annualized turnover: MVO **23,822**, BL+ML **8,630**, Hybrid **16,868** vòngNAV/năm. Đây là bookkeeping cho Step8, chưa là net returns. Không ước đoán chi phí bps hoặc kết luận có thể giao dịch thực tế từ các valuation proxies.

### 12.3. Table2 PDF so với fresh corrected run

{chr(10).join(reference)}

{link('paper_vs_corrected_metrics.csv',Path('outputs/step1/paper_period/paper_vs_corrected_metrics.csv'))} chứa đủ return/volatility/deltas. Cùng **kỳ mô tả** nhưng không đồng nhất input snapshots, calendar, execution/ML mechanics hoặc kỳ actual archived log. Số cũ không tự trở nên sai vì baseline khác; bằng chứng yêu cầu ghi rõ nó thuộc run nào, còn phiên bản tháng4 mới phải dùng output mới.

### 12.4. Legacy và corrected trên cùng canonical matrix / kỳ April

{chr(10).join(control)}

Đây là đối chiếu có kiểm soát **inputs, asset order, effective period, environment và research params**; bao gồm đồng thời khác biệt timing, daily holdings, validation purge/inference state và feasibility cleanup. Legacy OOS640returns, corrected641returns do cách reset boundary, được khai báo thay vì âm thầm loại ngày. Không suy ra phần chênh NAV là hiệu quả riêng của ML hoặc của một fix. {link('legacy_vs_corrected_metrics.csv',Path('outputs/step1/paper_period/legacy_vs_corrected_metrics.csv'))} giữ bảng đầy đủ.

Đối chiếu phụ {link('common_oos_window_comparison.csv',legacy.relative_to(ROOT)/'common_oos_window_comparison.csv')} chuẩn hóa cả hai NAV tại02/10/2023, cùng640returns: corrected EW1,7126 / MVO3,2245 / BL1,9458 / Hybrid2,7620. Bảng chính vẫn giữ đúng641returns của baseline sửa. Legacy có112targetcapflags ở1e−8, trong đó30excess>1e−4, maxexcess0,00722417; corrected0vi phạm ở cùng tolerance. {link('legacy_constraint_summary.json',legacy.relative_to(ROOT)/'legacy_constraint_summary.json')} lưu mức độ; không gộp flags legacy vào file violation của bản sửa.

### 12.5. Table3 — alpha sensitivity của cùng thiết kế đã có

{chr(10).join(alpha_table)}

Giữ alpha_stress0,3 và alpha_crisis0,1 ở cả năm dòng. Đây là physical-share resimulation từ **MVO/BL legs đã fit mới** và price-only regime decisions của run chính; không fit lại ML riêng từng alpha, không chọn alpha tốt nhất theo OOS. Kiểm defaultalpha0,6 khớp actual NAV IS/OOS, maxerror **2,18e−14**. {link('alpha_grid_method.json',Path('outputs/step1/paper_period/alpha_grid_method.json'))} ghi phương pháp. Alpha0,2 Sharpe1,812 cao hơn default Hybrid1,648, nên claim “highest Sharpe” nếu dùng chỉ nói trong **bốn mô hình mặc định Table2**, không toàn bộ grid.

### 12.6. Table4 — hit rate theo đúng forecast origin

PDF overall174/335=51,9%; archived same-view realignment178/335=53,13% chỉ là chẩn đoán cũ. Run mới rawOOS324/635=**51,02%**, emitted ML views175/347=**50,43%**. Hai population khác nhau; raw có640issued/5unmatured, emitted có351issued/4unmatured. Dưới đây là views mới, outcome endpoint phải nằm trong April matrix:

{chr(10).join(hit_table)}

{link('corrected_hitrate_summary.csv',Path('outputs/step1/paper_period/corrected_hitrate_summary.csv'))} và details lưu từng dự báo; {link('printed_table4.csv',Path('outputs/step1/paper_period/pdf_audit/printed_table4.csv'))} lưu chính xác số PDF để đối chiếu. Hit rate không chứng minh incremental economic value của XGBoost; noML/fixedconfidence ablations vẫn thuộc các bước sau.

Phase của hit-rate diagnostic được gán theo **ngày phát dự báo**, khác với phase của realized-return metrics. Trong IS raw376/769 có5dự báo (3đúng), và trong IS emitted views có4dự báo (2đúng), phát28/09/2023, origin27/09, outcomeend04/10 nên mature ở OOS. Các outcome này chỉ được chấm hồi cứu, không dùng để tune hoặc fit trước split. OOS hit rate vẫn chỉ chấm endpoints nằm trong April matrix. Không đọc IS hit rate như một thống kê đã biết hoàn toàn tại29/09/2023.

### 12.7. Những điểm phương pháp trong PDF cần đồng bộ với actual code

1. **Khoảng thời gian:** prose April, Figure1 March, số archived tái dựng từ run đến February. Đối chiếu bằng log và cập nhật thống nhất khi sửa manuscript.
2. **Sharpe:** công thức PDF/trang8 `(annualized geometric return−6%)/annualized volatility` không tái tạo Table2. Ví dụ MVO `(69,4%−6%)/31,8%≈1,994`, khác1,64. Run mới giữ actual metric code: daily excess mean/std ×sqrt252, risk-free compounded daily. Sửa mô tả hoặc chạy lại toàn bộ bảng với định nghĩa được chốt, không trộn hai định nghĩa.
3. **View transformation:** Eq5/trang5 mô tả annualization tuyến tính, default code dùng volatility-scaled tanh (OptionB). Run giữ implemented policy, không đổi transform để kéo NAV về số PDF.
4. **Risk aversion:** Eq9 PDF dùng `lambda/2 × wᵀΣw`, lambda1,5. Actual optimizer dùng trực tiếp `risk_aversion × wᵀΣw`, hệ số1,5 ở default và5,0 khi crisis; theo ký hiệu PDF, penalty tương ứng lambda3/10. Cần đồng bộ cả convention1/2 và regime switch. **Alpha1:** mô tả normal-only và stress/crisis còn blend như §9; thay câu giải thích universe/constraint chưa phù hợp actual loop.

Kết luận đủ bằng chứng: **phép tính NAV/weights/turnover và thứ tự dated inputs của baseline mới nhất quán, tái lập; pattern BL phòng thủ vẫn xuất hiện có điều kiện**. Chưa có bằng chứng mới cho release-time causality, survivorship-free/net-return performance hoặc vai trò riêng của ML. Không thay các giới hạn bằng kết quả fit thêm.
""")
    # Restore active readiness language while preserving the unchanged strict blockers.
    replace("| Reproducibility của baseline mới với fixed seeds/env | PASS — hai fresh runs, exact outputs |",
        "| Reproducibility của baseline April với fixed seeds/env | PASS — hai April fresh runs, exact outputs; common July prefix cũng exact |")
    assert len(re.findall(r"(?m)^## \d+\.",text))==13
    assert text.strip().endswith("NOT READY FOR STEP 2")
    # Improve prose spacing without changing code blocks, paths or identifiers.
    for old,new in {"tháng4":"tháng 4","tháng7":"tháng 7","tháng5":"tháng 5", "Step1":"Step 1","Step2":"Step 2",
        "toàn bộ32cột":"toàn bộ 32 cột", "đủ5phiên":"đủ 5 phiên", "seeds42–46":"seeds 42–46",
        "anchor29/09":"anchor 29/09", "returns02/10":"returns 02/10", "anchor02/10":"anchor 02/10",
        "firstreturn03/10":"first return 03/10", "cuối01/03":"cuối 01/03", "cuối24/03":"cuối 24/03",
        "trang1":"trang 1", "trang4":"trang 4", "trang5":"trang 5", "trang7":"trang 7", "trang8":"trang 8",
        "Table2":"Table 2", "Table3":"Table 3", "Table4":"Table 4", "Figure1":"Figure 1",
        "review52checks":"review 52 checks", ":715fits,1.409predictions,311executions,78global selection optima,294BLposteriors":": 715 fits, 1.409 predictions, 311 executions, 78 global selection optima, 294 BL posteriors",
        "OOS640returns":"OOS 640 returns", "corrected641returns":"corrected 641 returns", "cùng640returns":"cùng 640 returns",
        "đúng641returns":"đúng 641 returns", "tại02/10":"tại 02/10", "Legacy có112targetcapflags":"Legacy có 112 target cap flags",
        "đó30excess":"đó 30 excess", "corrected0vi phạm":"corrected 0 vi phạm", "alpha_normal1":"alpha_normal=1",
        "rawOOS324":"raw OOS 324", "issued/5unmatured":"issued / 5 unmatured", "issued/4unmatured":"issued / 4 unmatured",
        "Eq9":"Eq 9", "Eq5":"Eq 5", "lambda1,5":"lambda 1,5", "lambda3/10":"lambda 3/10",
        "defaultalpha0,6":"default alpha 0,6", "Alpha0,2":"Alpha 0,2", "Sharpe1,812":"Sharpe 1,812",
        "Hybrid1,648":"Hybrid 1,648", "PDF1,5":"PDF 1,5", "dùng5,0":"dùng 5,0", "gồm641":"gồm 641",
        "Anchor29":"Anchor 29", "NAV11/02":"NAV 11/02", "911returns":"911 returns", "641returns":"641 returns",
        "costs0":"costs 0", "vòngNAV":"vòng NAV", "Step8":"Step 8", "Step7":"Step 7",
        "overall174/335":"overall 174/335", "realignment178/335":"realignment 178/335", "views175/347":"views 175/347",
        "có640issued":"có 640 issued", "có351issued":"có 351 issued", "alpha_stress0,3":"alpha_stress=0,3",
        "alpha_crisis0,1":"alpha_crisis=0,1", "maxerror":"max error", "maxexcess":"max excess ",
        "ở1e−8":"ở 1e−8", "excess>1e−4":"excess >1e−4", "EW1,7126":"EW 1,7126", "MVO3,2245":"MVO 3,2245",
        "BL1,9458":"BL+ML 1,9458", "Hybrid2,7620":"Hybrid 2,7620", "NAV3,73":"NAV 3,73", "NAV3,57":"NAV 3,57",
        "pureMVO":"pure MVO", "alpha1":"alpha=1", "thành1":"thành 1", "vẫn0,3":"vẫn 0,3",
        "hệ số1,5":"hệ số 1,5", "và5,0":"và 5,0", "convention1/2":"convention 1/2", "khác1,64":"khác 1,64",
        "**1,021 phiên":"**1.021 phiên", "**1,073 zero":"**1.073 zero", "**1,416 zero":"**1.416 zero",
        "raw376/769":"raw 376/769", "có5dự báo":"có 5 dự báo", "có4dự báo":"có 4 dự báo",
        "3đúng":"3 đúng", "2đúng":"2 đúng", "phát28/09":"phát 28/09", "origin27/09":"origin 27/09",
        "outcomeend04/10":"outcome end 04/10", "tại29/09":"tại 29/09"}.items():
        text=text.replace(old,new)
    (ROOT/"report.md").write_text(text)
    (OUT/"step1_report.md").write_text(text)
    print(json.dumps({"report_bytes":len(text.encode()),"active_run":args.run_id,
        "repeat":repeated['repeat_run_id'],"legacy_comparator":args.legacy_run_id,
        "report_sha256":hashlib.sha256(text.encode()).hexdigest()}))


if __name__=="__main__":
    main()
