# Kế hoạch chuyển sang một đề xuất phân bổ HYBRID

**Trạng thái:** Đã triển khai và chạy pilot trên `portfolio-auth-demo` ngày 22/11/2026. Hai job Web và một job Chat thực thi HYBRID qua broker. Bảng phối chưa qua ngưỡng biến động của hồ sơ Tăng trưởng, nên chế độ mặc định là `paused`. Xem [báo cáo kiểm chứng local](../../../output/hybrid-20261122/REPORT.md).

**Mục tiêu:** Investor chọn mục tiêu, xác nhận hồ sơ rủi ro và chọn tài sản được cân nhắc. Hệ thống tính một đề xuất HYBRID. Investor xem, chủ động lưu làm mục tiêu hoặc quay lại sửa đầu vào. EW và MVO nằm trong mục so sánh thu gọn, chỉ để đọc.

**Phạm vi:** Web, Chat, Portfolio API và broker contracts, Quant và portfolio-core, lưu vết, tài liệu vận hành và kiểm chứng local. Tái dùng Next.js, FastAPI, RabbitMQ, PostgreSQL, CVXPY và native XGBoost hiện có. Không đổi trình huấn luyện, nguồn giá, lịch refresh hoặc quyền duyệt model trong đợt này.

## Cơ sở và quyết định

- Baseline đóng băng `availability-observed-contract-20261012T233110` tính `w = α × w_MVO + (1 − α) × w_BL_ML`. `α` là phần MVO, bằng 0,60 / 0,30 / 0,10 theo normal / stress / crisis. MVO chạy trên toàn bộ universe, BL_ML dùng K5 và tài sản ngoài cổ phiếu đã chọn. Xem [cấu hình](../../../outputs/step1/readiness_20261012/runs/availability-observed-contract-20261012T233110/run_config.json) và [vòng lặp](../../../outputs/step1/readiness_20261012/runs/availability-observed-contract-20261012T233110/source_snapshot/backtest/_loop.py).
- Serving hiện đã có policy khảo sát, K5 động, P/Q, confidence và model v5 đã duyệt. Lượt local ngày 22/11 đã chứng minh đổi hệ số 1,5 → 6 làm đổi BL_ML dù rổ, model, snapshot và đầu vào số giống nhau. Đây là bằng chứng cho policy đang hoạt động, chưa phải kiểm chứng HYBRID.
- Giữ kiến trúc hai nhánh của Phase 1. Trong app, universe của nhánh MVO là toàn bộ rổ investor cho phép cân nhắc. Nhánh BL_ML chạy K5 khi có hơn 5 cổ phiếu và luôn giữ các tài sản ngoài cổ phiếu có trong rổ. Mã ngoài K5 có thể có tỷ trọng dương qua nhánh MVO. Cả hai nhánh chỉ có thể phân bổ vào mã investor đã chọn.
- Dùng chung hệ số ngại rủi ro hiệu lực và các giới hạn đang áp dụng cho cả hai nhánh. Hồ sơ thận trọng / cân bằng / tăng trưởng hiện dùng 6 / 3 / 1,5. Khi crisis, sàn hiện hành là 5. Bảng phối dùng **nhãn hồ sơ đã xác nhận**, do đó Cân bằng và Tăng trưởng vẫn có thể khác nhau khi cùng chạm sàn 5.
- HYBRID theo regime và hồ sơ là chính sách serving mới. Kiến trúc Phase 1, rổ do investor chọn và policy mới cần được ghi riêng khi báo cáo kết quả.

## Chính sách HYBRID đề xuất cho bản đầu

Tính `α = alpha_phase1[regime] × profile_multiplier[profile]`. Các hệ số đề xuất là 0,75 / 1,00 / 1,25 theo Thận trọng / Cân bằng / Tăng trưởng, giữ nguyên tỷ lệ Phase 1 cho hồ sơ Cân bằng.

| Trạng thái thị trường | Thận trọng | Cân bằng | Tăng trưởng |
| --- | ---: | ---: | ---: |
| Bình thường | 45% MVO | 60% MVO | 75% MVO |
| Căng thẳng | 22,5% MVO | 30% MVO | 37,5% MVO |
| Khủng hoảng | 7,5% MVO | 10% MVO | 12,5% MVO |

