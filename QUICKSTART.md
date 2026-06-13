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
# Mặc định: phase=train, view_mode=ranking_absolute
python -m backtest

# Không vẽ chart
python -m backtest --no-plot

# Chạy theo train period
python -m backtest --phase train

# Chạy với mode rule_based
python -m backtest --phase test --view-mode rule_based

# Chạy với mode relative
python -m backtest --phase test --view-mode relative

# Chạy với bộ assets tùy chọn
python -m backtest --assets E1VFVN30,GOLD,DCDS
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
python -m backtest --assets-config path/to/custom_assets.json
```

## 6. View modes hiện có

```bash
# rule-based: EMA + RSI + momentum
python -m backtest --view-mode rule_based

# relative: momentum giữa cặp assets
python -m backtest --view-mode relative

# ML views (XGBoost)
python -m backtest --view-mode ml --ml-model-type xgboost

# kết hợp rule_based + relative + ml + static
python -m backtest --view-mode combined --ml-model-type xgboost

# ranking: K-Medoids + XGBoost Ranker → relative views
python -m backtest --view-mode ranking

# ranking_absolute: K-Medoids + XGBoost Ensemble → absolute views
python -m backtest --view-mode ranking_absolute
```

## 7. Ranking Mode (Enhanced Pipeline)

The ranking mode implements a representative stock selection + pairwise ranking approach:

### Quick Start

```bash
# Run ranking backtest on training period
python -m backtest --phase train --view-mode ranking --assets-config assets_1.json --no-plot

# Compare all view modes (rule_based / ml / ranking)
python -m backtest._compare_backtests --phase train --no-plot

# Compare ranking vs ranking_absolute
python -m backtest._compare_ranking --phase train --no-plot
```

### Pipeline

1. **K-Medoids Selection**: Selects K=5 representative stocks from VN30 universe
2. **XGBoost Ranker**: Predicts relative stock performance using LambdaMART
3. **Relative Views**: Generates pairwise BL views (Stock A > Stock B)
4. **Black-Litterman**: Incorporates relative views with dynamic confidence
5. **MVO**: Optimizes combined portfolio (K stocks + Gold + MBBOND)

### Configuration (config.py)

- `RANKING_K`: Number of representative stocks (default: 5)
- `RANKING_RETRAIN_FREQUENCY`: Retrain ranker every N days (default: 20)
- `RANKING_RESELECT_FREQUENCY`: Re-run K-Medoids every N days (default: 60)
- `RANKING_VIEW_SPREAD`: Annual spread for relative views (default: 0.03)

## 8. Train model XGBoost cho ML views

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
python -m backtest --phase test --view-mode ml --ml-model-type xgboost
```

## 9. So sánh nhanh các mode

```bash
# So sánh rule_based vs ml vs ranking
python -m backtest._compare_backtests --phase train --no-plot

# So sánh ranking vs ranking_absolute
python -m backtest._compare_ranking --phase train --no-plot
```

Output mặc định:
- `reports/backtest_compare_views.csv` + `.png`
- `reports/ranking_compare.csv` + `.png`

## 10. Lỗi thường gặp

1. Báo không tìm thấy model khi chạy `--view-mode ml`:
- Train model trước bằng `gen_view/xgboost/model_train.py`

2. Báo lỗi không tìm thấy asset trong config:
- Kiểm tra tên asset trong `assets.json` và giá trị `--assets`

3. Dữ liệu quá ngắn:
- Kiểm tra dữ liệu CSV có đủ lịch sử để tính window 20 ngày + features
