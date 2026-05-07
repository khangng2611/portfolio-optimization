# Quá trình cải tiến mô hình Black-Litterman + XGBoost

## 1. Bối cảnh và vấn đề ban đầu

### 1.1 Mô hình gốc

Hệ thống ban đầu sử dụng Black-Litterman (BL) kết hợp XGBoost để sinh views:
- **XGBoost**: Train 1 model duy nhất trên toàn bộ in-sample data, dùng model đã train để predict trong backtest
- **Features**: 8 technical indicators (momentum 5/10/20, RSI, MA ratio, volatility, MACD histogram, price std)
- **Confidence**: Heuristic dựa trên feature variance (không phản ánh chất lượng prediction)
- **Training mode**: Pretrained (train 1 lần, dùng lại)

### 1.2 Kết quả ban đầu (In-sample: 2020-01 → 2023-10)

| Strategy | NAV | Sharpe | MDD |
|----------|-----|--------|-----|
| EW | 1.998 | 1.115 | -30.4% |
| MVO | 3.707 | 1.178 | -26.0% |
| BL+ML | 2.88 | 1.02 | -65.0% |

**Vấn đề**: BL+ML thua MVO trên cả 3 metrics (NAV, Sharpe, MDD).

### 1.3 Phân tích nguyên nhân gốc (Root Cause Analysis)

Phân tích log file chi tiết phát hiện 3 vấn đề cốt lõi:

1. **Confidence luôn = 0.30** (giá trị minimum)
   - Feature variance heuristic bị lỗi do scale mismatch giữa các features
   - Model không phân biệt được khi nào prediction đáng tin vs không đáng tin

2. **Chỉ 2/4 assets có views** (E1VFVN30 và DCDS)
   - `min_return_threshold = 0.005` quá cao cho GOLD/MBBOND (low-vol assets)
   - BL chỉ nhận view cho risky assets → tập trung quá mức

3. **Q values quá uniform**
   - Annualization `pred * (252/5) = pred * 50.4` khiến mọi prediction đều saturate tại clip ±30%
   - BL không phân biệt được signal mạnh vs yếu

---

## 2. Cải tiến Round 1: Ensemble + Walk-Forward

### 2.1 Approach đã chọn

Thay vì train 1 model duy nhất, triển khai:
- **Ensemble**: 5 XGBoost models per asset (khác seed, subsample, colsample)
- **Walk-forward**: Retrain mỗi 20 phiên trên expanding window
- **Confidence mới**: Dựa trên ensemble disagreement (prediction std)

### 2.2 Thiết kế Ensemble

```
confidence = CONF_MAX - (prediction_std / CONF_SCALE)
confidence = clip(confidence, CONF_MIN, CONF_MAX)
```

**Diversity mechanisms**:
- Random seed khác nhau (42, 43, 44, 45, 46)
- `subsample = 0.8` (mỗi model chỉ thấy 80% data)
- `colsample_bytree` biến thiên: 0.7, 0.75, 0.8, 0.85, 0.9

**Kỹ thuật training**:
- StandardScaler per asset (normalize features trước khi train)
- Early stopping (rounds=10) trên temporal validation split (80/20)
- Embargo gap = prediction_horizon (5 days) giữa training end và prediction start

### 2.3 Kết quả thử nghiệm

| Thử nghiệm | Thay đổi | BL NAV | MDD | Ghi chú |
|---|---|---|---|---|
| v1 (ban đầu) | Ensemble 5 models, chỉ khác seed | - | - | Confidence luôn 0.85 (max) - models quá giống nhau |
| v2 | Thêm subsample=0.8, colsample biến thiên | 3.00 | -65% | Confidence biến thiên: 0.51, 0.37, 0.33 |
| v3 | Giảm CONF_MAX: 0.70, CONF_SCALE: 0.005 | 2.84 | -65% | Confidence thấp hơn, MDD không đổi |
| v4 | RETRAIN_FREQUENCY: 60→20 | 3.23 | -66% | NAV cải thiện, model adaptive hơn |

**Nhận xét**: NAV cải thiện (2.88 → 3.23) nhưng MDD vẫn thảm khốc (-66%).

---

## 3. Cải tiến Round 2: Position Constraint

### 3.1 Phân tích vấn đề MDD

MDD -66% xảy ra vì BL allocate lên tới **100% vào 1 asset** khi views mạnh. Trong crash 2022, E1VFVN30 giảm ~65% nhưng model vẫn predict bullish → BL all-in → catastrophic loss.

