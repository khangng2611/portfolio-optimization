# Báo Cáo Cải Tiến: Ranking-Based Relative Views cho Black-Litterman

**Phiên bản**: 06-06-2026
**Mục tiêu**: Mở rộng pipeline Black-Litterman với tầng chọn cổ phiếu đại diện (tối ưu tổ hợp toàn cục), ranking dựa trên XGBoost Ranker để sinh relative views, và tầng quản lý rủi ro chủ động cho chế độ ranking.

---

## 1. Bối cảnh và động lực

### 1.1 Pipeline cũ (Baseline)

Hệ thống hiện tại sử dụng:

```
Lịch sử giá
→ Feature Engineering
→ XGBoost Regression (dự đoán lợi suất tuyệt đối)
→ Absolute Views
→ Black-Litterman
→ Mean-Variance Optimization (MVO)
```

Danh mục tối ưu gồm 4 tài sản: **E1VFVN30**, **GOLD**, **DCDS**, **MBBOND**.

### 1.2 Hạn chế của pipeline cũ

1. **Universe hạn chế**: Chỉ 4 tài sản, không khai thác được thông tin từ thị trường cổ phiếu rộng hơn.
2. **Absolute views bất ổn định**: Dự đoán lợi suất tuyệt đối của từng tài sản riêng lẻ khó khăn hơn so với dự đoán thứ hạng tương đối.
3. **Không có stock selection**: Không có cơ chế chọn lọc cổ phiếu tiêu biểu để đại diện cho toàn bộ thị trường.

### 1.3 Pipeline mới (Ranking-Based)

```
30 cổ phiếu VN30
→ Chọn K đại diện (Combinatorial Optimization, K=5)
→ XGBoost Ranking Model (LambdaMART)
→ Relative Views Generation
→ Risk Management Layer (Regime Detection + Defensive Views)
→ Black-Litterman
→ Constrained MVO (defensive floor + equity cap)
→ Kết hợp với Gold + MBBOND (core assets)
```

**Nguyên tắc giữ nguyên**:
- **GOLD** và **MBBOND** là tài sản phòng thủ/core, không thay đổi cách xử lý.
- Chỉ thay đổi cách tiếp cận với universe cổ phiếu.

---

## 2. Kiến trúc tổng quan

### 2.1 So sánh kiến trúc

| Thành phần | Pipeline cũ | Pipeline mới |
|---|---|---|
| Stock universe | 4 assets cố định | 30 VN30 stocks |
| Selection | Không có | Combinatorial Optimization (K=5) — global optimum |
| ML model | XGBoost Regressor | XGBoost Ranker |
| View type | Absolute (lợi suất tuyệt đối) | Relative (so sánh tương đối) |
| Confidence | Ensemble disagreement | Margin + Disagreement + Volatility Dampener |
| BL P matrix | 1 hàng / 1 asset | 1 hàng / 1 cặp so sánh |
| Risk management | Không có | Regime detection + defensive views + constrained MVO |

### 2.2 Các module mới

```
gen_view/
├── ranking/
│   ├── stock_selection.py      # Combinatorial Optimization (global optimum)
│   ├── ranking_model.py         # XGBoost Ranker Ensemble
│   ├── relative_views.py        # Sinh relative views từ ranking
│   ├── feature_engineering.py   # Features cho ranking model
│   ├── risk_management.py       # Regime detection + defensive views
│   └── config.py                # Cấu hình ranking module
```

---

## 3. Giai đoạn 1: Chọn cổ phiếu đại diện (Representative Stock Selection)

### 3.1 Phương pháp: Combinatorial Optimization (Tối ưu Tổ hợp Toàn cục)

Thuật toán đã được nâng cấp từ heuristic K-Medoids/PAM lên **vét cạn tổ hợp** (exhaustive combinatorial search) nhằm đảm bảo nghiệm **tối ưu toàn cục**, không còn nguy cơ kẹt local optimum.

**So sánh với phương pháp cũ (PAM):**

