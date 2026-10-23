# Báo cáo Step 1 về kiểm tra tính đúng đắn và tái dựng kết quả đối chứng

**Ngày thực hiện:** 04/10/2026. **Ngày biên tập:** 12/10/2026.

Báo cáo đánh giá tính nhân quả, khả năng tái lập và sự nhất quán của quy trình xây dựng danh mục theo `guide_0.md` và `project_0.md`. Cấu trúc giữ đủ 13 mục theo hướng dẫn; phạm vi là kiểm tra và sửa lỗi triển khai, **không tối ưu tham số để cải thiện OOS**. Kiến trúc EW/MVO/BL+ML/Hybrid được giữ nguyên để làm nền tảng cho các thí nghiệm thành phần ở giai đoạn tiếp theo.

**Kết quả chung:** READY FOR STEP 2 trong phạm vi giao thức dùng giá định giá đại diện và availability giả định được khai báo tại mục 13. Hai lượt mới và audit độc lập đã đạt; bảng 12.1 là kết quả mới. Các mục 2–11 lưu kiểm tra nền 04/10; mục 13 ghi bổ sung và thay đổi 12/10. Chưa chứng nhận thời điểm công bố đầu tiên/vintage điều chỉnh lịch sử hoặc thực thi giao dịch quỹ thực tế.

| Phần | Kỳ đánh giá và dữ liệu thực tế |
|---|---|
| Toàn mẫu | Yêu cầu 01/01/2020–30/04/2026; ma trận chung 14/01/2020–29/04/2026, 1.568 phiên × 32 tài sản |
| IS | Ngày trước 01/10/2023; NAV đánh giá từ 18/02/2020 đến 29/09/2023 sau khởi tạo, gồm 906 mức sinh lợi |
| OOS | Ngày từ 01/10/2023; NAV chuẩn hóa tại 29/09/2023, ghi nhận 641 mức sinh lợi từ 02/10/2023 đến 29/04/2026 |

Ngày 30/04 được chọn theo quy ước hết tháng vì bài báo chỉ nêu tháng; phiên cuối quan sát được là 29/04. Các kết quả dưới đây dùng snapshot đã lưu và chưa trừ chi phí giao dịch.

## 1. Tái lập kết quả bài báo (Reproduction status)

**Bảo toàn phiên bản gốc.** `legacy_version/` lưu 631 tệp mã nguồn, cấu hình, dữ liệu và kết quả, được đặt chỉ đọc và kiểm tra bằng SHA-256. Commit tham chiếu là `5350e2a7960797e6a9b0fb73edfe5c5a20d8ce54`; các thay đổi chưa commit lúc bắt đầu được ghi trong hồ sơ. Mã nguồn nghiên cứu gốc được giữ riêng với bản hiệu chỉnh.

**Tái lập lượt lịch sử đã được bổ sung.** Lần chạy nguyên trạng ban đầu đến 01/07/2026 không khớp số công bố; khác biệt liên quan đến kỳ kết thúc, danh tính dữ liệu quỹ, nguồn GOLD và snapshot giá. Kết quả này được lưu làm bằng chứng lịch sử, không sử dụng thay cho baseline tháng 4.

Snapshot lịch sử `71cc107` khôi phục được các tỷ trọng mục tiêu đã lưu. Tái dựng phép tính từ các quyết định này cho **24 giá trị NAV cuối khớp ở độ chính xác hiển thị**, sai lệch lớn nhất **1,09e−6**, phù hợp với tỷ trọng chỉ lưu sáu chữ số thập phân. OOS lịch sử cho NAV EW/MVO/BL/Hybrid lần lượt **1,8224/3,7257/1,9000/2,8572** và hit rate **174/335 = 51,94%**. Ngày 12/10 đã huấn luyện mới IS/OOS từ source/data commit 71cc107 trong môi trường ghi nhận, không cache; metrics, toàn bộ tỷ trọng và views khớp chính xác log gốc. Chưa xác nhận môi trường gốc hoặc fit lại năm lượt alpha riêng.

**Bất nhất về kỳ dữ liệu:** văn bản bài báo ghi tháng 4/2026, Figure 1 ghi tháng 3/2026, còn hồ sơ lịch sử khôi phục có ngày OOS cuối **27/02/2026** và tái dựng được NAV công bố. Bộ dữ liệu lịch sử cũng thiếu GOLD/VFF để phủ trọn tháng 4; 29/30 chuỗi cổ phiếu khác snapshot hiện tại trên ngày chung. Do đó, lượt chạy mới sử dụng snapshot chuẩn hóa đã kiểm tra, không được gọi là tái tạo đúng bộ dữ liệu lịch sử của bài báo.

Môi trường chạy được ghi nhận gồm Python **3.12.0**, NumPy **2.2.6**, pandas **2.2.3**, scikit-learn **1.8.0**, XGBoost **3.2.0**, CVXPY **1.8.2**, vnstock **4.0.4**; seed **42–46**. Chi tiết phụ thuộc, đầu vào, cấu hình, nhật ký và hàm băm nằm trong hồ sơ thực thi.

**Minh chứng:** [snapshot phiên bản gốc](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/legacy_version/snapshot_manifest.json); [kết quả chạy nguyên trạng](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/legacy_results); [tái dựng lịch sử](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/portfolio_static/historical_replay_report.json); [coverage dữ liệu](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/input_coverage.md).

## 2. Kiểm tra dữ liệu (Data audit)

