# Báo cáo Step 2 về bằng chứng thực nghiệm cho xây dựng danh mục

Ngày thực hiện 23/10/2026. Báo cáo tiếp nối Step 1 đã cập nhật ngày 12/10/2026, theo hai tệp guide_1.md và project_1.md. Tên nội bộ của hai tệp vẫn ghi guide_0 và project_0; cụm “NEW STEP 1” trong đó là gói thí nghiệm tiếp theo, được gọi Step 2 ở đây để phân biệt với đợt kiểm toán đã hoàn tất.

## 1 Phạm vi và kết luận chính

Đã thực hiện đủ thí nghiệm A về lựa chọn tài sản, B về so sánh ước lượng lợi nhuận trên cùng tập đầu tư, độ nhạy chi phí và bootstrap ghép cặp. Kết quả ủng hộ giá trị của lựa chọn đại diện về độ phủ tương quan và độ ổn định; bằng chứng về ưu thế hiệu suất còn hỗn hợp. Prior BL cho phân bổ ít tập trung và turnover thấp hơn MVO matched. ML cải thiện các chỉ số gross OOS trong cửa sổ này, nhưng lợi ích suy giảm khi tính chi phí. Tất cả khoảng tin cậy 95% của chênh lệch CAGR và Sharpe đều chứa 0, nên chưa đủ bằng chứng kết luận ưu thế thống kê.

Baseline tiếp tục là `availability-observed-contract-20261012T233110`. Dữ liệu gồm 1.568 phiên × 32 tài sản, từ 14/01/2020 đến 29/04/2026. IS có 906 return sau khởi tạo ngày 18/02/2020. OOS neo NAV tại 29/09/2023, gồm 641 return từ 02/10/2023 đến 29/04/2026. Không tải dữ liệu mới, đổi K, thay mô hình ML hoặc chọn tham số theo kết quả OOS.

Các mục 2–11 và nhiều số đếm trong báo cáo Step 1 thuộc kiểm toán 04/10; mục 13 cùng manifest 12/10 xác định baseline hiện hành. Ví dụ, baseline hiện hành có 310 sự kiện giao dịch, 293 lần có views và 17 lần không views, 78 lần chọn tập. Không chuyển số hit rate cũ hoặc ngày lựa chọn cũ thành kết quả mới.

## 2 Đóng băng và tái lập baseline

Đã đối chiếu hash dữ liệu và mã số học với snapshot lượt gốc, kiểm tra CSV giữa hai lượt huấn luyện mới đã lưu của Step 1 và tái tính độc lập NAV từ tỷ trọng quyết định. NAV, chỉ số IS/OOS và turnover khớp ở ngưỡng kiểm tra 1e-9 cho chỉ số và 1e-10 cho đường NAV. Đây là replay quyết định đã lưu, không phải lượt huấn luyện ML mới trong sprint này.

| Legacy unmatched | NAV OOS | Sharpe | MDD % | TO năm |
|---|---|---|---|---|
| EW | 1.7278 | 0.946 | -17.08 | 0.628 |
| MVO | 3.3904 | 1.441 | -30.18 | 23.363 |
| BL | 1.8136 | 1.385 | -9.51 | 8.200 |
| HYBRID | 2.7044 | 1.665 | -16.13 | 16.613 |

Bảng baseline là đối chứng mô tả: EW/MVO dùng 32 tài sản, BL thường dùng 7 tài sản, Hybrid kết hợp hai tập khác nhau. Không dùng bảng này để quy đóng góp riêng cho BL, ML hoặc Hybrid.

Quy ước thông tin giữ nguyên: quyết định sau 18:00 giờ Việt Nam; VFF có độ trễ tối thiểu năm phiên quan sát hoặc metadata muộn hơn; GOLD ngày D chỉ vào thông tin từ D+1. Bảng thông tin dùng ra quyết định tách khỏi bảng giá dùng định giá. Toàn bộ 50.176 dòng lineage được đối chiếu với cutoff và tái dựng lại bảng thông tin. Đây là kiểm tra thực thi giả định availability, không xác nhận ngày công bố lịch sử thực tế.