Mức giảm tỷ phần MVO là giả thuyết thiết kế cần kiểm tra. Phương sai của danh mục phối phụ thuộc cả phương sai hai nhánh lẫn hiệp phương sai giữa chúng. Tỷ phần BL_ML cao hơn tự nó không bảo đảm biến động hoặc drawdown thấp hơn. Nếu bảng phối không vượt tiêu chí đã định trước, giữ sau cờ tính năng để đánh giá lại. Chọn bảng bằng dữ liệu kiểm định theo thời gian, giữ riêng tập đánh giá cuối cùng và ghi chi phí giả định khi báo cáo.

Hai nhánh tính từ cùng snapshot, phiên quyết định, lịch sử lợi nhuận ngày và rổ có cùng thứ tự. Mỗi nhánh phải hợp lệ trước khi phối. Mở rộng nhánh BL_ML về thứ tự rổ, gán đúng 0 ngoài active set của nhánh đó, rồi phối các vector. Phép phối lồi giữ các giới hạn tuyến tính chung, gồm tổng 100%, vị thế không âm, cap mỗi mã và giới hạn nhóm. Kiểm tra lại nghiệm cuối và chỉ làm tròn khi hiển thị. Chính sách bỏ vị thế nhỏ hiện áp dụng ở nhánh tương ứng, không tự áp thêm sau phối.

## Luồng và nội dung hiển thị

| Bề mặt | Hành vi mới |
| --- | --- |
| Onboarding và sửa danh mục | Giữ mục tiêu, vốn, thời hạn, khảo sát và rổ tài sản. Nêu rằng hồ sơ ảnh hưởng mức ngại rủi ro và cách hệ thống phối hai nhánh. Tick một mã cho phép cân nhắc, có thể nhận 0%. |
| Tổng quan | Một hành động “Tạo đề xuất phân bổ” hoặc “Tính lại đề xuất”. Hiển thị hồ sơ hiện tại, ngày dữ liệu và điều kiện cần xử lý nếu đang bị chặn. |
| Xem trước và gửi | Tóm tắt danh mục, hồ sơ, rổ và trạng thái đầu vào. Một nút “Xác nhận tạo đề xuất”. Bỏ ba radio, checkbox EW dự phòng và bảng readiness theo phương pháp khỏi luồng investor. |
| Kết quả | Ưu tiên tỷ trọng, vốn theo kế hoạch, căn cứ phân bổ và nút “Chấp nhận làm mục tiêu”. Hiển thị hồ sơ đã ghim của đề xuất, ngày dữ liệu và lý do phải tính lại nếu phiên bản danh mục đã đổi. Các mục “Cách hệ thống tính” và “So sánh với phương án tham chiếu” mặc định thu gọn. |
| So sánh trong đề xuất | Một bảng cho đề xuất hệ thống, EW và MVO. Giải thích EW là chia đều, MVO dựa trên lợi nhuận và biến động lịch sử. Có thể xem tỷ trọng tham chiếu, tỷ trọng phòng thủ và biến động ước tính trên cùng covariance. Chỉ đề xuất hệ thống có hành động chấp nhận. |
| Chat | Investor yêu cầu đề xuất, chọn đúng danh mục nếu còn thiếu ngữ cảnh và xác nhận yêu cầu. Chat gọi cùng admission của Portfolio. Có thể giải thích phương pháp hoặc đối chứng từ dữ kiện của đề xuất theo quyền owner. |
| Lịch sử | Giữ nhãn phương pháp, tỷ trọng, phiên bản, trạng thái và liên kết của đề xuất cũ. So sánh hai đề xuất đã lưu là một luồng riêng với so sánh đối chứng của một đề xuất. |

MVO đối chứng là nhánh MVO đã tính trong job, dùng cùng rổ, snapshot, covariance và constraints. EW là vector chia đều trên cùng rổ. Nếu EW vi phạm policy, vẫn hiển thị như mốc tham chiếu lý thuyết và ghi rõ giới hạn bị vi phạm, ví dụ rổ 4 mã cho VFF 25% trong khi giới hạn nhóm ngoài phòng thủ buộc VFF đạt ít nhất 30%. Không dùng lợi nhuận dự báo từ hai mô hình khác nhau làm thước đo so sánh. Mọi ước tính phải ghi rõ cửa sổ và đơn vị. Không tạo thêm recommendation, job hay mục tiêu cho đối chứng.

## Các bước triển khai

