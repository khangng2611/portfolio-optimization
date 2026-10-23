"""Assemble the requested Vietnamese Step 1 report from verified evidence."""
import hashlib
import json
from pathlib import Path
import re
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/step1"
RUN="corrected-20261004T085654"
REPEAT="corrected-20261004T090341"


def link(label,path):
    return f"[{label}]({ROOT/path})"


def metrics_table(frame):
    lines=["| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for x in frame.itertuples():
        lines.append(f"| {x.strategy} | {x.final_nav:.4f} | {100*x.ann_return:.2f}% | {100*x.ann_volatility:.2f}% | {x.sharpe:.3f} | {100*x.max_drawdown:.2f}% | {x.annualized_turnover:.3f} |")
    return "\n".join(lines)


def main():
    metrics=pd.read_csv(OUT/"trusted_baseline_metrics.csv")
    repeated=json.loads((OUT/"reproducibility_verification.json").read_text())
    checks=json.loads((OUT/"baseline_verification.json").read_text())
    assert repeated["status"]=="PASS" and checks["constraint_violations"]==0
    tests=(OUT/"final_trusted_tests.log").read_text()
    assert "Ran 27 tests" in tests and tests.strip().endswith("OK")
    is_table=metrics_table(metrics[metrics.phase=="IS"])
    oos_table=metrics_table(metrics[metrics.phase=="OOS"])
    output_names=["data_manifest.csv","universe_provenance.md","training_window_audit.csv",
        "selection_history.csv","ml_training_audit.csv","execution_ledger.csv","parameter_provenance.csv",
        "constraint_violations.csv","mvo_reconciliation.md","change_log.md","trusted_baseline_daily_returns.csv",
        "trusted_baseline_weights.csv","trusted_baseline_metrics.csv","trusted_baseline_turnover.csv"]
    inventory=[]
    for name in output_names:
        p=OUT/name
        assert p.is_file(),name
        inventory.append({"requested_artifact":name,"absolute_path":str(p),"bytes":p.stat().st_size,
                          "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"status":"created"})
    pd.DataFrame(inventory).to_csv(OUT/"deliverable_inventory.csv",index=False)
    delivery="\n".join(f"| {name} | {link('Mở file',Path('outputs/step1')/name)} |" for name in output_names)
    report=f"""# Báo cáo Step 1 — Kiểm tra tính đúng đắn và tái dựng baseline

Ngày thực hiện: **04/10/2026**. Đặc tả: `guide_0.md` và `project_0.md` của giảng viên; phạm vi thực hiện là **Step 1**, theo yêu cầu của bạn. Baseline mới dùng kỳ kết thúc **01/07/2026**, đúng lựa chọn bạn đã xác nhận.

**Kết quả chính:** đã đóng băng bản cũ, kiểm tra dữ liệu và toàn bộ chuỗi quyết định, sửa các lỗi tính toán trong một bản riêng, chạy lại EW/MVO/BL+ML/Hybrid, và kiểm tra tái lập bằng hai lượt fit mới. 27/27 regression tests đạt; không còn vi phạm target-weight constraints với tolerance 1e-8. Tuy nhiên, chưa đủ bằng chứng để chứng nhận thời điểm dữ liệu VFF/GOLD thực sự được công bố trong lịch sử hoặc cách giá cổ phiếu xử lý corporate actions. Vì vậy, đây là **baseline tính toán đã kiểm chứng dưới giả định dữ liệu sẵn có theo ngày định giá**, chưa phải nền tảng được chứng nhận hoàn toàn để bắt đầu thí nghiệm Step 2.

`trusted_baseline_*` được giữ theo tên output yêu cầu trong guide. Tên file không thay thế quyết định readiness ở cuối báo cáo. Không đưa các số mới vào paper dưới nhãn kết quả đã hoàn tất kiểm tra nhân quả lịch sử.

## 1. Reproduction status — Tái lập kết quả manuscript

### 1.1. Bảo toàn phiên bản gốc

{link('legacy_version/snapshot_manifest.json',Path('legacy_version/snapshot_manifest.json'))} lưu **631 file, 74.642.193 byte**, gồm code, config, datasets, logs/output và tài liệu nghiên cứu. SHA-256 manifest: `b5a8da0abb324039348d78f97c399eae59068346352a3c807bbf2f9b5359518d`. Các file được đặt read-only và kiểm lại hash; đây là snapshot có thể kiểm chứng, không phải cơ chế lưu trữ WORM. Đã kiểm lại 631 file: **không thay đổi bản đóng băng hoặc file gốc đã lưu**. Các thay đổi phần mềm đang có sẵn của bạn được giữ nguyên.

HEAD được ghi nhận: `5350e2a7960797e6a9b0fb73edfe5c5a20d8ce54`; trạng thái dirty ban đầu có trong manifest và `initial_tracked_diff.patch`. Không commit, reset hoặc sửa scientific source gốc để làm khớp paper.

Môi trường chạy: Python **3.12.0**, NumPy **2.2.6**, pandas **2.2.3**, scikit-learn **1.8.0**, XGBoost **3.2.0**, CVXPY **1.8.2**, vnstock **4.0.4**, matplotlib **3.10.8**. Interpreter: `venv/bin/python`; seeds **42–46**. Các solver hiện có: CLARABEL, HIGHS, OSQP, SCIPY, SCS; ECOS không có. Chi tiết và toàn bộ package versions trong {link('environment.json',Path('outputs/step1/environment.json'))} và {link('requirements_frozen.txt',Path('outputs/step1/requirements_frozen.txt'))}. Môi trường của lượt chạy paper gốc chưa có lockfile gắn với log, nên không suy diễn rằng đó là cùng môi trường.

### 1.2. Chạy nguyên trạng code/config/dữ liệu hiện tại

Đã chạy paper runner không sửa trong hai workspace sao chép, fit walk-forward mới, không dùng model cache cũ:

- IS: `legacy-current-20261004T082822-train`.
- OOS: `legacy-current-20261004T083952-test`.

Manifest tạo trước chạy, stdout/stderr, NAV/drawdown PNG/PDF nằm tại {link('legacy_results',Path('outputs/step1/legacy_results'))}. Cả hai process kết thúc **exit code 0**. Kết quả OOS hiện tại đến 01/07/2026, đọc từ stdout của runner:

| Strategy | NAV | Ann. return | Ann. volatility | Sharpe | MDD |
|---|---:|---:|---:|---:|---:|
| EW | 1,728 | 21,2% | 17,5% | 0,852 | −17,56% |
| MVO | 2,656 | 41,0% | 32,1% | 1,049 | −34,06% |
| BL | 1,757 | 21,9% | 13,6% | 1,099 | −15,29% |
| Hybrid | 2,296 | 33,9% | 21,6% | 1,193 | −24,30% |

IS NAV tương ứng: EW **2,002**, MVO **5,554**, BL **1,891**, Hybrid **3,943**. Hit-rate mà runner hiện tại tính: **193/396 = 48,7%** theo phép ghép ngày legacy.

**Không tái tạo được paper bằng trạng thái hiện tại.** Nguyên nhân có bằng chứng: ngày kết thúc đã thay đổi; dữ liệu quỹ bị trùng danh tính; GOLD split/full khác nhau; snapshot giá/crawler đã thay đổi. Header “Oct 2023–Apr 2026” của runner là chuỗi hardcoded, không phản ánh kỳ dữ liệu thật. Đã ghi nhận chênh lệch trước khi tạo bản sửa; không coi reproduction gate là PASS.

### 1.3. Phục hồi bằng chứng lịch sử của paper

Đã trích xuất snapshot Git **71cc107b807b6437ddd38430f30a0381333befa2**, trước các thay đổi dữ liệu sau đó, vào `historical_source_71cc107/`. Config đó kết thúc 01/03/2026; ngày OOS cuối thực tế là **27/02/2026**, không phải tháng 4/2026. Mốc NAV OOS legacy là 02/10/2023, return đầu được tính là 03/10/2023, tổng **629 return**.

Replay các target weights đã lưu, dùng loader và metric source lịch sử, tái dựng IS/OOS và đủ năm cấu hình alpha normal = 0,2/0,4/0,6/0,8/1,0. **24 strategy/scenario terminal NAV khớp ở độ chính xác hiển thị**, sai lệch NAV lớn nhất **1,09e-6**, phù hợp weights log chỉ lưu sáu chữ số thập phân. Bảng OOS chính khớp EW **1,822375116**, MVO **3,725745773**, BL **1,900014561**, Hybrid **2,857199476** theo số đã log. NAV/drawdown và alpha tables được lưu trong {link('portfolio_static',Path('outputs/step1/portfolio_static'))}.

Hit-rate paper tái lập từ archived views: **174/335 = 51,9403%**. Ghép lại đúng feature-origin cho cùng các view cũ cho **178/335 = 53,1343%**; đây chỉ là chẩn đoán lệch ngày, không phải cải thiện của mô hình được fit mới.

**Giới hạn:** đây là replay arithmetic từ quyết định đã lưu, không phải tái sinh độc lập toàn bộ selection, fit ML và quyết định BL của paper. Không khẳng định đã tái lập “exactly” toàn bộ paper end-to-end. Khả năng truy xuất số gốc đã phục hồi; chứng nhận reproduction mạnh hơn vẫn thiếu môi trường/training artifacts gắn với lượt chạy gốc. Các output lịch sử này khác kỳ và input của baseline mới.

## 2. Data audit — Dữ liệu và lịch

{link('data_manifest.csv',Path('outputs/step1/data_manifest.csv'))} có **288 file CSV gốc + 1 dòng canonical VFF**, ghi asset/type, provider, first/last date, count, price definition, corporate actions, calendar/missingness, notes và hashes. Dòng canonical được phân biệt với dữ liệu đóng băng; lineage của input baseline mới nằm trong `canonical_input_changes.json`, manifests và `data_static/final_run_review.json`.

Không có duplicate date trong từng CSV gốc, null date/price hoặc nonpositive selected price. `VPL_train.csv` rỗng, nhưng VPL không thuộc universe đang chạy. Các schema checks này không chứng minh đúng danh tính hoặc corporate-action handling.

### VFF: phát hiện và sửa sai danh tính

**62 file quỹ hiện tại có cùng chuỗi giá**, dù ticker khác nhau. Adapter vnstock hiện tại không truyền symbol tới `Fund.nav_report`, để mặc định fundId=23; crawler sau đó ghi đè symbol bằng tên yêu cầu. Không thể xem CSV có tên VFF đó là bằng chứng dữ liệu quỹ trái phiếu VFF.

Đã truy vấn FMarket với mã rõ ràng và xác minh **VFF = product ID21, BOND, VinaCapital**. Raw response/request/payload, fetch timestamp và SHA-256 được giữ trong `data_static/`. Toàn bộ **542 ngày NAV trùng snapshot lịch sử đều khớp chính xác** sau cùng phép làm tròn của legacy. Source canonical có 595 observation đến 01/10/2026; baseline **chỉ dùng 569 observation ≤01/07/2026**, gồm 295 IS và 274 OOS. Giá cuối đến kỳ yêu cầu: NAV ngày **30/06/2026 = 26.380,73 VND**, normalized legacy price **26,38**.

Đối chiếu quy mô giá với {link('audit_data.md',Path('outputs/step1/audit_data.md'))} và [factsheet VFF tháng 01/2026 của VinaCapital](https://vinacapital.com/wp-content/uploads/2026/02/20260212-VINACAPITAL-VFF_Monthly-Factsheet_Jan-2026-VN.pdf). NAV 29/01 của provider và số 31/01 trong factsheet có ngày định giá khác nhau; không gọi đây là đối chiếu giá cùng ngày.

### GOLD: thống nhất snapshot, chưa giải quyết đầy đủ nguồn lịch sử

JSON gốc trỏ `full_path` vào `gold_test.csv`, làm mất warm-up nếu chạy full mode. Physical full và nối train/test **khác 1.973/2.392 ngày chung**. Baseline chọn **physical `gold_full.csv` đã đóng băng**, giới hạn đến ngày kết thúc, rồi tạo lại split từ cùng source. Lựa chọn theo coverage và một quy ước nguồn được công khai, không theo NAV tốt hơn. Đây là thay đổi lịch sử giá thật sự, không chỉ sửa tên đường dẫn.

GOLD là **SJC sell quote proxy**, không có cờ quote thật/imputed, timestamp công bố, revision history, đơn vị được khai báo hoặc location identity xuyên suốt. Crawler hiện tại lọc TPHCM không chứng minh mọi dòng lịch sử trước đó đều đến từ TPHCM. Không tự bịa metadata còn thiếu.

### Calendar, fill và price definition

Baseline dùng **ngày quan sát VNINDEX trong snapshot**, thay weekday `freq='B'`. Đây là calendar thực nghiệm, chưa phải archive lịch HOSE được xác thực đầy đủ. Giữ observations ngoài calendar bằng hợp nhất ngày, forward-fill rồi lọc ngày phiên; không backward-fill. Trước first VFF observation không điền giá. Bảng chung có **1.616 ngày × 32 tài sản**, 07/01/2020–01/07/2026, exact matrix hash `a409eefecb89c8009a8c8e958d6a135a7f62302c320a391d09b4a3964ccd87cc`.

Independent as-of reconstruction khớp toàn bộ 32 cột; **19 kiểm tra dữ liệu đạt**, 33 input và 45 source/config hashes khớp tại lúc review. Trên calendar mới, VFF có **1.047 phiên carried**, max age **13 calendar days**, **1.102 zero returns**. GOLD có **1.426 zero returns**, nhưng tuổi quote thật vẫn UNKNOWN. Không suy từ zero return rằng quỹ giao dịch hằng ngày hoặc quote bị mất.

Stock CSV dùng provider `close` nhưng **adjusted/raw UNKNOWN**; không có corporate-action ledger hoặc cash-dividend accounting. Kết quả là return từ tỷ lệ close đã lưu, chưa được xác nhận là capital-gain đúng sau split hay total return. File {link('data_static/final_run_review.md',Path('outputs/step1/data_static/final_run_review.md'))} phân biệt valuation date với public availability.

## 3. Universe audit — VN30 được định nghĩa thế nào

Một danh sách **30 cổ phiếu cố định áp dụng cho toàn bộ lịch sử**:

```text
ACB BID CTG DGC FPT GAS GVR HDB HPG LPB MBB MSN MWG PLX SAB SHB SSI STB TCB TPB VCB VHM VIB VIC VJC VNM VPB VRE BVH POW
```

Reference/effective constituent date: **UNKNOWN**. Không có archive thành phần theo từng thời điểm, kiểm listing/delisting hoặc logic loại cổ phiếu thiếu history theo ngày. SSB/VPL có physical files nhưng không nằm trong JSON universe; không có bằng chứng rằng chúng bị loại bởi một history filter. Không gọi danh sách này là “VN30 đúng tại mọi ngày” hoặc khẳng định nó là thành phần chính thức cuối kỳ.

Default portfolio có 30 cổ phiếu + GOLD + VFF. VNINDEX là input riêng, không phải tài sản đầu tư. EW và standalone MVO dùng **toàn bộ 32 tài sản**. BL active set thường là **5 representatives + GOLD + VFF**. Hybrid dùng MVO full32 và BL active7; một helper tính constrained MVO trên active set không phải leg được loop thực sự dùng để blend.

Giữ universe trong Step 1 và ghi survivorship risk. Point-in-time reconstruction thuộc **Step 7**, không xem việc chưa chạy Step 7 là lỗi thực thi Step 1. Chi tiết: {link('universe_provenance.md',Path('outputs/step1/universe_provenance.md'))}.

## 4. Timing / leakage audit — Thông tin, quyết định và lợi nhuận

Legacy không trực tiếp lấy future return vào covariance: covariance tại quyết định gồm close(t), rồi tính P(t)→P(t+1). Vấn đề là giả định target hình thành sau khi biết close(t) nhưng vẫn khớp tại chính close đó. Ngoài ra, ngày log view trễ hơn feature-origin hai price rows, và reset OOS bỏ return phiên đầu.

Quy ước mới được định nghĩa và kiểm tra bằng actual ledger:

| Đại lượng | Thời điểm mới |
|---|---|
| Features/prediction origin | Qua close(t−1), giữ lag gốc |
| Representative correlation | Prefix kết thúc không muộn hơn t−1 tại ngày reselection |
| Covariance/sample mean/regime inputs | Các return kết thúc đến close(t) |
| Training outcomes | Hoàn toàn nằm trước ngày quyết định; giữ cutoff bảo thủ gốc |
| Prediction/target | Sau close(t), ghi ngày quyết định riêng |
| Execution | Close phiên quan sát kế tiếp t+1 |
| Return đầu target mới được hưởng | P(t+1)→P(t+2), ghi ngày kết thúc t+2 |

Tại t+1, return P(t)→P(t+1) thuộc holdings trước giao dịch; target mới không hưởng biến động đã xảy ra trước khi thực thi. Có assertion index universe/market/portfolio phải khớp để tránh `.iloc` lệch ngày. Lệnh cuối mẫu không tạo return ngoài mẫu.

{link('execution_ledger.csv',Path('outputs/step1/execution_ledger.csv'))} lưu **319 quyết định/thực thi** qua early IS, COVID, 2022 correction, OOS start, stress và kỳ cuối, vượt yêu cầu ≥20 ngày. **0 execution-timing failures** theo ngày đã lưu. `prediction_time`/`weight_calculation_time` là quy ước mô phỏng, không phải timestamp wall-clock giao dịch lịch sử.

**Chưa chứng nhận public availability:** ngày NAV/quote là ngày định giá, không nhất thiết là ngày/giờ đã công bố. `createdAt` là metadata provider, chưa chứng minh thời điểm công khai hoặc NAV không được sửa sau đó. Do đó PASS về thứ tự ngày không chứng minh hoàn toàn “mọi input đã biết tại decision time”. Ledger next-close sửa arithmetic timing; không tự khắc phục thiếu chứng cứ release history.

## 5. ML training audit — Nhãn, purge, scaler và features

Mục tiêu vẫn là **simple return 5 phiên**: `y_i = P[i+5]/P[i] − 1`. Không đổi horizon, ensemble, confidence hoặc tần suất để làm đẹp OOS.

Outer cutoff gốc đã bảo thủ: helper truyền prefix đến hàng t−6 rồi model mới tạo labels 5 phiên. Không có bằng chứng label-end tương lai trong default path. Đã giữ cutoff đó, thay vì tận dụng thêm dữ liệu mới hơn. Lỗi được sửa là **nhãn fitting chồng vào validation** ở split nội bộ 80/20: purge mọi fitting row có label-end ≥ first validation feature date. Scaler fit chỉ trên fitting rows sau purge.

Ví dụ actual fit DGC tại **07/08/2020**: 106 valid rows trước split; 84 fitting rows ban đầu; purge 5 → **79 fitting rows**, **22 validation rows**. Fitting feature cuối 16/06, fitting label-end cuối 23/06; validation bắt đầu 24/06; outcome cuối toàn bộ train/validation là 30/07, trước quyết định 07/08; execution 10/08. `scaler_n_samples_seen = 79`, có đủ mean/scale/variance và từng member parameter/best iteration.

| Feature | Định nghĩa/lookback | Kết quả kiểm tra |
|---|---|---|
| Momentum 5/10/20 | P(t)/P(t−n)−1 | Causal, backward shift |
| RSI14 | Rolling gain/loss, quy ước neutral đầu mẫu như code gốc | Causal |
| `ma_ratio_10_30` | EMA10/EMA30−1; tên MA không phải rolling SMA | Causal; cần giữ trạng thái prefix |
| Volatility20 | Std 20 daily simple returns, sample std | Causal |
| MACD histogram | EMA12−EMA26 trừ EMA9 signal | Causal; cần giữ trạng thái prefix |
| Price std20 normalized | Sample std của 20 giá / mean 20 giá | Causal |

Training dùng expanding-prefix EMA/MACD, nhưng inference cũ dùng tail30 gây khác định nghĩa trạng thái. Đã chuyển inference sang full causal prefix, giữ endpoint lag1. Vectorization khớp công thức prefix cũ trên cả synthetic series và ACB thật; regression perturb future values không đổi features quá khứ. Không dùng centered rolling, whole-sample scaler hoặc backward fill.

Actual exports có **735 asset-training events**, **1.449 predictions**, seeds/parameter/scaler/member predictions/std/confidence. Training audit root là **actual fit**, không phải mô phỏng lịch retrain. **0 label/validation window failures** trong kiểm tra đã chạy. Các baseline CSV và dự báo actual của hai lượt fit mới giống hệt nhau. Dữ liệu audit: {link('ml_training_audit.csv',Path('outputs/step1/ml_training_audit.csv'))}, {link('training_window_audit.csv',Path('outputs/step1/training_window_audit.csv'))}, {link('ml_prediction_audit.csv',Path('outputs/step1/ml_prediction_audit.csv'))}.

Chẩn đoán mới ghép đúng origin, tính **tất cả raw ensemble predictions**, cho OOS **340/680 = 50,0%**; IS **376/769 = 48,895%**. Không so trực tiếp tỷ lệ này với 51,9% của paper: paper dùng view đã threshold/transform và ngày outcome khác, kỳ dữ liệu khác. Đây không phải confidence calibration hoặc ML ablation của các bước sau. Nhánh `ranking` comparator có mismatch window40 vs feature60 được ghi trong audit, nhưng không được thêm vào default architecture hoặc dùng làm benchmark mới trong Step 1.

## 6. Asset-selection audit — Nhân quả và khả năng tái lập

Thuật toán duyệt exhaustive các tập **K=5** trên 30 candidates và tối thiểu hóa `sum_i min_m (1 − rho[i,m])`. Correlation dùng expanding history; covariance portfolio dùng window20. Undefined correlations được code xử lý thành zero. Tie behavior phụ thuộc thứ tự candidates cố định. Không có future return trong prefix đã ghi.

Tên phù hợp: **correlation-structure-based representative asset selection** hoặc **medoid-like correlation coverage selection**. Không gọi là “correlation clustering” hoặc PAM/K-medoids implementation chỉ vì comment cũ có tên đó.

Đã lưu **80 selection events**, mỗi event có universe có thứ tự, start/end history, selected set, objective và exact distance matrix `.npz`. Lượt đầu 11/02/2020 dùng history 07/01–10/02, chọn GVR/MBB/SAB/TPB/VIC, objective **6,583373529**. Lượt cuối 10/06/2026 dùng prefix đến 09/06, chọn MBB/PLX/SAB/VHM/VJC, objective **10,240579482**. Hai lần chạy mới chọn giống nhau. Matrix paths trong {link('selection_history.csv',Path('outputs/step1/selection_history.csv'))} tương đối với primary run folder `runs/{RUN}/`, không tương đối với root CSV.

Đây chỉ xác minh thuật toán đang có; chưa chứng minh selection tốt hơn Full VN30/Random K/Simple selection. So sánh đó là Step 2.

## 7. BL audit — Prior, views và posterior

Đã lưu actual covariance, market/equilibrium weights, delta/tau, pi, P/Q, confidence, Omega, posterior và final target weights cho từng construction. Equilibrium weights là **equal weights trong active universe**, không phải verified market capitalization weights. Đơn vị mu/Q là daily simple expected return; covariance là daily squared units.

Với covariance đã regularize, công thức audit độc lập:

```text
pi = delta × Sigma × w_eq
Omega = diag(diag(P × tau × Sigma × Pᵀ) / clipped_confidence)
mu_BL = pi + tau × Sigma × Pᵀ × solve(P × tau × Sigma × Pᵀ + Omega, Q − P × pi)
```

So với công thức implementation, **302 posterior thực tế** khớp; max absolute error **3,04e-18**. Hai real-input samples lịch sử 06/10 và 20/10/2023 cũng khớp khoảng 1e-19. Khi Omega tỷ lệ tau, tau phần lớn triệt tiêu trong posterior; không diễn giải riêng tau như một nguồn lợi ích đã được kiểm nghiệm. Numerical floors còn có thể ảnh hưởng các edge cases.

Tổng **319 decision snapshots** trong {link('bl_audit_sample/corrected',Path('outputs/step1/bl_audit_sample/corrected'))}: 302 posterior-applied và **17 no-view fallback**. Legacy no-view fallback dùng sample mean với constrained optimizer, không dùng BL prior; đã giữ behavior này và gắn nhãn rõ, không biến nó thành no-ML baseline trong Step 1. Final target weights full/active order và execution date đều được bổ sung. Samples lịch sử ở parent folder được giữ riêng với các samples mới.

## 8. Portfolio mechanics — Holdings, constraints, NAV và turnover

### Holdings/NAV

Legacy giữ tỷ trọng cố định mỗi ngày giữa lịch rebalance, tương đương constant-mix daily rebalancing ngầm. Baseline mới giữ **số đơn vị tài sản** giữa các lần giao dịch. Với asset return r và portfolio return rp, weight cuối ngày = `w × (1+r)/(1+rp)`. Holdings cũ hưởng return đến execution close, sau đó mới chuyển sang target mới. Cash chỉ dùng ở đầu mẫu, không có lãi cash; initial allocation không được hưởng return đã xảy ra trước khi mua.

OOS NAV=1 ở **29/09/2023**, giữ models/holdings/pending orders từ IS; first earned OOS return là **02/10/2023**, end **01/07/2026**, **684 return**. IS performance bắt đầu mốc NAV **11/02/2020**, qua 29/09/2023, **911 return**; các phiên đầu có window/cold-start theo design được giữ.

Independent review tái tính OOS bằng daily matrix và một mô phỏng **physical shares riêng từ cash**, không gọi helper tính P&L chính. Max direct NAV error **6,22e-15**, physical-share replay error **1,20e-14**. Đã kiểm **547 nontrade transitions/strategy**, holdings drift và pre-trade/turnover đều khớp trong numerical precision. Chi tiết: {link('portfolio_static/final_run_review.md',Path('outputs/step1/portfolio_static/final_run_review.md'))}.

### Target constraints

Tolerance **1e-8**; kiểm sau solver, clipping, cleanup và blend. Có **1.276 strategy-trades** = 319 executions × 4 strategies; **0 substantive violations**, max residual **1,18e-10**. `constraint_violations.csv` chỉ còn header. Các historical nominal flags được giữ riêng trong `portfolio_static/legacy_constraint_violations.csv`; không nhầm đó là lỗi của run đã sửa.

EW/MVO/Hybrid kiểm budget, long-only, position cap0,50. BL còn kiểm non-defensive cap0,70 và nominal VFF floor0,15. **GOLD thuộc non-defensive theo code**, nên chỉ VFF defensive khiến floor hiệu dụng của BL là **0,30**, không phải 0,15. Hybrid full32 leg không giữ BL group cap. Đây là thiết kế legacy được công khai, không thay ngữ nghĩa constraint để cải thiện kết quả. Caps được áp tại target/trade; giữa giao dịch, fixed-share weights có thể drift vượt cap, không áp continuous-rebalancing guardrail.

Cleanup weight<1% từng có thể đẩy survivor qua cap. Sửa mới giữ cleanup cũ nếu feasible; nếu cần dùng capped/group projection, hoặc giữ unpruned feasible weights khi survivor support không đủ. Solver residual được kiểm lại; fallback phải feasible, cấu hình vô nghiệm phải báo lỗi. Không nhận một vector sai chỉ vì solver báo optimal.

### Turnover và metric definitions

Turnover = **0,5 × sum |target − drifted pre-trade|**, ghi từng asset và portfolio. Initial funding từ cash có asset-only turnover0,5/cash-inclusive1,0; xuất cả hai và loại initial funding khỏi annualized turnover. Không có OOS initial funding lần hai. Giao dịch 29/09 nằm IS; OOS turnover chỉ tính execution_date **>29/09/2023**. Có **136 OOS trades/strategy**, không tính anchor trade. Annualized turnover = tổng turnover ×252/n_returns; đơn vị là vòng NAV/năm, không phải phần trăm.

Return annualization dùng `(NAV_end/NAV_start)^(252/n_returns)−1`; volatility sample std daily returns ×sqrt252; Sharpe dùng daily excess mean/std, risk-free annual6% quy đổi compounded daily. MDD là min NAV/cumulative_peak−1. Sortino dùng RMS của các **negative excess returns** như code gốc; không trộn với định nghĩa dùng toàn bộ observation count. Chi phí giao dịch vẫn **0**, chưa chạy cost sensitivity.

## 9. MVO reconciliation — Vì sao 3,73 và 3,57

Standalone MVO của paper có terminal NAV **3,7257457727**. Dòng sensitivity gắn nhãn “alpha=1/pure MVO” có Hybrid NAV **3,5697514342** vì chỉ **alpha_normal** đổi thành1,0; **alpha_stress=0,3** và **alpha_crisis=0,1** vẫn giữ nguyên. Khi stress/crisis xuất hiện, Hybrid vẫn pha BL. Universe/constraints của standalone MVO không phải nguyên nhân của chênh lệch này.

**Ngày weights và NAV bắt đầu phân kỳ: 20/10/2023**, stress. Replayed NAV tại ngày đó: MVO0,957085210, Hybrid0,961214972. Đây là bằng chứng từ quyết định/return, không chỉ sửa typography.

Định nghĩa sửa: gọi dòng đó **Hybrid với alpha_normal=1**, hoặc nếu muốn pure MVO thì phải đặt **alpha=1 ở mọi regime**. Với cùng MVO leg/cleanup/return stream, pure-MVO endpoint phải giống standalone MVO; smoke test alpha-one identity đã đạt. Không chọn lại alpha để tăng P&L.

Table OOS chính 3,73 đúng với archived run đó; **cách diễn giải dòng sensitivity 3,57 là “pure MVO” sai**. Không thay 3,57 thành3,73 mà vẫn giữ cấu hình stress/crisis cũ. Baseline mới tới 01/07/2026 có standalone MVO NAV **2,8933212018**; không lấy số này sửa hồi tố bảng của kỳ cũ. Chi tiết: {link('mvo_reconciliation.md',Path('outputs/step1/mvo_reconciliation.md'))}.

## 10. Parameter provenance — Nguồn gốc lựa chọn tham số

{link('parameter_provenance.csv',Path('outputs/step1/parameter_provenance.csv'))} có **135 entries**, gồm K, correlation/covariance windows, ensemble/member params, horizon, lịch5/10/20, tau/delta, risk aversion, confidence bounds/scales, pruning threshold, caps, regime thresholds và hybrid alpha. Phân biệt giá trị thực thi trong code với bằng chứng nó được chọn trên IS và freeze trước OOS.

Không có search log, pre-OOS freeze artifact hoặc protocol timestamp đủ chứng minh các lựa chọn đó. Mục thiếu nguồn gốc ghi đúng **UNKNOWN / POSSIBLE POST-HOC CHOICE**. Manuscipt có claim “IS tuning/fixed before OOS” nhưng không xem claim là chứng cứ đã được kiểm tra. Không bịa một lý do lựa chọn tham số sau khi nhìn hiệu suất.

Trong công việc Step 1 này, tham số chiến lược được giữ như snapshot; không so sánh nhiều cấu hình rồi chọn OOS tốt hơn. Solver tolerance, calendar và corrections phục vụ integrity, đã ghi log. Guide cho phép ghi UNKNOWN trong register; thiếu provenance được lưu như giới hạn, không tự biến thành kết luận có tuning leakage đã được chứng minh.

## 11. Corrections — Bản sửa, checks và outputs

Code sửa nằm trong {link('trusted_baseline',Path('trusted_baseline'))}; original source giữ nguyên. {link('change_log.md',Path('outputs/step1/change_log.md'))} ghi issue, legacy behavior, correct behavior, reason và ảnh hưởng. Các thay đổi chính: VFF identity, GOLD source consistency, observed session calendar, causal fill, validation purge, prefix feature parity, next-close execution, fixed-share drift, OOS boundary, final feasibility, provenance/turnover exports.

**27/27 regression tests đạt**: 10 optimizer, 5 execution, 9 ML và 3 data/calendar. Các lỗi có red-before/green-after evidence; real-solver smoke/property checks và review độc lập bổ sung các tình huống residual/cap/fallback. {link('final_trusted_tests.log',Path('outputs/step1/final_trusted_tests.log'))} là final run đúng cwd `trusted_baseline`. Có một diagnostic test invocation từ root import nhầm legacy source; log được giữ riêng `legacy_import_tests_misrun.log`, không dùng nó làm kết quả test của baseline mới.

Hai lượt chạy fresh-fit `{RUN}` và `{REPEAT}` cùng source khoa học/input/config/seeds, không dùng cache: **13 CSV giống từng byte**, actual prediction JSON giống hoàn toàn; max numeric result difference **0**. {link('reproducibility_verification.json',Path('outputs/step1/reproducibility_verification.json'))} lưu comparison hashes. Determinism này áp dụng cho môi trường đang ghi nhận, không chứng minh run paper gốc dùng cùng môi trường.

Independent actual-run ML review còn kiểm lại scaler moments, cả 1.449 feature/prediction statistics, **80 global selection optima** và 302 BL posterior; kết quả mechanical PASS nằm trong `ml_static/final_run_review.json`. Không nhầm review này với rerun fit thứ hai. Model parameter audit raw JSON có XGBoost `missing=NaN`; có thêm `.strict.json` dùng string `nan` cho nonfinite metadata để parser JSON chuẩn đọc được, không sửa dữ liệu chạy hoặc các CSV đã đối chiếu. `STATUS.json` cập nhật sau khi chạy xong để ghi kết luận hiện tại; bản metadata trước chạy giữ tại `source_metadata_at_execution/STATUS.json`, còn code/config/data khoa học của hai run không đổi.

Các file được yêu cầu đã tạo:

| Artifact | Đường dẫn |
|---|---|
{delivery}

Report này có bản giống hệt tại `report.md` và `outputs/step1/step1_report.md`; `deliverable_inventory.csv` có hash các output chính. `trusted_baseline/run_config.json`, `random_seeds.txt`, `requirements_frozen.txt` và mỗi run `manifest.json` giữ cấu hình, seeds, env/input/source/output identity; `aligned_prices.csv`, result pickle, actual training/prediction JSON và selection matrices cho phép kiểm tra lại.

Đã tạo đủ bốn nhóm figure được yêu cầu, kèm corrected NAV/drawdown, dưới `outputs/step1/plots/`, cả PNG/PDF:

1. `walk_forward_timing`: actual dates của bốn lượt fit; schematic spacing không biểu diễn độ dài thời gian.
2. `legacy_vs_corrected_nav`: MVO/BL/Hybrid; đường paper replay kết thúc27/02, đường mới kết thúc01/07; input/calendar/execution khác nhau nên không xem là hiệu ứng một sửa lỗi đơn lẻ.
3. `constraint_diagnostics`: budget, position cap, negative weights so với tolerance1e-8.
4. `turnover_history`: turnover mỗi rebalance của bốn chiến lược, initial capital excluded.

![NAV legacy và bản sửa]({ROOT}/outputs/step1/plots/legacy_vs_corrected_nav.png)

Lệnh tái lập từ project root:

```sh
venv/bin/python scripts/step1_run_baseline.py --verification-run
```

Lệnh regression:

```sh
cd trusted_baseline
MPLCONFIGDIR=/private/tmp/portfolio-step1-mpl XDG_CACHE_HOME=/private/tmp/portfolio-step1-cache ../venv/bin/python -B -m unittest discover -s tests -v
```

`--verification-run` tạo run/artifact folder mới, không ghi đè bộ kết quả chính. Không cần sửa tham số hoặc tải lại dữ liệu để tái lập input đã đóng băng. Manifest ghi argv, thời gian, interpreter, hash và trạng thái; chỉ các run `succeeded` mới được dùng ở đây.

## 12. Impact on empirical conclusions — Ảnh hưởng đến kết luận thực nghiệm

### Baseline sau sửa, IS

Mốc NAV 11/02/2020–29/09/2023, 911 returns:

{is_table}

### Baseline sau sửa, OOS

Mốc NAV 29/09/2023; earned returns 02/10/2023–01/07/2026, 684 returns:

{oos_table}

Mẫu kết quả **risk reduction của BL** còn hiện diện trong valuation-proxy study: BL volatility12,81%/MDD−9,64% thấp hơn MVO32,74%/−26,86%, nhưng NAV thấp hơn. Hybrid lấy lại upside so với BL, đồng thời volatility/MDD tăng. **Hybrid không còn có Sharpe cao nhất**: BL1,537 > Hybrid1,445 trong kỳ mới. Vì thế không thể giữ nguyên mọi kết luận định tính của bảng paper.

Turnover OOS/năm cao ở MVO **24,071** và Hybrid **16,965**, BL **8,385**; đây là dữ liệu cần cho Step 8, chưa phải ước lượng net return. Không tự áp bps hoặc dự đoán chính xác mức giảm Sharpe khi chưa chạy cost experiment.

Chênh lệch với paper phản ánh nhiều yếu tố đồng thời, gồm kỳ kết thúc mới, nguồn input, lịch phiên và sửa mechanics. Không gán riêng lợi ích cho XGBoost, confidence, constraints hay một sửa lỗi. OOS raw ensemble hit-rate50% cũng không trả lời incremental economic value của ML; cần no-ML/matched-constraint ablations theo các bước sau.

Kết luận hiện đủ bằng chứng: **code tính P&L/weights/turnover mới nhất quán và deterministic dưới dữ liệu đã khai báo; pattern BL phòng thủ vẫn xuất hiện có điều kiện**. Chưa đủ bằng chứng cho fully causal historical release data, total-return interpretation, survivorship-free performance, net returns hoặc implementable VFF/GOLD trading.

## 13. Blocking issues — Còn thiếu gì để chứng nhận Step 1

Không có blocker kỹ thuật về solver, fit, xuất CSV hay NAV arithmetic trong run đã kiểm. Các vấn đề dưới đây là bằng chứng dữ liệu/reproduction còn thiếu, không thể giải quyết bằng cách chạy lại cùng code thêm lần nữa:

| Vấn đề còn mở | Bằng chứng hiện có và giới hạn | Cách đóng vấn đề |
|---|---|---|
| Historical public availability của VFF/GOLD | Có valuation date, NAV đúng danh tính; provider `createdAt` không phải release history đã xác nhận. Decision chỉ ghi “after close”, chưa có precise cutoff | Có archive công bố/revision hoặc xác nhận release policy áp dụng toàn kỳ; định nghĩa decision clock cụ thể; join theo thông tin known-by-cutoff và rerun nếu chronology thay đổi |
| GOLD instrument/quote origin | Snapshot SJC sell đã fill, không có quote-origin/imputation/location/unit metadata đầy đủ | Phục hồi raw quote snapshots, đơn vị, địa điểm, giờ và cờ fill; hoặc chốt bằng văn bản phạm vi nghiên cứu là frozen valuation proxy rồi đánh giá lại gate, không tự nhận nó là feed đã xác minh |
| Stock corporate actions/return semantics | Provider close reproducible, adjusted/raw và cash dividend handling UNKNOWN | Lưu contract/version adjustment của provider, đối chiếu corporate actions và xác định rõ price return/total return; sửa input/arithmetic khi có bằng chứng, rồi rerun |
| Strong historical end-to-end reproduction | Archived arithmetic/alpha/hit-rate được phục hồi; fresh current code khác paper; không có original fit environment gắn run | Phục hồi dependency/model/protocol artifacts của run paper, tái sinh quyết định độc lập; nếu không thể, giữ reproduction là partial và phân biệt bảng cũ với baseline mới |

Static-universe bias thuộc Step7; zero costs và dealing/spread/settlement realism thuộc các thí nghiệm triển khai sau. Chúng vẫn phải được công khai, nhưng **không được lẫn với các lỗi Step1 đã sửa**. Parameter-origin UNKNOWN được ghi theo chính hướng dẫn của guide; không bịa retrospective provenance.

Đánh giá completion criteria của guide:

| Tiêu chí | Trạng thái |
|---|---|
| Causal feature formulas và label availability theo dated inputs | PASS theo audit/tests |
| Không same-period earned-return leakage; execution rõ ràng | PASS trong quy ước next-session-close |
| Historical input public availability/revisions | UNVERIFIED — blocker strict causal gate |
| Reproducibility của baseline mới với fixed seeds/env | PASS — hai fresh runs, exact outputs |
| Target feasibility, holdings drift, NAV và turnover | PASS |
| BL posterior calculation và MVO discrepancy | PASS |
| Full original-manuscript end-to-end recreation | PARTIAL — archived-decision replay, không độc lập refit toàn pipeline |
| Universe và parameter choices được ghi rõ, unknown không che giấu | PASS về documentation |
| Source price/adjustment semantics đủ chắc để chứng nhận economic P&L | UNVERIFIED |

Các đầu việc audit, corrections và recomputation đã thực hiện, có file kiểm chứng. **Chưa đánh dấu Step 1 đạt toàn bộ completion criteria** và chưa chạy thí nghiệm Step 2. Cần đóng các bằng chứng nêu trên rồi kiểm lại readiness; không dùng sự tồn tại của thư mục `trusted_baseline` để bỏ qua gate của giảng viên.

NOT READY FOR STEP 2
"""
    (ROOT/"report.md").write_text(report)
    (OUT/"step1_report.md").write_text(report)
    print(json.dumps({"report":str(ROOT/"report.md"),"bytes":len(report.encode()),"decision":"NOT READY FOR STEP 2"}))


if __name__=="__main__":
    main()