| Tiêu chí | PAM (cũ) | Combinatorial Optimization (mới) |
|---|---|---|
| Chiến lược | Heuristic local search (BUILD + SWAP) | Vét cạn toàn bộ tổ hợp C(N,K) |
| Đảm bảo tối ưu | Local optimum, có thể kẹt | **Global optimum** tuyệt đối |
| Số tổ hợp đánh giá | Không xác định, phụ thuộc khởi tạo | C(30,5) = **142,506** tổ hợp |
| Tham số khởi tạo | Có (max_iter, seed) | Không cần |
| Thời gian thực thi | ~ms | ~3 giây với pruning |
| Tính lặp lại (deterministic) | Phụ thuộc seed | **Hoàn toàn deterministic** |

**Tại sao vét cạn lại khả thi?**
- Universe VN30 chỉ có N = 30 mã, K = 5 → không gian tìm kiếm = C(30,5) = 142,506 tổ hợp.
- Với pruning sớm (early-stopping), thuật toán chạy trong khoảng 3 giây — chi phí tính toán hoàn toàn không đáng kể so với chu kỳ tái lựa chọn (60 ngày giao dịch).
- Không cần dùng heuristic xấp xỉ khi đã có thể vét cạn nghiệm chính xác.

**Tại sao không dùng K-Means?**
- K-Means chọn centroid ảo (giá trung bình), không phải cổ phiếu thực tế trong universe → không thể dùng làm đại diện đầu tư.
- Cách tiếp cận tổ hợp luôn chọn ra K cổ phiếu thực sự tồn tại.

### 3.2 Công thức toán học

**Bước 1: Tính ma trận tương quan**

```
r(i,j) = correlation(returns_i, returns_j)
```

**Bước 2: Chuyển tương quan thành khoảng cách**

```
distance(i,j) = 1 - correlation(i,j)
```

- distance = 0: tương quan hoàn hảo (cùng hướng)
- distance = 1: không tương quan
- distance = 2: tương quan nghịch hoàn hảo

**Bước 3: Tối ưu hóa**

```
Minimize: Σ_i min_{m ∈ M} distance(i, m)
```

Trong đó M là tập K medoid được chọn.

### 3.3 Thuật toán Combinatorial Optimization

**Pseudocode:**

```python
from itertools import combinations

best_cost  = +inf
best_combo = None

for combo in combinations(range(N), K):    # C(N,K) tổ hợp
    cost = 0
    for i in range(N):
        # khoảng cách tới medoid gần nhất trong combo
        cost += min(distance(i, j) for j in combo)
        if cost >= best_cost:               # Pruning sớm
            break                           # bỏ qua tổ hợp này
    else:
        if cost < best_cost:
            best_cost  = cost
            best_combo = combo
```

**Tính chất của thuật toán:**
1. **Vét cạn toàn bộ không gian C(N,K)** — không bỏ sót tổ hợp nào.
2. **Early-stopping pruning**: nếu chi phí cộng dồn (partial cost) đã lớn hơn best_cost hiện tại thì bỏ qua phần còn lại của tổ hợp đang xét → giảm số phép tính trên thực tế.
3. **Đảm bảo tối ưu toàn cục**: vì xét toàn bộ tổ hợp, nghiệm trả về luôn là min của hàm mục tiêu.
4. **Không cần `max_iter`**: thuật toán dừng tự nhiên sau khi quét hết tổ hợp.

**Độ phức tạp:**
- Thời gian (worst case): O(C(N,K) · N · K).
- Với N=30, K=5: ≈ 142,506 × 30 × 5 ≈ 21.4 triệu phép so sánh — chạy ≈ 3 giây trên CPU thông thường, giảm còn dưới 1 giây với pruning.
- Không gian: O(N²) cho ma trận khoảng cách.

### 3.4 Triển khai

File: `gen_view/ranking/stock_selection.py`

```python
selected_stocks = select_representatives(
    prices=vn30_prices,  # DataFrame 30 cột giá VN30
    k=5,                 # Số đại diện
)
# Trả về: list[str] ví dụ ['FPT', 'VCB', 'HPG', 'MWG', 'VNM']
# Nghiệm là GLOBAL OPTIMUM của hàm Σ_i min_{j∈combo} distance(i,j)
```