- [x] **1. Khóa policy và fixture.** Đối chiếu hàm phối với baseline đóng băng. Tái dùng receipt rủi ro ngày 22/11 ở `output/playwright/risk-blml-20261122/receipt.json` nếu có, làm tham chiếu cho ca kiểm thử. Viết fixture ghim rổ, regime, hồ sơ, hai vector nhánh, `α` và nghiệm cuối. Kiểm đủ 9 cặp hồ sơ/regime, hoạt động khi hai nhánh giống nhau, và trường hợp thay hồ sơ có tác động riêng lên `α` ngay cả khi hệ số ngại rủi ro bằng nhau.
- [x] **2. Tính trong một job Quant.** Tái dùng `portfolio_core.allocate` cho mỗi nhánh và thêm một bộ phối thuần có policy version, ví dụ `phase1-hybrid-profile-v1`. Sửa `quant_service/selection.py`, `selection_ready.py` và `workflow.py` để lấy một panel, sinh hai input đúng active set và chỉ inference một lần. Test fixture đối chiếu công thức và thứ tự, rổ dưới/bằng/trên 5 cổ phiếu, hai tài sản bị ép 50/50, mã ngoài K5 nhận tỷ trọng qua MVO, cùng constraints trên hai nhánh và kết quả cuối.
- [x] **3. Ghim lệnh phía server và kiểm chứng kết quả.** Trong `portfolio_service/api.py` và `delegation.py`, tạo luồng đề xuất hệ thống với payload investor không có `strategy`/`fallback_strategy`. Giữ xác nhận, `If-Match`, `Idempotency-Key`, CSRF và scope owner. Ghim asset revision, risk revision, policy version, snapshot/model/panel hash, phiên, regime và `α` vào command hoặc dữ kiện có hash tương ứng. Mở rộng contracts/OpenAPI/event schemas theo cách đọc được lệnh cũ. Trong `portfolio_service/workflow.py`, kiểm tra proof từng nhánh, pin chung, `α`, tỷ trọng cuối và công thức phối trước khi lưu. Test request giả mạo phương pháp trên cả BFF lẫn API và Chat, retry, input hết hạn, result sai hash và thay hồ sơ giữa lúc job đang chạy.
- [x] **4. Readiness cho một đề xuất.** Trả trạng thái chung kèm hành động cụ thể khi thiếu hồ sơ, thiếu VFF, rổ chưa khả thi, cần cổ phiếu có ML view, VFF stale, snapshot hết hạn, model chưa duyệt, lỗi hash/coverage/fit epoch hoặc inference lỗi. Cho lưu rổ khi chưa sẵn sàng như hiện tại. Khi một nhánh không khả thi, chặn HYBRID và đưa người dùng về bước xử lý phù hợp. Không chuyển sang EW hay MVO. Nhánh MVO vẫn dùng được nội bộ để tính đối chứng khi HYBRID chạy.
- [x] **5. Web và Chat.** Cập nhật `apps/web/src/app/home.tsx`, `portfolio-workspace.tsx`, `allocation-view.tsx`, `risk-reassessment.tsx`, `chat-workspace.tsx` và các kiểu dữ liệu liên quan. Cập nhật `chat_service/workflow.py` và tools để giữ bước xác nhận và chỉ có một phương thức tạo đề xuất. Tái dùng phần giải thích và evidence đang được phát triển trong `recommendation-evidence.tsx` và các module `explanation.py`. Hiển thị tỷ trọng, phần phối và lý do từ dữ kiện đã lưu. Chat chỉ tóm tắt bằng chứng được phép truy cập. Test giao diện desktop/mobile, bàn phím, thông báo lỗi, lời nhắc cần xác nhận lại và lịch sử legacy.
- [x] **6. Lưu lịch sử và chuyển đổi.** Nếu cần schema mới, dùng migration bổ sung. Không sửa payload đề xuất, snapshot, model, tài khoản, selection revision hay mục tiêu đã lưu. Đọc được đề xuất cũ và xử lý xong các job đang chờ theo contract lúc nhận. Phát hành consumer đọc được cả phiên bản cũ/mới trước, rồi bật đường gửi HYBRID đồng bộ cho Web/API/Chat. Đường gọi legacy chỉ còn cho tương thích khi chuyển đổi hoặc công cụ vận hành đã giới hạn quyền. Trong chế độ investor mới, tắt cờ HYBRID đưa UI về trạng thái tạm chưa sẵn sàng và giữ lịch sử đọc được.
- [x] **7. Kiểm chứng định lượng và stack thật.** Trước khi chốt hệ số, so với HYBRID chỉ theo regime và BL_ML hiện tại trên cùng mẫu walk-forward, rổ, dữ liệu khả dụng, rebalance và chi phí giả định. Đăng ký trước cách tách tập và ngưỡng sai số/chất lượng. Báo cáo turnover, volatility, drawdown, kết quả theo regime và mức khác biệt giữa hồ sơ. Công bố trường hợp bất lợi, nghiệm bằng nhau và giới hạn lịch sử. Sau đó chạy bộ test Python/Web liên quan, kiểm chứng browser và restart trên `portfolio-auth-demo` theo tiêu chí bên dưới.