## 3 Thiết kế thí nghiệm và ràng buộc chung

A gồm Full 30, Simple K5, Proposed K5 và 10 lượt Random K5 với seed 7, 11, 19, 23, 31, 43, 59, 71, 83, 97. Tất cả cộng GOLD và VFF, chọn lại mỗi 20 phiên và rebalance mỗi 5 phiên. Simple chọn năm cổ phiếu có biến động thấp nhất trong 20 return quá khứ, kết thúc t−1; đồng hạng theo ticker. Ở sự kiện đầu IS chỉ có 19 return quá khứ, dùng số quan sát sẵn có chung, không điền ngược; các sự kiện sau đủ 20. Mỗi seed tạo một chuỗi chọn mới tại từng sự kiện, không chọn seed thắng sau khi xem OOS.

Proposed dùng đúng các tập đã lưu của baseline. Đã tái tính ma trận từ lịch sử đến t−1 và kiểm tra độc lập cả 142.506 tổ hợp tại mỗi trong 78 sự kiện. Full 30 có coverage bằng 0 theo định nghĩa nên chỉ là đối chứng kích thước tập, không phải đối chứng K5 công bằng trên chính score này.

B giữ đúng chuỗi Proposed K5 cộng GOLD và VFF: B0 dùng trung bình mẫu 20 phiên; B1 dùng prior BL; B2 thêm các ML views P/Q/confidence đã lưu và có nguồn gốc nhân quả. Ba nhánh dùng cùng covariance, tập khả thi và lịch quyết định. Không có view thì posterior bằng prior pi, tuyệt đối không dùng fallback trung bình mẫu của pipeline legacy.

Tất cả A/B dùng risk aversion cố định 1,5, tắt defensive regime views và điều chỉnh risk aversion theo regime; tau=0,05, delta=2,5, prior weights đều trên tập đang đầu tư. B2 giữ confidence ML động đã lưu, bao gồm volatility dampener cố định. Đây là lựa chọn kiểm soát được ghi trước khi đọc kết quả ablation; B2 không được coi là bản sao của BL legacy có regime. H4/H5 về confidence và regime không được kiểm định độc lập.

| Điều kiện | Giá trị thực thi |
|---|---|
| Tổng tỷ trọng và long-only | sum w = 1; w ≥ 0 |
| Cap mỗi tài sản | 0,50, áp dụng cả GOLD và VFF |
| Nhóm ngoài VFF | ≤ 0,70, bao gồm GOLD |
| Floor VFF | danh nghĩa 0,15; hiệu dụng 0,30 |
| Loại vị thế nhỏ | ngưỡng 0,01 chỉ khi vẫn khả thi |
| Ngưỡng kiểm tra | 1e-8 sau giải và làm sạch |
| Hàm mục tiêu | muᵀw − 1,5 wᵀSigma w |
| Covariance | return ngày, 20 phiên; eigenvalue floor 1e-8 |

Quyết định sau close(t) thực thi close(t+1); lượng nắm giữ mới chỉ hưởng return t+1→t+2. Số đơn vị được giữ giữa hai giao dịch, tỷ trọng trôi theo giá. IS và OOS nối cùng một danh mục; chỉ chuẩn hóa NAV để báo cáo, không cấp vốn lại. Cap được kiểm tại giao dịch, không áp đặt lại mỗi ngày giữa hai giao dịch.

## 4 Thí nghiệm A về lựa chọn đại diện

Kết quả cấu trúc dưới đây tính trên 32 sự kiện chọn tập trong OOS. Jaccard so với sự kiện liền trước, kể cả sự kiện đầu OOS so với cuối IS; số thay đổi là số cổ phiếu mới vào tập.