> **Lưu ý tương thích ngược**: tham số `max_iter` vẫn còn trong chữ ký hàm để các caller cũ không bị vỡ, nhưng không được sử dụng trong logic chọn nữa.

---

## 4. Giai đoạn 2: Mô hình Ranking (XGBoost Ranker)

### 4.1 Tại sao dùng Ranking thay vì Regression?

| Regression | Ranking |
|---|---|
| Dự đoán giá trị lợi suất tuyệt đối | Dự đoán thứ hạng tương đối |
| Sai số lớn khi thị trường biến động mạnh | Không cần dự đoán chính xác giá trị |
| Khó đánh giá confidence | Tự nhiên phù hợp với relative views |
| Mỗi asset train model riêng | Một model học trên toàn bộ universe |

### 4.2 Công nghệ: LambdaMART (XGBRanker)

Sử dụng `xgboost.XGBRanker` với objective `rank:pairwise`:

- **Pairwise ranking**: Model học so sánh từng cặp cổ phiếu (A vs B), dự đoán cổ phiếu nào sẽ có lợi suất cao hơn.
- **Query group**: Mỗi ngày tạo thành một query group chứa K cổ phiếu đại diện.
- **Label**: Forward return được chuyển thành thứ hạng (0..K-1), rank cao = lợi suất tốt.

### 4.3 Ensemble Ranking

Tương tự pipeline cũ, sử dụng ensemble 5 models:
- Seed khác nhau (42, 43, 44, 45, 46)
- `subsample = 0.8`
- `colsample_bytree` biến thiên: 0.7, 0.75, 0.8, 0.85, 0.9

**Lợi ích**:
- Mean score dùng để xếp hạng.
- Std across ensemble dùng để ước tính confidence.

### 4.4 Triển khai

File: `gen_view/ranking/ranking_model.py`

```python
model = XGBoostRankingModel(
    prediction_horizon=5,
    feature_window=60,
    n_ensemble=5,
)

# Train
model.train(stock_prices, market_prices, verbose=True)

# Predict
rank_scores, ensemble_std = model.predict(
    stock_prices_recent, market_prices_recent
)
# rank_scores: {stock: score} (cao hơn = dự đoán tốt hơn)
```

---

## 5. Giai đoạn 3: Feature Engineering

### 5.1 Tổng quan features

File: `gen_view/ranking/feature_engineering.py`

Các feature được tính vectorized trên toàn bộ lịch sử, không có look-ahead bias.

### 5.2 Nhóm features

**A. Momentum (động lực giá)**

| Feature | Kỳ hạn | Công thức |
|---|---|---|
| momentum_5 | 5 ngày | (P_t - P_{t-5}) / P_{t-5} |
| momentum_20 | 20 ngày | (P_t - P_{t-20}) / P_{t-20} |
| momentum_60 | 60 ngày | (P_t - P_{t-60}) / P_{t-60} |

**B. Volatility (biến động)**

| Feature | Kỳ hạn | Công thức |
|---|---|---|
| volatility_20 | 20 ngày | std(returns_daily, 20) |
| volatility_60 | 60 ngày | std(returns_daily, 60) |

**C. Technical Indicators**

| Feature | Công thức |
|---|---|
| rsi_14 | RSI theo Wilder (14 ngày) |
| macd_hist | MACD(12,26) - Signal(9) |
| bollinger_pctb | (P - lower) / (upper - lower) |

**D. Market Features**

| Feature | Ý nghĩa |
|---|---|
| market_ret_5, market_ret_20, market_ret_60 | Lợi suất VNIndex (E1VFVN30 proxy) |
| market_vol_20 | Biến động VNIndex |

**E. Cross-Sectional Rank Features**

| Feature | Ý nghĩa |
|---|---|
| rank_momentum_5, rank_momentum_20, rank_momentum_60 | Percentile xếp hạng momentum trong nhóm K cổ phiếu |
| rank_volatility_20 | Percentile xếp hạng volatility trong nhóm |
| rank_overall | Trung bình các momentum rank |

### 5.3 Đảm bảo không look-ahead bias

