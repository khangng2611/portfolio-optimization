# Portfolio Optimization - Thị trường Việt Nam

Dự án nghiên cứu tối ưu hóa danh mục đầu tư cho thị trường Việt Nam, tập trung vào việc so sánh các chiến lược phân bổ tài sản và cải tiến mô hình Black-Litterman với các phương pháp sinh quan điểm (views) động dựa trên phân tích kỹ thuật.

## Mục lục

1. [Tổng quan](#tổng-quan)
2. [Cấu trúc dự án](#cấu-trúc-dự-án)
3. [Các chiến lược tối ưu hóa](#các-chiến-lược-tối-ưu-hóa)
4. [Mô hình Black-Litterman](#mô-hình-black-litterman)
5. [Các phương pháp sinh Views động](#các-phương-pháp-sinh-views-động)
6. [Cách sử dụng](#cách-sử-dụng)
7. [Kết quả Backtest](#kết-quả-backtest)

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
├── view_generators.py             # Module sinh views động (rule-based, relative)
├── llm_view_generators.py         # 🆕 ML/LLM view generators (RF, LSTM, GPT-4)
├── train_ml_models.py             # 🆕 Script train ML models
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
└── docs/
    └── INDICATORS.md       # Tài liệu chi tiết về các chỉ báo kỹ thuật
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

## Các phương pháp sinh Views động

Dự án cung cấp 2 modules để sinh views tự động:
- `view_generators.py`: Rule-based & Relative views (dựa trên chỉ báo kỹ thuật)
- `llm_view_generators.py`: 🆕 ML/LLM views (Random Forest, LSTM, GPT-4)

### Module 1: view_generators.py

File `view_generators.py` cung cấp 3 phương pháp sinh views dựa trên phân tích kỹ thuật:

#### 1. Rule-Based View Generator (`rule_based`)

**Cơ sở lý thuyết**: Sử dụng các chỉ báo kỹ thuật cổ điển để xác định xu hướng và sinh views.

#### Các chỉ báo sử dụng

**a) MA Crossover (Giao cắt đường trung bình)**

```
MA_ratio = (EMA_short / EMA_long) - 1
```

- `EMA_short`: Exponential Moving Average 10 ngày
- `EMA_long`: Exponential Moving Average 30 ngày

**Tín hiệu**:
- `MA_ratio > 2%`: **Bullish** - xu hướng tăng
- `MA_ratio < -2%`: **Bearish** - xu hướng giảm
- `|MA_ratio| < 2%`: Không có tín hiệu rõ ràng

**b) RSI (Relative Strength Index)**

```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain / Average Loss (14 ngày)
```

**Diễn giải**:
- `RSI > 70`: **Overbought** - có thể đảo chiều xuống
- `RSI < 30`: **Oversold** - có thể đảo chiều lên
- `30 ≤ RSI ≤ 70`: Vùng trung tính

**Vai trò trong sinh views**: Điều chỉnh confidence
- Nếu bullish nhưng RSI > 70: Giảm confidence 30%
- Nếu bearish nhưng RSI < 30: Giảm confidence 30%

**c) Momentum**

```
Momentum = (P_today - P_{20 days ago}) / P_{20 days ago}
```

**Vai trò**: Xác định độ lớn của view return
- Momentum càng mạnh → view return càng lớn

#### Logic sinh View

```python
# Pseudo-code
for mỗi asset:
    # Bước 1: Xác định hướng từ MA Crossover
    if MA_ratio > 2%:
        signal = "bullish"
        base_return = 5% + momentum * 50%
        base_confidence = 0.6
    elif MA_ratio < -2%:
        signal = "bearish"
        base_return = -3% - momentum * 30%
        base_confidence = 0.5
    else:
        continue  # Bỏ qua, không có tín hiệu
    
    # Bước 2: Điều chỉnh confidence theo RSI
    if RSI > 70 and signal == "bullish":
        confidence *= 0.7  # Giảm vì overbought
    if RSI < 30 and signal == "bearish":
        confidence *= 0.7  # Giảm vì oversold
    
    # Bước 3: Sinh view
    view = {
        "name": f"{asset}_rule_based",
        "legs": {asset: 1.0},
        "view_return_annual": base_return,
        "confidence": confidence
    }
```

#### Minh họa

```
Giá     |     *
        |   *   *     *
        | *       * *   * 
        |           
        +-------------------> Thời gian

EMA_10  -------- (xanh, phản ứng nhanh)
EMA_30  -------- (đỏ, phản ứng chậm)

Khi EMA_10 cắt lên EMA_30: Tín hiệu BULLISH → Sinh positive view
Khi EMA_10 cắt xuống EMA_30: Tín hiệu BEARISH → Sinh negative view
```

---

### 2. Relative View Generator (`relative`)

**Cơ sở lý thuyết**: So sánh momentum giữa các cặp tài sản để xác định tài sản nào sẽ outperform.

#### Nguyên lý

```
Momentum_A = Return của asset A trong 20 ngày
Momentum_B = Return của asset B trong 20 ngày
Momentum_diff = Momentum_A - Momentum_B
```

**Nếu `Momentum_diff > 1%`**: Asset A sẽ outperform Asset B

#### Logic sinh View

```python
# Pseudo-code
for mỗi cặp (asset_A, asset_B):
    momentum_A = compute_momentum(asset_A, 20)
    momentum_B = compute_momentum(asset_B, 20)
    diff = momentum_A - momentum_B
    
    if abs(diff) < 1%:
        continue  # Chênh lệch không đủ lớn
    
    if diff > 0:
        long_asset = asset_A
        short_asset = asset_B
    else:
        long_asset = asset_B
        short_asset = asset_A
        diff = -diff
    
    # Annualize chênh lệch
    view_return = diff * 252 / 20
    view_return = clip(view_return, -30%, +30%)  # Giới hạn
    
    # Confidence dựa trên độ lớn momentum diff
    confidence = min(0.8, 0.4 + abs(diff) * 10)
    
    view = {
        "name": f"{long_asset}_over_{short_asset}",
        "legs": {long_asset: 1.0, short_asset: -1.0},
        "view_return_annual": view_return,
        "confidence": confidence
    }
```

#### Ưu điểm của Relative Views

1. **Market-neutral**: Không phụ thuộc vào xu hướng chung của thị trường
2. **Momentum effect**: Tận dụng hiệu ứng momentum (tài sản đang tăng tiếp tục tăng)
3. **Pairs trading**: Tương tự chiến lược pairs trading trong thực tế

#### Minh họa

```
Asset A: Momentum 20 ngày = +8%
Asset B: Momentum 20 ngày = +2%
         ↓
Momentum diff = 6%
         ↓
View: "A outperform B 6% annualized"
P = [1, -1] (Long A, Short B)
```

---

### 3. ML-Based View Generator (`ml`)

**Cơ sở lý thuyết**: Sử dụng Machine Learning để dự đoán returns và sinh views.

#### Features sử dụng

```python
features = {
    "momentum_5":   Momentum 5 ngày,
    "momentum_10":  Momentum 10 ngày,
    "momentum_20":  Momentum 20 ngày,
    "rsi":          RSI 14 ngày,
    "ma_ratio":     EMA_10 / EMA_30 - 1,
    "volatility":   Độ lệch chuẩn returns,
    "macd_hist":    MACD histogram
}
```

#### Fallback mode (khi không có model)

Nếu chưa train model ML, sử dụng simple prediction:

```python
def simple_return_prediction(prices, window):
    momentum = compute_momentum(prices, window)
    rsi = compute_rsi(prices, 14)
    
    if rsi > 70:
        # Overbought: dự đoán đảo chiều
        return momentum * 0.5 - 0.02
    elif rsi < 30:
        # Oversold: dự đoán đảo chiều
        return momentum * 0.5 + 0.02
    else:
        # Trend continuation
        return momentum * 0.8
```

#### Logic sinh View

```python
# Pseudo-code
for mỗi asset:
    features = compute_features(prices)
    
    if model is not None:
        predicted_return = model.predict(features)
        confidence = model.predict_proba(features)
    else:
        predicted_return = simple_return_prediction(prices)
        confidence = 0.4  # Lower confidence cho fallback
    
    if abs(predicted_return) < 1%:
        continue  # Prediction quá yếu
    
    view = {
        "name": f"{asset}_ml_pred",
        "legs": {asset: 1.0},
        "view_return_annual": predicted_return * 252 / window,
        "confidence": confidence
    }
```

#### Sử dụng với model đã train

```python
from sklearn.ensemble import RandomForestRegressor
import joblib

# Load pre-trained model
model = joblib.load("models/return_predictor.pkl")

# Sinh views với model
views = generate_ml_views(prices, model=model)
```

---

### Module 2: llm_view_generators.py 🆕

File `llm_view_generators.py` cung cấp 3 phương pháp ML/LLM nâng cao:

#### Option 1: Traditional ML (Random Forest / XGBoost)

**Cơ sở lý thuyết**: Học có giám sát (supervised learning) để dự đoán return tương lai.

**Training process**:
1. Tính features từ price data (MA, RSI, momentum, volatility, MACD)
2. Label = return sau N ngày (ví dụ: 5 ngày)
3. Train model: `features -> future_return`
4. Predict return cho current state

**Ưu điểm**:
- ✅ Huấn luyện nhanh (5-10 giây)
- ✅ Có thể xem feature importance (giải thích được)
- ✅ Hoạt động tốt với dữ liệu ít
- ✅ Không cần GPU

**Nhược điểm**:
- ❌ Cần manual feature engineering
- ❌ Không bắt được pattern phức tạp

**Sử dụng**:
```python
from llm_view_generators import TraditionalMLViewGenerator

# Khởi tạo
ml_gen = TraditionalMLViewGenerator(
    model_type="random_forest",  # hoặc "xgboost"
    feature_window=20,
    prediction_horizon=5,
)

# Train
ml_gen.train(train_prices, verbose=True)
ml_gen.save(".cache/rf_models.pkl")

# Tạo views
views = ml_gen.generate_views(test_prices)
```

#### Option 2: Deep Learning (LSTM)

**Cơ sở lý thuyết**: LSTM (Long Short-Term Memory) - neural network chuyên cho time series.

**Training process**:
1. Tạo sequences: [60 ngày giá] -> [return 5 ngày sau]
2. Train LSTM để học temporal patterns
3. Predict return từ sequence gần nhất

**Ưu điểm**:
- ✅ Bắt được complex temporal dependencies
- ✅ Không cần feature engineering thủ công
- ✅ State-of-the-art cho time series
- ✅ Có thể học long-term patterns

**Nhược điểm**:
- ❌ Cần nhiều data (1000+ samples)
- ❌ Huấn luyện chậm (vài phút)
- ❌ Black-box (khó giải thích)
- ❌ Dễ overfit

**Sử dụng**:
```python
from llm_view_generators import LSTMViewGenerator

# Khởi tạo
lstm_gen = LSTMViewGenerator(
    sequence_length=60,  # nhìn lại 60 ngày
    hidden_size=64,
    num_layers=2,
    epochs=50,
    device="cpu",  # hoặc "cuda" nếu có GPU
)

# Train
lstm_gen.train(train_prices, verbose=True)
lstm_gen.save(".cache/lstm_models.pt")

# Tạo views
views = lstm_gen.generate_views(test_prices)
```

#### Option 3: LLM-based (GPT-4 / Claude)

**Cơ sở lý thuyết**: Kết hợp phân tích định lượng + định tính bằng Large Language Models.

**Input**:
- Quantitative: Price data, technical indicators (MA, RSI, momentum)
- Qualitative: News headlines, market sentiment, events

**Process**:
1. Crawl tin tức từ CafeF, VnExpress
2. Tạo prompt với giá + indicators + news
3. Query LLM API (GPT-4 hoặc Claude)
4. Parse response để lấy predicted return + reasoning

**Ưu điểm**:
- ✅ Kết hợp quantitative + qualitative
- ✅ Hiểu được ngữ cảnh, sự kiện, sentiment
- ✅ Không cần training (zero-shot)
- ✅ Có reasoning (giải thích được)

**Nhược điểm**:
- ❌ Chi phí API cao (~$0.03-0.10/view)
- ❌ Latency cao (2-5 giây)
- ❌ Non-deterministic
- ❌ Cần internet

**Chi phí ước tính**:
- 4 assets × 5 rebalances/ngày × 252 ngày = 5,040 calls/năm
- Chi phí: $176/năm (GPT-4) hoặc $44/năm (với caching)

**Sử dụng**:
```python
from llm_view_generators import LLMViewGenerator
import os

# Set API key
os.environ["OPENAI_API_KEY"] = "sk-..."

# Khởi tạo
llm_gen = LLMViewGenerator(
    llm_provider="openai",
    model_name="gpt-4",
    enable_caching=True,     # giảm cost 75%
    enable_news=True,        # bật crawl tin tức
)

# Tạo views (không cần train!)
views = llm_gen.generate_views(test_prices, verbose=True)

# Xem chi phí
cost = llm_gen.get_cost_summary()
print(f"Total cost: ${cost['total_cost_usd']:.2f}")
```

#### Ensemble: Kết hợp 3 phương pháp

Tận dụng ưu điểm của từng phương pháp:

```python
from llm_view_generators import combine_multi_source_views

# Load các models đã train
ml_gen.load(".cache/rf_models.pkl")
lstm_gen.load(".cache/lstm_models.pt")

# Tạo views từ mỗi source
ml_views = ml_gen.generate_views(prices)
lstm_views = lstm_gen.generate_views(prices)
llm_views = llm_gen.generate_views(prices)

# Kết hợp với trọng số
combined = combine_multi_source_views(
    ml_views, lstm_views, llm_views,
    weights=(0.3, 0.3, 0.4)  # 30% ML, 30% LSTM, 40% LLM
)
```

**So sánh performance (dự kiến)**:

| Method | Sharpe Ratio | Training Time | Inference Time | Cost |
|--------|--------------|---------------|----------------|------|
| Rule-based | 1.70 | 0s | <1ms | $0 |
| Random Forest | 1.50-1.80 | 5-10s | <1ms | $0 |
| XGBoost | 1.55-1.85 | 10-20s | <1ms | $0 |
| LSTM | 1.60-1.90 | 2-5 min | 10-50ms | $0 |
| LLM (GPT-4) | 1.65-2.00 | 0s | 2-5s | $176/năm |
| **Ensemble** | **1.80-2.10** | - | - | - |

**Xem hướng dẫn chi tiết**: `docs/HUONG_DAN_SU_DUNG_LLM_GENERATORS.md`

---

### 4. Combined View Generator (`combined`)

Kết hợp tất cả các phương pháp với trọng số:

```python
# Weights mặc định: (rule_based, relative, ml)
COMBINED_VIEW_WEIGHTS = (0.4, 0.4, 0.2)

def combine_views(rule_views, relative_views, ml_views, weights):
    combined = []
    
    # Điều chỉnh confidence theo weight
    for view in rule_views:
        view["confidence"] *= weights[0]  # 0.4
        combined.append(view)
    
    for view in relative_views:
        view["confidence"] *= weights[1]  # 0.4
        combined.append(view)
    
    for view in ml_views:
        view["confidence"] *= weights[2]  # 0.2
        combined.append(view)
    
    return combined
```

---

## Áp dụng Views trong Backtest

### Cấu hình VIEW_MODE

Trong file `backtest.py`, thay đổi biến `VIEW_MODE`:

```python
# Dòng 36 trong backtest.py
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

### 1. Cài đặt môi trường

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

### 2. Thu thập dữ liệu

```bash
python crawl/stock.py   # Crawl ETF/cổ phiếu
python crawl/fund.py    # Crawl NAV quỹ
python crawl/gold.py    # Crawl giá vàng
```

### 3. Chạy Backtest

```bash
# Chạy với view mode mặc định (rule_based)
python backtest.py

# Chạy không hiện chart
python backtest.py --no-plot

# Chạy với khoảng thời gian tùy chỉnh
python backtest.py --start-date 2021-01-01 --end-date 2023-06-01
```

### 4. Thay đổi View Mode

Mở file `backtest.py` và sửa dòng 36:

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

---

## Kết quả Backtest

### Kết quả mẫu (Train period: 2020-08 → 2023-09)

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

## Ghi chú phát triển

### Pending tasks
- [ ] Train ML model thực sự cho `ml` mode
- [ ] Test trên Test period (2023-10 → nay)
- [ ] Thêm transaction costs vào backtest
- [ ] Thêm các chỉ báo kỹ thuật khác (Bollinger Bands, ATR)

### Files quan trọng
- `backtest.py:36` - Thay đổi VIEW_MODE
- `backtest.py:55` - Thay đổi COMBINED_VIEW_WEIGHTS
- `view_generators.py:29-32` - Thay đổi thresholds cho indicators
