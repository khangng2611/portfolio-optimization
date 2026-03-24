# Portfolio Optimization (VN Market)

Project này dùng để crawl dữ liệu tài sản tại Việt Nam (ETF/cổ phiếu, quỹ, vàng) và backtest các chiến lược phân bổ danh mục:
- Equal Weight (EW)
- Mean-Variance Optimization (MVO)
- Black-Litterman (BL)

Script backtest chính: `backtest.py`.

## Cấu trúc repository

```text
portfolio-optimization/
├── backtest.py         # Backtest 4 tài sản: EW, MVO, BL
├── requirements.txt            # Danh sách thư viện Python
├── crawl/
│   ├── stock.py                # Crawl VN30 + ETF E1VFVN30
│   ├── fund.py                 # Crawl NAV quỹ mở/bond fund
│   └── gold.py                 # Crawl giá vàng PNJ/SJC
└── datasets/
    ├── stocks/                 # CSV giá cổ phiếu/ETF
    ├── funds/                  # CSV NAV quỹ
    ├── gold/                   # CSV giá vàng
    ├── vn30_list.txt           # Danh sách mã VN30
    ├── fund_list.txt           # Danh sách quỹ
    └── bond_list.txt           # Danh sách quỹ trái phiếu
```

## Yêu cầu môi trường

- Python: **3.11 hoặc 3.12** (khuyến nghị 3.12)
- Hệ điều hành: macOS/Linux/Windows
- Cài đặt trong môi trường ảo (`virtualenv` hoặc `venv`)

## Hướng dẫn cài đặt và chạy

### 1) Clone repository

```bash
git clone <REPO_URL>
cd portfolio-optimization
```

### 2) Tạo và kích hoạt virtual environment

macOS/Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

Nếu máy chưa có Python 3.12, có thể dùng `python3` hoặc `py -3.11`.

### 3) Cài dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install vnstock
```

`vnstock` đang được dùng trong các script crawl dữ liệu và có thể chưa nằm đầy đủ trong `requirements.txt`, nên cài thêm để tránh thiếu thư viện.

### 4) (Tuỳ chọn) Cập nhật dữ liệu

```bash
python crawl/stock.py
python crawl/fund.py
python crawl/gold.py
```

Các script này sẽ ghi dữ liệu CSV vào thư mục `datasets/`.

### 5) Chạy backtest

```bash
python backtest.py
```

Kết quả gồm:
- Bảng thống kê return theo asset
- Chỉ số NAV/Sharpe/Max Drawdown cho EW, MVO, BL
- Gợi ý trọng số cho kỳ tiếp theo
- Biểu đồ NAV so sánh giữa các chiến lược

## Ghi chú

- Backtest hiện dùng 4 asset chính: `E1VFVN30`, `GOLD (SJC sell)`, `DCDS`, `MBBOND`.
- Nếu thiếu dữ liệu đầu vào trong `datasets/`, hãy chạy các script trong `crawl/` trước.
