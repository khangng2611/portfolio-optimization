# **Báo cáo Step 1 (Về kiểm tra tính đúng đắn và tái dựng kết quả đối chứng)**

**Ngày kiểm tra nền: 04/10/2026. Cập nhật và chạy lại: 12/10/2026.** 

Báo cáo đánh giá khả năng tái lập và sự nhất quán của quy trình xây dựng danh mục. Phạm vi là kiểm tra và sửa lỗi triển khai, **không tối ưu tham số để cải thiện OOS**. Kiến trúc EW/MVO/BL+ML/Hybrid được giữ nguyên để làm nền tảng cho các thí nghiệm thành phần ở giai đoạn tiếp theo.

**Kết quả chung:** READY FOR STEP 2 trong phạm vi giao thức dùng giá định giá đại diện và availability giả định được khai báo tại mục 13\. Hai lượt mới và audit độc lập đã đạt; bảng ở mục 13 là kết quả mới; mục 12 lưu đối chứng 04/10. Các mục 2–11 lưu kiểm tra nền 04/10; mục 13 ghi bổ sung và thay đổi 12/10. Chưa chứng nhận thời điểm công bố đầu tiên/vintage điều chỉnh lịch sử hoặc thực thi giao dịch quỹ thực tế.

| Phần | Kỳ đánh giá và dữ liệu thực tế |
| :---- | :---- |
| Toàn mẫu | Yêu cầu 01/01/2020–30/04/2026; ma trận chung 14/01/2020–29/04/2026, 1.568 phiên × 32 tài sản |
| IS | Ngày trước 01/10/2023; NAV đánh giá từ 18/02/2020 đến 29/09/2023 sau khởi tạo, gồm 906 mức sinh lợi |
| OOS | Ngày từ 01/10/2023; NAV chuẩn hóa tại 29/09/2023, ghi nhận 641 mức sinh lợi từ 02/10/2023 đến 29/04/2026 |

Phiên cuối quan sát được là 29/04. Các kết quả dưới đây dùng snapshot đã lưu và chưa trừ chi phí giao dịch.

## **1\. Tái lập kết quả bài báo (Reproduction status)**

**Bảo toàn phiên bản gốc.** legacy\_version/ lưu 631 tệp mã nguồn, cấu hình, dữ liệu và kết quả, được đặt chỉ đọc và kiểm tra bằng SHA-256. Commit tham chiếu là 5350e2a7960797e6a9b0fb73edfe5c5a20d8ce54; các thay đổi chưa commit lúc bắt đầu được ghi trong hồ sơ. Mã nguồn nghiên cứu gốc được giữ riêng với bản hiệu chỉnh.

**Hồ sơ lượt chạy ban đầu.** Lần chạy nguyên trạng ban đầu đến 01/07/2026 không khớp số công bố; khác biệt liên quan đến kỳ kết thúc, danh tính dữ liệu quỹ, nguồn GOLD và snapshot giá. Kết quả này được lưu làm bằng chứng lịch sử, không sử dụng thay cho baseline tháng 4\.

Snapshot lịch sử 71cc107 khôi phục được các tỷ trọng mục tiêu đã lưu. Tái dựng phép tính từ các quyết định này cho 24 giá trị NAV cuối khớp ở độ chính xác hiển thị, sai lệch lớn nhất 1,09e−6, phù hợp với tỷ trọng chỉ lưu sáu chữ số thập phân. OOS lịch sử cho NAV EW/MVO/BL/Hybrid lần lượt 1,8224/3,7257/1,9000/2,8572 và hit rate 174/335 \= 51,94%. Ngày 12/10 đã huấn luyện mới IS/OOS từ source/data commit 71cc107 trong môi trường ghi nhận, không cache; metrics, toàn bộ tỷ trọng và views khớp chính xác log gốc. Chưa xác nhận môi trường gốc hoặc fit lại năm lượt alpha riêng.

## **2\. Kiểm tra dữ liệu (Data audit)**

Danh mục dữ liệu ghi nhận **288 CSV gốc và nguồn VFF hiệu chỉnh**, gồm nguồn, ngày bao phủ, số quan sát, định nghĩa giá, lịch phiên, dữ liệu thiếu và hàm băm. Không ghi nhận ngày trùng/rỗng hoặc giá không dương trong các CSV gốc được kiểm. Kiểm tra cấu trúc chưa đủ xác nhận danh tính tài sản hoặc cách điều chỉnh giá.

**VFF.**. Baseline tháng 4 sử dụng **552 quan sát**, gồm **295 IS và 257 OOS**; NAV cuối ngày **28/04/2026 \= 26.064,61 VND**, giá chuẩn hóa **26,06**. 

**GOLD**. Baseline thống nhất dùng gold\_full.csv đã đóng băng, rồi lấy IS/OOS từ cùng nguồn. Đây là lựa chọn theo độ bao phủ, không theo hiệu suất. GOLD vẫn là **đại diện định giá theo giá bán SJC**; metadata về quote gốc, giá đã điền, đơn vị, địa điểm và thời điểm công bố chưa đầy đủ.

**Lịch phiên và giá thiếu.** Ma trận dùng các ngày VNINDEX quan sát được thay lịch thứ Hai–thứ Sáu. Hợp nhất ngày quan sát trước khi chuyển tiếp giá gần nhất từ quá khứ, sau đó lọc phiên; không điền ngược hoặc điền trước quan sát VFF đầu tiên. VFF có **1.021 phiên chuyển tiếp giá**, tuổi quan sát tối đa **13 ngày lịch** và **1.073 mức sinh lợi bằng 0**; GOLD có **1.416 mức sinh lợi bằng 0**, nhưng tuổi quote gốc chưa xác định. Đây là lịch thực nghiệm, chưa phải archive lịch HOSE được xác thực đầy đủ.

**Giới hạn giá cổ phiếu.** Trường close tái lập được nhưng chưa rõ là giá thô hay đã điều chỉnh chia tách/cổ tức; chưa có sổ sự kiện hoặc hạch toán cổ tức tiền mặt. Lợi nhuận hiện được tính từ tỷ lệ giá đã lưu, chưa được xác nhận là total return. Ngày định giá của VFF/GOLD cũng chưa chứng minh thời điểm dữ liệu đã được công bố.

