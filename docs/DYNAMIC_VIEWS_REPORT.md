# Báo Cáo Tiến Độ: Dynamic Views cho Black-Litterman

**Đề tài**: Tối ưu hóa danh mục đầu tư cho thị trường Việt Nam  
**Phiên bản tài liệu**: cập nhật theo code hiện tại

---

## 1. Mục tiêu

Xây dựng cơ chế sinh views động để thay cho hardcoded views, nhằm:
- Giảm tính chã quan
- Cập nhật views tại mọi lần rebalance
- So sánh nhiều kiểu sinh views trong cùng framework BL

## 2. View modes đang hỗ trợ

`backtest.py` đang hỗ trợ 5 chế độ:

1. `static`
   - Dùng `STATIC_VIEWS` hardcoded trong code

2. `rule_based` (Quy tắc)
   - Sử dụng EMA crossover + RSI + động lực
   - Sinh absolute views cho từng tài sản

3. `relative` (So sánh tương đối)
   - So sánh động lực giữ a các cặp tài sản
   - Sinh relative views (long tài sản mạnh, short tài sản yếu)

4. `ml` (Máy học)
   - Dùng `TraditionalMLViewGenerator`
   - Hiện tại chỉ hỗ trợ model `xgboost`
   - Cần model đã train trước và lưu cache

5. `combined` (Kết hợp)
   - Trộn rule_based + relative + ml
   - Trọng số mặc định: `(0.4, 0.4, 0.2)`

## 3. Công thức Black-Litterman

$$\pi = \delta \times \Sigma \times w_{market}$$
$$\mu_{BL} = \left[(\tau \Sigma)^{-1} + P^T \Omega^{-1} P\right]^{-1} \times \left[(\tau \Sigma)^{-1} \pi + P^T \Omega^{-1} Q\right]$$
$$\Omega = \text{diag}(P \times \tau \times \Sigma \times P^T) / \text{confidence}$$

Tham số mặc định:
- `tau = 0.05` - Tham số điểu của mo hình
- `delta = 2.5` - Hệ số cãi đặt

## 4. Luồng xử lý trong backtest

Tại mọi lần rebalance:

1. Tính `mu`, `sigma` từ cỚ sổ lịch sử (`WINDOW = 20`)
2. Tính MVO weights
3. Sinh views theo `view_mode`
4. Nếu có views hợp lệ -> tính `mu_BL`; nếu không -> fallback `mu_BL = mu`
5. Tối ưu BL weights

Pseudo-flow:

```text
hist returns -> (mu, sigma)
            -> MVO optimize
price_window -> generate views -> (P, Q, conf)
(P, Q, conf) + (sigma, market_weights) -> mu_BL
mu_BL + sigma -> BL optimize
```

## 5. Chi tiết view generators

### 5.1 Rule-based (Quy tắc)

Tín hiệu chính:

```text
ma_ratio = EMA_short / EMA_long - 1
if ma_ratio > 2%: xu hướng tăng
if ma_ratio < -2%: xu hướng giảm
```

Điều chỉnh confidence bằng RSI:
- RSI > 70: giảm confidence xu hướng tăng
- RSI < 30: giảm confidence xu hướng giảm

Độ lớn expected return được scale theo động lực.

### 5.2 Relative (So sánh tương đối)

Với mọi cặp `(A, B)`:
- Tính động lực A, động lực B
- Nếu chênh lệch > threshold thì tạo view `A_over_B` hoặc `B_over_A`
- Annualize chênh lệch và cập trong khoảng cho phép

### 5.3 ML (XGBoost) - Máy học

Class: `TraditionalMLViewGenerator` trong `view_llm/llm_view_generators.py`.

Bộ feature chính:
- momentum_5, momentum_10, momentum_20
- rsi_14
- ma_ratio_10_30
- volatility_20 (độ biến động)
- macd_hist (nhiệt biểu MACD)
- price_std_20

Nhãn:
- forward return theo `prediction_horizon` (được mặc định 5 ngày)

Train script:

```bash
python view_llm/xgboost_train.py --method xgboost --train-phase train --validate
```

## 6. Kết quả và đánh giá

Hệ thống đã cho phép:
- Backtest nhiều view modes trong cùng khuôn EW/MVO/BL
- So sánh rule_based và ml qua `run_compare_backtests.py`
- Lưu reports để đối chiếu theo từng phase

Tài liệu này không khởi tạo kết luận hiệu năng có định vì kết quả thay đổi theo:
- Tập tài sản
- Phase train/test/full
- Dữ liệu cập nhật
- Model cache hiện hành

## 7. Giới hạn hiện tại

- LLM và LSTM không đang ở trạng thái active trong code backtest
- `--ml-model-type` hiện chỉ có `xgboost`
- Chất lượng ML phụ thuộc vào dữ liệu train và kỷ luật retrain

## 8. Hướng phát triển

1. Bổ sung cơ chế retrain định kỳ và versioning model
2. Bổ sung calibration confidence cho ML views
3. Đánh giá mở rộng cho LLM/LSTM khi cần, nhưng tách rõ với luồng production