Tất cả features chỉ sử dụng dữ liệu đến thờ điểm t hiện tại:
- Rolling windows: `min_periods=window` để đảm bảo đủ dữ liệu.
- Drop rows đầu tiên trước `feature_window` (mặc định 60 ngày).
- Forward returns làm label được tính từ `price[t+h]` nhưng chỉ dùng cho training, không dùng cho feature.

---

## 6. Giai đoạn 4: Sinh Relative Views

### 6.1 Từ ranking sang relative views

Thay vì sinh view dạng "FPT expected return = 8%", sinh view dạng:
- "FPT outperform VNM"
- "VCB outperform MWG"

### 6.2 Chiến lược chọn cặp so sánh

Với K=5 cổ phiếu đã xếp hạng (0 = tốt nhất, 4 = tệ nhất):

Chỉ so sánh top-half với bottom-half để tránh over-constraining BL:
- View 1: rank 0 > rank 4 (diff 4)
- View 2: rank 0 > rank 3 (diff 3)
- View 3: rank 0 > rank 2 (diff 2)
- View 4: rank 1 > rank 4 (diff 3)
- View 5: rank 1 > rank 3 (diff 2)

→ Tổng cộng ~K views thay vì K*(K-1)/2 = 10 views.

### 6.3 Công thức P matrix và Q vector

**Ví dụ**: View "FPT outperform VNM by spread"

```
P = [0, 0, 1, 0, 0, -1]   # +1 FPT, -1 VNM, 0 elsewhere
Q = spread * (rank_diff / K) / 252   # daily expected outperformance
```

Trong đó:
- `spread = 0.03` (3% annual, cấu hình tại `RANKING_VIEW_SPREAD`)
- `rank_diff = j_short - i_long` (càng xa nhau về rank thì Q càng lớn)
- Chia 252 để chuyển về daily scale phù hợp với BL formula.

### 6.4 Triển khai

File: `gen_view/ranking/relative_views.py`

```python
P, Q, confidence, view_names = generate_ranking_relative_views(
    rank_scores=rank_scores,
    ensemble_std=ensemble_std,
    assets=asset_list,       # Danh sách tài sản tối ưu (gồm GOLD, MBBOND)
    spread=0.03,
)
```

---

## 7. Giai đoạn 5: Dynamic Confidence

### 7.1 Công thức confidence

```
margin               = score_long - score_short
margin_bonus         = margin * RANKING_MARGIN_SCALE
disagreement_penalty = (std_long + std_short) / 2 * RANKING_DISAGREEMENT_SCALE

confidence = clip(
    RANKING_CONF_BASE + margin_bonus - disagreement_penalty,
    RANKING_CONF_MIN,
    RANKING_CONF_MAX,
)
```

### 7.2 Ý nghĩa từng thành phần

| Thành phần | Ý nghĩa |
|---|---|
| `margin_bonus` | Khoảng cách score càng lớn → model càng "tự tin" → confidence cao hơn |
| `disagreement_penalty` | Ensemble std càng cao → các model không đồng thuận → confidence thấp hơn |
| `RANKING_CONF_BASE` | 0.50 — điểm khởi đầu trung lập |
| `RANKING_CONF_MIN/MAX` | 0.25 / 0.75 — floor và ceiling |

### 7.3 Từ confidence sang Omega

Black-Litterman sử dụng:

```
Ω = diag(P * τ * Σ * P^T) / confidence
```

Confidence cao → Omega nhỏ → BL tin tưởng view nhiều hơn.
Confidence thấp → Omega lớn → BL coi view như nhiễu.

---

## 8. Giai đoạn 6: Tích hợp Black-Litterman

### 8.1 Tích hợp vào backtest

File: `backtest.py`

Backtest hỗ trợ mode mới `--view-mode ranking`:

```python
if view_mode == "ranking":
    # 1. Re-select representatives nếu đến hạn
    if t - last_reselect_t >= RANKING_RESELECT_FREQUENCY:
        selected_stocks = select_representatives(universe_up_to_t, k=RANKING_K)

    # 2. Retrain ranking model nếu đến hạn
    if t - last_ranking_retrain_t >= RANKING_RETRAIN_FREQUENCY:
        ranking_model.train(stock_prices_train, market_train)

    # 3. Predict rankings và sinh relative views
    rank_scores, ensemble_std = ranking_model.predict(stock_prices_recent, market_recent)
    P, Q, conf, names = generate_ranking_relative_views(rank_scores, ensemble_std, assets)

    # 4. BL tính posterior returns
    mu_bl = black_litterman_posterior_mu(sigma, market_weights, P, Q, conf)
```

### 8.2 Tương thích ngược

- Các mode cũ (`rule_based`, `relative`, `ml`, `combined`) vẫn hoạt động bình thường.
- Mode mới `ranking` được thêm vào `choices` của argparse mà không ảnh hưởng đến code hiện có.

---

## 9. Giai đoạn 7: Xây dựng danh mục

### 9.1 Cấu trúc danh mục

Danh mục tối ưu gồm 2 nhóm:

**Core Assets (phòng thủ) — giữ nguyên:**
- GOLD
- MBBOND

**Stock Sleeve (đại diện VN30) — thay đổi động:**
- 5 cổ phiếu được chọn bởi Combinatorial Optimization (global optimum)
- Trọng số tối ưu từ BL+MVO

### 9.2 File cấu hình tài sản

`assets_1.json` định nghĩa universe đầy đủ:
- 30 cổ phiếu VN30
- GOLD
- MBBOND
- E1VFVN30 (dùng làm market proxy)

---

## 10. Giai đoạn 8: Quản lý Rủi ro (Risk Management)

Một tầng quản lý rủi ro chủ động được thêm riêng cho chế độ `ranking` nhằm bảo vệ danh mục trong các giai đoạn thị trường biến động mạnh hoặc khủng hoảng. Toàn bộ logic được đóng gói trong `gen_view/ranking/risk_management.py` và được kích hoạt mỗi lần rebalance.

Tầng này gồm 4 thành phần độc lập nhưng phối hợp chặt chẽ:

### 10.1 Phát hiện chế độ thị trường (Regime Detection)

Hàm: `detect_market_regime(returns, t, lookback)`

**Hai tín hiệu chính:**

1. **Vol ratio** = volatility 20 ngày gần nhất / volatility 120 ngày lịch sử.
2. **Drawdown** = mức giảm hiện tại so với đỉnh trên cửa sổ `lookback` ngày (mặc định 60).

**Phân loại 3 chế độ:**

| Chế độ | Điều kiện | Ý nghĩa |
|---|---|---|
| **Normal** | `vol_ratio < 1.3` VÀ `drawdown > -10%` | Thị trường ổn định |
| **Stress** | `vol_ratio >= 1.3` HOẶC `drawdown <= -10%` | Thị trường căng thẳng |
| **Crisis** | `vol_ratio >= 1.8` HOẶC `drawdown <= -20%` | Khủng hoảng |

Đầu ra là dict chứa `regime`, `vol_ratio`, `drawdown`, `equity_momentum` — được consumer ở downstream sử dụng để quyết định mức độ phòng thủ.

### 10.2 Sinh Defensive Views

Hàm: `generate_defensive_views(regime, assets, defensive_assets, confidence)`

Khi regime là `stress` hoặc `crisis`, hệ thống chèn thêm các view BL ưu tiên tài sản phòng thủ (GOLD, MBBOND) so với rổ cổ phiếu trung bình:

```
View GOLD:    +1·GOLD   − (1/n_stocks)·Σ stocks
View MBBOND:  +1·MBBOND − (1/n_stocks)·Σ stocks
```

**Spread theo mức độ nghiêm trọng:**

| Regime | Annual spread | Daily Q | Confidence |
|---|---|---|---|
| Stress | 5% | 0.05 / 252 | 0.80 × 0.85 = 0.68 |
| Crisis | 10% | 0.10 / 252 | 0.80 × 1.00 = 0.80 (full) |

Các view này được **stack chung** với P/Q của ranking views trước khi đưa vào Black-Litterman, kéo posterior dịch chuyển về phía tài sản an toàn một cách định lượng.