| Nhánh | Coverage | Corr cặp | Jaccard | Đổi mã |
|---|---|---|---|---|
| Full 30 | 0.000 | 0.420 | 1.000 | 0 |
| Simple K5 | 12.472 | 0.401 | 0.274 | 95 |
| Proposed K5 | 10.050 | 0.319 | 0.958 | 4 |
| Random K5 trung vị | 11.886 | 0.422 | 0.087 | 136.5 |

Coverage thấp hơn của Proposed phù hợp với mục tiêu tối ưu được thiết kế. Độ ổn định cao và turnover thấp là kết quả riêng có ý nghĩa thực nghiệm; không suy ra chỉ từ việc thuật toán thắng chính hàm mục tiêu của nó.

| Nhánh | NAV | CAGR % | Vol % | Sharpe | MDD % | TO năm |
|---|---|---|---|---|---|---|
| Full 30 | 1.7164 | 23.66 | 14.16 | 1.160 | -12.47 | 10.685 |
| Simple K5 | 1.6381 | 21.41 | 11.90 | 1.200 | -9.06 | 4.940 |
| Proposed K5 | 1.7104 | 23.49 | 13.81 | 1.175 | -10.26 | 0.851 |

| Nhánh | NAV | CAGR % | Vol % | Sharpe | MDD % | TO năm |
|---|---|---|---|---|---|---|
| Random K5 trung vị | 1.6117 | 20.63 | 14.46 | 0.978 | -11.25 | 6.906 |

Proposed có CAGR cao hơn Simple 2,08 điểm phần trăm, nhưng Sharpe thấp hơn 0,025 và MDD âm hơn khoảng 1,19 điểm phần trăm. Turnover giảm từ 4,940 xuống 0,851 mỗi năm. Trong 10 seed, Proposed đứng trên 7/10 lượt về Sharpe; đây là vị trí trong tập seed nhỏ đã định trước, không phải xác suất thắng tổng quát.

| Chỉ số | Trung vị | Min | Q25 | Q75 | Max |
|---|---|---|---|---|---|
| NAV | 1.6117 | 1.5080 | 1.5611 | 1.7351 | 2.0848 |
| CAGR % | 20.6343 | 17.5272 | 19.1367 | 24.1911 | 33.4867 |
| Vol % | 14.4622 | 13.9793 | 14.2921 | 14.5385 | 14.7534 |
| Sharpe | 0.9778 | 0.7817 | 0.8762 | 1.1858 | 1.6756 |
| MDD % | -11.2531 | -14.7396 | -12.1431 | -10.8082 | -10.3702 |
| TO năm | 6.9062 | 6.6096 | 6.7104 | 6.9815 | 7.0450 |

Trung vị trong bảng phân phối là trung vị chỉ số của 10 backtest hoàn chỉnh. Nó khác chuỗi “Random median ngày” trong bootstrap, vốn lấy trung vị return của 10 seed tại từng ngày và chỉ dùng làm đối chứng phân tích, không phải danh mục có thể đầu tư.

HHI bình quân ngày của Proposed là 0.1717, số vị thế hiệu dụng bình quân là 5.824; tương ứng Full 30 là 0.1192 và 8.424. Đó là số đo tỷ trọng thực tế trước return, không phải số mã danh nghĩa.

## 5 Thí nghiệm B về BL và ML trên cùng danh mục

| Nhánh | NAV | CAGR % | Vol % | Sharpe | MDD % | TO năm |
|---|---|---|---|---|---|---|
| MVO matched | 1.6932 | 23.00 | 20.28 | 0.835 | -17.50 | 13.544 |
| BL prior-only | 1.7104 | 23.49 | 13.81 | 1.175 | -10.26 | 0.851 |
| BL cộng ML | 1.8244 | 26.66 | 13.71 | 1.367 | -9.51 | 7.975 |

