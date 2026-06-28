# Technical Indicators for Dynamic View Generation

Tài liệu này mô tả các chỉ báo kỹ thuật được dùng trong `gen_view/view_generators.py` và một phần trong `gen_view/xgboost/xgboost_core.py`.

Tham số cấu hình nằm tại:
- `config.py`: tham số toàn dự án (BL, view mode, ML defaults)
- `gen_view/xgboost/config.py`: tham số riêng module XGBoost (hyperparams, feature periods, confidence heuristic)

## 1. Tổng quan

Pipeline tổng quát:

```text
Price data -> Indicators -> Signals/Predictions -> Views -> Black-Litterman
```

Trong code hiện tại:
- Rule-based views: sử dụng EMA, RSI, mômen-tum
- Relative views: sử dụng mômen-tum chênh lệch giữa các cặp tài sản
- ML views (XGBoost): sử dụng bộ feature kỹ thuật (mômen-tum/EMA/RSI/MACD/độ biến động)

## 2. Đường trung bình động

### 2.1 SMA (Đường trung bình)  

```text
SMA(n) = (P1 + ... + Pn) / n
```

`compute_sma(prices, period)`

### 2.2 EMA (Đường trung bình có trọng số)

```text
EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}
alpha = 2 / (period + 1)
```

`compute_ema(prices, period)`

Rule-based mặc định dùng:
- EMA ngắn hạn: 10
- EMA dài hạn: 30

Tín hiệu:
- `(EMA_10 / EMA_30 - 1) > 0.02` -> xu hướng tăng
- `(EMA_10 / EMA_30 - 1) < -0.02` -> xu hướng giảm

## 3. Động lực giá

### 3.1 ROC / Động lực giá

```text
Momentum(n) = P_t / P_{t-n} - 1
```

`compute_momentum(prices, period=20)`

Dùng trong:
- Rule-based: điều chỉnh mức lợi suất kỳ vọng
- Relative: so sánh tài sản A vs B
- ML features: momentum_5, momentum_10, momentum_20

## 4. RSI (Chỉ số sức mạnh tương đối)

```text
RSI = 100 - 100 / (1 + RS)
RS = Lợi suất trung bình / Mất mát trung bình
```

`compute_rsi(prices, period=14)`

Dùng trong rule-based để điều chỉnh độ tin cậy:
- RSI > 70: giảm độ tin cậy xu hướng tăng, tăng độ tin cậy xu hướng giảm
- RSI < 30: giảm độ tin cậy xu hướng giảm, tăng độ tin cậy xu hướng tăng

## 5. MACD (Hội tụ và phân kỳ của đường trung bình động)

```text
MACD = EMA(12) - EMA(26)
Tín hiệu = EMA(MACD, 9)
Nhiệt biểu = MACD - Tín hiệu
```

`compute_macd(prices)`

Trong code hiện tại, nhiệt biểu MACD được dùng trong bộ feature của `XGBoostCoreModel`.

## 6. Dải Bollinger và ATR (Phạm vi dao động thực)

Hai chỉ báo này đã có hàm tiện ích:
- `compute_bollinger_bands(prices, period=20, num_std=2.0)` - Dải Bollinger
- `compute_atr(high, low, close, period=14)` - Phạm vi dao động thực

Trạng thái sử dụng:
- Có sẵn để mở rộng và hiển thị biểu đồ
- Không nằm trong quy tắc rule-based mặc định hiện tại

## 7. Ngưỡng mặc định trong code

Rule-based (trong `view_generators.py`):
- `DEFAULT_MA_SHORT = 10` - Độ dài EMA ngắn hạn
- `DEFAULT_MA_LONG = 30` - Độ dài EMA dài hạn
- `DEFAULT_RSI_PERIOD = 14` - Chu kỳ RSI
- `DEFAULT_MOMENTUM_PERIOD = 20` - Chu kỳ động lực
- `MA_CROSSOVER_THRESHOLD = 0.02` - Ngưỡng cắt ngang đường trung bình
- `MOMENTUM_THRESHOLD = 0.01` - Ngưỡng động lực
- `RSI_OVERBOUGHT = 70` - Mức RSI quá mua
- `RSI_OVERSOLD = 30` - Mức RSI quá bán

Black-Litterman (trong `config.py`):
- `BL_TAU = 0.05` - Tham số điều chỉnh mô hình
- `BL_DELTA = 2.5` - Hệ số rủi ro
- `BL_VIEW_DEFAULT_CONFIDENCE_WHEN_NULL = 0.5` - Độ tin cậy mặc định

ML Defaults (trong `config.py`):
- `DEFAULT_FEATURE_WINDOW = 20` - Cửa sổ feature
- `DEFAULT_PREDICTION_HORIZON = 5` - Horizon dự đoán

XGBoost (trong `gen_view/xgboost/config.py`):
- `MOMENTUM_PERIODS = [5, 10, 20]` - Các chu kỳ động lực
- `RSI_PERIOD = 14` - Chu kỳ RSI
- `MA_SHORT_PERIOD = 10` / `MA_LONG_PERIOD = 30` - Chu kỳ MA
- `VOLATILITY_WINDOW = 20` - Cửa sổ biến động
- `CONFIDENCE_MIN/MAX/BASE = 0.3/0.9/0.6` - Heuristic độ tin cậy

## 8. Các hàm liên quan

- Static (Cố định): `generate_static_views()`
- Rule-based (Quy tắc): `generate_rule_based_views()`
- Relative (So sánh tương đối): `generate_relative_views()`
- ML views: `generate_ml_views()`
- Xây dựng P/Q/độ tin cậy: `build_views_matrix()`
- Kết hợp quan điểm: `combine_views()`

Logic máy học XGBoost nằm ở:
- `gen_view/xgboost/xgboost_core.py` (`XGBoostCoreModel`)