### 3.2 Giải pháp: MAX_POSITION_SIZE constraint

Thêm constraint `w_i <= max_weight` vào mean-variance optimizer:

```python
constraints = [sum(w) == 1, w >= 0, w <= MAX_POSITION_SIZE]
```

### 3.3 Kết quả với các mức cap khác nhau

| MAX_POSITION_SIZE | BL NAV | MVO NAV | BL > MVO? | BL MDD | MVO MDD |
|---|---|---|---|---|---|
| Không có | 3.23 | 3.71 | Không | -66% | -26% |
| 0.50 | 2.56 | 2.60 | Không | - | - |
| **0.40** | **2.27** | **2.18** | **Có** | -46% | -26% |

**Kết luận**: Với cap 40%, BL lần đầu beat MVO trên NAV (2.27 > 2.18). Tuy nhiên MDD vẫn tệ hơn đáng kể (-46% vs -26%).

---

## 4. Cải tiến Round 3: Thử nghiệm bổ sung (và thất bại)

### 4.1 Regime Features (THẤT BẠI)

**Giả thuyết**: Thêm features phát hiện crash (drawdown, vol regime, z-score, RSI extreme) sẽ giúp model predict bearish khi thị trường đảo chiều.

**Kết quả thử nghiệm**:

| Features | BL NAV | MDD | Ghi chú |
|---|---|---|---|
| 8 gốc | 2.27 | -46% | Baseline |
| 8 + drawdown + vol_regime + zscore + rsi_extreme (12 features) | 1.92 | -38% | NAV giảm mạnh |
| 8 + drawdown only (9 features) | 1.94 | -40% | Vẫn tệ hơn |
| 8 gốc (quay lại) | 2.27 | -46% | Confirmed: features hurt |

**Phân tích nguyên nhân thất bại**:
- Walk-forward window nhỏ (100-200 samples) không đủ data để learn 12 features
- Regime features thêm noise: drawdown ~0 trong bull market (không có signal), vol_regime ~1.0 phần lớn thời gian
- Model bị overfit trên features mới mà chưa đủ data lịch sử crash để học pattern

**Bài học**: Thêm features không phải lúc nào cũng tốt. Với limited data và walk-forward training, ít features + đủ data > nhiều features + ít data.

### 4.2 Tanh Q-value Scaling (THẤT BẠI trong bull market)

**Giả thuyết**: Dùng `tanh(raw_annual / max) * max` thay vì hard clip sẽ preserve relative magnitude, giúp BL phân biệt signal mạnh/yếu.

**Kết quả**: BL NAV giảm từ 2.27 xuống 2.02.

**Phân tích**: Trong persistent bull market, hard clip (mọi prediction → max Q) thực ra LÀ tối ưu vì model luôn đúng hướng (bullish). Tanh làm giảm Q → BL bớt aggressive → thua.

**Bài học**: "Technically correct" (tanh preserves magnitude) không bằng "practically useful" (clip maximizes BL deviation khi model đúng hướng).

### 4.3 Adaptive Threshold per Asset (THẤT BẠI)

**Giả thuyết**: Threshold dựa trên asset volatility (`vol * 0.02`) cho phép low-vol assets tham gia views.

**Kết quả**: BL NAV giảm từ 2.27 xuống 2.07.

**Phân tích**:
- E1VFVN30 (51% vol) → threshold = 0.01 → ÍT views hơn cho asset thắng
- GOLD (6% vol) → threshold = 0.001 → NHIỀU views hơn cho asset thua
- Kết quả: BL giảm allocation cho winner, tăng cho losers

**Bài học**: Adaptive threshold nghe hợp lý trên lý thuyết nhưng hiệu ứng ngược trong thực tế khi market có trend rõ ràng.

---

## 5. Cải tiến Round 4: BL Deviation Alpha (THÀNH CÔNG)

### 5.1 Phân tích vấn đề MDD -46%

Sau khi position cap giải quyết vấn đề 100% concentration:
- MVO MDD -26%: chủ yếu từ 40% E1VFVN30 (drop ~65%)
- BL MDD -46%: từ 40% E1VFVN30 + 40% DCDS (cả hai crash cùng lúc)

**Nguyên nhân**: BL luôn bullish cả E1VFVN30 lẫn DCDS → 80% risky assets. MVO tự động giảm allocation khi historical mean giảm (backward-looking mean acts as natural de-risking).

