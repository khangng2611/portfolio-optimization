# Option B: Điều chỉnh độ lớn View theo biến động (Volatility-Adjusted Tanh Scaling)

Tài liệu này giải thích chi tiết giải pháp **Option B** được áp dụng trong hàm `generate_ml_views()` tại `gen_view/view_generators.py`, bao gồm bối cảnh vấn đề, các khái niệm toán học, cách triển khai và cách rollback nếu cần.

---

## 1. Bối cảnh vấn đề

### 1.1 Pipeline tạo View

Trong mô hình Black-Litterman (BL), **view** là nhận định của nhà đầu tư về lợi suất kỳ vọng của một (hoặc nhiều) tài sản. Mỗi view gồm 3 thành phần chính:

| Thành phần | Ký hiệu | Ý nghĩa |
|---|---|---|
| **P (Picking matrix)** | `P` | Xác định tài sản nào tham gia vào view (ví dụ: +1 cho tài sản long, -1 cho tài sản short) |
| **Q (View vector)** | `Q` | Lợi suất kỳ vọng (annualized) mà view dự đoán |
| **Confidence** | `conf` | Độ tin cậy của view, dùng để xây dựng ma trận Omega (ma trận hiệp phương sai của view) |

Pipeline tổng quát:

```text
XGBoost dự đoán lợi suất 5 ngày
        ↓
generate_ml_views() chuyển đổi thành view dict
        ↓
build_views_matrix() tạo P, Q, confidence
        ↓
Black-Litterman tính posterior expected returns (mu_bl)
        ↓
MVO tối ưu trọng số dựa trên mu_bl
```

### 1.2 Vấn đề của phương pháp cũ (Linear Annualization + Hard Cap)

Trong code gốc, giá trị **Q** (lợi suất annualized) được tính như sau:

```python
# Phương pháp cũ
view_return_annual = pred_return * (TRADING_DAYS_PER_YEAR / prediction_horizon)
view_return_annual = max(-MAX_ANNUAL_VIEW, min(MAX_ANNUAL_VIEW, view_return_annual))
```

Với các tham số:
- `pred_return`: lợi suất dự đoán trong `prediction_horizon` ngày (mặc định 5 ngày)
- `TRADING_DAYS_PER_YEAR = 252`: số ngày giao dịch/năm
- `prediction_horizon = 5`: horizon dự đoán
- `ML_MIN_ALLOWED_PREDICTION_RETURN = 0.001`: ngưỡng tối thiểu để phát view
- `ML_MAX_ANNUAL_VIEW_THRESHOLD = 0.5`: ngưỡng giới hạn trên (hard cap)

Hệ số annualize là:

\[
\text{annual\_factor} = \frac{252}{5} = 50.4
\]

Khi đó, khoảng giá trị của `|view_return_annual|` là:

\[
[0.001 \times 50.4, \; 0.5] = [0.0504, \; 0.5]
\]

Tuy đã được nới rộng (so với `[0.252, 0.30]` của phiên bản cũ hơn), phương pháp này vẫn có **hai nhược điểm cơ bản**:

1. **Hard cap (chặn cứng)**: Mọi dự đoán có `pred_return` đủ lớn đều bị "cắt" ở cùng mức `0.5`, làm mất thông tin về cường độ tín hiệu. Hai dự đoán 1% và 3% (trong 5 ngày) đều ra cùng `Q = 0.5`.

2. **Không xét đến biến động (volatility)**: Một dự đoán 1% trên cổ phiếu biến động mạnh (vol cao) mang ý nghĩa thống kê yếu hơn nhiều so với cùng dự đoán trên cổ phiếu ổn định (vol thấp). Phương pháp cũ không phân biệt hai trường hợp này.

---

## 2. Các khái niệm toán học

### 2.1 Z-score (điểm chuẩn hóa)

**Z-score** đo lường một giá trị so với phân phối của nó, tính bằng đơn vị độ lệch chuẩn:

\[
z = \frac{x - \mu}{\sigma}
\]

Trong Option B, ta áp dụng z-score cho dự đoán:

\[
z = \frac{\text{pred\_return}}{\sigma_h}
\]

Trong đó:
- `pred_return`: lợi suất dự đoán của XGBoost (5 ngày)
- `\sigma_h`: độ lệch chuẩn của lợi suất trong `prediction_horizon` ngày, ước lượng từ dữ liệu lịch sử gần đây

Z-score trả lời câu hỏi: **"Dự đoán này lớn gấp bao nhiêu lần độ biến động thông thường của tài sản?"**

- `z = 0.5`: dự đoán bằng nửa độ biến động → tín hiệu yếu
- `z = 1.0`: dự đoán bằng một độ lệch chuẩn → tín hiệu vừa
- `z = 2.0`: dự đoán gấp đôi độ lệch chuẩn → tín hiệu mạnh