### 10.3 Constrained Portfolio Optimizer

Hàm: `optimize_weight_ranking(...)` trong `backtest.py`.

Đây là biến thể MVO chuyên dụng cho ranking mode với 3 ràng buộc cứng + 1 ràng buộc động:

| Ràng buộc | Giá trị mặc định | Mục đích |
|---|---|---|
| **Sàn phòng thủ** (`min_defensive_weight`) | 25% (GOLD + MBBOND) | Đảm bảo lúc nào cũng có đệm an toàn |
| **Trần cổ phiếu** (`max_equity_exposure`) | 70% | Giới hạn rủi ro đầu cơ |
| **Risk aversion (normal)** | 2.5 | Cao hơn đáng kể so với 0.5 ở các mode khác → utility nghiêng về giảm rủi ro |
| **Risk aversion (stress/crisis)** | 5.0 | Tăng risk aversion lên gấp đôi khi regime chuyển sang stress hoặc crisis |

- **Fallback weights** (khi optimizer không hội tụ): vẫn tôn trọng sàn phòng thủ — không bao giờ cho phép `GOLD + MBBOND < 25%`.
- **Tự động chuyển δ**: tham số `risk_aversion` được caller chọn động dựa trên regime trả về từ bước 10.1.

### 10.4 Volatility Dampener cho ranking views

Ngoài defensive views, hệ thống còn giảm trực tiếp confidence của các relative ranking views khi thị trường biến động:

```
if vol_ratio > RANKING_VOL_DAMPENER_THRESHOLD (= 1.3):
    factor = RANKING_VOL_DAMPENER_THRESHOLD / vol_ratio   # < 1
    confidence_ranking *= factor
```

**Ý nghĩa:** khi thị trường nhiễu (vol_ratio cao), tín hiệu ranking ít đáng tin hơn → confidence giảm → Omega tăng → BL posterior trở về gần market equilibrium thay vì bám sát view của model. Cơ chế này hoạt động độc lập với defensive views và bổ trợ cho nhau.

### 10.5 Luồng tổng hợp tại mỗi rebalance

```
Đầu vào: returns, t, ranking views (P_r, Q_r, conf_r)
        │
        ▼
  detect_market_regime(returns, t)
        │  → regime ∈ {normal, stress, crisis}, vol_ratio, drawdown
        │
        ├─ if vol_ratio > 1.3:
        │     conf_r *= (1.3 / vol_ratio)        # Volatility Dampener
        │
        ├─ if regime != normal:
        │     (P_d, Q_d, conf_d) = generate_defensive_views(regime, assets)
        │     P, Q, conf = stack(P_r ∥ P_d), stack(Q_r ∥ Q_d), stack(conf_r ∥ conf_d)
        │  else:
        │     P, Q, conf = P_r, Q_r, conf_r
        │
        ▼
  μ_BL = black_litterman_posterior(Σ, w_mkt, P, Q, conf)
        │
        ▼
  δ = RANKING_RISK_AVERSION_STRESS  if regime != normal
      else RANKING_RISK_AVERSION_BASE
        │
        ▼
  w = optimize_weight_ranking(
          μ_BL, Σ,
          risk_aversion       = δ,
          min_defensive_weight = 0.25,
          max_equity_exposure  = 0.70,
      )
```

---

## 11. Walk-Forward Validation

### 11.1 Luồng walk-forward cho ranking mode

```
Tại mỗi lần rebalance (mỗi 5 ngày):
├─ Nếu đến hạn reselect (mỗi 60 ngày):
│   └─ Chạy Combinatorial Optimization trên dữ liệu tích lũy → chọn 5 đại diện mới
│      (global optimum, không phụ thuộc khởi tạo)
│
├─ Nếu đến hạn retrain (mỗi 20 ngày):
│   └─ Train XGBoost Ranker trên expanding window
│      (có embargo gap = 5 ngày tránh label leakage)
│
├─ Predict ranking scores cho 5 đại diện
├─ Sinh relative views (P_r, Q_r, confidence_r)
│
├─ ★ Risk Management Layer:
│   ├─ detect_market_regime(returns, t) → {normal | stress | crisis}
│   ├─ Nếu vol_ratio > 1.3 → Volatility Dampener giảm confidence_r
│   └─ Nếu regime != normal → Inject defensive views (GOLD/MBBOND outperform)
│
├─ Black-Litterman tính posterior mu (gộp ranking views + defensive views)
└─ Constrained MVO (optimize_weight_ranking):
   • min 25% GOLD+MBBOND, max 70% cổ phiếu
   • risk_aversion = 5.0 nếu stress/crisis, 2.5 nếu normal
```