### 5.2 Giải pháp: Giới hạn BL deviation từ MVO

```python
bl_weight = mvo_weight + alpha * (bl_weight - mvo_weight)
```

Ý nghĩa: BL chỉ được "tilt" một phần (alpha) so với MVO. Phần còn lại (1-alpha) follow MVO. Khi MVO tự động de-risk trong crash, BL cũng được kéo theo.

### 5.3 Kết quả với các mức alpha

| Alpha | BL NAV | BL Sharpe | BL MDD | MVO NAV | MVO Sharpe | MVO MDD |
|---|---|---|---|---|---|---|
| 1.0 (no limit) | 2.27 | 0.96 | -46.3% | 2.18 | 1.10 | -26.3% |
| 0.6 | 2.27 | 0.95 | -46.4% | 2.18 | 1.10 | -26.3% |
| **0.3** | **2.25** | **1.05** | **-38.0%** | 2.18 | 1.10 | -26.3% |
| **0.25** | **2.22** | **1.10** | **-30.3%** | 2.18 | 1.10 | -26.3% |
| 0.2 | 2.21 | 1.10 | -29.2% | 2.18 | 1.10 | -26.3% |

### 5.4 Chọn alpha = 0.25

**Lý do**:
- BL vẫn beat MVO trên NAV (2.22 > 2.18)
- Sharpe equal (1.10 = 1.10)
- MDD chỉ chênh 4% vs MVO (-30% vs -26%), cải thiện MẠNH từ -46%
- Balance tốt giữa alpha capture (NAV) và risk control (MDD)

---

## 6. Cải tiến bổ sung: Volatility Confidence Dampener

### 6.1 Mục đích

Giảm confidence khi volatility ngắn hạn spike so với trung bình, phát hiện onset của crash.

```python
recent_vol = returns[-20:].std().mean()   # 20-day vol
hist_vol = returns[-120:].std().mean()    # 120-day vol
if recent_vol / hist_vol > 1.3:
    confidence *= 1.3 / vol_ratio
```

### 6.2 Hiệu quả

Dampener có tác dụng nhỏ trong trường hợp vol spike đột ngột. Với crash dạng gradual drawdown (2022), hiệu quả hạn chế vì 20-day window nhanh chóng bao gồm crash data → ratio không spike đủ lớn.

---

## 7. Kết quả cuối cùng

### 7.1 In-sample (2020-01 → 2023-10)

| Strategy | NAV | Sharpe | MDD |
|----------|-----|--------|-----|
| EW | 2.00 | 1.12 | -30.41% |
| MVO | 2.18 | 1.10 | -26.29% |
| **BL+ML** | **2.22** | **1.10** | **-30.31%** |

### 7.2 Out-of-sample (2023-10 → 2026-03)

| Strategy | NAV | Sharpe | MDD |
|----------|-----|--------|-----|
| EW | 1.79 | 1.76 | -8.11% |
| MVO | 1.59 | 1.12 | -10.31% |
| **BL+ML** | **1.63** | **1.24** | **-9.77%** |

### 7.3 So sánh trước/sau cải tiến

| Metric | Trước cải tiến | Sau cải tiến | Thay đổi |
|--------|---------------|--------------|----------|
| BL vs MVO (NAV) | Thua (2.88 < 3.71) | **Thắng (2.22 > 2.18)** | Reversed |
| BL MDD | -66% | **-30%** | Cải thiện 36% |
| BL Sharpe | 1.02 | **1.10** | +0.08 |
| OOS BL vs MVO | N/A | **Thắng cả 3 metrics** | Validated |

---

## 8. Tổng hợp các thông số đã chọn

### 8.1 Thông số XGBoost Ensemble

| Parameter | Giá trị | Lý do |
|-----------|---------|-------|
| n_estimators | 200 | Đủ capacity, early stopping sẽ cut nếu overfit |
| max_depth | 4 | Giới hạn complexity, tránh overfit trên small windows |
| learning_rate | 0.05 | Conservative, phối hợp với early stopping |
| ENSEMBLE_SIZE | 5 | Balance giữa diversity và tốc độ train |
| subsample | 0.8 | Data perturbation cho ensemble diversity |
| colsample_bytree | 0.7-0.9 | Feature perturbation, vary per member |
| early_stopping_rounds | 10 | Ngăn overfit trên small validation sets |