### 2.2 Độ biến động theo horizon (Horizon-scaled volatility)

Độ lệch chuẩn của lợi suất **1 ngày** được tính từ dữ liệu lịch sử gần đây (20 ngày giao dịch). Để chuyển sang độ lệch chuẩn cho `h` ngày, ta dùng quy tắc bình phương (square-root-of-time rule):

\[
\sigma_h = \sigma_{\text{daily}} \times \sqrt{h}
\]

Ví dụ với `h = 5`:

\[
\sigma_5 = \sigma_{\text{daily}} \times \sqrt{5} \approx \sigma_{\text{daily}} \times 2.236
\]

Quy tắc này giả định lợi suất daily tuân theo phân phối chuẩn và độc lập theo thời gian. Dù là giả định đơn giản hóa, nó được sử dụng rộng rãi trong tài chính định lượng.

### 2.3 Hàm tanh (Hyperbolic tangent)

Hàm **tanh** là một hàm sigmoid (hình chữ S) có giá trị đầu ra nằm trong khoảng `(-1, 1)`:

\[
\tanh(z) = \frac{e^z - e^{-z}}{e^z + e^{-z}}
\]

Các tính chất quan trọng:

| z | tanh(z) | Ý nghĩa |
|---|---|---|
| 0.0 | 0.000 | Không có tín hiệu |
| 0.5 | 0.462 | Tín hiệu nhẹ |
| 1.0 | 0.762 | Tín hiệu vừa |
| 1.5 | 0.905 | Tín hiệu mạnh |
| 2.0 | 0.964 | Tín hiệu rất mạnh |
| 3.0 | 0.995 | Gần bão hòa |

Đồ thị hàm tanh:

```text
  1.0 |                    ___________
      |                 _/
      |               _/
  0.5 |            _/
      |          /
  0.0 |________/
      |      /
 -0.5 |    /
      |  /
 -1.0 |/
      +---+---+---+---+---+---+---→ z
     -3  -2  -1   0   1   2   3
```

**Tại sao chọn tanh thay vì hard cap?**

| Đặc điểm | Hard cap (cắt cứng) | tanh (nén mềm) |
|---|---|---|
| Dự đoán yếu (z=0.3) | Bị phóng đại thành 0.15 (nếu pred đủ lớn) | Được giữ nhỏ: `0.5 * tanh(0.3) = 0.145` |
| Dự đoán vừa (z=1.0) | Có thể bị cắt | Được giữ nguyên cường độ: `0.5 * tanh(1.0) = 0.381` |
| Dự đoán cực mạnh (z=3.0) | Bị cắt tại 0.5 | Nén mềm về `0.5 * tanh(3.0) = 0.498` |
| Phân biệt z=1.0 vs z=2.0 | Không (cùng bị cắt) | Có: 0.381 vs 0.482 |
| Phân biệt z=0.3 vs z=0.8 | Không (cùng bị cắt hoặc cùng đủ lớn) | Có: 0.145 vs 0.304 |

Tóm lại, **tanh bảo toàn thông tin về cường độ tín hiệu** ở mọi mức độ, trong khi hard cap xóa thông tin ở vùng giá trị lớn.

---

## 3. Giải pháp Option B chi tiết

### 3.1 Công thức tổng hợp

View return annualized được tính bằng:

\[
\text{view\_return\_annual} = \text{MAX\_ANNUAL\_VIEW} \times \tanh\left(\frac{\text{pred\_return}}{\sigma_h}\right)
\]

Trong đó:
- `MAX_ANNUAL_VIEW = ML_MAX_ANNUAL_VIEW_THRESHOLD = 0.5` (giá trị tiệm cận khi z → ∞)
- `pred_return`: dự đoán lợi suất `h` ngày từ XGBoostEnsembleModel
- `σ_h = std(returns_daily, 20 ngày) × √h`: độ biến động trong `h` ngày

### 3.2 Ý nghĩa từng bước

```text
Bước 1: Tính độ biến động
   σ_h = std(returns_daily gần đây, 20 ngày) × √5
   → Ước lượng "biến động thông thường" của tài sản trong 5 ngày

Bước 2: Tính z-score
   z = pred_return / σ_h
   → "Dự đoán này mạnh gấp bao nhiêu lần biến động thông thường?"

Bước 3: Ánh xạ tanh
   view_return_annual = 0.5 × tanh(z)
   → Chuyển z-score thành lợi suất annualized, nén mềm về [-0.5, +0.5]
```

### 3.3 Ví dụ số liệu

