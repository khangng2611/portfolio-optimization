"""Fixed-universe Phase 1 feature and view policy (five observed sessions)."""

from datetime import date

import numpy as np

from portfolio_contracts import ModelUnavailable, canonical_hash


UNIVERSE = "VN_EQUITY_PHASE1"
ASSETS = ["FPT", "MWG", "VCB"]
FEATURE_SCHEMA = "phase1-equity-features-v1"
FEATURES = [
    "momentum_5",
    "momentum_10",
    "momentum_20",
    "rsi_14",
    "ma_ratio_10_30",
    "volatility_20",
    "macd_hist",
    "price_std_20",
]
START = date(2020, 1, 14)
CUTOFF = date(2026, 4, 29)
SEEDS = tuple(range(42, 47))
HORIZON = 5
PRICE_CONVENTION = ("kbs-direct-v1", "close", "VND/share", "provider_adjusted")


def history_hash(dates, prices_vnd):
    """Pin the actual expanding EMA initialization and adjustment vintage."""
    return canonical_hash(
        {
            "asset_ids": ASSETS,
            "dates": [day.isoformat() for day in dates],
            "prices_vnd": np.asarray(prices_vnd, dtype=float).tolist(),
        }
    )


def _ema(prices, span):
    alpha = 2.0 / (span + 1)
    result = np.empty_like(prices)
    result[0] = prices[0]
    for i in range(1, len(prices)):
        result[i] = (1 - alpha) * result[i - 1] + alpha * prices[i]
    return result


def feature_row(prices):
    """Latest row in Phase 1 units (thousand VND), with expanding EMA state."""
    prices = np.asarray(prices, dtype=float)
    if len(prices) < 30 or not np.isfinite(prices).all() or np.any(prices <= 0):
        raise ValueError(
            "Phase 1 features require at least 30 positive observed closes"
        )
    changes = np.diff(prices[-15:])
    gain = np.maximum(changes, 0).mean()
    loss = np.maximum(-changes, 0).mean()
    macd = _ema(prices, 12) - _ema(prices, 26)
    return [
        *(prices[-1] / prices[-1 - period] - 1 for period in (5, 10, 20)),
        100 - 100 / (1 + gain / loss) if loss else 50.0,
        _ema(prices, 10)[-1] / _ema(prices, 30)[-1] - 1,
        np.std(prices[-20:] / prices[-21:-1] - 1, ddof=1),
        macd[-1] - _ema(macd, 9)[-1],
        np.std(prices[-20:], ddof=1) / prices[-20:].mean(),
    ]


def feature_batch(panel):
    if (
        panel.ids != ASSETS
        or panel.dates[0] != START
        or len(panel.dates) < 31
        or CUTOFF not in panel.dates
        or panel.dates[-2] <= CUTOFF
        or any(panel.conventions[asset] != {PRICE_CONVENTION} for asset in ASSETS)
    ):
        raise ValueError(
            "Phase 1 requires ordered KBS adjusted VND/share history from 2020-01-14"
        )
    end = panel.dates.index(CUTOFF) + 1
    return {
        "feature_schema_version": FEATURE_SCHEMA,
        "feature_names": FEATURES,
        "asset_ids": ASSETS,
        "feature_date": panel.dates[-2].isoformat(),
        "feature_known_at": max(t for row in panel.known for t in row).isoformat(),
        "history_start": START.isoformat(),
        "training_history_hash": history_hash(panel.dates[:end], panel.prices[:end]),
        # The frozen baseline uses returns through the decision session for
        # Option B, and prices only through the preceding session for features.
        "daily_volatility": np.std(panel.returns[-20:], axis=0, ddof=1).tolist(),
        "rows": [feature_row(column / 1000) for column in panel.prices[:-1].T],
    }


def ensemble_forecast(member_predictions):
    predictions = np.asarray(member_predictions, dtype=np.float32)
    if predictions.shape != (len(SEEDS),) or not np.isfinite(predictions).all():
        raise ValueError("Invalid Phase 1 ensemble predictions")
    # The frozen ranking-absolute path has no directional-accuracy history.
    return float(predictions.mean()), float(
        np.clip(0.70 - predictions.std() / 0.005, 0.25, 0.70)
    )


def option_b(forecasts, daily_volatility):
    rows, values, confidences = [], [], []
    for i, ((predicted, confidence), daily_vol) in enumerate(
        zip(forecasts, daily_volatility)
    ):
        if abs(predicted) < 0.001:
            continue
        horizon_vol = daily_vol * np.sqrt(HORIZON)
        annual = (
            0.5 * np.tanh(predicted / horizon_vol)
            if horizon_vol > 1e-8
            else np.clip(predicted * (252 / HORIZON), -0.5, 0.5)
        )
        rows.append([float(i == j) for j in range(len(ASSETS))])
        values.append(float(annual / 252))
        confidences.append(confidence)
    if not rows:
        raise ModelUnavailable("No valid Phase 1 views above the return threshold")
    return {"views_p": rows, "views_q": values, "view_confidences": confidences}