Danh mục dữ liệu ghi nhận **288 CSV gốc và nguồn VFF hiệu chỉnh**, gồm nguồn, ngày bao phủ, số quan sát, định nghĩa giá, lịch phiên, dữ liệu thiếu và hàm băm. Không ghi nhận ngày trùng/rỗng hoặc giá không dương trong các CSV gốc được kiểm; `VPL_train.csv` rỗng nhưng VPL không thuộc tập đang chạy. Kiểm tra cấu trúc chưa đủ xác nhận danh tính tài sản hoặc cách điều chỉnh giá.

**VFF.** 62 tệp quỹ hiện tại có cùng chuỗi giá dù khác mã. Nhánh API đang cài không chuyển symbol đến `Fund.nav_report`, giữ mặc định `fundId=23`, rồi crawler gán lại nhãn. Nguồn thay thế được truy vấn rõ **VFF = productId21, BOND, VinaCapital**; toàn bộ **542 ngày NAV chung với snapshot lịch sử khớp chính xác** sau quy tắc làm tròn. Baseline tháng 4 sử dụng **552 quan sát**, gồm **295 IS và 257 OOS**; NAV cuối ngày **28/04/2026 = 26.064,61 VND**, giá chuẩn hóa **26,06**. Việc thay thế áp dụng cho đầu vào baseline; **crawler gốc/vnstock chưa được sửa trực tiếp**, nên tải lại bằng nhánh cũ có thể tái diễn lỗi. Danh tính thực tế của chuỗi bị sao chép trước đây còn chưa xác định; không quy kết dữ liệu VFF của lượt bài báo gốc cũng sai.

**GOLD.** `full_path` gốc trỏ vào `gold_test.csv`, gây thiếu khởi tạo trong chế độ toàn mẫu. Giá toàn mẫu và chuỗi ghép train/test khác ở **1.973/2.392 ngày chung**. Baseline thống nhất dùng `gold_full.csv` đã đóng băng, rồi lấy IS/OOS từ cùng nguồn. Đây là lựa chọn theo độ bao phủ, không theo hiệu suất. GOLD vẫn là **đại diện định giá theo giá bán SJC**; metadata về quote gốc, giá đã điền, đơn vị, địa điểm và thời điểm công bố chưa đầy đủ.

**Lịch phiên và giá thiếu.** Ma trận dùng các ngày VNINDEX quan sát được thay lịch thứ Hai–thứ Sáu. Hợp nhất ngày quan sát trước khi chuyển tiếp giá gần nhất từ quá khứ, sau đó lọc phiên; không điền ngược hoặc điền trước quan sát VFF đầu tiên. VFF có **1.021 phiên chuyển tiếp giá**, tuổi quan sát tối đa **13 ngày lịch** và **1.073 mức sinh lợi bằng 0**; GOLD có **1.416 mức sinh lợi bằng 0**, nhưng tuổi quote gốc chưa xác định. Đây là lịch thực nghiệm, chưa phải archive lịch HOSE được xác thực đầy đủ.

**Giới hạn giá cổ phiếu.** Trường `close` tái lập được nhưng chưa rõ là giá thô hay đã điều chỉnh chia tách/cổ tức; chưa có sổ sự kiện hoặc hạch toán cổ tức tiền mặt. Lợi nhuận hiện được tính từ tỷ lệ giá đã lưu, chưa được xác nhận là total return. Ngày định giá của VFF/GOLD cũng chưa chứng minh thời điểm dữ liệu đã được công bố.

**Minh chứng:** [data_manifest.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/data_manifest.csv); [xác minh VFF và nguồn dữ liệu](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/audit_data.md); [chẩn đoán dữ liệu tháng 4](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/april_run_data_diagnostics.json).

## 3. Kiểm tra tập tài sản đầu tư (Universe audit)

Một danh sách **30 cổ phiếu cố định** được áp dụng cho toàn bộ lịch sử:

```text
ACB BID CTG DGC FPT GAS GVR HDB HPG LPB MBB MSN MWG PLX SAB SHB SSI STB TCB TPB VCB VHM VIB VIC VJC VNM VPB VRE BVH POW
```

Ngày tham chiếu/hiệu lực của danh sách chưa xác định; chưa có lịch sử thành phần VN30, kiểm tra đầy đủ niêm yết/hủy niêm yết hoặc quy tắc loại tài sản thiếu dữ liệu theo ngày. SSB/VPL có tệp dữ liệu nhưng không thuộc JSON đang dùng; chưa xác nhận việc loại do bộ lọc lịch sử. Vì vậy, danh sách không được mô tả là VN30 đúng tại mọi thời điểm.

EW và MVO sử dụng **32 tài sản** gồm 30 cổ phiếu, GOLD, VFF. BL thường sử dụng **5 đại diện + GOLD + VFF**; Hybrid kết hợp MVO toàn bộ 32 với BL trên tập 7 tài sản. VNINDEX chỉ là dữ liệu tham chiếu. Step 1 giữ thiết kế này và công khai nguy cơ thiên lệch sống sót; tái dựng thành phần theo thời điểm thuộc **Step 7**.

**Minh chứng:** [universe_provenance.md](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/universe_provenance.md).

## 4. Kiểm tra thời điểm thông tin và rò rỉ dữ liệu (Timing / leakage audit)

Phiên bản gốc dùng close(t) để hình thành tỷ trọng và giả định thực thi tại chính giá đó. Ngoài ra, ngày ghi views lệch ngày feature và chuẩn hóa OOS làm mất mức sinh lợi phiên đầu. Bản hiệu chỉnh áp dụng quy ước sau:

| Đại lượng | Thời điểm mới |
|---|---|
| Feature và ngày hình thành dự báo | Thông tin đến close(t−1), giữ độ trễ gốc |
| Tương quan dùng để chọn đại diện | Lịch sử kết thúc không muộn hơn t−1 khi chọn lại tài sản |
| Covariance, trung bình mẫu và tín hiệu chế độ | Các mức sinh lợi kết thúc đến close(t) |
| Outcome huấn luyện | Hoàn toàn nằm trước ngày quyết định; giữ ngưỡng cắt bảo thủ gốc |
| Dự báo và tỷ trọng mục tiêu | Sau close(t), có ngày quyết định riêng |
| Thực thi | Close phiên quan sát kế tiếp t+1 |
| Mức sinh lợi đầu của tỷ trọng mới | P(t+1)→P(t+2), ghi ngày kết thúc t+2 |

Biến động P(t)→P(t+1) thuộc lượng nắm giữ trước giao dịch; tỷ trọng mới chỉ hưởng P(t+1)→P(t+2). Chỉ số ngày thị trường/tài sản/danh mục phải khớp; lệnh cuối mẫu không tạo lợi nhuận tương lai. Sổ thực thi lưu **311 quyết định/giao dịch**, bao gồm đầu IS, COVID, năm 2022, đầu/cuối OOS và giai đoạn căng thẳng; không ghi nhận lỗi thứ tự ngày.

**Phạm vi xác nhận:** các mốc được kiểm theo ngày định giá. `createdAt` của provider chưa được xác nhận là thời điểm công bố; timestamp quyết định là quy ước mô phỏng. Do đó, kiểm tra ngày không đủ chứng nhận mọi input đã biết tại decision time.

**Minh chứng:** [execution_ledger.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/execution_ledger.csv); [sơ đồ walk-forward bằng ngày thực tế](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/plots/walk_forward_timing.png).

## 5. Kiểm tra huấn luyện mô hình học máy (ML training audit)

Mục tiêu giữ nguyên **lợi nhuận đơn giản 5 phiên**, `y_i=P[i+5]/P[i]−1`. Lịch sử huấn luyện ngoài được cắt bảo thủ đến hàng t−6 trước khi tạo nhãn; không ghi nhận label endpoint tương lai trong nhánh mặc định. Sai lệch nằm ở chia nội bộ **80/20**, khi nhãn fitting chồng vào validation. Bản hiệu chỉnh loại hàng có label-end ≥ feature đầu validation và fit scaler chỉ trên fitting còn lại.

Ví dụ DGC ngày **07/08/2020**: 106 hàng hợp lệ, 84 fitting ban đầu, loại 5 hàng còn **79 fitting/22 validation**. Label fitting cuối 23/06, validation bắt đầu 24/06, outcome train/validation cuối 30/07, trước quyết định 07/08 và thực thi 10/08. Hồ sơ scaler xác nhận dùng 79 hàng.

| Feature | Định nghĩa và cửa sổ dữ liệu | Kết quả kiểm tra |
|---|---|---|
| Momentum 5/10/20 | P(t)/P(t−n)−1 | Nhân quả, dịch về quá khứ |
| RSI14 | Trung bình trượt mức tăng/giảm, giữ quy ước trung tính đầu mẫu | Nhân quả |
| `ma_ratio_10_30` | EMA10/EMA30−1; tên MA không phải rolling SMA | Nhân quả; duy trì trạng thái theo lịch sử |
| Volatility20 | Độ lệch chuẩn mẫu của 20 mức sinh lợi ngày | Nhân quả |
| MACD histogram | EMA12−EMA26 trừ EMA9 signal | Nhân quả; duy trì trạng thái theo lịch sử |
| Price std20 normalized | Độ lệch chuẩn mẫu của 20 giá chia giá trung bình 20 giá | Nhân quả |

Dự báo cũ chỉ lấy 30 giá cuối, khác trạng thái EMA/MACD khi huấn luyện trên lịch sử mở rộng. Bản hiệu chỉnh dùng cùng lịch sử nhân quả, giữ lag một hàng. Vector hóa khớp công thức prefix ở cả chuỗi giả lập và ACB; thay giá tương lai không đổi feature quá khứ. Không dùng chuẩn hóa toàn mẫu, cửa sổ đặt tâm hoặc điền ngược.

Đã lưu **715 lần huấn luyện theo tài sản và 1.409 dự báo**, kèm tham số, seed, scaler, dự báo thành viên, độ lệch chuẩn và confidence. Không ghi nhận lỗi cửa sổ nhãn/validation trong kiểm tra đã thực hiện. Không thay hyperparameter hoặc chọn cấu hình theo OOS; giới hạn bằng chứng về nguồn gốc tham số được nêu tại mục 10.

**Minh chứng:** [training_window_audit.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/training_window_audit.csv); [ml_training_audit.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/ml_training_audit.csv); [ml_prediction_audit.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/ml_prediction_audit.csv).

## 6. Kiểm tra lựa chọn tài sản đại diện (Asset-selection audit)

Thuật toán duyệt toàn bộ tổ hợp **K=5 trong 30 ứng viên**, tối thiểu hóa `sum_i min_m(1−rho[i,m])`. Tương quan dùng lịch sử mở rộng đến không muộn hơn t−1; covariance danh mục dùng 20 phiên. Tương quan không xác định được đặt bằng 0, xử lý đồng hạng theo thứ tự ứng viên cố định.

