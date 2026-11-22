# Giải thích phân bổ từ evidence của lần tính toán

Trạng thái: **đã được người dùng duyệt và triển khai** ngày22/11/2026. Gate thực tại `docs/software/ALLOCATION_EXPLANATION.md`; paid OpenAI/hybrid vẫn nghiệm thu riêng.

## Mục tiêu và phạm vi

Sau khi có kết quả, giúp người dùng hiểu tín hiệu nào đã được sử dụng, đặc điểm của rổ tài sản, vai trò của từng mã và liên hệ với hồ sơ đã xác nhận. Nội dung phải truy nguyên về chính recommendation/run đang xem; không suy diễn rằng giải thích tốt hơn làm model hoặc lợi nhuận tốt hơn.

Giữ thuật toán, trọng số, numerical diagnostics, canonical recommendation JSON/hash, confirmation và accept hiện tại. Không train lại, sửa research, lấy tin tức mới, thêm agent tự do hoặc tự tạo allocation từ câu hỏi giải thích. Các lựa chọn dưới đây là phương án người dùng đã duyệt cho MVP.

## Khảo sát source hiện tại

- Quant `selection.py::resolve_selection` đã tính features, native ensemble views và provenance. `asset_ensemble.py::infer_asset_views` trả P/Q/confidence nhưng chưa giữ raw forecasts/features trong receipt giải thích.
- `portfolio_core/selection.py` chọn tối đa 5 cổ phiếu đại diện bằng correlation-distance k-medoids. Đây không phải xếp hạng lợi nhuận; nếu có không quá 5 cổ phiếu thì giữ tất cả.
- `candidate_regime` tính tỷ lệ biến động 20/120 phiên, drawdown cuối cửa sổ so với đỉnh trong cửa sổ 60 phiên và trung bình lợi suất ngày của rổ trong cửa sổ đó. Không phải max drawdown, xác suất khủng hoảng hay chỉ số toàn thị trường. Rổ có thể chứa GOLD/VFF, dù tên trường cũ là `equity_momentum`.
- Portfolio đã ghim `risk_profile` (gồm answers/mapping/version), requested/effective constraints, selection context/proof và diagnostics vào kết quả. Không cần đọc hồ sơ hiện tại để giải thích kết quả cũ.
- OpenAI `FactPlan` chỉ chọn weights/constraints/provenance/risk; renderer dùng câu mẫu. `explain_with_knowledge` bổ sung passage đã cite. Chỉ sửa prompt không cung cấp được dữ liệu còn thiếu.
- UI hiện tại đã theo V2.7: phân bổ chính, disclosure giải thích, nguồn và audit đầy đủ; toàn bộ trọng số 0% đã nằm trong disclosure. Ảnh người dùng là trạng thái cũ hơn source hiện tại.
- PIT audit v5 vẫn `point_in_time_certified=false`. Approved/grounded không đồng nghĩa được chứng nhận dữ liệu lịch sử, hiệu năng hay phù hợp chắc chắn.

## Đánh giá bốn hướng

| Hướng | MVP khả thi | Giới hạn phải thể hiện |
| --- | --- | --- |
| Views tích cực/tiêu cực | Lưu raw dự báo ensemble 5 phiên, trạng thái qua/ngưỡng, Q được dùng và confidence trước/sau điều chỉnh | Sign dự báo là hướng lợi suất ước lượng; không tự gọi là vượt thị trường. Confidence là heuristic, không phải xác suất tăng giá. |
| Rủi ro/xu hướng | Dùng regime và chỉ báo của rổ đã ghim, kèm phạm vi/cửa sổ/ngày dữ liệu | Không gọi đây là nhận định VNINDEX/toàn thị trường hoặc thời điểm hiện tại. Không thêm news/sentiment. |
| Vì sao có mã này | Tách candidate người dùng chọn → K5 active set → trọng số dương/0%; hiển thị features cùng thời điểm và thông tin doanh nghiệp nếu có nguồn | Features là đầu vào quan sát được, chưa phải attribution. Không nói “chọn vì RSI”, “doanh nghiệp tốt” hoặc “mã tốt nhất”. |
| Liên hệ hồ sơ | Giải thích mapping answers → profile → constraints → kết quả thực tế; phân biệt policy điều chỉnh theo regime | Chỉ dùng hồ sơ đã ghim; thời hạn đầu tư không trở thành horizon dự báo ML. Không cam kết bảo toàn vốn. |

## Các phương án