## Tiêu chí bật trên local

- Investor thấy một hành động tạo đề xuất ở Web và Chat. EW/MVO chỉ có trong đối chứng thu gọn hoặc nhãn lịch sử. API investor không nhận yêu cầu chọn phương pháp hay dự phòng.
- Cùng danh mục, rổ có hơn 5 cổ phiếu cùng GOLD/VFF, snapshot và model đã duyệt, tạo hai job thật qua broker khi đổi hồ sơ trên UI. Cả hai `SUCCEEDED` thực thi HYBRID. Receipt ghi ID job/đề xuất, phiên bản hồ sơ, rổ, K5 từng nhánh, regime, `α`, hash snapshot/model và hai vector nhánh. Kiểm tra vector cuối khớp công thức, tổng 100% và từng giới hạn.
- Thêm ca rổ nhỏ và ca EW đối chứng vi phạm policy. Hai benchmark cùng dữ liệu và chỉ để xem. Ca model thiếu/chưa duyệt/sai hash hoặc VFF stale bị chặn đúng lý do; không có kết quả thay thế.
- Mở lại đề xuất mới và đề xuất cũ sau reload/restart. Đối chiếu checksum các đề xuất/mục tiêu có sẵn, đồng thời giữ nguyên tài khoản, volume, model, snapshot và chính sách freshness **7 ngày**. Giữ khả dụng theo policy đã ghim của từng nguồn: baseline/selected v1 dùng VFF buffer 5 phiên, selected live v2 dùng quy tắc NAV đã xác minh. Chi tiết tại [runbook Phase 1](../../software/PHASE1_LOCAL_SERVING.md).
- Có bằng chứng định lượng trước khi bật bảng hệ số. Kết quả browser chứng minh pipeline và tác động của hồ sơ trên rổ đã chạy. Nó không thay thế kiểm chứng chất lượng chiến lược qua thời gian.

## Vận hành pilot và cổng định lượng

Compose dùng `SYSTEM_HYBRID_ENABLED=paused` mặc định cho Portfolio và Chat. Paused giữ trải nghiệm một đề xuất, trả trạng thái chưa sẵn sàng khi người dùng muốn tính mới và vẫn đọc được lịch sử. `SYSTEM_HYBRID_ENABLED=true` dùng trong pilot có kiểm soát. Chế độ `false` giữ đường API tương thích dành cho kiểm thử và quá trình chuyển đổi. Các job đã nhận tiếp tục dùng policy đã ghim.

`scripts/eval_hybrid_policy.py` chạy bằng môi trường nghiên cứu `venv` với `PYTHONPATH=packages/portfolio-core/src:packages/contracts/src`. Dùng run Phase 1 đã đóng băng làm đối số đầu và tệp JSON kết quả làm đối số sau. So sánh ba phương án trên cùng panel, lịch khớp sau phiên quyết định, policy rủi ro theo hồ sơ và phí giả định 10 bps trên mỗi đơn vị turnover. Không tái huấn luyện hay sử dụng model serving hiện tại để chấm lại quá khứ.

Các ngưỡng pilot so với HYBRID chỉ theo regime gồm tăng biến động năm tối đa 2 điểm phần trăm, tăng drawdown tối đa 3 điểm phần trăm và turnover tối đa 1,25 lần. Trên 641 phiên holdout, Tăng trưởng đạt 19,29% biến động năm so với 16,98% của đối chứng, tăng 2,31 điểm phần trăm. Không chỉnh bảng hệ số dựa trên tập vừa dùng để đánh giá. Bằng chứng phiên chạy và giới hạn so sánh được lưu trong [kết quả định lượng](../../../output/hybrid-20261122/quantitative.json).