B1 trừ B0: Sharpe tăng 0,340; volatility giảm 6,47 điểm phần trăm; MDD giảm độ sâu 7,24 điểm phần trăm; turnover giảm 12,693 mỗi năm. Đây là so sánh estimator/prior dưới cùng bộ giải tối ưu và ràng buộc, không phải bằng chứng rằng một thuật toán solver riêng của BL tốt hơn MVO.

B2 trừ B1: CAGR tăng 3,17 điểm phần trăm, Sharpe tăng 0,193; MDD giảm độ sâu 0,75 điểm phần trăm. Turnover tăng từ 0,851 lên 7,975 mỗi năm; HHI tăng từ 0,1717 lên 0,2726. ML có lợi về gross trong cửa sổ này nhưng làm danh mục tập trung hơn và giao dịch nhiều hơn. B1 và A3 được giải riêng và có đường NAV giống nhau, đúng như thiết kế chung prior-only.

Kết quả IS được giữ để nhìn cả hai kỳ, không dùng để lựa chọn lại cấu hình:

| Nhánh | NAV | CAGR % | Vol % | Sharpe | MDD % | TO năm |
|---|---|---|---|---|---|---|
| MVO matched | 2.1828 | 24.25 | 21.64 | 0.842 | -18.04 | 14.298 |
| BL prior-only | 1.7910 | 17.60 | 14.40 | 0.794 | -17.98 | 1.536 |
| BL cộng ML | 1.6603 | 15.14 | 15.44 | 0.614 | -18.12 | 7.907 |

Trong IS, Sharpe B2 là 0,614, thấp hơn B1 0,794 và B0 0,842; bằng chứng giữa IS và OOS không đồng nhất. Không dùng kết quả IS hoặc OOS này để đổi cấu hình đã đóng băng.

## 6 Chi phí và khoảng bất định

Chi phí đặt trước là 0, 10, 25, 50 bps cho mỗi đơn vị notional mua hoặc bán. Tại execution close, traded notional bằng sum abs(w_target − w_pretrade) = 2 × turnover. Mỗi sự kiện áp dụng hệ số 1 − c × traded notional lên NAV gross; khoản phí thuộc đúng ngày thực thi. Đây là xấp xỉ nhân theo sự kiện trên giao dịch gross, không phải mô hình holdings tự tài trợ chính xác khi có phí. Giao dịch ban đầu bị tính phí một lần trong IS, nhưng bị loại khỏi turnover năm; OOS không có phí cấp vốn lần hai. Giao dịch ở close cuối mẫu vẫn bị tính phí mà không thêm return tương lai.

| Nhánh | S 0bps | S 10bps | S 25bps | S 50bps | NAV 50bps |
|---|---|---|---|---|---|
| Full 30 | 1.160 | 1.009 | 0.782 | 0.403 | 1.3075 |
| Simple K5 | 1.200 | 1.115 | 0.989 | 0.777 | 1.4443 |
| Proposed K5 | 1.175 | 1.162 | 1.144 | 1.112 | 1.6738 |
| MVO matched | 0.835 | 0.701 | 0.500 | 0.165 | 1.1989 |
| BL cộng ML | 1.367 | 1.251 | 1.075 | 0.782 | 1.4891 |

B1 dùng cùng kết quả với Proposed K5. Ở 10 bps, Sharpe B2 vẫn cao hơn B1; ở 25 và 50 bps, B1 cao hơn B2. Không tìm ngưỡng hòa vốn liên tục; khoảng kịch bản này đã cho thấy tính nhạy chi phí. Phí quỹ, thuế, spread SJC và lịch nhận lệnh thực tế chưa được mô phỏng riêng.