1. **Chỉ mở rộng prompt:** ít thay đổi nhưng model vẫn thiếu raw views/features; không đáp ứng bằng chứng. Không đề xuất.
2. **Evidence có cấu trúc + claim plan hữu hạn + UI V2.7:** đề xuất MVP. Quant thu thập evidence ngay khi tính; Portfolio giữ bản bất biến; Chat chọn/diễn đạt bằng templates có tham chiếu; frontend hiển thị theo nhóm.
3. **Attribution/counterfactual sâu:** bước sau. SHAP nếu có sẽ giải thích dự báo booster, không tự giải thích K5 hoặc tỷ trọng optimizer. Cần thiết kế riêng về ensemble/scaler/output space; MVP không thêm dependency hoặc chạy lại solver để dựng câu chuyện nhân quả.

## Contract và ownership đề xuất

Không thêm evidence vào `Recommendation.result`, `diagnostics`, input hay canonical facts đang dùng tính hash. Dùng sidecar `OptimizationExplanationEvidence` trong `OptimizeResult`, tách khỏi `result`. Field mới optional và phải được bỏ khỏi wire khi absent; Quant lưu trong JSON `numerical_run.payload`/outbox hiện có. Portfolio thêm một cột nullable JSON `recommendation.explanation_evidence`, không backfill/rewrite kết quả cũ. Consumers đọc được field mới trước khi producer bắt đầu phát.

Contract ở `packages/contracts/src/portfolio_contracts/explanation.py`, dùng StrictModel/FiniteFloat, giới hạn 32 assets, 8 features/asset và tối đa 64 views. Bao gồm:

- `schema_version="optimization-explanation-v1"`, run/job/input/bundle/snapshot/model/feature/selection/transform/policy pins và actual decision/history endpoints; không dùng fit epoch thay trained_at/decision_at.
- `asset_ids`, active IDs, selection method và proof hash; features có tên, giá trị, đơn vị và endpoint. Chỉ thu từ chính dữ liệu đang được inference sử dụng.
- `views`: asset coefficients P, raw mean return (nếu có), `horizon_sessions=5` cho v5, `raw_return_unit="simple_fraction"`, prediction-member dispersion, confidence heuristic trước/sau điều chỉnh, applied daily Q, transform version, `source_kind=ML|POLICY|USER`, trạng thái `APPLIED|BELOW_THRESHOLD`. View dưới ngưỡng không có Q được áp dụng.
- `regime`: scope/ordered member IDs, chỉ báo đã dùng, số phiên thực sự có dữ liệu và cửa sổ danh nghĩa. Không đổi trường/tính toán cũ chỉ để sửa tên hiển thị.
- `limitations`: nguồn dữ liệu/PIT chưa chứng nhận, thông tin chưa lưu, attribution chưa có. Thiếu bằng chứng được biểu diễn rõ, không thế bằng số 0 hoặc latest data.
- Hash canonical của sidecar, độc lập input/facts hash; loại chính trường hash khỏi phép tính. Hash chống thay đổi tình cờ, không phải chứng nhận tính đúng của dự báo. Quyền tin producer vẫn theo authenticated Quant/outbox hiện tại.

Producer dựng sidecar bằng typed contract; wire `OptimizeResult.explanation_evidence` là optional raw dict để consumer có thể kiểm riêng. Collector và builder phía Quant cũng phải có error boundary riêng: lỗi instrumentation không đi vào nhánh `INPUT_UNAVAILABLE` của numerical workflow, không làm mất allocation hợp lệ; lỗi inference/allocator thật vẫn giữ semantics hiện tại. Portfolio kiểm typed schema, units, asset alignment, pins và sidecar hash trong guarded block sau validation numerical result, trước khi lưu cùng recommendation. Evidence sai không làm mất một allocation hợp lệ: giữ numerical result, bỏ sidecar không hợp lệ và ghi bounded diagnostic ngoài canonical JSON; API trả `UNAVAILABLE`. Không nuốt lỗi validation của numerical result hoặc nới validation envelope/authentication.

API mới `GET /api/v1/recommendations/{id}/evidence` cùng owner checks như recommendation. Response `RecommendationEvidence` gồm `schema_version="recommendation-evidence-v1"`, recommendation/run IDs, `facts_hash`, `status=COMPLETE|PARTIAL|UNAVAILABLE`, evidence payload/hash. `COMPLETE` chỉ nghĩa đủ trường trong contract, không phải model đáng tin tuyệt đối. Kết hợp sidecar với profile/constraints/weights từ frozen result, không đọc current portfolio. Không đưa answers đầy đủ sang provider; chỉ gửi các claim tối thiểu cần thiết.

Chat dùng read-only delegated tool `get_recommendation_evidence`, cùng grant owner/conversation/job/portfolio và expiry. Không thêm quyền request allocation. UI qua BFF chỉ có GET cho endpoint mới. Không dùng endpoint Chat `/explanation` hiện có thay cho endpoint evidence của Portfolio.

