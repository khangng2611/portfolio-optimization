# Hướng dẫn sử dụng ML View Generator (trong llm_view_generators.py)

## 1. Tổng quan

Mặc dù tên file là `llm_view_generators.py`, trạng thái code hiện tại:

- Active: `TraditionalMLViewGenerator` (XGBoost)
- Không active trong backtest: LSTM/LLM classes (chỉ còn ở dạng ý tưởng/comment)

Tài liệu này hướng dẫn cách dùng luồng đang hoạt động.

## 2. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

Tối thiểu cần:
- `scikit-learn`
- `xgboost`
- `pandas`, `numpy`

## 3. Cách train model XGBoost

Dùng script train có sẵn:

```bash
python view_llm/xgboost_train.py --method xgboost --train-phase train --validate
```

Tùy chọn:

```bash
# Train với danh sách assets cụ thể
python view_llm/xgboost_train.py \
  --method xgboost \
  --assets E1VFVN30,GOLD,DCDS,MBBOND \
  --train-phase train \
  --validate

# Train trên full phase
python view_llm/xgboost_train.py --method xgboost --train-phase full
```

Model output:
- `view_llm/.cache/xgboost_models.pkl`

## 4. Dùng model trong backtest

```bash
python backtest.py --phase test --view-mode ml --ml-model-type xgboost
```

Mode `combined` cũng cần model cache:

```bash
python backtest.py --phase test --view-mode combined --ml-model-type xgboost
```

## 5. Sử dụng class trực tiếp trong Python

```python
from pathlib import Path
import pandas as pd
from view_llm.llm_view_generators import TraditionalMLViewGenerator

# prices: DataFrame cột là assets, index là datetime
prices = pd.read_csv("your_prices.csv", index_col=0, parse_dates=True)

gen = TraditionalMLViewGenerator(
    model_type="xgboost",
    feature_window=20,
    prediction_horizon=5,
)

# Huấn luyện
gen.train(prices, verbose=True)

# Lưu
gen.save(Path("view_llm/.cache/xgboost_models.pkl"))

# Tải lại
gen.load(Path("view_llm/.cache/xgboost_models.pkl"))

# Sinh views
views = gen.generate_views(prices.tail(120), min_return_threshold=0.005)
for v in views:
    print(v["name"], v["view_return_annual"], v["confidence"])
```

## 6. Cơ chế feature và nhãn (label)

Features mặc định:
- momentum_5, momentum_10, momentum_20
- rsi_14
- ma_ratio_10_30
- volatility_20
- macd_hist
- price_std_20

Nhãn:
- Forward return theo `prediction_horizon` ngày

Sinh views:
- Nếu `abs(pred_return) < min_return_threshold` thì bỏ qua
- Ngược lại annualize return và tạo absolute view cho tài sản

## 7. Khắc phục sự cố

1. Lỗi không tìm thấy model khi chạy `--view-mode ml`
- Huấn luyện trước bằng `view_llm/xgboost_train.py`
- Kiểm tra file `view_llm/.cache/xgboost_models.pkl`

2. Lỗi import xgboost

```bash
pip install xgboost
```

3. Không sinh được view nào
- Kiểm tra độ dài dữ liệu
- Giảm `min_return_threshold`
- Kiểm tra model đã train đủ số tài sản cần test

## 8. Ghi chú về LLM

`test_llm.py` và nội dung LLM trong repo hiện ở trạng thái nghiên cứu/thử nghiệm, không phải luồng chính đang được backtest production.