Đã lưu **78 lần lựa chọn**, gồm ứng viên, đầu/cuối lịch sử, ma trận khoảng cách, tập chọn và giá trị mục tiêu. Lần đầu **11/02/2020** chọn **GVR/MBB/SAB/TPB/VIC**, mục tiêu **6,583373529**; lần cuối **10/04/2026** chọn **MBB/PLX/SAB/VHM/VJC**, mục tiêu **10,188801798**. Kiểm tra độc lập xác nhận các nghiệm tối ưu toàn cục và hai lượt chạy chọn cùng tập.

Tên phù hợp là **correlation-structure-based representative asset selection** hoặc **medoid-like correlation coverage selection**; triển khai chưa phải clustering/PAM. Kết quả xác nhận thuật toán nhân quả theo input định ngày và tái lập, chưa chứng minh ưu thế so với Full VN30/Random K/Simple selection. Đối chiếu đó thuộc Step 2.

**Minh chứng:** [selection_history.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/selection_history.csv). Ma trận `.npz` được tham chiếu tương đối với thư mục lượt chạy chính tại mục 11.

## 7. Kiểm tra mô hình Black–Litterman (BL audit)

Hồ sơ mỗi lần xây dựng BL gồm covariance, tỷ trọng cân bằng, delta/tau, pi, P/Q, confidence, Omega, hậu nghiệm và tỷ trọng mục tiêu. Prior dùng **tỷ trọng đều trong tập hoạt động**, chưa phải tỷ trọng vốn hóa được xác minh. Mu/Q là kỳ vọng lợi nhuận ngày; covariance có đơn vị bình phương lợi nhuận ngày.

```text
pi = delta × Sigma × w_eq
Omega = diag(diag(P × tau × Sigma × Pᵀ) / clipped_confidence)
mu_BL = pi + tau × Sigma × Pᵀ × solve(P × tau × Sigma × Pᵀ + Omega, Q − P × pi)
```

**294 hậu nghiệm thực tế** khớp phép tính độc lập, sai lệch tối đa **3,04e−18**. Hồ sơ gồm **311 trạng thái quyết định**, với **17 trường hợp không có view** dùng trung bình lợi nhuận mẫu và tối ưu có ràng buộc theo thiết kế cũ. Nhánh này không phải đối chứng BL-prior/no-ML. Omega tỷ lệ tau nên tau phần lớn triệt tiêu trong hậu nghiệm, ngoại trừ ảnh hưởng ngưỡng số học; chưa có cơ sở quy lợi ích riêng cho tau.

**Minh chứng:** [covariance, P/Q, hậu nghiệm và tỷ trọng thực tế](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/bl_audit_sample/corrected).

## 8. Kiểm tra cơ chế danh mục (Portfolio mechanics)

**Lượng nắm giữ và NAV.** Phiên bản gốc dùng cùng tỷ trọng để tính lợi nhuận hằng ngày giữa lịch rebalance, tương đương tái cân bằng ngầm. Bản hiệu chỉnh giữ **số đơn vị tài sản**; tỷ trọng trôi theo `w×(1+r)/(1+rp)`, giao dịch tại close phiên kế tiếp. OOS giữ mô hình/lượng nắm giữ/lệnh chờ từ IS, không cấp vốn ban đầu lần hai. Mô phỏng độc lập từ tiền mặt khớp NAV với sai lệch lớn nhất **1,42e−13** và turnover **5,00e−16**.

**Ràng buộc.** Kiểm tra sau bộ giải, làm sạch và kết hợp nhánh, với ngưỡng **1e−8**. Cả **1.244 vector giao dịch = 311 lần × 4 chiến lược** không có vi phạm vượt ngưỡng; sai lệch lớn nhất **1,18e−10**. Loại vị thế dưới 1% chỉ được giữ khi còn khả thi; nếu cần sử dụng phép chiếu có giới hạn hoặc giữ tỷ trọng khả thi chưa loại. Cấu hình vô nghiệm phải báo lỗi.

| Ràng buộc tại mục tiêu/giao dịch | Phạm vi áp dụng |
|---|---|
| Tổng tỷ trọng bằng 1, long-only, mỗi vị thế ≤0,50 | EW, MVO, BL, Hybrid |
| Nhóm không phòng thủ ≤0,70; VFF tối thiểu danh nghĩa 0,15 | BL |
| VFF tối thiểu hiệu dụng 0,30 | GOLD cũng thuộc nhóm không phòng thủ theo code, nên chỉ VFF thuộc nhóm phòng thủ |

Hybrid kết hợp MVO toàn bộ 32 tài sản với BL hoạt động, không kế thừa giới hạn nhóm BL. Giới hạn được kiểm tại giao dịch; tỷ trọng có thể trôi vượt cap giữa các lần giao dịch.

**Turnover và chỉ số.** `Turnover=0,5×sum|w_target−w_pretrade|`; dùng tỷ trọng trôi trước giao dịch, loại phân bổ vốn ban đầu khỏi quy đổi năm. OOS có **128 giao dịch/chiến lược**, tính sau mốc 29/09/2023. Turnover/năm = tổng turnover ×252/n_returns. Lợi nhuận năm là `(NAV_end/NAV_start)^(252/n_returns)−1`; biến động năm = độ lệch chuẩn mẫu return NAV ngày ×√252. Sharpe dùng lợi nhuận vượt lãi suất phi rủi ro ngày, với **6%/năm** quy đổi lãi kép. MDD đo sụt giảm từ đỉnh; Sortino giữ RMS trên các ngày excess return âm của code gốc. **Chi phí vẫn bằng 0**.

**Minh chứng:** [kiểm tra NAV, turnover và chỉ số độc lập](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/independent_review/final_run_review.md); [constraint_violations.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/constraint_violations.csv); [hình ràng buộc](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/plots/constraint_diagnostics.png); [lịch sử turnover](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected/plots/turnover_history.png).