Bootstrap dùng moving blocks không vòng tròn, độ dài 10 phiên, 1.000 mẫu lặp, seed 20261014. Trong mỗi cặp, hai chuỗi nhận cùng chỉ số ngày lấy mẫu. Mỗi mẫu tính lại CAGR và Sharpe với rf ngày = 1,06^(1/252) − 1, chuẩn hóa 252 phiên/năm, độ lệch chuẩn mẫu. CI là percentile 95%; chênh lệch drawdown được trình bày mô tả, không gắn CI bootstrap.

| Cặp so sánh | Chỉ số | Hiệu ứng | CI 95% |
|---|---|---|---|
| Proposed K5 trừ Simple K5 | CAGR điểm % | +2.081 | [-10.889; +14.674] |
| Proposed K5 trừ Simple K5 | Sharpe | -0.025 | [-0.850; +0.707] |
| Proposed K5 trừ Random median ngày | CAGR điểm % | +6.836 | [-1.908; +17.007] |
| Proposed K5 trừ Random median ngày | Sharpe | +0.383 | [-0.162; +1.014] |
| BL prior-only trừ MVO matched | CAGR điểm % | +0.491 | [-24.230; +22.698] |
| BL prior-only trừ MVO matched | Sharpe | +0.340 | [-0.497; +1.276] |
| BL cộng ML trừ BL prior-only | CAGR điểm % | +3.171 | [-5.643; +12.044] |
| BL cộng ML trừ BL prior-only | Sharpe | +0.193 | [-0.290; +0.730] |

Tất cả CI chứa 0: chưa đủ bằng chứng xác định hướng hiệu ứng, không đồng nghĩa các mô hình tương đương. CI có điều kiện theo cửa sổ, universe và giả định dữ liệu đã cố định; không loại bỏ rủi ro thử nhiều chiến lược hay nguồn gốc tham số trước OOS chưa đầy đủ.

## 7 Hình so sánh

![NAV và drawdown OOS của các nhánh matched](../outputs/plots/matched_nav_drawdown.png)

Vùng xám của A biểu diễn khoảng min–max đường NAV của 10 seed Random, không phải khoảng tin cậy.

![Coverage và độ ổn định của tập chọn](../outputs/plots/selection_coverage_stability.png)

![Sharpe sau chi phí của ba nhánh B](../outputs/plots/cost_sharpe.png)

## 8 Kết luận theo giả thuyết

- H1: Hỗn hợp. Proposed tối ưu coverage, ít đổi mã và turnover thấp; không thắng Simple về Sharpe gross hoặc MDD, và CI về chênh lệch hiệu suất chứa 0. Full 30 là bối cảnh kích thước, không phải causal K5 comparison.
- H2: Có hỗ trợ mô tả trong mẫu. Prior BL ít tập trung, ít giao dịch và ít drawdown hơn MVO matched. CI chênh lệch Sharpe và CAGR chứa 0 nên chưa kết luận ưu thế thống kê.
- H3: Hỗn hợp. ML cải thiện gross OOS nhưng tăng turnover, và lợi ích không bền ở mức phí 25–50 bps mỗi chiều; CI chứa 0.
- H4 và H5: Chưa kiểm định riêng. Không chạy fixed-confidence hay regime on/off; không ghi “kết quả bằng 0” cho các probe chưa chạy.
- H6: Có kết quả end-to-end gross trong baseline và kết quả matched có điều kiện trong sprint. Chưa xác nhận lợi nhuận tổng quát hoặc chiến lược thực thi thực tế. Hybrid legacy chỉ là tham chiếu mô tả.

## 9 Kiểm chứng và khả năng tái lập

Lượt chính `core-evidence-20261023T211011`; lượt kiểm tra lặp `core-evidence-20261023T211139`. Cả hai thực thi lại toàn bộ 16 cấu hình phân bổ và phân tích, dùng cùng kho tín hiệu bất biến; không huấn luyện lại ML. Mọi CSV thí nghiệm giống từng byte, trừ registry có runtime khác nhau. Bộ kiểm tra gồm sáu kiểm thử mới cho timing, drift, prior, Simple, phí và paired bootstrap; 35 kiểm thử kế thừa chạy từ đúng candidate workspace; 10,245 assertion độc lập về file lặp, holdings units, constraints, timing, matched inputs, posterior và cost0. Số assertion lớn bao gồm kiểm tra lặp theo từng giao dịch, không phải từng đó kiểm định thống kê độc lập.

