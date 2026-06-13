# Portfolio Optimization - Thị trường Việt Nam

Dự án nghiên cứu tối ưu hóa danh mục đầu tư cho thị trường Việt Nam, tập trung vào việc so sánh các chiến lược phân bổ tài sản và cải tiến mô hình Black-Litterman bằng views động.

## Mục lục

1. [Tổng quan](#tổng-quan)
2. [Cấu trúc dự án](#cấu-trúc-dự-án)
3. [Các chiến lược tối ưu hóa](#các-chiến-lược-tối-ưu-hóa)
4. [View generation modes](#view-generation-modes)
5. [Cách sử dụng nhanh](#cách-sử-dụng-nhanh)
6. [Kết quả và báo cáo](#kết-quả-và-báo-cáo)

---

## Tổng quan

### Mục tiêu nghiên cứu

1. Thu thập dữ liệu thị trường Việt Nam (ETF/cổ phiếu, vàng, quỹ mô)
2. So sánh hiệu quả 3 chiến lược phân bổ: Equal Weight, MVO, Black-Litterman
3. Đánh giá tác động của views động (rule-based, relative, ML XGBoost)

### Tài sản

Danh sách tài sản được quản lý bởi `assets.json` (không hardcode trong code). Script sẽ:
- Đọc `default_selection` nếu không truyền `--assets`
- Hỗ trợ train/test/full theo cấu hình path mỗi tài sản

### Phân chia dữ liệu mặc định

- Train: `2020-01-01 -> 2023-10-01`
- Test: `2023-10-01 -> 2026-03-01`
- Full: `2020-01-01 -> 2026-03-01`

(Cấu hình tại `config.py`: `TRAIN_START_DATE`, `SPLIT_DATE`, `TEST_END_DATE`)

---

## Cấu trúc dự án

```text
portfolio-optimization/
|- config.py              # project-wide configuration constants
|- assets.json            # asset universe configuration
|- requirements.txt
|- README.md
|- QUICKSTART.md
|
|- backtest/              # backtest package (python -m backtest ...)
|  |- __init__.py         # re-export facade for backward compatibility
|  |- __main__.py         # CLI entry point (python -m backtest)
|  |- _loop.py            # core walk-forward backtest loop
|  |- _optimizer.py       # MVO optimisation (standard + constrained)
|  |- _black_litterman.py # BL posterior returns
|  |- _views.py           # dynamic view generation dispatch
|  |- _ranking_helpers.py # shared ranking/ranking_absolute helpers
|  |- _data_helpers.py    # VN30 universe, market proxy, ML model loading
|  |- _metrics.py         # Sharpe, MDD, Sortino, Calmar, etc.
|  |- _compare.py         # shared comparison utilities
|  |- _compare_backtests.py  # compare rule_based/ml/ranking modes
|  |- _compare_ranking.py    # compare ranking vs ranking_absolute
|  |- _prediction.py      # next-period weight prediction
|  |- _cli.py             # CLI argument parsing
|  `- _main.py            # main entry point
|
|- gen_view/
|  |- view_generators.py  # rule-based, relative, ML view generation
|  |- xgboost/
|  |  |- config.py
|  |  |- xgboost_core.py
|  |  `- model_train.py
|  `- ranking/
|     |- stock_selection.py
|     |- ranking_model.py
|     |- relative_views.py
|     `- risk_management.py
|
|- utils/
|  |- data_loader.py
|  `- view_logger.py
|
|- crawl/
|  |- stock.py
|  |- fund.py
|  `- gold.py
|
|- datasets/
|  |- stocks/
|  |- funds/
|  `- gold/
|
|- docs/
|
`- reports/
```

---

## Các chiến lược tối ưu hóa

### 1. Equal Weight (EW)

Phân bổ đều:

```text
w_i = 1 / n
```

### 2. Mean-Variance Optimization (MVO)

```text
max   mu^T w - lambda * w^T Sigma w
s.t.  sum(w_i) = 1, w_i >= 0
```

### 3. Black-Litterman (BL)

Kết hợp equilibrium returns với views:

```text
mu_BL = [(tau Sigma)^-1 + P^T Omega^-1 P]^-1 * [(tau Sigma)^-1 pi + P^T Omega^-1 Q]
```

---

## View generation modes

`backtest` package hỗ trợ 6 modes:

1. `rule_based`: EMA crossover + RSI + momentum
2. `relative`: so sánh momentum giữa các cặp assets
3. `ml`: views từ model XGBoost đã train trước
4. `combined`: kết hợp rule_based + relative + ml + static theo trọng số
5. `ranking`: K-Medoids selection + XGBoost Ranker → relative views
6. `ranking_absolute`: K-Medoids selection + XGBoost Ensemble → absolute views

Lưu ý:
- ML mode hiện tại chỉ hỗ trợ `xgboost`
- Cần train model trước, sau đó backtest chỉ load model từ cache
- Static views (`STATIC_VIEWS` trong `config.py`) được gộp vào combined mode với trọng số riêng

---

## Cách sử dụng nhanh

```bash
# 1) Cài đặt
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2) Chạy backtest mặc định
python -m backtest --phase train

# 3) Train model XGBoost
python gen_view/xgboost/model_train.py --method xgboost --train-phase train --validate

# 4) Chạy BL với views từ ML
python -m backtest --phase test --view-mode ml --ml-model-type xgboost

# 5) So sánh rule_based vs ml vs ranking
python -m backtest._compare_backtests --phase train --no-plot

# 6) So sánh ranking vs ranking_absolute
python -m backtest._compare_ranking --phase train --no-plot
```

Hướng dẫn chi tiết: xem `QUICKSTART.md`.

---

## Kết quả và báo cáo

Thư mục `reports/` lưu các kết quả so sánh và log backtest. Ví dụ:
- `reports/backtest_compare_views.csv`
- `reports/backtest_ml_xgboost.txt`

Khuyến nghị:
- Regenerate report sau mỗi lần thay đổi logic views/model
- Không sử dụng report cũ để kết luận nếu code đã thay đổi

---

## Files quan trọng

- `config.py`: cấu hình toàn dự án (BL params, view mode, ML defaults, ranking params)
- `backtest/`: package backtest chính (loop, optimizer, BL, views, metrics)
- `backtest/__main__.py`: CLI entry point (`python -m backtest`)
- `backtest/_compare_backtests.py`: so sánh rule_based / ml / ranking
- `backtest/_compare_ranking.py`: so sánh ranking vs ranking_absolute
- `gen_view/view_generators.py`: rule-based/relative/ML views + utilities
- `gen_view/xgboost/xgboost_core.py`: `XGBoostCoreModel` (train, predict, save, load)
- `gen_view/xgboost/model_train.py`: train model XGBoost
- `utils/data_loader.py`: load assets config + đồng bộ dữ liệu
- `assets_1.json`: cấu hình universe tài sản