## 9. Đối chiếu hai kết quả MVO (MVO reconciliation)

Table 2 ghi MVO **3,73**, Table 3 ghi Hybrid với `alpha_normal=1` đạt **3,57**, nhãn **“MVO component”**. PDF không ghi “pure MVO” dù đề xuất giảng viên mô tả như cấu hình MVO thuần. Nhật ký tương ứng là **3,7257457727** và **3,5697514342**.

**Nguyên nhân xác định:** chỉ alpha ở chế độ bình thường bằng 1, còn stress/crisis giữ **0,3/0,1**. Hybrid tiếp tục pha BL, phân kỳ với MVO từ **20/10/2023**, trạng thái stress. Vòng lặp dùng cùng nhánh MVO trên 32 tài sản; giải thích chênh lệch do tập đầu tư/ràng buộc tại trang 10 chưa phù hợp triển khai thực tế.

Định nghĩa đúng là **Hybrid với alpha_normal=1, alpha_stress=0,3, alpha_crisis=0,1**. MVO thuần phải đặt alpha=1 trong mọi chế độ; kiểm thử cùng nhánh, làm sạch và chuỗi lợi nhuận xác nhận trùng MVO độc lập. Lượt tháng 4 cho MVO **3,2030589963** và Hybrid alpha_normal=1 **3,3184305868**. Các số đều gắn với đúng cấu hình; cần sửa diễn giải, không thay số 3,57 bằng 3,73 khi vẫn giữ blend ngoài normal.

**Minh chứng:** [mvo_reconciliation.md](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/mvo_reconciliation.md).

## 10. Nguồn gốc lựa chọn tham số (Parameter provenance)

Bảng nguồn gốc có **135 mục**, bao gồm K, cửa sổ dữ liệu, số mô hình và hyperparameter XGBoost, horizon, lịch **rebalance/retrain/reselect 5/10/20**, tau/delta, mức phạt rủi ro, confidence, ngưỡng loại vị thế, cap, regime và alpha. Bảng phân biệt giá trị thực thi với bằng chứng chọn trên IS/cố định trước OOS.

Thiết lập chính được giữ nguyên: **K=5**, tổ hợp **5 mô hình**, horizon **5 phiên**, covariance **20 phiên**, **tau=0,05**, **delta=2,5** và alpha Hybrid **0,6/0,3/0,1** cho normal/stress/crisis. Các giới hạn tỷ trọng được nêu tại mục 8; toàn bộ hyperparameter và ánh xạ confidence nằm trong bảng nguồn gốc và cấu hình thực thi.

Chưa có nhật ký tìm kiếm hoặc hồ sơ đóng băng trước OOS đủ xác nhận nguồn gốc các lựa chọn; trường thiếu chứng cứ được ghi **UNKNOWN / POSSIBLE POST-HOC CHOICE** theo guide. Step 1 giữ nguyên tham số và không chọn cấu hình dựa trên OOS. Thiếu hồ sơ chưa chứng minh đã xảy ra tối ưu hậu nghiệm, nhưng cũng chưa đủ xác nhận phát biểu “đã cố định trước OOS” trong bài báo.

**Minh chứng:** [parameter_provenance.csv](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/parameter_provenance.csv).

## 11. Các hiệu chỉnh và kết quả kiểm tra (Corrections)

Các sửa đổi nằm trong `trusted_baseline/`, giữ mã nguồn nghiên cứu gốc riêng. Nhóm hiệu chỉnh chính là **dữ liệu VFF/GOLD và lịch phiên; nhãn/scaler/feature ML; thực thi phiên kế tiếp; lượng nắm giữ và mốc OOS; khả thi sau làm sạch; hồ sơ và turnover**. Nhật ký thay đổi ghi hành vi trước/sau, lý do và ảnh hưởng. Không đổi K, mô hình, công thức confidence, regime hoặc tham số để cải thiện OOS.

**Kết quả kiểm tra:** 27/27 kiểm thử hồi quy, 52/52 kiểm tra độc lập và 40/40 kiểm tra tái lập đạt. Hai lượt mới `corrected-paper-period-20261004T132742` và `corrected-paper-period-repeat-20261004T133908` cho **13 CSV giống từng byte, dự báo giống hoàn toàn**, không dùng cache; phần chung với lượt tháng 7 cũng khớp. Kết quả xác nhận tính toán và tái lập trong môi trường ghi nhận, chưa xác nhận lịch sử công bố dữ liệu.

Mỗi lượt lưu manifest, cấu hình thực thi, seed, môi trường, input hashes, bản chụp mã nguồn, ma trận giá, hồ sơ fit/dự báo, ma trận lựa chọn và BL. Metadata JSON có XGBoost `missing=NaN`, là giới hạn với parser JSON nghiêm ngặt. Cấu hình trên đĩa vẫn mặc định tháng 7; kỳ tháng 4 được ghi bằng CLI trong manifest. Các CSV tháng 4 tại `paper_period/corrected/` được phân biệt với CSV tháng 7 ở thư mục gốc `outputs/step1/`.