Kết quả cũ: dựng `PARTIAL` từ những gì thực sự đã lưu (profile/regime/selection/weights); raw ML/features ghi `NOT_RETAINED`. Không infer lại, gọi model mới hoặc cập nhật receipt cũ. Giữ riêng hai hash: canonical facts và explanation evidence. Source knowledge/corpus/citations vẫn dùng cơ chế immutable hiện có.

## Quy tắc diễn giải

- Raw forecast v5 qua ngưỡng `abs(mean) >= 0.001` mới vào BL. Applied Q hiện là `0.5*tanh(mean/(daily_vol*sqrt(5)))/252`, với nhánh vol nhỏ giữ nguyên code hiện tại. Đây là biến đổi heuristic Option B; không nói Q là geometric daily forecast hoặc lãi chắc chắn sau 5 phiên.
- View policy VFF trong stress/crisis là relative basket view, không phải dự báo ML riêng của quỹ. Không gán ML view cho GOLD/VFF khi source không có.
- Một view dương vẫn có thể nhận 0%, và một view âm không tự động buộc 0%; tỷ trọng còn phụ thuộc covariance, prior/posterior và ràng buộc. Không dựng lý do chính xác cho từng 0% nếu run chưa lưu quyết định đó.
- Hồ sơ thận trọng tác động risk_aversion; max_position/min_defensive/max_non_defensive là các giới hạn riêng. Ví dụ nếu max_non_defensive=70% thì tổng phòng thủ phải ít nhất 30%, ngay cả khi min_defensive=15%. Chỉ giải thích bằng chính constraints được ghim, không hardcode ví dụ thành policy mới.
- Chỉ nói một tỷ trọng “đang chạm giới hạn” bằng phép đối chiếu tolerance của validator hiện có; không nói giới hạn đó là nguyên nhân duy nhất tạo tỷ trọng. Không thêm VaR/Sharpe/lợi nhuận kỳ vọng danh mục khi chưa có metric owner xác minh.
- Feature names/units phải lấy từ schema thực tế: momentum 5/10/20, RSI14, EMA ratio10/30, volatility20, MACD histogram và normalized price std20. Không gọi MACD là phần trăm; `price_std_20` hiện là std/mean, không phải std giá tuyệt đối.
- Thông tin tên/ngành/mô tả doanh nghiệp là metadata có nguồn, không phải feature model hoặc lý do optimizer. MVP chỉ cần ticker; metadata thiếu/legacy-static không chặn giải thích.

## Chat và UI

Backend dựng finite claims từ evidence, mỗi claim có ID, template ID và fact references. Provider chỉ chọn/sắp xếp claims hợp lệ theo câu hỏi; không trả prose tự do, numbers, URLs hoặc tool calls. Mặc định khoảng 3–5 ý: hồ sơ, bối cảnh rổ, views nổi bật/cân bằng nếu có, selection/weights, giới hạn. Overview có complete evidence phải bao phủ cả bốn nhóm; views có cả hai dấu thì không chỉ nêu dấu thuận lợi. Câu hỏi tập trung được chọn nhóm liên quan. Provider unavailable/quota/invalid output dùng cùng deterministic renderer, không mất bốn nhóm evidence.

Giữ reading lane, controls, tokens, CTA accept và draft-only suggestions V2.7. Trong disclosure giải thích: tóm tắt ngắn, rồi “Tín hiệu mô hình”, “Bối cảnh và rủi ro của rổ”, “Vai trò các tài sản”, “Liên hệ hồ sơ của bạn”; audit kỹ thuật ở phần mở rộng. Trên mobile không ép tất cả thành bảng rộng. Hiển thị positive/negative bằng chữ và dấu, không chỉ màu; không dùng badge xanh “đã xác minh” để ngụ ý certified/safe.

Tham chiếu visual hiện hành: Figma `YKRbiOAJNoVA9DaSZHc7Wc`, V2.7 section `210:8603`, page `4:212` và handoff `2026-11-22-figma-v27-frontend.md`. Phiên lập plan đọc handoff/source; chưa mở/đổi live Figma. Khi triển khai phải đối chiếu live Figma mới nhất; không redesign toàn app hoặc thêm admin UI.

## Định nghĩa đạt

Offline kiểm được units/pins/legacy/hash/grounding/security, eval tiếng Việt đo riêng retrieval và explanation, rồi real backend dùng model đã duyệt còn phù hợp. UI làm sau backend gate. Restart phải đọc lại chính recommendation/message/evidence/citations/usage receipt, không tạo luồng thay thế. Không có budget/provider call hoặc training trong bước lập plan. Paid acceptance chỉ theo budget approval và ledger hiện hành đã đối chiếu; không coi con số trong status doc là quyền tăng chi tiêu.