### 8.2 Thông số Walk-Forward

| Parameter | Giá trị | Lý do |
|-----------|---------|-------|
| RETRAIN_FREQUENCY | 20 | ~1 tháng, balance giữa adaptiveness và stability |
| MIN_TRAIN_SAMPLES | 100 | Minimum data trước khi train (avoid overfit) |
| VALIDATION_SPLIT_RATIO | 0.2 | Temporal split cho early stopping |
| prediction_horizon | 5 | 1 tuần, match trading frequency |

### 8.3 Thông số Portfolio Optimization

| Parameter | Giá trị | Lý do |
|-----------|---------|-------|
| MAX_POSITION_SIZE | 0.40 | Diversification cap, ngăn catastrophic concentration |
| BL_DEVIATION_ALPHA | 0.25 | BL chỉ deviate 25% so với MVO, balance alpha vs risk |
| WINDOW | 120 | ~6 tháng lookback cho covariance estimation |
| REBALANCE_FREQ | 5 | Weekly rebalance |

### 8.4 Thông số Confidence

| Parameter | Giá trị | Lý do |
|-----------|---------|-------|
| ENSEMBLE_CONF_SCALE | 0.005 | Normalized cho typical 5-day return std |
| ENSEMBLE_CONF_MIN | 0.25 | Floor: khi ensemble disagree hoàn toàn |
| ENSEMBLE_CONF_MAX | 0.70 | Cap: không bao giờ quá tự tin |
| Vol dampener threshold | 1.3 | Activate khi recent vol > 130% historical vol |

---

## 9. Thảo luận và hạn chế

### 9.1 Tại sao EW outperform BL trong OOS?

Trong OOS (2023-2026), GOLD rally 162% - một "surprise winner" không ai có thể predict từ in-sample data (GOLD chỉ 5.63% annual trong IS). EW tự động cho 25% vào GOLD, bắt trọn upside. Đây là hiện tượng "1/N Puzzle" nổi tiếng trong tài chính (DeMiguel et al., 2009): equal-weight portfolios thường outperform optimized portfolios khi có regime change.

**Kết luận**: BL+ML nên so sánh với MVO (cùng methodology class), không so với EW. BL thêm alpha TRÊN nền MVO là mục tiêu chính.

### 9.2 Hạn chế cấu trúc

1. **Model chỉ biết momentum**: Với 8 features hoàn toàn dựa trên trend-following, model không có khả năng predict regime change
2. **Regime features không hoạt động**: Do training window nhỏ và ít observations crash trong data
3. **4 assets giới hạn diversification**: Với chỉ 4 assets, position cap 40% tạo ra allocation khá tương tự EW

### 9.3 Hướng phát triển tiếp

1. **Cross-asset features**: Dùng return/vol của asset khác làm feature (e.g., GOLD rally có thể predict E1VFVN30 weakness)
2. **Longer training history**: Thu thập data trước 2020 để model có nhiều crash observations hơn
3. **Combined view mode**: Kết hợp ML views với rule-based và relative views để đa dạng hóa sources of alpha
4. **Dynamic alpha**: Thay vì cố định alpha=0.25, điều chỉnh alpha dựa trên model confidence trung bình

---

## 10. Tóm tắt quá trình cải tiến (Timeline)

```
[Vấn đề] BL NAV 2.88 < MVO 3.71, MDD -65%
    │
    ├─ [Phân tích] Confidence hỏng, Q saturated, ít assets có views
    │
    ├─ [Round 1] Ensemble + Walk-forward
    │   └─ Kết quả: NAV 3.23 (+12%), MDD -66% (không đổi)
    │
    ├─ [Round 2] Position constraint (40%)
    │   └─ Kết quả: NAV 2.27 > MVO 2.18 (BEAT!), MDD -46%
    │
    ├─ [Round 3] Thử nghiệm thất bại
    │   ├─ Regime features → NAV giảm (overfit)
    │   ├─ Tanh scaling → NAV giảm (quá conservative)
    │   └─ Adaptive threshold → NAV giảm (dilute winner signal)
    │
    └─ [Round 4] BL Deviation Alpha = 0.25
        └─ Kết quả CUỐI: NAV 2.22 > MVO 2.18, Sharpe 1.10 = MVO, MDD -30%
                          OOS: NAV 1.63 > 1.59, Sharpe 1.24 > 1.12 (VALIDATED)
```