| Nhóm hồ sơ cần lưu/nộp kèm | Tệp hoặc thư mục |
|---|---|
| Kết quả danh mục | `trusted_baseline_metrics.csv`, `trusted_baseline_nav.csv`, `trusted_baseline_daily_returns.csv`, `trusted_baseline_weights.csv`, `trusted_baseline_turnover.csv` |
| Kiểm tra pipeline | `training_window_audit.csv`, `ml_training_audit.csv`, `ml_prediction_audit.csv`, `selection_history.csv`, `execution_ledger.csv`, `constraint_violations.csv`, `bl_audit_sample/corrected/` |
| Nguồn dữ liệu/thiết kế/sửa lỗi | `data_manifest.csv`, `universe_provenance.md`, `parameter_provenance.csv`, `mvo_reconciliation.md`, `change_log.md` |
| Tái lập lượt chạy | `manifest.json`, `run_config.json`, `random_seeds.txt`, `requirements_frozen.txt`, `source_snapshot/` |
| Chẩn đoán hình | `walk_forward_timing`, `legacy_vs_corrected_nav`, `constraint_diagnostics`, `turnover_history`; bổ sung `corrected_nav`, `corrected_drawdown` |

**Minh chứng:** [manifest lượt chính](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/runs/corrected-paper-period-20261004T132742/manifest.json); [kết quả tháng 4](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected); [change_log.md](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/change_log.md); [kiểm thử](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/final_trusted_tests.log); [kiểm tra tái lập](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/reproducibility_verification.json).

[Bản báo cáo đầy đủ trước lần chắt lọc này](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/step1_report_before_selection_20261007.md) giữ các ví dụ, lịch sử đối chiếu và chi tiết kỹ thuật để tra cứu khi cần. Báo cáo hiện tại giữ các kết quả chính; các tệp kiểm chứng vẫn được bảo toàn.

Lệnh tái lập từ thư mục gốc dự án, dùng interpreter nghiên cứu và tạo thư mục mới:

```sh
MPLCONFIGDIR=/private/tmp/portfolio-step1-mpl XDG_CACHE_HOME=/private/tmp/portfolio-step1-cache venv/bin/python scripts/step1_run_baseline.py --verification-run --run-label paper-period --start-date 2020-01-01 --split-date 2023-10-01 --end-date 2026-04-30
```

## 12. Ảnh hưởng đến kết luận thực nghiệm (Impact on empirical conclusions)

### 12.1. Kết quả IS và OOS sau hiệu chỉnh

**Baseline đang dùng cho Step 2:** lượt mới ngày 12/10/2026, theo quy ước availability ở mục 13. Giá dùng ra quyết định tách khỏi giá dùng định giá danh mục. Ma trận chung 1.568 phiên × 32 tài sản từ 14/01/2020; sau khởi tạo, IS từ 18/02/2020 đến 29/09/2023 có 906 mức sinh lợi; OOS có 641 mức sinh lợi đến 29/04/2026, neo NAV=1 tại 29/09/2023. Chi phí bằng 0.

**IS**

| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |
|---|---:|---:|---:|---:|---:|---:|
| EW | 1.9287 | 20.05% | 23.34% | 0.651 | -37.44% | 0.739 |
| MVO | 4.1511 | 48.57% | 34.79% | 1.146 | -41.05% | 24.521 |
| BL+ML | 1.6295 | 14.55% | 14.20% | 0.617 | -18.70% | 9.551 |
| HYBRID | 3.0507 | 36.37% | 22.33% | 1.241 | -30.49% | 17.104 |

**OOS**

| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |
|---|---:|---:|---:|---:|---:|---:|
| EW | 1.7278 | 23.98% | 18.37% | 0.946 | -17.08% | 0.628 |
| MVO | 3.3904 | 61.61% | 33.08% | 1.441 | -30.18% | 23.363 |
| BL+ML | 1.8136 | 26.37% | 13.33% | 1.385 | -9.51% | 8.200 |
| HYBRID | 2.7044 | 47.86% | 21.38% | 1.665 | -16.13% | 16.613 |

BL+ML có biến động 13,33% và MDD −9,51%, thấp hơn MVO 33,08%/−30,18%, nhưng NAV cũng thấp hơn. Hybrid có Sharpe 1,665 và MDD −16,13%; chênh Sharpe với BL là 0,280, chưa được kiểm định. Turnover MVO/Hybrid còn cao (23,363/16,613 vòng NAV/năm). Các kết quả chưa xác định đóng góp riêng của ML; không quy sự thay đổi từ lượt 04/10 cho một hiệu chỉnh riêng lẻ.

### 12.2. Đối chiếu số công bố và logic gốc

**Đối chứng lưu trữ:** số liệu/hình của lượt 04/10, trước hiệu chỉnh availability và nguồn ngày 12/10; không dùng làm baseline Step 2.

| Kỳ | Chiến lược | NAV bài báo | NAV mới | Sharpe PDF | Sharpe mới | MDD PDF | MDD mới |
|---|---|---:|---:|---:|---:|---:|---:|
| IS | EW | 1.90 | 1.9308 | 0.60 | 0.648 | -37.7% | -37.47% |
| IS | MVO | 4.79 | 4.3186 | 1.19 | 1.174 | -38.7% | -42.13% |
| IS | BL+ML | 2.09 | 1.7778 | 0.96 | 0.805 | -14.8% | -18.99% |
| IS | HYBRID | 3.80 | 3.0363 | 1.36 | 1.222 | -24.9% | -30.53% |
| OOS | EW | 1.82 | 1.7149 | 1.15 | 0.936 | -17.3% | -17.15% |
| OOS | MVO | 3.73 | 3.2031 | 1.64 | 1.381 | -15.0% | -26.86% |
| OOS | BL+ML | 1.90 | 1.9479 | 1.71 | 1.629 | -7.1% | -9.64% |
| OOS | HYBRID | 2.86 | 2.7521 | 1.83 | 1.648 | -11.4% | -18.08% |