Giả sử 2 cổ phiếu có cùng dự đoán `pred_return = 0.005` (0.5% trong 5 ngày):

| Tài sản | σ_daily | σ_5 = σ_daily × √5 | z = 0.005 / σ_5 | view_annual = 0.5 × tanh(z) |
|---|---|---|---|---|
| Cổ phiếu A (ít biến động) | 0.008 | 0.01789 | 0.279 | **0.136** |
| Cổ phiếu B (nhiều biến động) | 0.020 | 0.04472 | 0.112 | **0.056** |

**Cùng dự đoán 0.5%, nhưng cổ phiếu A (ít biến động) nhận view lớn gấp ~2.4 lần cổ phiếu B (nhiều biến động).**

Điều này phản ánh nguyên lý: **cùng một mức dự đoán, tín hiệu trên tài sản ít biến động đáng tin cậy hơn và nên có tác động lớn hơn lên posterior của BL.**

### 3.4 So sánh với phương pháp cũ

| Tình huống | Phương pháp cũ (linear + cap) | Option B (tanh + vol) |
|---|---|---|
| pred=0.005, σ_daily=0.008 | `0.005 × 50.4 = 0.252` | `0.5 × tanh(0.279) = 0.136` |
| pred=0.005, σ_daily=0.020 | `0.005 × 50.4 = 0.252` | `0.5 × tanh(0.112) = 0.056` |
| pred=0.010, σ_daily=0.008 | `0.010 × 50.4 = 0.504 → cap 0.5` | `0.5 × tanh(0.558) = 0.263` |
| pred=0.010, σ_daily=0.020 | `0.010 × 50.4 = 0.504 → cap 0.5` | `0.5 × tanh(0.224) = 0.110` |
| pred=0.020, σ_daily=0.020 | `0.020 × 50.4 = 1.008 → cap 0.5` | `0.5 × tanh(0.447) = 0.207` |

**Nhận xét:**
- Phương pháp cũ cho cùng kết quả (`0.252` hoặc `0.5`) bất kể biến động → mất thông tin
- Option B cho **6 giá trị khác nhau** cho 5 tình huống → bảo toàn thông tin về cả cường độ tín hiệu lẫn đặc tính rủi ro của tài sản

---

## 4. Cài đặt trong code

### 4.1 Hàm `generate_ml_views()` — `gen_view/view_generators.py`

```python
def generate_ml_views(
    predictions: dict[str, tuple[float, float]],
    prediction_horizon: int = DEFAULT_PREDICTION_HORIZON,
    min_return_threshold: float = ML_MIN_ALLOWED_PREDICTION_RETURN,
    model_type: str = "xgboost",
    returns: Optional[pd.DataFrame] = None,   # ← THÊM MỚI
    vol_lookback: int = 20,                    # ← THÊM MỚI
) -> list[dict]:
```

**Tham số mới:**
- `returns`: DataFrame chứa lợi suất daily của các tài sản (columns = tên tài sản). Khi được cung cấp, Option B sẽ được kích hoạt.
- `vol_lookback`: số ngày giao dịch dùng để tính độ biến động (mặc định 20).

**Logic chính:**

```python
# --- Bước 1: Tính độ biến động horizon-scaled cho từng tài sản ---
vol_h = {}
if returns is not None:
    for asset in predictions:
        if asset in returns.columns:
            recent_ret = returns[asset].dropna().tail(vol_lookback)
            if len(recent_ret) >= 5:
                vol_h[asset] = recent_ret.std() * sqrt(prediction_horizon)

# --- Bước 2 & 3: Tính z-score và ánh xạ tanh ---
for asset, (pred_return, confidence) in predictions.items():
    if abs(pred_return) < min_return_threshold:
        continue

    if asset in vol_h and vol_h[asset] > 1e-8:
        z_score = pred_return / vol_h[asset]
        view_return_annual = ML_MAX_ANNUAL_VIEW_THRESHOLD * tanh(z_score)
    else:
        # Fallback: linear annualization khi không có dữ liệu returns
        view_return_annual = pred_return * (TRADING_DAYS_PER_YEAR / prediction_horizon)
        view_return_annual = clip(view_return_annual, -MAX, +MAX)
```

### 4.2 Hàm `generate_ranking_abs_mode_views()` — `backtest/_ranking_helpers.py`

Hàm gọi được cập nhật để truyền dữ liệu returns:

```python
def generate_ranking_abs_mode_views(
    t, ranking_abs_model, selected_stocks, ranking_universe_prices,
    active_asset_names, returns,   # ← THÊM MỚI
):
    # ...
    # Cắt dữ liệu returns gần đây (20 ngày) cho đến thời điểm t
    vol_start = max(0, t - 20)
    recent_returns = returns.iloc[vol_start:t]

    ml_views = generate_ml_views(
        predictions,
        prediction_horizon=ranking_abs_model.prediction_horizon,
        min_return_threshold=ML_MIN_ALLOWED_PREDICTION_RETURN,
        returns=recent_returns,   # ← TRUYỀN VÀO
    )
```

