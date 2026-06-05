# Hướng dẫn chạy Portfolio Optimization

## 1. Cài đặt môi trường

```bash
# Clone repository
# git clone <REPO_URL>
cd portfolio-optimization

# Tạo virtual environment
python3.12 -m venv venv
source venv/bin/activate  # macOS/Linux
# hoặc: venv\Scripts\activate  # Windows

# Cài dependencies
pip install -r requirements.txt
```

## 2. Thu thập dữ liệu (nếu cần cập nhật)

```bash
python crawl/stock.py
python crawl/fund.py
python crawl/gold.py
```

## 3. Cấu hình dự án

Tất cả tham số mặc định đã được tập trung vào `config.py` (ở root dự án):

```python
# config.py - Tham số chung
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.06

# Data split
TRAIN_START_DATE = "2020-01-01"
SPLIT_DATE = "2023-10-01"
TEST_END_DATE = "2026-03-01"

# Backtest
BACKTEST_PHASE = "train"
WINDOW = 20
REBALANCE_FREQ = 5
INITIAL_NAV = 1.0

# Black-Litterman
BL_TAU = 0.05
BL_DELTA = 2.5
BL_VIEW_CONFIDENCE = 0.5

# View generation
VIEW_MODE = "combined"        # mặc định hiện tại
COMBINED_VIEW_WEIGHTS = (0.4, 0.3, 0.3, 0.0)  # (rule, relative, ml, static)

# ML defaults
ML_MODEL_TYPE = "xgboost"
DEFAULT_FEATURE_WINDOW = 20
DEFAULT_PREDICTION_HORIZON = 5
ML_MIN_RETURN_THRESHOLD = 0.005
```

Module XGBoost có thêm file cấu hình riêng tại `gen_view/xgboost/config.py` (hyperparams, feature periods, confidence heuristic).

Chỉnh trực tiếp `config.py` để thay đổi mặc định, hoặc dùng CLI flags để ghi đè khi chạy.

## 4. Chạy backtest nhanh

```bash
# Mặc định: phase=test, view_mode=combined
python backtest.py

# Không vẽ chart
python backtest.py --no-plot

# Chạy theo train period
python backtest.py --phase train

# Chạy với mode rule_based
python backtest.py --phase test --view-mode rule_based

# Chạy với mode relative
python backtest.py --phase test --view-mode relative

# Chạy với bộ assets tùy chọn
python backtest.py --assets E1VFVN30,GOLD,DCDS
```

## 5. Cấu hình assets bằng JSON

Backtest đọc danh sách tài sản từ `assets.json` (mặc định ở root dự án).

Ví dụ:

```json
{
  "default_selection": ["E1VFVN30", "GOLD", "DCDS", "MBBOND"],
  "assets": {
    "E1VFVN30": {
      "full_path": "datasets/stocks/full/E1VFVN30.csv",
      "train_path": "datasets/stocks/train/E1VFVN30_train.csv",
      "test_path": "datasets/stocks/test/E1VFVN30_test.csv",
      "date_col": "date",
      "price_col": "close"
    }
  }
}
```

Quy tắc chọn assets:
- Nếu truyền `--assets`, script sẽ dùng đúng danh sách này
- Nếu không truyền `--assets`, script dùng `default_selection`
- Nếu không có `default_selection`, script dùng tất cả keys trong `assets`

Dùng file config khác:

```bash
python backtest.py --assets-config path/to/custom_assets.json
```

## 6. View modes hiện có

```bash
# rule-based: EMA + RSI + momentum
python backtest.py --view-mode rule_based

# relative: momentum giữa cặp assets
python backtest.py --view-mode relative

# ML views (XGBoost)
python backtest.py --view-mode ml --ml-model-type xgboost

# kết hợp rule_based + relative + ml + static (mặc định)
python backtest.py --view-mode combined --ml-model-type xgboost
```

## 7. Train model XGBoost cho ML views

ML mode cần model đã train trước. Script train:

```bash
python gen_view/xgboost/model_train.py --method xgboost --train-phase train --validate
```

Tùy chọn thường dùng:

```bash
# Train với tập assets chỉ định
python gen_view/xgboost/model_train.py \
  --method xgboost \
  --train-phase train \
  --assets E1VFVN30,GOLD,DCDS,MBBOND \
  --validate

# Train trên full phase
python gen_view/xgboost/model_train.py --method xgboost --train-phase full
```

Model được lưu tại:
- `gen_view/xgboost/.cache/xgboost_models.pkl`

Sau khi train, chạy backtest với ML:

```bash
python backtest.py --phase test --view-mode ml --ml-model-type xgboost
```

## 8. So sánh nhanh rule-based và ML

```bash
python run_compare_backtests.py --phase test
```

Output mặc định:
- `reports/backtest_compare_views.csv`
- `reports/backtest_compare_views.png`

## 9. Lỗi thường gặp

1. Báo không tìm thấy model khi chạy `--view-mode ml`:
- Train model trước bằng `gen_view/xgboost/model_train.py`

2. Báo lỗi không tìm thấy asset trong config:
- Kiểm tra tên asset trong `assets.json` và giá trị `--assets`

3. Dữ liệu quá ngắn:
- Kiểm tra dữ liệu CSV có đủ lịch sử để tính window 20 ngày + features
