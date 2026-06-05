# Enhance XGBoost: Ensemble Confidence + Walk-Forward Training

## Context

BL+ML (NAV 2.88, Sharpe 1.02) underperforms plain MVO (NAV 3.71, Sharpe 1.18) in the in-sample backtest. Two root causes identified:

1. **Confidence always = 0.30**: The heuristic `confidence = 0.6 - np.var(raw_features) * 5.0` computes variance across features of different scales (RSI ~0-100, momentum ~0.05, volatility ~0.01). Variance is always >> 0.06, so confidence always floors at 0.30. This makes BL almost ignore ML views but still enough to perturb allocation negatively.

2. **Look-ahead bias**: Model trained once on full 2020-2023 data, then used to "predict" from 2020-09 onwards. The model already saw future data during training.

## Solution

### Fix 1: Ensemble-Based Confidence
Replace the broken feature-variance heuristic with **ensemble disagreement**: train 5 XGBoost models with different random seeds. If all models agree, confidence is high. If they disagree, confidence is low.

### Fix 2: Walk-Forward (Expanding Window) Training
At each retrain point, only use data available up to that time. Retrain every 60 trading days with expanding window + StandardScaler + early stopping.

---

## Implementation Plan

### Step 1: Add config parameters (`gen_view/xgboost/config.py`)

```python
# Ensemble settings
ENSEMBLE_SIZE = 5
ENSEMBLE_BASE_SEED = 42

# Walk-forward settings
RETRAIN_FREQUENCY = 60           # retrain every 60 trading days
MIN_TRAIN_SAMPLES = 100          # min observations before first train
VALIDATION_SPLIT_RATIO = 0.2     # last 20% for early stopping
EARLY_STOPPING_ROUNDS = 10

# Ensemble confidence (replaces broken heuristic)
ENSEMBLE_CONF_SCALE = 0.02       # normalizer for prediction std
ENSEMBLE_CONF_MIN = 0.30
ENSEMBLE_CONF_MAX = 0.85
```

### Step 2: Add project-wide config (`config.py`)

```python
# ML Training mode
ML_TRAINING_MODE = "walk_forward"   # "pretrained" or "walk_forward"
ML_RETRAIN_FREQUENCY = 60
```

### Step 3: Create `XGBoostEnsembleModel` class (`gen_view/xgboost/xgboost_core.py`)

New class added below existing `XGBoostCoreModel` (which remains unchanged):

- **`__init__`**: Accepts `n_ensemble`, `base_seed`, plus standard params
- **`train(prices)`**:
  1. Compute features + labels (reuse `_compute_features`, `_compute_labels`)
  2. Temporal split: first 80% train, last 20% validation
  3. Fit `StandardScaler` on training features per asset
  4. Train N models per asset with different seeds + early stopping on validation set
- **`predict(prices)`** → `dict[str, (float, float)]`:
  1. Compute latest features, apply stored scaler
  2. Get N predictions per asset
  3. Return `(mean_prediction, ensemble_confidence)`
- **`_compute_ensemble_confidence(preds_array)`**:
  ```
  confidence = CONF_MAX - (std(preds) / ENSEMBLE_CONF_SCALE)
  clip to [CONF_MIN, CONF_MAX]
  ```
- **`is_trained`** property
- **`save()` / `load()`**: Serialize ensemble models + scalers

### Step 4: Modify backtest loop (`backtest.py`)

Modify `backtest()` function:

```python
def backtest(..., ml_training_mode="pretrained", retrain_frequency=60):
    ...
    if ml_training_mode == "walk_forward":
        ml_model = XGBoostEnsembleModel(...)
        last_retrain_t = -retrain_frequency  # force first train ASAP

    for t in range(window, len(returns)):
        if (t - window) % rebalance_freq == 0:
            # Walk-forward: retrain if due
            if ml_training_mode == "walk_forward":
                if t - last_retrain_t >= retrain_frequency:
                    train_end = t - prediction_horizon  # embargo gap
                    if train_end >= min_train_samples + feature_window:
                        train_prices = prices.iloc[:train_end]
                        ml_model.train(train_prices, verbose=False)
                        last_retrain_t = t

            # Predict (same for both modes)
            price_window = prices.iloc[max(0, t - window - 30) : t]  # FIX: was t+window
            ...
```

Also fix the existing **look-ahead bug** on line 284: `prices.iloc[...:t+window]` should be `prices.iloc[...:t]`.

### Step 5: Update `main()` in `backtest.py`

- Import new configs (`ML_TRAINING_MODE`, `ML_RETRAIN_FREQUENCY`)
- Add CLI arg `--ml-training-mode` with choices `["pretrained", "walk_forward"]`
- Route to either `load_ml_model()` (existing) or walk-forward logic

### Step 6: Update `model_train.py` (optional enhancement)

- Add `--ensemble` flag to pre-train an ensemble model
- Useful for OOS testing: pre-train ensemble on IS data, evaluate on test phase
- Default behavior unchanged

---

## Files to Modify

| File | Change |
|------|--------|
| `gen_view/xgboost/config.py` | Add ensemble, walk-forward, confidence config |
| `gen_view/xgboost/xgboost_core.py` | Add `XGBoostEnsembleModel` class |
| `config.py` | Add `ML_TRAINING_MODE`, `ML_RETRAIN_FREQUENCY` |
| `backtest.py` | Walk-forward logic in loop + fix price_window bug + new CLI arg |
| `gen_view/xgboost/model_train.py` | Optional: add `--ensemble` flag |

---

## Key Design Decisions

1. **Retrain every 60 days** (not every rebalance): XGBoost is fast but 5-day data increments add negligible information. 60 days ≈ quarterly retrain matches financial intuition.

2. **Expanding window** (not rolling): With only 824 total observations, a rolling window would discard valuable data. Expanding window grows the training set over time.

3. **5 ensemble members**: Balances diversity vs speed. Each retrain: 5 models × 4 assets = 20 fits, ~1-2s total.

4. **Embargo gap = prediction_horizon (5 days)**: Ensures the model never trains on labels that overlap with the current prediction period.

5. **StandardScaler per-asset**: Each asset has different feature distributions. Scaler is re-fitted at each retrain (no stale statistics).

6. **Backward compatible**: Setting `ML_TRAINING_MODE = "pretrained"` preserves existing behavior exactly. Walk-forward is opt-in.

---

## Confidence Behavior (Expected)

| Scenario | Ensemble std | Confidence |
|----------|-------------|------------|
| Strong agreement (all predict +2%) | ~0.002 | 0.75 |
| Moderate agreement | ~0.008 | 0.45 |
| High disagreement | ~0.015 | 0.30 (floor) |

This produces **meaningful variation** in confidence (not constant 0.30), allowing BL to appropriately weight views.

---

## Verification

1. **Unit test**: Train ensemble on sample data, verify predictions return varying confidence values (not constant)
2. **Backtest comparison**:
   ```bash
   # Walk-forward mode
   python backtest.py --phase train --view-mode ml --ml-training-mode walk_forward
   # Compare with pretrained (current)
   python backtest.py --phase train --view-mode ml --ml-training-mode pretrained
   # Compare with MVO baseline
   python backtest.py --phase train --view-mode ml --ml-training-mode walk_forward | grep "KET QUA"
   ```
3. **Check confidence distribution**: Views should show varied confidence (0.30-0.85), not constant 0.30
4. **Check NAV**: BL should improve relative to current 2.88 (target: beat or match MVO's 3.71)
5. **OOS validation**: Run on test phase to confirm no overfitting:
   ```bash
   python backtest.py --phase test --view-mode ml --ml-training-mode walk_forward
   ```
