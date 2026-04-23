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

(Cấu hình tại `data_loader.py`)

---

## Cấu trúc dự án

```text
portfolio-optimization/
|- backtest.py
|- data_loader.py
|- view_generators.py
|- run_compare_backtests.py
|- assets.json
|- requirements.txt
|- README.md
|- QUICKSTART.md
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
|- view_llm/
|  |- llm_view_generators.py
|  |- xgboost_train.py
|  |- .cache/
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

`backtest.py` hỗ trợ đầy đủ 5 modes:

1. `static`: views cố định trong code
2. `rule_based`: EMA crossover + RSI + momentum
3. `relative`: so sánh momentum giữa các cặp assets
4. `ml`: views từ model XGBoost đã train trước
5. `combined`: kết hợp rule_based + relative + ml theo trọng số

Lưu ý:
- ML mode hiện tại chỉ hỗ trợ `xgboost`
- Cần train model trước, sau đó backtest chỉ load model từ cache

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
python view_llm/xgboost_train.py --method xgboost --train-phase train --validate

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

- `backtest.py`: luồng backtest chính + CLI
- `data_loader.py`: load assets config + đồng bộ dữ liệu
- `view_generators.py`: rule-based/relative + utilities P,Q,confidence
- `view_llm/llm_view_generators.py`: `TraditionalMLViewGenerator` (XGBoost)
- `view_llm/xgboost_train.py`: train model XGBoost
- `assets.json`: cấu hình universe assets
