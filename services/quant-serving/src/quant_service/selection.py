"""Deterministic candidate selection and read-only native inference in a job."""

import numpy as np

from portfolio_contracts import ModelUnavailable, canonical_hash, utcnow
from portfolio_contracts.assets import EQUITY_IDS, candidate_hash, canonical_candidates
from portfolio_contracts.selection import SelectionProof
from portfolio_core.selection import (
    select_candidate_equities,
    effective_candidate_constraints,
    check_candidate_feasibility,
)
from .phase1 import feature_row
from .selection_ready import regime_pin, check_model
from .selection_panel import SelectionDataError


def recompute_selection(catalog, command, *, now=None):
    now = now or utcnow()
    context = command.selection_context
    if context is None:
        raise ValueError("Selection context required")
    ids = canonical_candidates(context.candidate_asset_ids)
    if ids != context.candidate_asset_ids or context.candidate_hash != candidate_hash(
        ids
    ):
        raise ValueError("Selection candidate order/hash mismatch")
    if context.decision_at > now or command.deadline > context.valid_until:
        raise SelectionDataError("INPUT_INVALID")
    value, panel = catalog.load_resource(command.inputs)
    if context.data_policy_id != panel.snapshot["availability_policy"]:
        raise ValueError("Selection data policy does not match pinned panel")
    from .snapshot_inputs import timestamp

    if context.decision_at < max(
        timestamp(value.get("decision_at", panel.snapshot["created_at"])),
        timestamp(panel.snapshot["created_at"]),
    ):
        raise ValueError("Selection predates verified resource")
    try:
        t = panel.dates.index(context.decision_session)
    except ValueError:
        raise ValueError("Selection session missing") from None
    if panel.index_at(context.decision_at) != t:
        raise ValueError("Selection decision/session mismatch")
    projected = panel.project(ids, now, decision_index=t)
    if context.valid_until <= now or command.inputs.valid_until <= now:
        raise SelectionDataError("INPUT_EXPIRED")
    if context.valid_until != min(projected["valid_until"], command.inputs.valid_until):
        raise ValueError("Selection TTL mismatch")
    regime, regime_hash = regime_pin(panel, projected)
    if (
        context.regime.model_dump() != regime
        or context.regime_input_hash != regime_hash
    ):
        raise ValueError("Selection regime pin mismatch")
    requested = (
        command.decision_context.requested_constraints
        if command.decision_context
        else None
    )
    requested = requested or command.constraints
    effective = effective_candidate_constraints(requested.model_dump(), regime)
    if effective != command.constraints.model_dump():
        raise ValueError("Selection effective constraints mismatch")
    uses_views = command.strategy in {"BL_ML", "HYBRID"}
    reason = check_candidate_feasibility(ids, effective, "BL_ML" if uses_views else command.strategy)
    if command.strategy == "HYBRID" and not reason:
        reason = check_candidate_feasibility(ids, effective, "MVO")
    if reason:
        raise SelectionDataError(reason)
    equities = [a for a in ids if a in EQUITY_IDS]
    selected = equities
    if uses_views and len(equities) > 5:
        columns = [panel.ids.index(a) for a in equities]
        selected = select_candidate_equities(panel.prices[:t, columns], equities)
    active = [a for a in ids if a not in EQUITY_IDS or a in selected]
    proof_fields = dict(
        candidate_hash=context.candidate_hash,
        snapshot_hash=panel.snapshot["content_hash"],
        panel_hash=panel.panel_hash,
        selection_policy_id=context.selection_policy_id,
        applied_selection="equity-k5-v1"
        if uses_views and len(equities) > 5
        else "all-candidates-v1",
        decision_session=context.decision_session,
        selection_price_end_date=panel.dates[t - 1],
        active_asset_ids=active,
        selected_equity_ids=selected,
        rejected_equity_ids=[a for a in equities if a not in selected],
        effective_constraints_hash=canonical_hash(effective),
    )
    deterministic = dict(
        proof_fields,
        decision_session=str(context.decision_session),
        selection_price_end_date=str(panel.dates[t - 1]),
        regime_input_hash=regime_hash,
        data_policy_id=context.data_policy_id,
        risk_policy_id=context.risk_policy_id,
        base_bundle_hash=command.inputs.bundle_hash,
        strategy=command.strategy,
    )
    proof = SelectionProof(
        input_hash=command.input_hash,
        selection_hash=canonical_hash(deterministic),
        **proof_fields,
    )
    return value, panel, projected, proof


def resolve_selection(catalog, command, *, now=None, evidence=None):
    value, panel, projected, proof = recompute_selection(catalog, command, now=now)
    ids, active = projected["asset_ids"], proof.active_asset_ids
    t = projected["decision_index"]
    returns = projected["returns"][-20:]
    numerical = dict(
        asset_ids=ids,
        active_asset_ids=active,
        active_policy_version="user-selection-active-v1",
        mean_returns=returns.mean(axis=0).tolist(),
        covariance=np.cov(returns, rowvar=False, ddof=1).tolist(),
        market_weights=[1 / len(active) if a in active else 0 for a in ids],
    )
    inference = None
    if command.strategy in {"BL_ML", "HYBRID"}:
        manifest = check_model(catalog, value, panel, projected)
        directory, _ = catalog.model(value)
        equities = [a for a in active if a in EQUITY_IDS]
        features = {
            a: feature_row(panel.prices[:t, panel.ids.index(a)] / 1000)
            for a in equities
        }
        volatility = {a: float(returns[:, ids.index(a)].std(ddof=1)) for a in equities}
        from .asset_ensemble import infer_asset_views

        try:
            views = infer_asset_views(
                directory,
                manifest,
                features,
                volatility,
                active,
                command.selection_context.regime.model_dump(),
                **({"evidence": evidence} if evidence is not None else {}),
            )
        except ModelUnavailable:
            raise SelectionDataError("NO_VALID_ML_VIEWS") from None
        # Native views refer to active columns; allocator accepts candidate-order views.
        expanded = np.zeros((len(views["views_p"]), len(ids)))
        expanded[:, [ids.index(a) for a in active]] = views["views_p"]
        numerical.update(views, views_p=expanded.tolist())
        inference = dict(
            model_id=str(manifest.model_id),
            manifest_hash=value["model_bundle_id"],
            snapshot_id=panel.snapshot["id"],
            snapshot_hash=panel.snapshot["content_hash"],
            fit_epoch=str(manifest.fit_epoch),
            model_family="phase1-asset-ensemble-v5",
            covered_asset_ids=manifest.covered_asset_ids,
        )
    from .explanation import capture, capture_selection

    capture(evidence, lambda: capture_selection(command, panel, proof, features if inference else {}, manifest if inference else None, t))
    return numerical, proof, inference
