# Hướng dẫn chạy Portfolio Optimization

## 1. Cài đặt môi trường

```bash
# Clone repository
git clone <REPO_URL>
cd portfolio-optimization

# Tạo virtual environment
python3.12 -m venv venv
source venv/bin/activate  # macOS/Linux
# hoặc: venv\Scripts\activate  # Windows

# Cài dependencies
pip install -r requirements.txt
pip install vnstock
```

## 2. Thu thập dữ liệu

```bash
python crawl/stock.py   # Crawl ETF/cổ phiếu
python crawl/fund.py    # Crawl NAV quỹ
python crawl/gold.py    # Crawl giá vàng
```

## 3. Chạy Backtest

### Chạy cơ bản

```bash
# Chạy với view mode mặc định (rule_based)
python backtest.py

# Chạy không hiện chart
python backtest.py --no-plot

# Chạy với khoảng thời gian tùy chỉnh
python backtest.py --start-date 2021-01-01 --end-date 2023-06-01

# Chạy với subset assets cụ thể
python backtest.py --assets E1VFVN30,GOLD,DCDS

# Chạy với file cấu hình assets riêng
python backtest.py --assets-config datasets/assets.json --assets E1VFVN30,MBBOND
```

## 4. Cấu hình Assets bằng JSON

Backtest không còn hardcode assets trong code. Danh sách tài sản nằm ở file `assets.json`.

Ví dụ format:

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

Quy tắc chọn assets khi chạy:
- Nếu truyền `--assets`, script sẽ dùng đúng danh sách này.
- Nếu không truyền `--assets`, script dùng `default_selection` trong JSON.
- Nếu JSON không có `default_selection`, script dùng toàn bộ key trong `assets`.

## 5. Thay đổi View Mode

Mở file `backtest.py` và sửa biến `VIEW_MODE`:

```python
# Option 1: Views cố định (hardcoded)
VIEW_MODE = "static"

# Option 2: Sinh views từ MA Crossover + RSI + Momentum
VIEW_MODE = "rule_based"

# Option 3: Sinh views từ so sánh momentum giữa các cặp assets
VIEW_MODE = "relative"

# Option 4: Sinh views từ ML predictions
VIEW_MODE = "ml"

# Option 5: Kết hợp tất cả
VIEW_MODE = "combined"
```