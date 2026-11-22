"""Read-only native asset ensembles for candidate-specific jobs."""

import numpy as np
import xgboost as xgb

from portfolio_contracts import ModelUnavailable
from portfolio_core.assets import canonical_candidates, EQUITY_IDS
from . import phase1

MODEL_FAMILY = "phase1-asset-ensemble-v5"
FEATURE_SCHEMA = "phase1-asset-features-v1"


def validate_coverage(manifest, equity_ids, fit_epoch, *, require_approved=True):
    if manifest.schema_version != 5 or manifest.xgboost_version != xgb.__version__:
        raise ValueError("Unsupported asset ensemble runtime")
    if require_approved and manifest.status != "APPROVED":
        raise ModelUnavailable("Asset ensemble requires registry review")
    if str(manifest.fit_epoch) != str(fit_epoch):
        raise ValueError("Asset ensemble epoch mismatch")
    if (
        not isinstance(equity_ids, list)
        or len(set(equity_ids)) != len(equity_ids)
        or not set(equity_ids) <= set(EQUITY_IDS)
        or not set(equity_ids) <= set(manifest.covered_asset_ids)
    ):
        raise ValueError("Asset ensemble coverage missing")


def infer_asset_views(
    directory,
    manifest,
    features_by_asset,
    daily_volatility,
    active_asset_ids,
    regime_info,
    *,
    require_approved=True,
    evidence=None,
):
    """Return views_p/q/view_confidences with columns in active asset order.

    Existing native files are read only for active equities. At least one ML
    view must survive its threshold before defensive views may be injected.
    """
    from .ml import phase1_predictions

    if active_asset_ids != canonical_candidates(active_asset_ids):
        raise ValueError("Active assets must use canonical candidate order")
    equities = [a for a in active_asset_ids if a in EQUITY_IDS]
    validate_coverage(
        manifest, equities, manifest.fit_epoch, require_approved=require_approved
    )
    if set(features_by_asset) != set(equities) or set(daily_volatility) != set(
        equities
    ):
        raise ValueError("Active equity feature coverage mismatch")
    if not equities:
        raise ModelUnavailable("No valid ML view without active equity")
    rows = np.asarray([features_by_asset[a] for a in equities], dtype=float)
    predictions = phase1_predictions(directory, manifest, rows, asset_ids=equities)
    p, q, confidence = [], [], []
    for asset, members in zip(equities, predictions):
        vol = daily_volatility[asset]
        if (
            isinstance(vol, bool)
            or not isinstance(vol, (int, float, np.number))
            or not np.isfinite(vol)
            or vol < 0
        ):
            raise ValueError("Invalid asset daily volatility")
        mean, conf = phase1.ensemble_forecast(members)
        if abs(mean) < 0.001:
            continue
        horizon_vol = vol * np.sqrt(5)
        annual = (
            0.5 * np.tanh(mean / horizon_vol)
            if horizon_vol > 1e-8
            else np.clip(mean * 252 / 5, -0.5, 0.5)
        )
        p.append([float(asset == a) for a in active_asset_ids])
        q.append(float(annual / 252))
        confidence.append(conf)
    if not p:
        raise ModelUnavailable("No valid ML view above the return threshold")
    if not isinstance(regime_info, dict) or regime_info.get("regime") not in {
        "normal",
        "stress",
        "crisis",
    }:
        raise ValueError("Invalid candidate regime")
    ratio = regime_info.get("vol_ratio")
    if (
        isinstance(ratio, bool)
        or not isinstance(ratio, (int, float, np.number))
        or not np.isfinite(ratio)
        or ratio < 0
    ):
        raise ValueError("Invalid candidate volatility ratio")
    if ratio > 1.3:
        confidence = [c * 1.3 / ratio for c in confidence]
    if regime_info["regime"] in {"stress", "crisis"} and "VFF" in active_asset_ids:
        nondef = [a for a in active_asset_ids if a != "VFF"]
        if nondef:
            p.append(
                [1.0 if a == "VFF" else -1 / len(nondef) for a in active_asset_ids]
            )
            crisis = regime_info["regime"] == "crisis"
            q.append((0.1 if crisis else 0.05) / 252)
            confidence.append(0.8 * (1 if crisis else 0.85))
    from .explanation import capture, capture_asset_views

    capture(evidence, lambda: {"views": capture_asset_views(predictions, equities, active_asset_ids, p, q, confidence)})
    return dict(views_p=p, views_q=q, view_confidences=confidence)