Các số công bố khác baseline mới về snapshot, lịch phiên, thực thi/huấn luyện và kỳ thực tế của log; không quy chênh lệch cho riêng ML hoặc một sửa lỗi. Đối chiếu bổ sung dưới đây cố định **cùng ma trận chuẩn hóa, thứ tự tài sản, môi trường, tham số và kỳ tháng 4**, chỉ thay logic gốc/hiệu chỉnh:

| Kỳ | Chiến lược | NAV gốc | NAV hiệu chỉnh | Sharpe gốc | Sharpe hiệu chỉnh |
|---|---|---:|---:|---:|---:|
| IS | EW | 1.9253 | 1.9308 | 0.644 | 0.648 |
| IS | MVO | 6.0647 | 4.3186 | 1.445 | 1.174 |
| IS | BL+ML | 1.8892 | 1.7778 | 0.925 | 0.805 |
| IS | HYBRID | 3.5173 | 3.0363 | 1.401 | 1.222 |
| OOS | EW | 1.7055 | 1.7149 | 0.924 | 0.936 |
| OOS | MVO | 2.2401 | 3.2031 | 0.952 | 1.381 |
| OOS | BL+ML | 1.9933 | 1.9479 | 1.763 | 1.629 |
| OOS | HYBRID | 2.2780 | 2.7521 | 1.319 | 1.648 |

Phiên bản gốc có 640 mức sinh lợi OOS, bản hiệu chỉnh 641 do mốc chuẩn hóa. Đối chiếu cùng 640 mức sinh lợi, neo tại 02/10/2023, cho NAV hiệu chỉnh EW/MVO/BL+ML/Hybrid **1,7126/3,2245/1,9458/2,7620**. Logic gốc có **112 vector vượt cap tại 1e−8**, mức vượt lớn nhất **0,00722417**; bản hiệu chỉnh không có vi phạm vượt ngưỡng. Các sửa lỗi vẫn cùng tác động, nên đây chưa phải ablation từng thành phần.

![Logic gốc và hiệu chỉnh trên cùng ma trận, kết thúc 29/04/2026](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/google_doc_20261007/legacy_vs_corrected_readable.png)

### 12.3. Độ nhạy alpha và tỷ lệ dự báo đúng hướng

**Đối chứng lưu trữ:** số liệu/hình của lượt 04/10, trước hiệu chỉnh availability và nguồn ngày 12/10; không dùng làm baseline Step 2.

| alpha_normal | NAV bài báo | NAV mới | Sharpe bài báo | Sharpe mới | MDD mới |
|---:|---:|---:|---:|---:|---:|
| 0.2 | 2.23 | 2.2260 | 1.98 | 1.812 | -11.56% |
| 0.4 | 2.53 | 2.4875 | 1.94 | 1.761 | -14.53% |
| 0.6 | 2.86 | 2.7521 | 1.83 | 1.648 | -18.08% |
| 0.8 | 3.20 | 3.0278 | 1.72 | 1.544 | -21.86% |
| 1.0 | 3.57 | 3.3184 | 1.64 | 1.467 | -25.20% |

Giữ alpha_stress=0,3 và alpha_crisis=0,1; tái tính số đơn vị tài sản từ hai nhánh MVO/BL đã fit và regime dựa trên giá, không fit riêng hoặc chọn alpha theo OOS. Alpha_normal=0,6 khớp NAV thực tế với sai lệch **2,18e−14**. Sharpe alpha_normal=0,2 đạt **1,812**, cao hơn Hybrid mặc định **1,648**; “cao nhất” chỉ áp dụng trong bốn cấu hình mặc định, không toàn grid.

OOS dự báo thô đạt **324/635 = 51,02%** (640 phát ra, 5 chưa đủ outcome); ML views sau chuyển đổi/ngưỡng đạt **175/347 = 50,43%** (351 phát ra, 4 chưa đủ outcome). Tất cả endpoint được chấm nằm trong mẫu tháng 4; các tập quan sát khác **174/335 = 51,9%** của bài báo.

| Tài sản | Views đúng/tổng đủ outcome | Tỷ lệ đúng hướng |
|---|---:|---:|
| Overall | 175/347 | 50.43% |
| MBB | 72/124 | 58.06% |
| PLX | 29/69 | 42.03% |
| SAB | 25/58 | 43.10% |
| VHM | 22/49 | 44.90% |
| VJC | 27/47 | 57.45% |

Phân nhóm dự báo theo ngày phát; IS đạt **376/769** nhưng gồm 5 dự báo thô/4 views phát 28/09, có outcome đến 04/10. Các outcome được chấm hồi cứu, không dùng để fit/tune trước chia mẫu. Hit rate chưa chứng minh đóng góp kinh tế của ML; no-ML/fixed-confidence là thí nghiệm tiếp theo.

### 12.4. So sánh đường NAV và điểm cần sửa trong bài báo

**Đối chứng lưu trữ:** số liệu/hình của lượt 04/10, trước hiệu chỉnh availability và nguồn ngày 12/10; không dùng làm baseline Step 2.

Đường bài báo được tái dựng từ quyết định lịch sử, không phải fit lại mô hình gốc. Để so hình dạng, cả hai đường neo NAV=1 tại **11/02/2020 trong IS** và **02/10/2023 trong OOS**. Vì mốc chuẩn hóa khác bảng hiệu suất gốc, số cuối đường có thể khác bảng. OOS lịch sử chỉ đến **27/02/2026**; nền xám đến 29/04 chỉ có đường mới.

