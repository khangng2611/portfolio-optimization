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

(Cấu hình tại `utils/data_loader.py`)

---

## Cấu trúc dự án

```text
portfolio-optimization/
|- backtest.py
|- config.py              # project-wide configuration constants
|- run_compare_backtests.py
|- inspect_ew_vs_assets.py
|- assets.json
|- requirements.txt
|- README.md
|- QUICKSTART.md
|
|- utils/
|  |- data_loader.py
|  |- plotting.py
|
|- gen_view/
|  |- view_generators.py    # rule-based, relative, ML view generation + utilities
|  |- xgboost/
|     |- config.py           # XGBoost module configuration
|     |- xgboost_core.py
|     |- model_train.py
|
|- crawl/
|  |- stock.py
|  |- fund.py
|  |- gold.py
|
|- datasets/
|  |- stocks/
|  |- funds/
|  |- gold/
|
|- docs/
|  |- DYNAMIC_VIEWS_REPORT.md
|  |- INDICATORS.md
|  |- GEN_VIEW_LLM_GUIDE.md
|  |- HOW_TO_USE_LLM_GENERATORS.md
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

`backtest.py` hỗ trợ 4 modes:

1. `rule_based`: EMA crossover + RSI + momentum
2. `relative`: so sánh momentum giữa các cặp assets
3. `ml`: views từ model XGBoost đã train trước
4. `combined`: kết hợp rule_based + relative + ml + static theo trọng số

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

# 2) Chạy backtest mặc định (rule_based)
python backtest.py --phase train

# 3) Train model XGBoost
python gen_view/xgboost/model_train.py --method xgboost --train-phase train --validate

# 4) Chạy BL với views từ ML
python backtest.py --phase test --view-mode ml --ml-model-type xgboost

# 5) So sánh rule_based vs ml
python run_compare_backtests.py --phase test
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

- `config.py`: cấu hình toàn dự án (BL params, view mode, ML defaults, static views)
- `gen_view/xgboost/config.py`: cấu hình riêng module XGBoost (hyperparams, feature periods, confidence heuristic)
- `backtest.py`: luồng backtest chính + CLI
- `utils/data_loader.py`: load assets config + đồng bộ dữ liệu
- `gen_view/view_generators.py`: rule-based/relative/ML views + utilities P,Q,confidence
- `gen_view/xgboost/xgboost_core.py`: `XGBoostCoreModel` (train, predict, save, load)
- `gen_view/xgboost/model_train.py`: train model XGBoost
- `assets.json`: cấu hình universe tài sản
