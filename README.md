# Portfolio Optimization - Thị trường Việt Nam

Dự án nghiên cứu tối ưu hóa danh mục đầu tư cho thị trường Việt Nam, tập trung vào việc so sánh các chiến lược phân bổ tài sản và cải tiến mô hình Black-Litterman với các phương pháp sinh quan điểm (views) động dựa trên phân tích kỹ thuật.

## Mục lục

1. [Tổng quan](#tổng-quan)
2. [Cấu trúc dự án](#cấu-trúc-dự-án)
3. [Các chiến lược tối ưu hóa](#các-chiến-lược-tối-ưu-hóa)
4. [Mô hình Black-Litterman](#mô-hình-black-litterman)
5. [Cách sử dụng](#cách-sử-dụng)
6. [Kết quả Backtest](#kết-quả-backtest)

---

## Tổng quan

### Mục tiêu nghiên cứu

1. **Thu thập dữ liệu** thị trường Việt Nam (ETF, vàng, quỹ đầu tư)
2. **So sánh hiệu quả** 3 chiến lược phân bổ: Equal Weight, MVO, Black-Litterman
3. **Cải tiến Black-Litterman** bằng cách thay thế views cố định bằng views động sinh tự động từ chỉ báo kỹ thuật

### Tài sản sử dụng

| Tài sản | Loại | Mô tả |
|---------|------|-------|
| E1VFVN30 | ETF | Quỹ ETF theo dõi chỉ số VN30 |
| GOLD | Hàng hóa | Giá vàng SJC (giá bán) |
| DCDS | Quỹ cổ phiếu | Quỹ đầu tư cổ phiếu Dragon Capital |
| MBBOND | Quỹ trái phiếu | Quỹ trái phiếu MB Capital |

### Phân chia dữ liệu

- **Train**: 2020-01-01 → 2023-10-01 (dùng để phát triển và đánh giá chiến lược)
- **Test**: 2023-10-01 → hiện tại (dùng để kiểm tra out-of-sample)

---

## Cấu trúc dự án

```
portfolio-optimization/
├── backtest.py                    # Script backtest chính
├── data_loader.py                 # Module load dữ liệu + assets config
├── view_generators.py             # Module sinh views động (rule-based, relative)
├── assets.json                    # Cấu hình universe assets cho backtest
├── requirements.txt               # Dependencies
├── README.md                      # Tài liệu này
│
├── crawl/                         # Scripts thu thập dữ liệu
│   ├── stock.py            # Crawl giá ETF/cổ phiếu (vnstock)
│   ├── fund.py             # Crawl NAV quỹ đầu tư
│   └── gold.py             # Crawl giá vàng từ PNJ API
│
├── datasets/               # Dữ liệu CSV
│   ├── stocks/
│   │   ├── train/          # Dữ liệu train
│   │   ├── test/           # Dữ liệu test
│   │   └── full/           # Dữ liệu đầy đủ
│   ├── funds/
│   │   ├── train/
│   │   ├── test/
│   │   └── full/
│   └── gold/
│       ├── gold_train.csv
│       └── gold_test.csv
│
└── docs/        # Tài liệu khác
```

---

## Các chiến lược tối ưu hóa

### 1. Equal Weight (EW)

**Cơ sở lý thuyết**: Phân bổ đều tài sản, không cần ước lượng tham số.

```
w_i = 1/n   với mọi i = 1, 2, ..., n
```

**Ưu điểm**:
- Đơn giản, không cần estimation
- Đa dạng hóa tự nhiên
- Robust với estimation error

**Nhược điểm**:
- Không tận dụng thông tin về risk/return
- Có thể không tối ưu

### 2. Mean-Variance Optimization (MVO)

**Cơ sở lý thuyết**: Tối đa hóa utility function dựa trên expected return và variance (Markowitz, 1952).

```
max   μᵀw - (λ/2) wᵀΣw
s.t.  Σw_i = 1
      w_i ≥ 0
```

Trong đó:
- `μ`: Vector expected returns (ước lượng từ dữ liệu lịch sử)
- `Σ`: Ma trận covariance
- `λ`: Hệ số risk aversion
- `w`: Vector trọng số tài sản

**Ưu điểm**:
- Tối ưu theo lý thuyết (nếu input chính xác)
- Cân bằng risk-return

**Nhược điểm**:
- Rất nhạy cảm với estimation error của μ
- Dễ sinh ra concentrated portfolios
- "Garbage in, garbage out"

### 3. Black-Litterman (BL)

**Cơ sở lý thuyết**: Kết hợp equilibrium returns (từ CAPM) với quan điểm chủ quan của nhà đầu tư (Black & Litterman, 1992).

#### Bước 1: Tính Equilibrium Returns (π)

```
π = δ × Σ × w_market
```

Trong đó:
- `δ`: Risk aversion coefficient (mặc định 2.5)
- `Σ`: Ma trận covariance
- `w_market`: Trọng số thị trường (ở đây dùng equal weight)

#### Bước 2: Kết hợp với Views

Views được biểu diễn dưới dạng:
- `P`: Ma trận pick (K × N) - xác định tài sản nào trong view
- `Q`: Vector view returns (K × 1) - mức return kỳ vọng
- `Ω`: Ma trận uncertainty của views (K × K)

**Công thức posterior returns**:

```
μ_BL = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ × [(τΣ)⁻¹π + PᵀΩ⁻¹Q]
```

Trong đó:
- `τ`: Scalar uncertainty về equilibrium (mặc định 0.05)
- `Ω = diag(P × τΣ × Pᵀ) / confidence`: Uncertainty tỷ lệ nghịch với confidence

**Ưu điểm**:
- Ổn định hơn MVO (bắt đầu từ equilibrium)
- Cho phép kết hợp views chủ quan
- Tự động điều chỉnh theo confidence

**Nhược điểm**:
- Cần xác định views - nếu views sai sẽ ảnh hưởng kết quả
- Phức tạp hơn MVO

---

## Mô hình Black-Litterman

### Cấu trúc một View

Trong code, mỗi view là một dictionary với format:

```python
{
    "name": "GOLD_over_E1VFVN30",       # Tên view
    "legs": {"GOLD": 1.0, "E1VFVN30": -1.0},  # Tài sản và hệ số
    "view_return_annual": 0.06,          # Return kỳ vọng (năm)
    "confidence": 0.70                   # Độ tin cậy [0, 1]
}
```

### Các loại Views

#### Absolute View (View tuyệt đối)
Kỳ vọng về return của một tài sản cụ thể.

```python
# "E1VFVN30 sẽ tăng 10% trong năm tới"
{
    "name": "E1VFVN30_bullish",
    "legs": {"E1VFVN30": 1.0},
    "view_return_annual": 0.10,
    "confidence": 0.6
}
```

Ma trận P: `[1, 0, 0, 0]` (với 4 assets: E1VFVN30, GOLD, DCDS, MBBOND)

#### Relative View (View tương đối)
Kỳ vọng về chênh lệch return giữa hai tài sản.

```python
# "GOLD sẽ outperform E1VFVN30 6%"
{
    "name": "GOLD_over_E1VFVN30",
    "legs": {"GOLD": 1.0, "E1VFVN30": -1.0},
    "view_return_annual": 0.06,
    "confidence": 0.7
}
```

Ma trận P: `[-1, 1, 0, 0]` (Long GOLD, Short E1VFVN30)

---

## Áp dụng Views trong Backtest

### Cấu hình VIEW_MODE

Trong file `backtest.py`, thay đổi biến `VIEW_MODE`:

```python
# Dòng 39 trong backtest.py
VIEW_MODE = "rule_based"  # Các giá trị: "static", "rule_based", "relative", "ml", "combined"
```

### Luồng xử lý trong Backtest

```
┌─────────────────────────────────────────────────────────────────┐
│                         BACKTEST LOOP                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  for t in range(window, len(data)):                            │
│      │                                                          │
│      ├── Tính returns trong ngày t                              │
│      │                                                          │
│      ├── Cập nhật NAV của EW                                    │
│      │                                                          │
│      └── if t là ngày rebalance:                                │
│              │                                                  │
│              ├── Tính μ, Σ từ dữ liệu lịch sử                   │
│              │                                                  │
│              ├── MVO: Tối ưu với μ, Σ                           │
│              │                                                  │
│              ├── BL:                                            │
│              │   ├── Lấy price_window cho indicators            │
│              │   ├── Gọi generate_dynamic_views()               │
│              │   │       → Sinh P, Q, confidence               │
│              │   ├── Tính μ_BL = posterior returns              │
│              │   └── Tối ưu với μ_BL, Σ                         │
│              │                                                  │
│              └── Lưu weights cho kỳ tiếp theo                   │
│                                                                 │
│      Cập nhật NAV của MVO, BL                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Code chi tiết

```python
# Trong hàm backtest() - dòng 365-394

if (t - window) % rebalance_freq == 0:
    # Tính mean và covariance từ dữ liệu lịch sử
    mu = hist.mean().values
    sigma = hist.cov().values
    
    # MVO: Tối ưu trực tiếp
    mvo_weight = optimize_weight(mu, sigma)
    
    # BL: Sinh views động và tối ưu
    if view_mode != "static":
        # Lấy cửa sổ giá để tính indicators
        price_window = prices.iloc[max(0, t - window - 30) : t + window]
        
        # Sinh views dựa trên mode
        p_view, q_view, conf_view, view_names = generate_dynamic_views(
            price_window, assets, view_mode
        )
    
    if p_view is not None:
        # Tính posterior returns
        mu_bl = black_litterman_posterior_mu(
            sigma, market_weights, p_view, q_view, conf_view
        )
    else:
        mu_bl = mu  # Fallback về historical mean
    
    # Tối ưu với BL returns
    bl_weight = optimize_weight(mu_bl, sigma)
```

---

## Cách sử dụng

Hướng dẫn chi tiết về cách cài đặt, chạy backtest, và cấu hình các tham số nằm ở [QUICKSTART.md](QUICKSTART.md).

### Các bước nhanh

```bash
# 1. Cài đặt
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Chạy backtest
python backtest.py

# 3. Thay đổi view mode (trong backtest.py)
VIEW_MODE = "rule_based"  # hoặc "static", "relative", "ml", "combined"
```

---

## Kết quả Backtest

### Kết quả mẫu (Train period: 2020-01 → 2023-10)

```
======================================================================
KET QUA BACKTEST (2020-01-01 den 2023-10-01)
======================================================================
EW   | NAV cuoi: 199,839 | Sharpe:  1.12 | MDD: -30.41%
MVO  | NAV cuoi: 370,714 | Sharpe:  1.18 | MDD: -26.01%
BL   | NAV cuoi: 531,725 | Sharpe:  1.70 | MDD: -28.94%

(VIEW_MODE = "rule_based")
```

### So sánh các View Modes

| View Mode | NAV cuối | Sharpe | Max Drawdown |
|-----------|----------|--------|--------------|
| EW (baseline) | 199,839 | 1.12 | -30.41% |
| MVO | 370,714 | 1.18 | -26.01% |
| BL (static) | ~400,000 | ~1.30 | ~-28% |
| BL (rule_based) | 531,725 | 1.70 | -28.94% |

### Mẫu Views sinh ra trong Backtest

```
2020-09-02:
  - E1VFVN30_rule_based: Q=0.000481 (daily), conf=0.60
  - DCDS_rule_based: Q=0.000250 (daily), conf=0.42

2023-09-27:
  - E1VFVN30_rule_based: Q=-0.000267 (daily), conf=0.50
```

---

## Tham khảo

1. Markowitz, H. (1952). *Portfolio Selection*. Journal of Finance.
2. Black, F. & Litterman, R. (1992). *Global Portfolio Optimization*. Financial Analysts Journal.
3. Idzorek, T. (2005). *A Step-By-Step Guide to the Black-Litterman Model*.
4. Murphy, J.J. (1999). *Technical Analysis of the Financial Markets*.

---
## Files quan trọng
- `backtest.py` - Luồng backtest chính + tham số CLI
- `data_loader.py` - Load dữ liệu + đọc assets config từ JSON
- `assets.json` - Khai báo universe assets
- `view_generators.py` - Thay đổi thresholds cho indicators