![So sánh NAV trong IS](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/google_doc_20261006/paper_vs_rerun_is.png)

![So sánh NAV trong OOS](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/google_doc_20261006/paper_vs_rerun_oos.png)

EW gần như trùng đường lịch sử. Trong OOS chung, MVO có NAV cuối gần bằng bài báo nhưng từng lệch **15,81%** trong kỳ; BL+ML/Hybrid có tương quan return **0,933/0,911** và NAV cuối khoảng chung cao hơn **6,68%/5,04%**. Trong IS, MVO từng lệch **45,54%** dù chênh cuối khoảng chung chỉ **−1,89%**. Các pattern tăng/giảm lớn tương đồng nhưng đường tích lũy chưa được tái tạo chính xác. Tương quan được tính trên return giữa các mốc chung, không phải kiểm định ý nghĩa thống kê hay tác động riêng một thành phần.

Bài báo cần đồng bộ **kỳ dữ liệu**; **Sharpe** (công thức năm hình học không tái tạo bảng, MVO cho khoảng 1,994 thay vì 1,64); **view transformation** (Eq 5 tuyến tính, code dùng tanh theo biến động); **penalty rủi ro** (Eq 9 lambda/2, code dùng trực tiếp hệ số 1,5/default và 5,0/crisis, tương ứng lambda 3/default và 10/crisis); và **alpha_normal=1 vẫn blend ngoài normal** như mục 9.

**Minh chứng kết quả bổ sung:** [đối chiếu bài báo](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/paper_vs_corrected_metrics.csv); [đối chiếu cùng đầu vào](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/legacy_vs_corrected_metrics.csv); [cùng cửa sổ OOS](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/legacy_on_canonical_inputs/legacy-canonical-20261004T133015/common_oos_window_comparison.csv); [alpha và phương pháp tính](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/alpha_grid_method.json); [hit rate và mẫu quan sát](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/corrected_hitrate_summary.csv); [số đo đường NAV](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/paper_period/google_doc_20261006/trajectory_comparison.csv).

## 13. Hoàn tất bốn vấn đề trước Step 2

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
| Kiểm tra độc lập | 42/42 đạt: tái tính NAV từ lượng nắm giữ, return, turnover, chỉ số hiệu suất, scaler/nhãn, lựa chọn tài sản và hậu nghiệm BL. 310 bản ghi thực thi, 715 lượt huấn luyện, 1.404 dự báo, 78 lần lựa chọn. |
| Chạy lặp mới | 21/21 kiểm tra đạt; 13 CSV giống từng byte, hồ sơ fit/dự báo và views giống hoàn toàn; cả hai lượt fit mới, không cache. |
| Bảo toàn và đóng băng | 33 đầu vào lượt 04/10 không đổi; lưu source/config/seed/input hashes/môi trường cho hai lượt mới. Không tối ưu tham số theo OOS. |
| MVO/alpha | Giữ giải thích đã xác minh: alpha_normal=1 vẫn blend trong stress/crisis; MVO thuần chỉ tương ứng alpha=1 ở mọi regime. Không còn bất nhất này làm blocker. |

### 13.3. So sánh đường NAV sau lần chạy mới

Các đường dưới đây lấy từ CSV xuất, neo tại quan sát chung đầu tiên của từng kỳ. Đường paper đến 27/02/2026; phần nền xám chỉ có các baseline tháng 4, không kéo dài đường paper. Lượt 04/10 được giữ làm đối chứng; thay nguồn, độ chính xác giá và quy ước thông tin cùng lúc nên không gọi đây là ablation một yếu tố.

![NAV IS: lượt mới, đối chứng 04/10 và lượt lịch sử](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/readiness_20261012/plots/NAV_IS_New_vs_Reference.png)

![NAV OOS: lượt mới, đối chứng 04/10 và lượt lịch sử](/Users/nguyenkhang/Documents/MASTER/Thesis/source/portfolio-optimization/outputs/step1/readiness_20261012/plots/NAV_OOS_New_vs_Reference.png)

Trong OOS chung 03/10/2023–27/02/2026, tương quan return với đường paper của EW/MVO/BL/Hybrid là **0,994/0,889/0,642/0,853**. EW gần trùng; BL khác đáng kể về đường đi. Các đường dùng chung mốc chuẩn hóa, khác mốc bảng hiệu suất. Số đo tương quan được lưu trong `17_Readiness_Evidence.zip/trajectory_comparison.csv`; đây là so sánh mô tả, không phải kiểm định đóng góp kinh tế của ML. Mục 12.2–12.4 và các hình 11–13 giữ kết quả kiểm tra 04/10 để tra cứu, không phải số liệu của baseline mới.

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

Baseline dùng tiếp là `availability-observed-contract-20261012T233110`; mã nguồn trong `readiness_20261012/candidate_workspace/`, không lấy CSV tháng 7 ở thư mục gốc. Step 2 sẽ so sánh full VN30, random K=5, benchmark đơn giản K=5 và phương pháp chọn đại diện đề xuất, giữ mô hình danh mục phía sau và policy dữ liệu cố định. Universe point-in-time/chi phí/ML ablation xử lý ở bước tương ứng; không kết luận giá trị riêng của ML ở Step 1.

**Kết luận:** đủ điều kiện bắt đầu Step 2 theo giao thức thí nghiệm định giá đã khai báo và được đóng băng. Chứng nhận khả dụng lịch sử thực tế và thực thi quỹ thực tế vẫn chưa đạt; đây là giới hạn của diễn giải kết quả, không được viết thành đã xác minh hoàn toàn.

READY FOR STEP 2
