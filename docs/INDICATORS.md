# Technical Indicators for Black-Litterman View Generation

This document explains the technical indicators used in `view_generators.py` to dynamically generate views for the Black-Litterman portfolio optimization model.

## Table of Contents

1. [Overview](#overview)
2. [Moving Averages](#moving-averages)
   - [Simple Moving Average (SMA)](#simple-moving-average-sma)
   - [Exponential Moving Average (EMA)](#exponential-moving-average-ema)
3. [Momentum Indicators](#momentum-indicators)
   - [Rate of Change (ROC/Momentum)](#rate-of-change-rocmomentum)
   - [Relative Strength Index (RSI)](#relative-strength-index-rsi)
4. [Trend Indicators](#trend-indicators)
   - [MACD](#macd-moving-average-convergence-divergence)
5. [Volatility Indicators](#volatility-indicators)
   - [Bollinger Bands](#bollinger-bands)
   - [Average True Range (ATR)](#average-true-range-atr)
6. [How Indicators Generate Views](#how-indicators-generate-views)

---

## Overview

The view generators use technical analysis indicators to form expectations (views) about future asset returns. These views are then incorporated into the Black-Litterman model to adjust the equilibrium returns.

```
Price Data --> Technical Indicators --> Signals --> Views --> Black-Litterman --> Optimal Weights
```

---

## Moving Averages

Moving averages smooth price data to identify trends by filtering out short-term noise.

### Simple Moving Average (SMA)

**Formula:**
```
SMA(n) = (P_1 + P_2 + ... + P_n) / n
```

**Visual Representation:**
```
Price   |     *
        |   *   *     *
        | *       * *   *
        |           
        +-------------------> Time
        
SMA     |       ----
        |   ----    ----
        | --            --
        +-------------------> Time
```

**Characteristics:**
- Lagging indicator (reacts slowly to price changes)
- Equal weight to all observations in the window
- Good for identifying long-term trends
- Used period: 20 days (default)

**Implementation:**
```python
def compute_sma(prices: pd.Series, period: int) -> pd.Series:
    return prices.rolling(window=period, min_periods=1).mean()
```

### Exponential Moving Average (EMA)

**Formula:**
```
EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}
where alpha = 2 / (period + 1)
```

**Visual Representation:**
```
Weights applied to prices:
       Today    Yesterday   2 days ago   3 days ago  ...
EMA:   [====]   [===]       [==]         [=]
SMA:   [===]    [===]       [===]        [===]       (equal weights)
```

**Characteristics:**
- More responsive to recent price changes than SMA
- Gives exponentially decreasing weight to older prices
- Better for short-term trend detection
- Used periods: 10 (short), 30 (long)

**Implementation:**
```python
def compute_ema(prices: pd.Series, period: int) -> pd.Series:
    return prices.ewm(span=period, adjust=False, min_periods=1).mean()
```

---

## Momentum Indicators

Momentum indicators measure the speed and magnitude of price movements.

### Rate of Change (ROC/Momentum)

**Formula:**
```
ROC = (P_today - P_{n days ago}) / P_{n days ago}
```

**Visual Representation:**
```
Price movement over 20 days:
100 --> 110 : ROC = +10%  (Bullish momentum)
100 --> 95  : ROC = -5%   (Bearish momentum)
100 --> 100 : ROC = 0%    (No momentum)
```

**Signal Interpretation:**
```
ROC > +1%  : Strong bullish momentum --> Generate positive view
ROC < -1%  : Strong bearish momentum --> Generate negative view
|ROC| < 1% : Weak momentum --> No view generated
```

**Implementation:**
```python
def compute_momentum(prices: pd.Series, period: int = 20) -> float:
    return (prices.iloc[-1] / prices.iloc[-period - 1]) - 1
```

### Relative Strength Index (RSI)

**Formula:**
```
RSI = 100 - (100 / (1 + RS))
where RS = Average Gain / Average Loss over n periods
```

**Visual Representation:**
```
RSI Scale (0-100):

100 |                          OVERBOUGHT ZONE (>70)
 70 |------------------------  Potential reversal down
    |
 50 |        NEUTRAL ZONE     Fair value
    |
 30 |------------------------  Potential reversal up
  0 |                          OVERSOLD ZONE (<30)
```

**Signal Interpretation:**
```
RSI > 70 : Overbought
  - If bullish view exists: reduce confidence
  - If bearish view exists: increase confidence

RSI < 30 : Oversold
  - If bullish view exists: increase confidence  
  - If bearish view exists: reduce confidence

30 <= RSI <= 70 : Neutral (no adjustment)
```

**Implementation:**
```python
def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]
```

---

## Trend Indicators

### MACD (Moving Average Convergence Divergence)

**Formula:**
```
MACD Line = EMA(12) - EMA(26)
Signal Line = EMA(MACD Line, 9)
Histogram = MACD Line - Signal Line
```

**Visual Representation:**
```
        |    MACD Line        Signal Line
        |      /\      /\
        |     /  \    /  \
   0 ---|----/----\--/----\----- Zero line
        |   /      \/      \
        |  /                \
        +-----------------------> Time
        
Histogram:
        |  [+] [+]      [+]
   0 ---|--------------------
        |      [-] [-]
```

**Signal Interpretation:**
```
MACD crosses above Signal: Bullish signal
  --> Generate positive view

MACD crosses below Signal: Bearish signal
  --> Generate negative view

Histogram > 0: Bullish momentum strengthening
Histogram < 0: Bearish momentum strengthening
```

**Implementation:**
```python
def compute_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = compute_ema(prices, fast)
    ema_slow = compute_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
```

---

## Volatility Indicators

### Bollinger Bands

**Formula:**
```
Middle Band = SMA(20)
Upper Band = Middle + 2 * STD(20)
Lower Band = Middle - 2 * STD(20)
```

**Visual Representation:**
```
        |     Upper Band ........
        |    .           .     .
Price   |   .   *   *     .   .
        |  .  *   *   *    . .
        | .                  *    <-- Price touches lower band
        |    Lower Band ........
        +-------------------------> Time
```

**Signal Interpretation:**
```
Price near Upper Band: Potentially overbought
  --> Reduce confidence in bullish views

Price near Lower Band: Potentially oversold
  --> Reduce confidence in bearish views

Band Width (Upper - Lower):
  Wide bands  = High volatility = Lower confidence
  Narrow bands = Low volatility = Higher confidence
```

**Implementation:**
```python
def compute_bollinger_bands(prices, period=20, num_std=2.0):
    sma = compute_sma(prices, period)
    std = prices.rolling(window=period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std
    return lower.iloc[-1], sma.iloc[-1], upper.iloc[-1]
```

### Average True Range (ATR)

**Formula:**
```
True Range = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
ATR = SMA(True Range, 14)
```

**Visual Representation:**
```
          High
           |
           |  True Range captures
           |  the largest move
    Close -+- (prev day)
           |
           |
          Low
```

**Use in View Generation:**
```
High ATR = High volatility = Lower confidence in views
Low ATR  = Low volatility  = Higher confidence in views

ATR is used to scale the uncertainty (omega) in Black-Litterman
```

---

## How Indicators Generate Views

### Rule-Based View Generator

The rule-based generator combines multiple indicators to generate views:

```
                    MA Crossover
                         |
                    +----v----+
                    | Signal  |
                    | Direction|
                    +----+----+
                         |
        +----------------+----------------+
        |                                 |
   +----v----+                       +----v----+
   |  RSI    |                       |Momentum |
   |Confidence|                       | Magnitude|
   |Adjustment|                       |         |
   +----+----+                       +----+----+
        |                                 |
        +----------------+----------------+
                         |
                    +----v----+
                    |  VIEW   |
                    |         |
                    | name    |
                    | return  |
                    | confidence|
                    +---------+
```

**Decision Logic:**

```python
# Step 1: MA Crossover determines direction
ma_ratio = (EMA_short / EMA_long) - 1

if ma_ratio > 2%:
    signal = "bullish"
    base_return = 5% + momentum_bonus
    base_confidence = 0.6
elif ma_ratio < -2%:
    signal = "bearish"
    base_return = -3% - momentum_penalty
    base_confidence = 0.5
else:
    # No clear signal, skip this asset
    continue

# Step 2: RSI adjusts confidence
if RSI > 70:  # Overbought
    if signal == "bullish":
        confidence *= 0.7  # Reduce confidence
    else:
        confidence *= 1.2  # Increase confidence
        
if RSI < 30:  # Oversold
    if signal == "bearish":
        confidence *= 0.7  # Reduce confidence
    else:
        confidence *= 1.2  # Increase confidence

# Step 3: Generate view
view = {
    "name": f"{asset}_rule_based",
    "legs": {asset: 1.0},
    "view_return_annual": base_return,
    "confidence": confidence
}
```

### Relative View Generator

Compares momentum between pairs of assets:

```
Asset A: Momentum = +8%
Asset B: Momentum = +2%
                    |
                    v
         Momentum Diff = 6%
                    |
                    v
    View: "A outperforms B by 6% annually"
    
    legs = {A: +1.0, B: -1.0}  # Long A, Short B
```

### ML-Based View Generator

Uses features from multiple indicators:

```
Features:
  - momentum_5, momentum_10, momentum_20
  - RSI
  - MA ratio (EMA10/EMA30)
  - Volatility (std of returns)
  - MACD histogram
          |
          v
    +------------+
    |  ML Model  |
    | (or fallback)|
    +------------+
          |
          v
    Predicted Return
    + Confidence
```

---

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `DEFAULT_MA_SHORT` | 10 | Short-term MA period |
| `DEFAULT_MA_LONG` | 30 | Long-term MA period |
| `DEFAULT_RSI_PERIOD` | 14 | RSI calculation period |
| `DEFAULT_MOMENTUM_PERIOD` | 20 | Momentum lookback period |
| `MA_CROSSOVER_THRESHOLD` | 0.02 | Min MA ratio for signal (2%) |
| `RSI_OVERBOUGHT` | 70 | RSI overbought threshold |
| `RSI_OVERSOLD` | 30 | RSI oversold threshold |
| `MOMENTUM_THRESHOLD` | 0.01 | Min momentum diff for relative views (1%) |

---

## Example Output

Running `view_generators.py` on sample data:

```
Rule-based Views:
  ASSET_A_rule_based: 8.50% (conf: 0.72)
  ASSET_C_rule_based: -4.20% (conf: 0.50)

Relative Views:
  ASSET_A_over_ASSET_B: 12.60% (conf: 0.65)
  ASSET_A_over_ASSET_C: 6.30% (conf: 0.52)

ML-based Views (fallback mode):
  ASSET_A_ml_pred: 5.04% (conf: 0.40)
  ASSET_B_ml_pred: -2.52% (conf: 0.40)
```

---

## References

- Murphy, J.J. (1999). *Technical Analysis of the Financial Markets*
- Black, F. & Litterman, R. (1992). *Global Portfolio Optimization*
- Idzorek, T. (2005). *A Step-By-Step Guide to the Black-Litterman Model*