### 4.3 Tính tương thích ngược (Backward compatibility)

- Hai tham số mới `returns` và `vol_lookback` đều có giá trị mặc định (`None` và `20`).
- Khi `returns = None`, hàm tự động fallback về phương pháp linear annualization cũ.
- Các caller khác (`backtest/_views.py`, `gen_view/xgboost/model_train.py`) không cần thay đổi — chúng vẫn hoạt động như trước.

---

## 5. Thuật ngữ tham chiếu

| Thuật ngữ | Tiếng Việt | Giải thích |
|---|---|---|
| **View** | Nhận định | Nhận định về lợi suất kỳ vọng của tài sản |
| **Annualized return** | Lợi suất quy năm | Lợi suất quy đổi ra thang năm để so sánh |
| **Volatility** | Độ biến động | Độ lệch chuẩn của lợi suất, đo mức rủi ro |
| **Horizon-scaled volatility** | Độ biến động theo horizon | σ_daily × √h, biến động trong h ngày |
| **Z-score** | Điểm chuẩn hóa | Tỷ lệ giữa giá trị và độ lệch chuẩn |
| **tanh** | Tang hyperbolic | Hàm nén mềm, ánh xạ R → (-1, 1) |
| **Hard cap** | Chặn cứng | Cắt giá trị tại ngưỡng cố định, mất thông tin |
| **Soft cap / compression** | Nén mềm | Nén giá trị về khoảng cố định nhưng bảo toàn thông tin thứ bậc |
| **Black-Litterman (BL)** | — | Mô hình kết hợp prior (market equilibrium) với views của nhà đầu tư |
| **Posterior** | Phân phối hậu nghiệm | Kết quả sau khi BL kết hợp prior và views |
| **Omega matrix** | Ma trận Omega | Ma trận hiệp phương sai của sai số view, được suy ra từ confidence |
| **Walk-forward** | — | Phương pháp backtest: huấn luyện trên cửa sổ trượt, dự đoán phía trước |
| **Ensemble** | Tập hợp | Nhiều mô hình với seed khác nhau, lấy trung bình dự đoán |

---

## 6. Cách rollback (khôi phục phương pháp cũ)

Nếu thí nghiệm Option B không mang lại kết quả tốt hơn, có thể rollback dễ dàng:

**Bước 1:** Trong `gen_view/view_generators.py`, bỏ comment 2 dòng phương pháp cũ và comment block Option B:

```python
# --- Phương pháp cũ (bỏ comment để rollback) ---
view_return_annual = pred_return * (TRADING_DAYS_PER_YEAR / prediction_horizon)
view_return_annual = max(-ML_MAX_ANNUAL_VIEW_THRESHOLD, min(ML_MAX_ANNUAL_VIEW_THRESHOLD, view_return_annual))

# --- Option B (comment lại khi rollback) ---
# if asset in vol_h and vol_h[asset] > 1e-8:
#     z_score = pred_return / vol_h[asset]
#     view_return_annual = ML_MAX_ANNUAL_VIEW_THRESHOLD * np.tanh(z_score)
# else:
#     view_return_annual = pred_return * (TRADING_DAYS_PER_YEAR / prediction_horizon)
#     view_return_annual = max(-ML_MAX_ANNUAL_VIEW_THRESHOLD, min(ML_MAX_ANNUAL_VIEW_THRESHOLD, view_return_annual))
```

**Bước 2:** Không cần thay đổi gì ở `_ranking_helpers.py` — tham số `returns` vẫn được truyền nhưng sẽ bị bỏ qua bởi phương pháp cũ.

---

## 7. Kỳ vọng cải thiện

| Khía cạnh | Trước | Sau |
|---|---|---|
| Phân biệt cường độ tín hiệu | Không (hard cap) | Có (tanh nén mềm) |
| Điều chỉnh theo rủi ro tài sản | Không | Có (z-score) |
| Khoảng giá trị Q | [0.0504, 0.5] (hẹp, nhiều giá trị bị cap) | [~0.01, ~0.50] (rộng, phân tán) |
| Thông tin trong BL posterior | Thấp (Q đồng nhất) | Cao (Q phản ánh cả dự đoán lẫn biến động) |

Kỳ vọng chính: **BL posterior sẽ phản ánh chính xác hơn chất lượng tín hiệu**, từ đó cải thiện hiệu suất chiến lược BL và HYBRID trong backtest.