### 11.2 Tần suất cấu hình

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `RANKING_RESELECT_FREQUENCY` | 60 | ~3 tháng chọn lại đại diện |
| `RANKING_RETRAIN_FREQUENCY` | 20 | ~1 tháng train lại model |
| `RANKING_FEATURE_WINDOW` | 60 | Cần 60 ngày lịch sử cho features |
| `RANKING_PREDICTION_HORIZON` | 5 | Dự đoán 5 ngày tới (1 tuần) |

---

## 12. Tham số cấu hình

### 12.1 config.py (toàn dự án)

```python
# ====================== RANKING MODE ======================
RANKING_K = 5                          # Số cổ phiếu đại diện
RANKING_PREDICTION_HORIZON = 5         # Horizon dự đoán (ngày)
RANKING_FEATURE_WINDOW = 60            # Cửa sổ tính feature
RANKING_RETRAIN_FREQUENCY = 20         # Tần suất train lại
RANKING_RESELECT_FREQUENCY = 60        # Tần suất chọn lại đại diện
RANKING_VIEW_SPREAD = 0.03             # Spread annual cho relative views
VN30_LIST_PATH = "datasets/vn30_list.txt"

# ====================== RANKING RISK MANAGEMENT ======================
RANKING_MIN_DEFENSIVE_WEIGHT  = 0.25   # Sàn GOLD + MBBOND (defensive floor)
RANKING_MAX_EQUITY_EXPOSURE   = 0.70   # Trần cổ phiếu (equity exposure cap)
RANKING_VOL_DAMPENER_THRESHOLD = 1.3   # Vol ratio kích hoạt dampener / regime stress
RANKING_VOL_DAMPENER_SEVERE   = 1.8    # Vol ratio kích hoạt regime crisis
RANKING_DRAWDOWN_LOOKBACK     = 60     # Số ngày tính drawdown
RANKING_DRAWDOWN_STRESS_THRESHOLD    = -0.10  # Drawdown -10% → stress
RANKING_DRAWDOWN_CRISIS_THRESHOLD    = -0.20  # Drawdown -10% → crisis
RANKING_DEFENSIVE_CONFIDENCE  = 0.80   # Confidence cho defensive views
RANKING_RISK_AVERSION_BASE    = 2.5    # δ cho regime normal (vs 0.5 ở các mode khác)
RANKING_RISK_AVERSION_STRESS  = 5.0    # δ cho regime stress / crisis
```

### 12.2 gen_view/ranking/config.py (module ranking)

```python
# Stock selection
# (Combinatorial Optimization vét cạn toàn cục — KHÔNG cần max_iter)
# KMEDOIDS_MAX_ITER vẫn tồn tại như placeholder để tương thích ngược,
# nhưng KHÔNG được thuật toán mới sử dụng.

# XGBoost Ranker
DEFAULT_RANKER_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "tree_method": "hist",
    "objective": "rank:pairwise",
}

# Feature periods
RANKING_MOMENTUM_PERIODS = [5, 20, 60]
RANKING_VOLATILITY_WINDOWS = [20, 60]
RANKING_RSI_PERIOD = 14

# Ensemble
RANKING_ENSEMBLE_SIZE = 5
RANKING_ENSEMBLE_BASE_SEED = 42

# Confidence
RANKING_CONF_BASE = 0.50
RANKING_CONF_MIN = 0.25
RANKING_CONF_MAX = 0.75
RANKING_MARGIN_SCALE = 2.0
RANKING_DISAGREEMENT_SCALE = 5.0
```

---

## 13. Cách sử dụng