Các check đọc lại số đơn vị tài sản và giá để tái tạo mọi NAV mới, kiểm tra toàn bộ target sau làm sạch, xác nhận covariance/active universe/prior/risk aversion giống nhau giữa ba nhánh B và xác nhận no-ML bằng prior. Rà soát độc lập bổ sung xác nhận covariance saved với panel dựng lại sai lệch tối đa 2,60e-18 trên 293 mẫu. Mã nguồn, input hashes, tham số, dependency versions, seed, OS/CPU, solver và log được lưu theo từng run.

Hash của references và báo cáo Docs xuất được ghi trong evidence manifest lúc đóng gói. Các hash này là dấu vết tài liệu tại thời điểm đóng gói, khác với manifest và experiment_plan đã tạo trước thực thi. Những giới hạn về ngày công bố gốc và corporate-action vintage không được nâng thành chứng nhận dữ liệu.

Lệnh tái lập từ root repository:

```sh
venv/bin/python -B -m unittest discover -s experiments_core/tests -v
venv/bin/python -B -m experiments_core.src.run
venv/bin/python -B -m experiments_core.src.run --parent-run RUN_CHINH
venv/bin/python -B -m experiments_core.src.validate RUN_CHINH RUN_LAP
venv/bin/python -B -m experiments_core.src.report RUN_CHINH RUN_LAP
```

Tệp CSV đầy đủ gồm chỉ số IS/OOS, lịch chọn và score, phân phối cả 10 seed, return ngày, target và pretrade weights, holdings ngày, turnover sự kiện, covariance/prior/posterior/P/Q, CI, chi phí và registry. `run_manifest` chỉ ra đầu vào gốc; bản snapshot và archive tái lập kèm bảng ánh xạ cho phép truy nguyên sau khi đổi thư mục dự án.

## 10 Giới hạn và đề xuất sửa bài báo

Universe là danh sách cố định 30 cổ phiếu, có khả năng survivorship bias. Giá điều chỉnh là snapshot provider, chưa có vintage point-in-time hoặc sổ corporate actions chứng minh total return. Availability của VFF/GOLD là policy mô phỏng, chưa phải timestamp first-release đã xác minh. GOLD theo giá bán SJC và VFF theo NAV đại diện; next-close không phải cam kết nhận lệnh quỹ hay khớp vàng thực tế. Chi phí là stress test đơn giản. Chưa đủ bằng chứng nguồn gốc của mọi lựa chọn tham số trước OOS.

Tuyên bố đóng góp nên tập trung vào kiến trúc xây dựng danh mục và các hiệu ứng tăng thêm đo được. Giữ cả kết quả âm và CI rộng. Đồng bộ công thức Sharpe theo excess return ngày; mu/Q và Sigma theo đơn vị ngày; views dùng tanh theo volatility; objective dùng hệ số phạt 1,5 và 5 trong legacy, tương đương lambda/2 nếu đổi ký hiệu; alpha Hybrid là tỷ phần MVO và alpha_normal=1 không làm các regime khác trở thành MVO thuần. Không gọi toàn bộ các layer là đã chứng minh hiệu quả.

Gói này đủ để sửa phần phương pháp, bảng thực nghiệm và thảo luận của bản thảo. `paper_revision_handoff.md` chứa đề xuất abstract, contribution và cách trình bày kết quả. Chưa tuyên bố bản thảo đã sẵn sàng gửi journal hoặc chiến lược giao dịch đã được xác nhận thực thi.

READY FOR PAPER REVISION
