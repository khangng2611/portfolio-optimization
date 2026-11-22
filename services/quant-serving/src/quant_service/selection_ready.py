"""Preflight projects candidates and regime, never performs K5 or inference."""

from portfolio_contracts import Constraints, canonical_hash, utcnow
from portfolio_contracts.assets import EQUITY_IDS, candidate_hash, canonical_candidates
from portfolio_contracts.selection import SelectionReadiness
from portfolio_core.selection import (
    candidate_regime,
    effective_candidate_constraints,
    check_candidate_feasibility,
)
from .asset_ensemble import validate_coverage
from .selection_panel import SelectionDataError


def fit_index(t):
    if t < 145:
        raise SelectionDataError("HISTORY_INSUFFICIENT")
    return 145 + ((t - 145) // 10) * 10


def regime_pin(panel, projected):
    t = projected["decision_index"]
    regime = candidate_regime(projected["returns"], t)
    digest = canonical_hash(
        dict(
            policy="candidate-regime-v1",
            panel_hash=panel.panel_hash,
            candidate_hash=candidate_hash(projected["asset_ids"]),
            decision_session=str(panel.dates[t]),
            returns=projected["returns"][max(0, t - 120) : t].tolist(),
        )
    )
    return regime, digest


def check_model(catalog, value, panel, projected):
    _, manifest = catalog.model(value)
    equities = [a for a in projected["asset_ids"] if a in EQUITY_IDS]
    if not equities:
        raise SelectionDataError("NO_VALID_ML_VIEWS")
    check_equity_model_inputs(manifest, panel, equities, projected["decision_index"])
    return manifest


def prepare_selection(catalog, body, now=None):
    now = now or utcnow()
    ids = canonical_candidates(body["candidate_asset_ids"])
    digest = candidate_hash(ids)
    if body.get("candidate_hash") is not None and body["candidate_hash"] != digest:
        raise ValueError("Candidate hash mismatch")
    result = dict(
        portfolio_version=body.get("portfolio_version"),
        revision_id=body.get("revision_id"),
        candidate_hash=digest,
        candidate_asset_ids=ids,
        checked_at=now,
        decision_at=now,
    )
    requested = body.get("constraints")
    global_reason = "RISK_PROFILE_REQUIRED" if requested is None else None
    if requested is not None:
        requested = Constraints.model_validate(requested).model_dump()
        effective = effective_candidate_constraints(requested, "normal")
        result["effective_constraints"] = effective
        global_reason = check_candidate_feasibility(ids, effective, "MVO")
    projected = None
    try:
        if global_reason:
            raise SelectionDataError(global_reason)
        pin = catalog.latest()
        value, panel = catalog.load_resource(pin)
        if pin.valid_until <= now:
            raise SelectionDataError("INPUT_EXPIRED")
        projected = panel.project(ids, now)
        regime, regime_hash = regime_pin(panel, projected)
        effective = effective_candidate_constraints(requested, regime)
        result.update(
            inputs=pin,
            regime=regime,
            regime_input_hash=regime_hash,
            effective_constraints=effective,
            selection_valid_until=min(pin.valid_until, projected["valid_until"]),
            decision_session=projected["decision_session"],
            asset_status=[
                dict(asset_id=a, **projected["availability"][a]) for a in ids
            ],
        )
    except SelectionDataError as exc:
        global_reason = exc.code
        if exc.details.get("asset_id"):
            result["asset_status"] = [exc.details]
    except (ValueError, OSError, KeyError, TypeError):
        global_reason = "INPUT_INVALID"
    strategies = []
    for strategy in ("EW", "MVO", "BL_ML"):
        reason = global_reason or check_candidate_feasibility(ids, effective, strategy)
        if not reason and strategy == "BL_ML":
            try:
                check_model(catalog, value, panel, projected)
            except SelectionDataError as exc:
                reason = exc.code
            except (ValueError, KeyError, TypeError, OSError):
                reason = "INPUT_INVALID"
        strategies.append(
            dict(
                strategy=strategy, can_submit=not reason, reason_code=reason or "READY"
            )
        )
    selected = next(
        s for s in strategies if s["strategy"] == body.get("strategy", "BL_ML")
    )
    result.update(
        strategies=strategies,
        can_submit=selected["can_submit"],
        reason_code=selected["reason_code"],
    )
    return SelectionReadiness.model_validate(result)


def check_equity_model_inputs(manifest, panel, equities, decision_index):
    if str(manifest.fit_epoch) != str(panel.dates[fit_index(decision_index)]):
        raise SelectionDataError("MODEL_EPOCH_MISMATCH")
    if not set(equities) <= set(manifest.covered_asset_ids):
        raise SelectionDataError("MODEL_COVERAGE_MISSING")
    f = fit_index(decision_index)
    for asset in equities:
        digest = canonical_hash(
            dict(
                asset_id=asset,
                dates=list(map(str, panel.dates[: f - 5])),
                prices_vnd=panel.prices[: f - 5, panel.ids.index(asset)].tolist(),
            )
        )
        if manifest.assets[asset].training_data_hash != digest:
            raise SelectionDataError("INPUT_INVALID", asset)
    validate_coverage(manifest, equities, manifest.fit_epoch)