### 13.1 Chạy backtest với ranking mode

```bash
python backtest.py --phase test --view-mode ranking --assets-config assets_1.json
```

### 13.2 So sánh với baseline

```bash
# Baseline: ML regression + absolute views
python backtest.py --phase test --view-mode ml --assets-config assets_0.json

# Mới: Ranking + relative views + risk management
python backtest.py --phase test --view-mode ranking --assets-config assets_1.json
```

### 13.3 Tùy chỉnh tham số

Chỉnh sửa trực tiếp trong `config.py` hoặc `gen_view/ranking/config.py`:
- Tăng `RANKING_K` để chọn nhiều đại diện hơn.
- Điều chỉnh `RANKING_VIEW_SPREAD` để thay đổi độ lớn relative views.
- Thay đổi `RANKING_CONF_BASE` để điều chỉnh mức confidence trung bình.
- Tăng `RANKING_MIN_DEFENSIVE_WEIGHT` nếu muốn danh mục bảo thủ hơn.
- Giảm `RANKING_MAX_EQUITY_EXPOSURE` nếu muốn hạn chế rủi ro cổ phiếu.
- Nạp `RANKING_RISK_AVERSION_*` cao hơn nếu muốn optimizer uống về phía variance thấp.

---

## 14. Đánh giá và metrics

### 14.1 Portfolio Metrics

So sánh trực tiếp với baseline trên các chỉ số:

| Metric | Ý nghĩa |
|---|---|
| Annual Return | Lợi suất danh mục hàng năm |
| Annual Volatility | Độ biến động hàng năm |
| Sharpe Ratio | Lợi suất/rủi ro |
| Sortino Ratio | Lợi suất/rủi ro downside |
| Maximum Drawdown | Mức giảm tối đa từ đỉnh |
| Calmar Ratio | Lợi suất / MDD |

### 14.2 Ranking Model Metrics

| Metric | Ý nghĩa |
|---|---|
| Ranking Accuracy | Tỷ lệ dự đoán đúng thứ hạng |
| Pairwise Accuracy | Tỷ lệ cặp so sánh đúng |
| NDCG | Normalized Discounted Cumulative Gain |
| Spearman Rank Correlation | Tương quan thứ hạng Spearman |

---

## 15. Tổng kết file structure

```
portfolio-optimization/
├── config.py                              # Thêm tham số ranking + risk management
├── assets_1.json                          # Universe 30 VN30 + GOLD + MBBOND
├── backtest.py                            # Thêm mode "ranking" + optimize_weight_ranking
├── gen_view/
│   ├── view_generators.py                 # Thêm generate_ranking_views_bridge
│   └── ranking/                           # MODULE MỚI
│       ├── __init__.py
│       ├── config.py                      # Cấu hình module ranking
│       ├── stock_selection.py             # Combinatorial Optimization (global optimum)
│       ├── ranking_model.py               # XGBoost Ranker Ensemble
│       ├── relative_views.py              # Sinh relative views
│       ├── feature_engineering.py         # Features cho ranking
│       └── risk_management.py             # Regime detection + defensive views
└── datasets/
    └── vn30_list.txt                      # Danh sách 30 mã VN30
```

---

## 16. Hướng phát triển tiếp theo

1. **Sector-aware selection**: Thêm thông tin ngành khi chọn đại diện để đảm bảo phủ sóng đa dạng ngành.
2. **Dynamic K**: Điều chỉnh K dựa trên điều kiện thị trường (K lớn hơn khi vol cao).
3. **Hybrid views**: Kết hợp relative views với rule-based views cho core assets.
4. **Online learning**: Cập nhật model incrementally thay vì retrain từ đầu.
5. **Transaction cost**: Tích hợp chi phí giao dịch vào tối ưu, đặc biệt khi reselection thay đổi universe.
6. **Regime model nâng cao**: Thay rule-based regime bằng HMM hoặc machine learning classifier học trực tiếp từ dữ liệu thị trường.
7. **Defensive asset động**: Mở rộng bộ tài sản phòng thủ vượt quá GOLD + MBBOND, ví dụ USD bond, treasury, defensive stocks.