**Minh chứng:** **07\_Data\_Audit** → [data\_manifest.csv](https://drive.google.com/open?id=1GR4TevK5zS9g2_EQFS8g0y0xePv1O03Q&usp=drive_copy); [audit\_data.md](https://drive.google.com/open?id=1cmjsEfkKBx1FeniKVF5r-GN2UbRw8YTr&usp=drive_copy); [april\_run\_data\_diagnostics.json](https://drive.google.com/open?id=1VyblIkM9kmhOZL4iGrBRO9ymTVVhwkXm&usp=drive_copy).

## **3\. Kiểm tra tập tài sản đầu tư (Universe audit)**

Một danh sách **30 cổ phiếu cố định** được áp dụng cho toàn bộ lịch sử:

ACB BID CTG DGC FPT GAS GVR HDB HPG LPB MBB MSN MWG PLX SAB SHB SSI STB TCB TPB VCB VHM VIB VIC VJC VNM VPB VRE BVH POW

Ngày tham chiếu/hiệu lực của danh sách chưa xác định; chưa có lịch sử thành phần VN30, kiểm tra đầy đủ niêm yết/hủy niêm yết hoặc quy tắc loại tài sản thiếu dữ liệu theo ngày. Vì vậy, danh sách không được mô tả là VN30 đúng tại mọi thời điểm.

EW và MVO sử dụng **32 tài sản** gồm 30 cổ phiếu, GOLD, VFF. BL thường sử dụng **5 đại diện \+ GOLD \+ VFF**; Hybrid kết hợp MVO toàn bộ 32 với BL trên tập 7 tài sản. VNINDEX chỉ là dữ liệu tham chiếu. Step 1 giữ thiết kế này; tái dựng thành phần theo thời điểm thuộc **Step 7**.

**Minh chứng:** **08\_Design\_Provenance** → [universe\_provenance.md](https://drive.google.com/open?id=1m917w-mrqqyeiHddYqP8H0yESFUXQAx1&usp=drive_copy)

## **4\. Kiểm tra thời điểm thông tin và rò rỉ dữ liệu (Timing / leakage audit)**

Phiên bản gốc dùng close(t) để hình thành tỷ trọng và giả định thực thi tại chính giá đó. Ngoài ra, ngày ghi views lệch ngày feature và chuẩn hóa OOS làm mất mức sinh lợi phiên đầu. Bản hiệu chỉnh áp dụng quy ước sau:

| Đại lượng | Thời điểm mới |
| :---- | :---- |
| Feature và ngày hình thành dự báo | Thông tin đến **close(t−1)**, giữ độ trễ gốc |
| Tương quan dùng để chọn đại diện | Lịch sử kết thúc không muộn hơn t−1 khi chọn lại tài sản |
| Covariance, trung bình mẫu và tín hiệu chế độ | Các mức sinh lợi kết thúc đến close(t) |
| Outcome huấn luyện | Hoàn toàn nằm trước ngày quyết định; giữ ngưỡng cắt bảo thủ gốc |
| Dự báo và tỷ trọng mục tiêu | Sau close(t), có ngày quyết định riêng |
| Thực thi | Close phiên quan sát kế tiếp t+1 |
| Mức sinh lợi đầu của tỷ trọng mới | P(t+1)→P(t+2), ghi ngày kết thúc t+2 |

*Đến cuối phiên t−1: Lấy dữ liệu tạo feature ML; giữ độ trễ của thiết kế gốc*

*Sau đóng cửa phiên t: Dùng dữ liệu được phép đến t để tính covariance, chế độ thị trường và tỷ trọng mục tiêu*

*Đóng cửa phiên t+1: Mô phỏng giao dịch sang danh mục mới*

*Từ đóng cửa t+1 đến đóng cửa t+2: Danh mục mới bắt đầu có mức sinh lợi đầu tiên*

Biến động **P(t)→P(t+1)** thuộc lượng nắm giữ trước giao dịch; tỷ trọng mới chỉ hưởng **P(t+1)→P(t+2)**. Chỉ số ngày thị trường/tài sản/danh mục phải khớp; lệnh cuối mẫu không tạo lợi nhuận tương lai. Sổ thực thi lưu **311 quyết định/giao dịch**, bao gồm đầu IS, COVID, năm 2022, đầu/cuối OOS và giai đoạn căng thẳng; không ghi nhận lỗi thứ tự ngày.

**Phạm vi xác nhận:** các mốc được kiểm theo ngày định giá. createdAt của provider chưa được xác nhận là thời điểm công bố; timestamp quyết định là quy ước mô phỏng. Do đó, kiểm tra ngày không đủ chứng nhận mọi input đã biết tại decision time.

**Minh chứng:** 

06\_Pipeline\_Audit → [execution\_ledger.csv](https://drive.google.com/open?id=1Yl4ftog7tzoUQU2JRsSVF4-_jvncaemc&usp=drive_copy); 

14\_Diagnostic\_Plots → [walk\_forward\_timing.png](https://drive.google.com/open?id=1M4i9P46cv0OK-i-mk5G1XQQPB6WXHUQF&usp=drive_copy).

## **5\. Kiểm tra huấn luyện mô hình học máy (ML training audit)**

Mục tiêu giữ nguyên **lợi nhuận đơn giản 5 phiên**, y\_i=P\[i+5\]/P\[i\]−1. Lịch sử huấn luyện ngoài được cắt bảo thủ đến hàng t−6 trước khi tạo nhãn; không ghi nhận label endpoint tương lai trong nhánh mặc định. S**ai lệch nằm ở chia nội bộ 80/20, khi nhãn fitting chồng vào validation**. Bản hiệu chỉnh loại hàng có label-end ≥ feature đầu validation và fit scaler chỉ trên fitting còn lại.

Ví dụ DGC ngày **07/08/2020**: 106 hàng hợp lệ, 84 fitting ban đầu, loại 5 hàng còn **79 fitting/22 validation**. Label fitting cuối 23/06, validation bắt đầu 24/06, outcome train/validation cuối 30/07, trước quyết định 07/08 và thực thi 10/08. Hồ sơ scaler xác nhận dùng 79 hàng.

| Feature | Định nghĩa và cửa sổ dữ liệu | Kết quả kiểm tra |
| :---- | :---- | :---- |
| Momentum 5/10/20 | P(t)/P(t−n)−1 | Nhân quả, dịch về quá khứ |
| RSI14 | Trung bình trượt mức tăng/giảm, giữ quy ước trung tính đầu mẫu | Nhân quả |
| ma\_ratio\_10\_30 | EMA10/EMA30−1; tên MA không phải rolling SMA | Nhân quả; duy trì trạng thái theo lịch sử |
| Volatility20 | Độ lệch chuẩn mẫu của 20 mức sinh lợi ngày | Nhân quả |
| MACD histogram | EMA12−EMA26 trừ EMA9 signal | Nhân quả; duy trì trạng thái theo lịch sử |
| Price std20 normalized | Độ lệch chuẩn mẫu của 20 giá chia giá trung bình 20 giá | Nhân quả |

Dự báo cũ chỉ lấy 30 giá cuối, khác trạng thái EMA/MACD khi huấn luyện trên lịch sử mở rộng. Bản hiệu chỉnh dùng cùng lịch sử nhân quả, giữ lag một hàng. Vector hóa khớp công thức prefix ở cả chuỗi giả lập và ACB; thay giá tương lai không đổi feature quá khứ. Không dùng chuẩn hóa toàn mẫu, cửa sổ đặt tâm hoặc điền ngược.

Đã lưu **715 lần huấn luyện theo tài sản và 1.409 dự báo**, kèm tham số, seed, scaler, dự báo thành viên, độ lệch chuẩn và confidence. Không ghi nhận lỗi cửa sổ nhãn/validation trong kiểm tra đã thực hiện. Không thay hyperparameter hoặc chọn cấu hình theo OOS; giới hạn bằng chứng về nguồn gốc tham số được nêu tại mục 10\.

**Minh chứng:** 06\_Pipeline\_Audit → [training\_window\_audit.csv](https://drive.google.com/open?id=139jxhCz4hfABzTmFY--GDqEhQOyK1gih&usp=drive_copy);  [ml\_training\_audit.csv](https://drive.google.com/open?id=1b9kxiA43kt0C3T2k22I5C-kMXruAK7SU&usp=drive_copy); [ml\_prediction\_audit.csv](https://drive.google.com/open?id=1T4ZwzW6vC9IAaTslYGnSrrnRN7Y73baC&usp=drive_copy).

## **6\. Kiểm tra lựa chọn tài sản đại diện (Asset-selection audit)**

Thuật toán duyệt toàn bộ tổ hợp **K=5 trong 30 ứng viên**, tối thiểu hóa sum\_i min\_m(1−rho\[i,m\]). Tương quan dùng lịch sử mở rộng đến không muộn hơn t−1; covariance danh mục dùng 20 phiên. Tương quan không xác định được đặt bằng 0, xử lý đồng hạng theo thứ tự ứng viên cố định.

Đã lưu **78 lần lựa chọn**, gồm ứng viên, đầu/cuối lịch sử, ma trận khoảng cách, tập chọn và giá trị mục tiêu. Lần đầu **11/02/2020** chọn **GVR/MBB/SAB/TPB/VIC**, mục tiêu **6,583373529**; lần cuối **10/04/2026** chọn **MBB/PLX/SAB/VHM/VJC**, mục tiêu **10,188801798**. Kiểm tra độc lập xác nhận các nghiệm tối ưu toàn cục và hai lượt chạy chọn cùng tập.

Tên phù hợp là **correlation-structure-based representative asset selection** hoặc **medoid-like correlation coverage selection**; triển khai chưa phải clustering/PAM. Kết quả xác nhận thuật toán nhân quả theo input định ngày và tái lập, chưa chứng minh ưu thế so với Full VN30/Random K/Simple selection. Đối chiếu đó thuộc Step 2\.

**Minh chứng:** 06\_Pipeline\_Audit → [selection\_history.csv](https://drive.google.com/open?id=1RmNraV9li2ZWMlLATLx8pYxX-adjZJF6&usp=drive_copy). Ma trận .npz được lưu trong thư mục  [selection\_matrices](https://drive.google.com/open?id=1BQbRj8SMqBdtOxSwz5J-J2IiRvmHDR-f&usp=drive_copy)

## **7\. Kiểm tra mô hình Black–Litterman (BL audit)**

Hồ sơ mỗi lần xây dựng BL gồm covariance, tỷ trọng cân bằng, delta/tau, pi, P/Q, confidence, Omega, hậu nghiệm và tỷ trọng mục tiêu. Prior dùng **tỷ trọng đều trong tập hoạt động**, chưa phải tỷ trọng vốn hóa được xác minh. Mu/Q là kỳ vọng lợi nhuận ngày; covariance có đơn vị bình phương lợi nhuận ngày.

pi \= delta × Sigma × w\_eq  
Omega \= diag(diag(P × tau × Sigma × Pᵀ) / clipped\_confidence)  
mu\_BL \= pi \+ tau × Sigma × Pᵀ × solve(P × tau × Sigma × Pᵀ \+ Omega, Q − P × pi)

**294 hậu nghiệm thực tế** khớp phép tính độc lập, sai lệch tối đa **3,04e−18**. Hồ sơ gồm **311 trạng thái quyết định**, với **17 trường hợp không có view** dùng trung bình lợi nhuận mẫu và tối ưu có ràng buộc theo thiết kế cũ. Nhánh này không phải đối chứng BL-prior/no-ML. Omega tỷ lệ tau nên tau phần lớn triệt tiêu trong hậu nghiệm, ngoại trừ ảnh hưởng ngưỡng số học; chưa có cơ sở quy lợi ích riêng cho tau.

**Minh chứng:** 06\_Pipeline\_Audit → [corrected](https://drive.google.com/open?id=1bU6RjSDmDaiYK5E06i_daCn1Z-92qTds&usp=drive_copy)

## **8\. Kiểm tra cơ chế danh mục (Portfolio mechanics)**

**Lượng nắm giữ và NAV.** Phiên bản gốc dùng cùng tỷ trọng để tính lợi nhuận hằng ngày giữa lịch rebalance, tương đương tái cân bằng ngầm. Bản hiệu chỉnh giữ **số đơn vị tài sản**; tỷ trọng trôi theo w×(1+r)/(1+rp), giao dịch tại close phiên kế tiếp. OOS giữ mô hình/lượng nắm giữ/lệnh chờ từ IS, không cấp vốn ban đầu lần hai. Mô phỏng độc lập từ tiền mặt khớp NAV với sai lệch lớn nhất **1,42e−13** và turnover **5,00e−16**.

**Ràng buộc.** Kiểm tra sau bộ giải, làm sạch và kết hợp nhánh, với ngưỡng **1e−8**. Cả **1.244 vector giao dịch \= 311 lần × 4 chiến lược** không có vi phạm vượt ngưỡng; sai lệch lớn nhất **1,18e−10**. Loại vị thế dưới 1% chỉ được giữ khi còn khả thi; nếu cần sử dụng phép chiếu có giới hạn hoặc giữ tỷ trọng khả thi chưa loại. Cấu hình vô nghiệm phải báo lỗi.

| Ràng buộc tại mục tiêu/giao dịch | Phạm vi áp dụng |
| :---- | :---- |
| Tổng tỷ trọng bằng 1, long-only, mỗi vị thế ≤0,50 | EW, MVO, BL, Hybrid |
| Nhóm không phòng thủ ≤0,70; VFF tối thiểu danh nghĩa 0,15 | BL |
| VFF tối thiểu hiệu dụng 0,30 | GOLD cũng thuộc nhóm không phòng thủ theo code, nên chỉ VFF thuộc nhóm phòng thủ |

Hybrid kết hợp MVO toàn bộ 32 tài sản với BL hoạt động, không kế thừa giới hạn nhóm BL. Giới hạn được kiểm tại giao dịch; tỷ trọng có thể trôi vượt cap giữa các lần giao dịch.

**Turnover và chỉ số.** Turnover=0,5×sum\|w\_target−w\_pretrade\|; dùng tỷ trọng trôi trước giao dịch, loại phân bổ vốn ban đầu khỏi quy đổi năm. OOS có **128 giao dịch/chiến lược**, tính sau mốc 29/09/2023. 

Turnover/năm \= tổng turnover ×252/n\_returns.

Lợi nhuận năm là (NAV\_end/NAV\_start)^(252/n\_returns)−1; 

Biến động năm \= độ lệch chuẩn mẫu return NAV ngày ×√252. 

Sharpe dùng lợi nhuận vượt lãi suất phi rủi ro ngày, với **6%/năm** quy đổi lãi kép. 

MDD đo sụt giảm từ đỉnh. 

**Chi phí vẫn bằng 0**.

**Minh chứng:** 

09\_Reproducibility → [final\_run\_review.md](https://drive.google.com/open?id=1oJ3fuDcJHOtKSH-46ZLC4xxS_CTG4Ivb&usp=drive_copy); 

06\_Pipeline\_Audit → [constraint\_violations.csv](https://drive.google.com/open?id=1B8ch34QvrmW5nzAPWVOpF4yiLMV2o1Qg&usp=drive_copy); 

14\_Diagnostic\_Plots → [constraint\_diagnostics.png](https://drive.google.com/open?id=1pLMffQEVCxuJ267unf2bRU-yNaIsTHXK&usp=drive_copy); [turnover\_history.png](https://drive.google.com/open?id=1MX_3Hof932sfl3GEtqttMZNLeRvrd04m&usp=drive_copy)

## **9\. Nguồn gốc lựa chọn tham số (Parameter provenance)**

Bảng nguồn gốc có **135 mục**, bao gồm K, cửa sổ dữ liệu, số mô hình và hyperparameter XGBoost, horizon, lịch **rebalance/retrain/reselect 5/10/20**, tau/delta, mức phạt rủi ro, confidence, ngưỡng loại vị thế, cap, regime và alpha. Bảng phân biệt giá trị thực thi với bằng chứng chọn trên IS/cố định trước OOS.

Thiết lập chính được giữ nguyên: **K=5**, tổ hợp **5 mô hình**, horizon **5 phiên**, covariance **20 phiên**, **tau=0,05**, **delta=2,5** và alpha Hybrid **0,6/0,3/0,1** cho normal/stress/crisis. Các giới hạn tỷ trọng được nêu tại mục 8; toàn bộ hyperparameter và ánh xạ confidence nằm trong bảng nguồn gốc và cấu hình thực thi.

Step 1 giữ nguyên tham số và không chọn cấu hình dựa trên OOS. Thiếu hồ sơ chưa chứng minh đã xảy ra tối ưu hậu nghiệm, nhưng cũng chưa đủ xác nhận phát biểu “đã cố định trước OOS” trong bài báo.

**Minh chứng:** 08\_Design\_Provenance →[parameter\_provenance.csv](https://drive.google.com/open?id=1rbchDdaIEfBRoxuqNSvMTNdvOXSP8-5o&usp=drive_copy)

## **10\. Các hiệu chỉnh và kết quả kiểm tra (Corrections)**

Các sửa đổi nằm trong thư mục mới, giữ mã nguồn nghiên cứu gốc riêng. Nhóm hiệu chỉnh chính là **dữ liệu VFF/GOLD và lịch phiên; nhãn/scaler/feature ML; thực thi phiên kế tiếp; lượng nắm giữ và mốc OOS; khả thi sau làm sạch; hồ sơ và turnover**. Nhật ký thay đổi ghi hành vi trước/sau, lý do và ảnh hưởng. Không đổi K, mô hình, công thức confidence, regime hoặc tham số để cải thiện OOS.

**Kết quả kiểm tra nền 04/10: 27 kiểm thử, 52 kiểm tra độc lập và 40 kiểm tra tái lập đạt. Kiểm tra và hai lượt chạy mới ngày 12/10 được trình bày ở mục 13; đó là baseline đang dùng cho Step 2\.**

Mỗi lượt lưu manifest, cấu hình thực thi, seed, môi trường, input hashes, bản chụp mã nguồn, ma trận giá, hồ sơ fit/dự báo, ma trận lựa chọn và BL. Metadata JSON có XGBoost missing=NaN, là giới hạn với parser JSON nghiêm ngặt.

**Những hiệu chỉnh đã áp dụng gồm:**

| Nhóm | Đã hiệu chỉnh những gì? |
| :---- | :---- |
| Dữ liệu VFF | Baseline dùng nguồn NAV đã xác minh là VFF, thay cho chuỗi bị gán nhãn VFF nhưng chưa xác định đúng danh tính. Sửa này áp dụng cho dữ liệu chạy baseline; crawler gốc chưa được sửa. |
| Dữ liệu GOLD | Dùng một snapshot gold\_full.csv thống nhất cho toàn mẫu và chia IS/OOS từ đó, thay cho việc dùng các nguồn full/train/test không nhất quán. |
| Lịch phiên và dữ liệu thiếu | Dùng các ngày quan sát của VNINDEX; chỉ chuyển tiếp giá đã có trong quá khứ, không điền ngược bằng giá tương lai. |
| Huấn luyện và dự báo ML  (mục 5\) | Loại các mẫu có nhãn chồng sang validation; fit scaler chỉ trên tập fitting; tính feature lúc dự báo nhất quán với lúc huấn luyện, đặc biệt EMA/MACD. |
| Thời điểm giao dịch (mục 4\) | Tính tỷ trọng sau đóng cửa ngày t, thực thi tại đóng cửa phiên t+1. Danh mục mới chỉ hưởng lợi nhuận từ t+1 đến t+2. |
| Lượng nắm giữ và đầu OOS  (mục 8\) | Giữ số đơn vị tài sản giữa các lần tái cân bằng, cho tỷ trọng thay đổi theo giá; tiếp nối danh mục từ IS sang OOS và không bỏ mất lợi nhuận phiên đầu OOS. |
| Ràng buộc và đo lường (mục 8\) | Kiểm tra tỷ trọng cuối sau làm sạch/kết hợp các nhánh; xử lý trường hợp vượt giới hạn; tính turnover từ tỷ trọng thực tế trước giao dịch và kiểm chứng lại NAV, các chỉ số. |

### **Danh mục tệp đính kèm**

Các tệp dưới đây được đặt cùng thư mục với Google Doc.

| Tên tệp trong thư mục nộp | Nội dung và mục đích | Mục báo cáo |
| :---- | :---- | :---- |
| [01\_Baseline\_Metrics.csv](https://drive.google.com/open?id=16w83BRhhmPi8dCHpWZdu6FLRVvXzyhBE&usp=drive_copy) | Hiệu suất IS/OOS của EW, MVO, BL+ML và Hybrid: NAV, lợi nhuận, biến động, Sharpe, drawdown và turnover. | 8, 12 |
| [02\_Baseline\_NAV.csv](https://drive.google.com/open?id=1qTFilqeb8lrmF3rGEBaLSYEU_h0MhNiB&usp=drive_copy) | Chuỗi NAV hằng ngày để đối chiếu diễn biến và số cuối kỳ. | 8, 12 |
| [03\_Baseline\_Daily\_Returns.csv](https://drive.google.com/open?id=1rROl_f6lmM0E695F1sh6dM3eB7CwSAV2&usp=drive_copy) | Lợi nhuận hằng ngày dùng tính lại các chỉ số hiệu suất. | 8, 12 |
| [04\_Baseline\_Target\_Weights.csv](https://drive.google.com/open?id=1a685iK8Us9bKvXPDF0LWn9LtZkrm72-P&usp=drive_copy) | Tỷ trọng mục tiêu tại mỗi lần tái cân bằng; không phải tỷ trọng trôi theo giá hằng ngày. | 8, 12 |
| [05\_Baseline\_Turnover.csv](https://drive.google.com/open?id=1KQ-SIQk_YatG63qPi3wVngiVnNDSs6gQ&usp=drive_copy) | Chi tiết giao dịch và turnover của từng chiến lược; kết quả chưa trừ chi phí. | 8, 12 |
| [06\_Pipeline\_Audit](https://drive.google.com/open?id=1_twBWFkTgFpRy-Jq04fXp5QlCeb8Nxf0&usp=drive_copy) | Nhật ký thời điểm thực thi, huấn luyện/dự báo ML, chọn tài sản, ma trận lựa chọn, BL và ràng buộc. CSV vi phạm chỉ có tiêu đề vì không phát hiện vi phạm ở ngưỡng 1e-8. | 4–8 |
| [07\_Data\_Audit](https://drive.google.com/open?id=1yLKiS5J5KH6Ej8SNhJ8wpSLeF1WEJ5nN&usp=drive_copy) | Danh mục nguồn dữ liệu, xác minh VFF, chẩn đoán dữ liệu và độ bao phủ; [active\_run.json](https://drive.google.com/open?id=1FJwq1y1e-uUjYjHMB2fml4ymw9SciO3k&usp=drive_copy) xác định kỳ nộp hiện tại. | 1–3 |
| [08\_Design\_Provenance](https://drive.google.com/open?id=14bDxuIBHN4yV7ckNvqHZOVLZ5-CaLNZ_&usp=drive_copy) | Nguồn gốc tập tài sản, tham số, nhật ký sửa lỗi và báo cáo chi tiết để tra cứu. Báo cáo chính cập nhật cách hiểu nhãn MVO component trong PDF. | 3, 9–11 |
| [09\_Reproducibility](https://drive.google.com/open?id=1VtlGfe1xjnA08DX_oqaPT6t3eKx1hDHn&usp=drive_copy) | Mã nguồn/config, dữ liệu và policy, hai manifest mới; 35 kiểm thử, 42 kiểm tra độc lập và 21 kiểm tra tái lập đạt. 13 CSV giống từng byte. | 1, 8, 11 |
| [10\_Comparison\_Details](https://drive.google.com/open?id=1ClnCj_fUkU54Pj2s3iaImUrIgTfajzAV&usp=drive_copy) | Bảng đối chiếu paper/logic gốc/baseline, cửa sổ OOS chung, alpha, hit rate và chuỗi NAV tái dựng lịch sử để kiểm tra các hình. | 9, 12 |
| **[11\_NAV\_Legacy\_vs\_Corrected.png](https://drive.google.com/open?id=1I0wzBsZ_Hgy35wIZwDiottXx-UEH-oUu&usp=drive_copy)** | Đường NAV logic gốc và baseline trên cùng đầu vào, cho MVO, BL+ML và Hybrid. | 12.2 |
| **[12\_NAV\_IS\_vs\_Paper.png](https://drive.google.com/open?id=1WBQdu6jMxDSbBYIltOVlMMqNti5on_Oh&usp=drive_copy)** | Đối chiếu đường NAV IS sau chuẩn hóa tại cùng mốc. | 12.4 |
| **[13\_NAV\_OOS\_vs\_Paper.png](https://drive.google.com/open?id=1fXsJIb3kemxG8uhU7NQuHVUXrbMqc9zQ&usp=drive_copy)** | Đối chiếu NAV OOS; vùng sau 27/02/2026 chỉ có baseline, không có đường paper kéo dài giả định. | 12.4 |
| [14\_Diagnostic\_Plots](https://drive.google.com/open?id=1gCqUVPX1-k0R30vdluo-A1esnV6K5Egf&usp=drive_copy) | Sơ đồ walk-forward và hình ràng buộc, turnover, NAV, drawdown; có cả PNG và PDF. | 4, 8, 11 |

**Phạm vi bộ minh chứng:** các gói chứa hồ sơ kiểm tra và cấu hình của nghiên cứu, không phải toàn bộ dự án, môi trường thực thi hoặc 631 tệp của phiên bản gốc. Đường dẫn trong manifest phản ánh nơi tạo lượt chạy; bảng ánh xạ [attachment\_source\_map.csv](https://drive.google.com/open?id=1SOvWyY9LpLIJtG1UYPs4vZBVHKwr08D0&usp=drive_copy) trong gói tái lập liên kết chúng với tệp nộp. Các tài liệu audit lịch sử được giữ nguyên và phải đọc cùng kỳ chạy ghi tại đầu báo cáo. Hai hồ sơ [training\_window\_audit.csv](https://drive.google.com/open?id=139jxhCz4hfABzTmFY--GDqEhQOyK1gih&usp=drive_copy) và [ml\_training\_audit.csv](https://drive.google.com/open?id=1b9kxiA43kt0C3T2k22I5C-kMXruAK7SU&usp=drive_copy) có nội dung giống nhau, được giữ cả hai theo tên đầu ra hướng dẫn.

**Minh chứng:** 09\_Reproducibility →[manifest.json](https://drive.google.com/open?id=1pDtzfc5jMAP7Mb8kCM2cQSjhZUyKC-1M&usp=drive_copy)

[01\_Baseline\_Metrics.csv](https://drive.google.com/open?id=16w83BRhhmPi8dCHpWZdu6FLRVvXzyhBE&usp=drive_copy);

08\_Design\_Provenance → [change\_log.md](https://drive.google.com/open?id=1Ai1ZihI5TLWPbXGqzrhqVt0GRUItztAC&usp=drive_copy)

09\_Reproducibility → [final\_trusted\_tests.log](https://drive.google.com/open?id=1NiPprnpkmNtoSzVbIM9Kb6S_SNk9b31T&usp=drive_copy)

09\_Reproducibility → [reproducibility\_verification.json](https://drive.google.com/open?id=1vXhiOp3sf5oAWGiz6OYq7Ehko772grym&usp=drive_copy)

08\_Design\_Provenance → [reference\_full\_report.md](https://drive.google.com/open?id=1PKNYXr_QqUFZsRfgPkpZS-D3wmlUQGHc&usp=drive_copy)

giữ các ví dụ, lịch sử đối chiếu và chi tiết kỹ thuật để tra cứu khi cần. Báo cáo hiện tại giữ các kết quả chính; các tệp kiểm chứng vẫn được bảo toàn.

## **12\. Ảnh hưởng đến kết luận thực nghiệm (Impact on empirical conclusions)**

### **12.1. Kết quả lần chạy 04/10 (đối chứng)**

**IS:** NAV từ 11/02/2020 đến 29/09/2023, 911 mức sinh lợi.

| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| EW | 1.9308 | 19.96% | 23.31% | 0.648 | \-37.47% | 0.737 |
| MVO | 4.3186 | 49.88% | 34.67% | 1.174 | \-42.13% | 24.328 |
| BL+ML | 1.7778 | 17.25% | 13.70% | 0.805 | \-18.99% | 9.403 |
| HYBRID | 3.0363 | 35.97% | 22.47% | 1.222 | \-30.53% | 17.197 |

**OOS:** NAV chuẩn hóa tại 29/09/2023, 641 mức sinh lợi đến 29/04/2026, chi phí bằng 0\.

| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| EW | 1.7149 | 23.62% | 18.22% | 0.936 | \-17.15% | 0.623 |
| MVO | 3.2031 | 58.04% | 32.84% | 1.381 | \-26.86% | 23.822 |
| BL+ML | 1.9479 | 29.97% | 13.04% | 1.629 | \-9.64% | 8.630 |
| HYBRID | 2.7521 | 48.88% | 22.11% | 1.648 | \-18.08% | 16.868 |

BL+ML có biến động **13,04%** và MDD **−9,64%**, thấp hơn MVO **32,84%/−26,86%**, với NAV thấp hơn. Hybrid tăng lợi nhuận so với BL+ML nhưng tăng biến động/drawdown. Chênh Sharpe **1,648−1,629=0,019** chưa được kiểm định. Turnover cao, đặc biệt MVO **23,822** và Hybrid **16,868** vòng NAV/năm, cần đánh giá chi phí ở Step 8\. Pattern giảm rủi ro của BL còn hiện diện trong phạm vi giả định dữ liệu; chưa xác định giá trị riêng của XGBoost.

### **12.2. Đối chiếu số công bố và logic gốc**

| Kỳ | Chiến lược | NAV (paper) | NAV mới | Sharpe (paper) | Sharpe mới | MDD (paper) | MDD mới |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| IS | EW | 1.90 | 1.9308 | 0.60 | 0.648 | \-37.7% | \-37.47% |
| IS | MVO | 4.79 | 4.3186 | 1.19 | 1.174 | \-38.7% | \-42.13% |
| IS | BL+ML | 2.09 | 1.7778 | 0.96 | 0.805 | \-14.8% | \-18.99% |
| IS | HYBRID | 3.80 | 3.0363 | 1.36 | 1.222 | \-24.9% | \-30.53% |
| OOS | EW | 1.82 | 1.7149 | 1.15 | 0.936 | \-17.3% | \-17.15% |
| OOS | MVO | 3.73 | 3.2031 | 1.64 | 1.381 | \-15.0% | \-26.86% |
| OOS | BL+ML | 1.90 | 1.9479 | 1.71 | 1.629 | \-7.1% | \-9.64% |
| OOS | HYBRID | 2.86 | 2.7521 | 1.83 | 1.648 | \-11.4% | \-18.08% |

Các số công bố khác baseline mới về snapshot, lịch phiên, thực thi/huấn luyện và kỳ thực tế của log; không quy chênh lệch cho riêng ML hoặc một sửa lỗi. Đối chiếu bổ sung dưới đây cố định **cùng ma trận chuẩn hóa, thứ tự tài sản, môi trường, tham số và kỳ tháng 4**, chỉ thay logic gốc/hiệu chỉnh:

| Kỳ | Chiến lược | NAV gốc | NAV hiệu chỉnh | Sharpe gốc | Sharpe hiệu chỉnh |
| :---- | :---- | :---- | :---- | :---- | :---- |
| IS | EW | 1.9253 | 1.9308 | 0.644 | 0.648 |
| IS | MVO | 6.0647 | 4.3186 | 1.445 | 1.174 |
| IS | BL+ML | 1.8892 | 1.7778 | 0.925 | 0.805 |
| IS | HYBRID | 3.5173 | 3.0363 | 1.401 | 1.222 |
| OOS | EW | 1.7055 | 1.7149 | 0.924 | 0.936 |
| OOS | MVO | 2.2401 | 3.2031 | 0.952 | 1.381 |
| OOS | BL+ML | 1.9933 | 1.9479 | 1.763 | 1.629 |
| OOS | HYBRID | 2.2780 | 2.7521 | 1.319 | 1.648 |

Phiên bản gốc có 640 mức sinh lợi OOS, bản hiệu chỉnh 641 do mốc chuẩn hóa. Đối chiếu cùng 640 mức sinh lợi, neo tại 02/10/2023, cho NAV hiệu chỉnh EW/MVO/BL+ML/Hybrid **1,7126/3,2245/1,9458/2,7620**. Logic gốc có **112 vector vượt cap tại 1e−8**, mức vượt lớn nhất **0,00722417**; bản hiệu chỉnh không có vi phạm vượt ngưỡng. Các sửa lỗi vẫn cùng tác động, nên đây chưa phải ablation từng thành phần.

![][image1]

### **12.3. Độ nhạy alpha và tỷ lệ dự báo đúng hướng**

| alpha\_normal | NAV (paper) | NAV mới | Sharpe (paper) | Sharpe mới | MDD mới |
| :---- | :---- | :---- | :---- | :---- | :---- |
| 0.2 | 2.23 | 2.2260 | 1.98 | 1.812 | \-11.56% |
| 0.4 | 2.53 | 2.4875 | 1.94 | 1.761 | \-14.53% |
| 0.6 | 2.86 | 2.7521 | 1.83 | 1.648 | \-18.08% |
| 0.8 | 3.20 | 3.0278 | 1.72 | 1.544 | \-21.86% |
| 1.0 | 3.57 | 3.3184 | 1.64 | 1.467 | \-25.20% |

Giữ alpha\_stress=0,3 và alpha\_crisis=0,1; tái tính số đơn vị tài sản từ hai nhánh MVO/BL đã fit và regime dựa trên giá, không fit riêng hoặc chọn alpha theo OOS. Alpha\_normal=0,6 khớp NAV thực tế với sai lệch **2,18e−14**. Sharpe alpha\_normal=0,2 đạt **1,812**, cao hơn Hybrid mặc định **1,648**; “cao nhất” chỉ áp dụng trong bốn cấu hình mặc định, không toàn grid.

OOS dự báo thô đạt **324/635 \= 51,02%** (640 phát ra, 5 chưa đủ outcome); ML views sau chuyển đổi/ngưỡng đạt **175/347 \= 50,43%** (351 phát ra, 4 chưa đủ outcome). Tất cả endpoint được chấm nằm trong mẫu tháng 4; các tập quan sát khác **174/335 \= 51,9%** của bài báo.

| Tài sản | Views đúng/tổng đủ outcome | Tỷ lệ đúng hướng |
| :---- | :---- | :---- |
| Overall | 175/347 | 50.43% |
| MBB | 72/124 | 58.06% |
| PLX | 29/69 | 42.03% |
| SAB | 25/58 | 43.10% |
| VHM | 22/49 | 44.90% |
| VJC | 27/47 | 57.45% |

Phân nhóm dự báo theo ngày phát; IS đạt **376/769** nhưng gồm 5 dự báo thô/4 views phát 28/09, có outcome đến 04/10. Các outcome được chấm hồi cứu, không dùng để fit/tune trước chia mẫu. Hit rate chưa chứng minh đóng góp kinh tế của ML; no-ML/fixed-confidence là thí nghiệm tiếp theo.

### **12.4. So sánh đường NAV và điểm cần sửa trong bài báo**

Đường bài báo được tái dựng từ quyết định lịch sử, không phải fit lại mô hình gốc. Để so hình dạng, cả hai đường neo NAV=1 tại **11/02/2020 trong IS** và **02/10/2023 trong OOS**. Vì mốc chuẩn hóa khác bảng hiệu suất gốc, số cuối đường có thể khác bảng. OOS lịch sử chỉ đến **27/02/2026**; nền xám đến 29/04 chỉ có đường mới.

![][image2]

![][image3]

EW gần như trùng đường lịch sử. Trong OOS chung, MVO có NAV cuối gần bằng bài báo nhưng từng lệch **15,81%** trong kỳ; BL+ML/Hybrid có tương quan return **0,933/0,911** và NAV cuối khoảng chung cao hơn **6,68%/5,04%**. Trong IS, MVO từng lệch **45,54%** dù chênh cuối khoảng chung chỉ **−1,89%**. Các pattern tăng/giảm lớn tương đồng nhưng đường tích lũy chưa được tái tạo chính xác. Tương quan được tính trên return giữa các mốc chung, không phải kiểm định ý nghĩa thống kê hay tác động riêng một thành phần.

Bài báo cần đồng bộ **kỳ dữ liệu**; **Sharpe** (công thức năm hình học không tái tạo bảng, MVO cho khoảng 1,994 thay vì 1,64); **view transformation** (Eq 5 tuyến tính, code dùng tanh theo biến động); **penalty rủi ro** (Eq 9 lambda/2, code dùng trực tiếp hệ số 1,5/default và 5,0/crisis, tương ứng lambda 3/default và 10/crisis); và **alpha\_normal=1 vẫn blend ngoài normal** như mục 9\.

**Minh chứng kết quả bổ sung:** 

10\_Comparison\_Details → [paper\_vs\_corrected\_metrics.csv](https://drive.google.com/open?id=1fOwf7v-gQBV1awIWgPwyF1BAVIE9nCNe&usp=drive_copy); 

10\_Comparison\_Details → [legacy\_vs\_corrected\_metrics.csv](https://drive.google.com/open?id=1JvCDXDhzh2BIswQOW44Sg9zlkJVjLd-Y&usp=drive_copy);

10\_Comparison\_Details → [common\_oos\_window\_comparison.csv](https://drive.google.com/open?id=1tTwgw18kDa5-oAPdpoQzQ3p88AgZeHWJ&usp=drive_copy)

10\_Comparison\_Details → [alpha\_grid\_method.json](https://drive.google.com/open?id=1kpzVch00gB-PJ4MfRKSNyX39Sjh3lrRI&usp=drive_copy)

10\_Comparison\_Details →[corrected\_hitrate\_summary.csv](https://drive.google.com/open?id=1PNQR8RZ833JO_7oAmYx6HrJaiUfneRbB&usp=drive_copy)

10\_Comparison\_Details →[trajectory\_comparison.csv](https://drive.google.com/open?id=12nQP0rtpyzn7-A_EiYoCCo4bl97Ow1Qs&usp=drive_copy)

## **13\. Hoàn tất bốn vấn đề trước Step 2**

**Trạng thái: READY FOR STEP 2 trong phạm vi thí nghiệm dùng dữ liệu định giá đại diện và quy ước khả dụng đã khai báo.** Người nghiên cứu đã chọn tiếp tục các phương án C1–C4; không còn bước chờ thống nhất với giảng viên. Trạng thái này không xác nhận dữ liệu point-in-time lịch sử, total return hoặc khả năng thực thi giao dịch thực tế. Đây là lựa chọn phạm vi nghiên cứu được công khai, kèm sửa dữ liệu, tách thông tin/định giá và chạy lại toàn bộ pipeline.

### **13.1. Quyết định đã áp dụng và chứng cứ**

| Mã | Đã thực hiện | Giới hạn còn phải công khai |
| ----- | ----- | ----- |
| C1 — Thời điểm thông tin VFF/GOLD | Chốt quyết định 18:00, giờ Việt Nam. Mỗi quan sát có ngày định giá và thời điểm được phép dùng. VFF chỉ vào thông tin sau 5 phiên VNINDEX quan sát, hoặc timestamp tạo bản ghi nếu muộn hơn; GOLD close ngày D chỉ đủ điều kiện từ ngày D+1. Mô hình chỉ nhận thông tin đã đủ điều kiện; NAV dùng chuỗi định giá riêng. | Năm phiên và độ trễ GOLD là giả định mô phỏng đặt trước khi chạy, không phải ngày công bố đầu tiên đã được xác minh. Kho NAV chính thức chưa truy xuất đủ kỳ; dữ liệu sửa đổi lịch sử chưa được chứng nhận. |
| C2 — GOLD đủ kỳ | Thay snapshot chưa đối chiếu được bằng một chuỗi lưu trữ SJC bán ra tại TPHCM của GiaVang.tv. Đã tải đủ 77 trang tháng, 2.343 ngày lịch 12/2019–04/2026; lưu giá mua/bán và cờ carry của nhà cung cấp. Không ghép các quote PNJ tải được rời rạc, không điền qua lỗi HTTP. | Đây là archive thứ cấp ghi nguồn SJC/GiaVang.org; giá hiển thị có độ phân giải khoảng 100.000 VND/lượng, không có giờ intraday. Định giá theo giá bán, chưa mô phỏng spread hoặc khớp lệnh vàng. |
| C3 — Lợi nhuận cổ phiếu | Dùng snapshot KBS đã tải và kiểm tra 30 mã, giữ giá trị nguồn/1.000, bỏ bước làm tròn thêm. Định nghĩa lợi nhuận là tỷ lệ giá đóng cửa điều chỉnh do provider cung cấp; không cộng cổ tức tiền mặt lần nữa. VFF cũng giữ NAV nguồn chưa làm tròn. | Không gọi là total return đã được xác minh. Công thức factor, ledger toàn bộ corporate actions và vintage điều chỉnh lịch sử chưa có. |
| C4 — Tái lập và chuyển bước | Lượt lịch sử IS/OOS dùng source/data commit 71cc107 được huấn luyện mới, không cache; metrics, tỷ trọng và views khớp chính xác log gốc. Baseline theo kỳ tháng 4 được chạy mới hai lần và kiểm tra độc lập trước khi đóng băng. | Hồ sơ lịch sử chỉ kết thúc 27/02/2026, không chứng minh paper có lượt gốc đến tháng 4\. Môi trường gốc chưa tìm thấy; năm lượt alpha gốc chưa fit lại riêng. |

Kho GOLD: [GiaVang.tv — lịch sử giá](https://giavang.tv/lich-su?range=all). Nguồn giá điều chỉnh: [tài liệu Vnstock](https://vnstocks.com/docs/vnstock/tham-khao/data-sources). Các bản cáo bạch VFF đã lưu ghi cutoff nhận lệnh 14:40 ngày T−1 và lịch giao dịch theo phiên quỹ; mô phỏng close phiên kế tiếp vẫn là quy ước định giá, không thay thế lịch nhận lệnh thật.

### **13.2. Kiểm chứng trước khi chuyển bước**

| Kiểm tra | Kết quả |
| ----- | ----- |
| Dữ liệu/availability | 1.568 phiên × 32 tài sản; 50.176 dòng lineage đều thỏa thời điểm quan sát ≤ availability giả định ≤ cutoff quyết định. Không điền ngược. |
| Kiểm thử | 35/35 đạt, gồm kiểm tra biên giờ, quan sát chưa khả dụng, cập nhật đến muộn và tách thông tin khỏi định giá P\&L. |
| Kiểm tra độc lập | 42/42 đạt: tái tính NAV từ lượng nắm giữ, return, turnover, chỉ số hiệu suất, scaler/nhãn, lựa chọn tài sản và hậu nghiệm BL. 310 bản ghi thực thi, 715 lượt huấn luyện, 1.404 dự báo, 78 lần lựa chọn. |
| Chạy lặp mới | 21/21 kiểm tra đạt; 13 CSV giống từng byte, hồ sơ fit/dự báo và views giống hoàn toàn; cả hai lượt fit mới, không cache. |
| Bảo toàn và đóng băng | 33 đầu vào lượt 04/10 không đổi; lưu source/config/seed/input hashes/môi trường cho hai lượt mới. Không tối ưu tham số theo OOS. |
| MVO/alpha | Giữ giải thích đã xác minh: alpha\_normal=1 vẫn blend trong stress/crisis; MVO thuần chỉ tương ứng alpha=1 ở mọi regime. Không còn bất nhất này làm blocker. |

### **Kết quả baseline mới**

**Baseline đang dùng cho Step 2:** lượt mới ngày 12/10/2026, theo quy ước availability ở mục 13\. Giá dùng ra quyết định tách khỏi giá dùng định giá danh mục. Ma trận chung 1.568 phiên × 32 tài sản từ 14/01/2020; sau khởi tạo, IS từ 18/02/2020 đến 29/09/2023 có 906 mức sinh lợi; OOS có 641 mức sinh lợi đến 29/04/2026, neo NAV=1 tại 29/09/2023. Chi phí bằng 0\.

**IS**

| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| EW | 1.9287 | 20.05% | 23.34% | 0.651 | \-37.44% | 0.739 |
| MVO | 4.1511 | 48.57% | 34.79% | 1.146 | \-41.05% | 24.521 |
| BL+ML | 1.6295 | 14.55% | 14.20% | 0.617 | \-18.70% | 9.551 |
| HYBRID | 3.0507 | 36.37% | 22.33% | 1.241 | \-30.49% | 17.104 |

**OOS**

| Chiến lược | NAV cuối | Lợi nhuận năm | Biến động năm | Sharpe | MDD | Turnover/năm |
| ----- | ----- | ----- | ----- | ----- | ----- | ----- |
| EW | 1.7278 | 23.98% | 18.37% | 0.946 | \-17.08% | 0.628 |
| MVO | 3.3904 | 61.61% | 33.08% | 1.441 | \-30.18% | 23.363 |
| BL+ML | 1.8136 | 26.37% | 13.33% | 1.385 | \-9.51% | 8.200 |
| HYBRID | 2.7044 | 47.86% | 21.38% | 1.665 | \-16.13% | 16.613 |

BL+ML có biến động 13,33% và MDD −9,51%, thấp hơn MVO 33,08%/−30,18%, nhưng NAV cũng thấp hơn. Hybrid có Sharpe 1,665 và MDD −16,13%; chênh Sharpe với BL là 0,280, chưa được kiểm định. Turnover MVO/Hybrid còn cao (23,363/16,613 vòng NAV/năm). Các kết quả chưa xác định đóng góp riêng của ML; không quy sự thay đổi từ lượt 04/10 cho một hiệu chỉnh riêng lẻ.

### **13.3. So sánh đường NAV sau lần chạy mới**

Các đường dưới đây lấy từ CSV xuất, neo tại quan sát chung đầu tiên của từng kỳ. Đường paper đến 27/02/2026; phần nền xám chỉ có các baseline tháng 4, không kéo dài đường paper. Lượt 04/10 được giữ làm đối chứng; thay nguồn, độ chính xác giá và quy ước thông tin cùng lúc nên không gọi đây là ablation một yếu tố.

![][image4]

![][image5]

Trong OOS chung 03/10/2023–27/02/2026, tương quan return với đường paper của EW/MVO/BL/Hybrid là 0,994/0,889/0,642/0,853. EW gần trùng; BL khác đáng kể về đường đi. Các khoảng so sánh được neo tại cùng ngày, khác mốc bảng hiệu suất. Số đo tương quan được lưu trong 17\_Readiness\_Evidence.zip/trajectory\_comparison.csv; đây là so sánh mô tả, không phải kiểm định đóng góp kinh tế của ML. Mục 12.2–12.4 và các hình 11–13 giữ kết quả kiểm tra 04/10 để tra cứu, không phải số liệu của baseline mới.

### **13.4. Bộ tệp nộp và baseline cho Step 2**

| Tệp/thư mục | Nội dung và cách dùng |
| ----- | ----- |
| 01\_Baseline\_Metrics.csv đến 05\_Baseline\_Turnover.csv | Kết quả baseline mới 12/10; khớp hai bảng IS/OOS ở mục 13\. |
| 06\_Pipeline\_Audit.zip, 09\_Reproducibility.zip | Audit, source/config/môi trường, đầu vào, hai manifest và kết quả kiểm tra/chạy lặp của lượt mới. |
| 07\_Data\_Audit.zip, 08\_Design\_Provenance.zip, 10\_Comparison\_Details.zip, hình 11–13, 14\_Diagnostic\_Plots.zip | Hồ sơ kiểm tra nền và so sánh 04/10 được giữ làm đối chứng, không thay cho baseline mới. |
| 15\_Blocker\_Evidence\_20261012.zip | Chứng cứ gốc cho VFF, PNJ, KBS, bản cáo bạch và tái lập lịch sử; giữ nguyên để tra nguồn. |
| 16\_Decisions\_Applied.md | Ghi quyết định C1–C4 đã áp dụng và giới hạn nghiên cứu; thay tệp yêu cầu xác nhận trước đây. |
| 17\_Readiness\_Evidence.zip | Policy availability, lineage, dữ liệu nguồn GOLD, kiểm tra coverage, trạng thái readiness và số đo đường NAV. |
| 18\_NAV\_IS\_New\_vs\_Reference.png, 19\_NAV\_OOS\_New\_vs\_Reference.png | Hình so sánh cập nhật cho lần chạy mới. |

Baseline dùng tiếp là availability-observed-contract-20261012T233110; mã nguồn trong readiness\_20261012/candidate\_workspace/, không lấy CSV tháng 7 ở thư mục gốc. Step 2 sẽ so sánh full VN30, random K=5, benchmark đơn giản K=5 và phương pháp chọn đại diện đề xuất, giữ mô hình danh mục phía sau và policy dữ liệu cố định. Universe point-in-time/chi phí/ML ablation xử lý ở bước tương ứng; không kết luận giá trị riêng của ML ở Step 1\.

**Kết luận:** đủ điều kiện bắt đầu Step 2 theo giao thức thí nghiệm định giá đã khai báo và được đóng băng. Chứng nhận khả dụng lịch sử thực tế và thực thi quỹ thực tế vẫn chưa đạt; đây là giới hạn của diễn giải kết quả, không được viết thành đã xác minh hoàn toàn.

READY FOR STEP 2