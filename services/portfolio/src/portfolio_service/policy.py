"""Versioned questionnaire-to-policy mapping, owned by Portfolio, not the browser."""

from typing import Literal

from pydantic import Field

from portfolio_contracts import Constraints, StrictModel
from portfolio_contracts.assets import canonical_candidates, EQUITY_IDS


class RiskAnswers(StrictModel):
    questionnaire_version: Literal["risk-v1"]
    horizon_months: int = Field(ge=1, le=600, strict=True)
    liquidity_need: Literal["low", "medium", "high"]
    loss_tolerance: Literal["low", "medium", "high"]
    experience: Literal["beginner", "experienced"]


def effective_constraints(constraints: Constraints, universe_id: str, regime: str = "normal"):
    if universe_id not in {"USER_SELECTED", "VN_PHASE1_FULL"}:
        return constraints
    return Constraints(**(constraints.model_dump() | {
        "risk_aversion": max(constraints.risk_aversion, 5.0 if regime == "crisis" else 1.5),
        "max_position_weight": min(constraints.max_position_weight, 0.5),
        "defensive_asset_ids": ["VFF"],
        "min_defensive_weight": max(constraints.min_defensive_weight, 0.15),
        "max_non_defensive_weight": min(constraints.max_non_defensive_weight, 0.70),
    }))


def risk_policy(answers: RiskAnswers, universe_id: str = "DEMO"):
    horizon = (
        0 if answers.horizon_months < 12 else 1 if answers.horizon_months < 60 else 2
    )
    score = min(
        horizon,
        {"high": 0, "medium": 1, "low": 2}[answers.liquidity_need],
        {"low": 0, "medium": 1, "high": 2}[answers.loss_tolerance],
        1 if answers.experience == "beginner" else 2,
    )
    profile = ("conservative", "balanced", "growth")[score]
    return {
        "profile": profile,
        "answers": answers.model_dump(),
        "mapping_version": "custom-mixed-risk-v1" if universe_id == "USER_SELECTED" else "risk-policy-v1",
    }, effective_constraints(Constraints(risk_aversion=(6.0, 3.0, 1.5)[score], max_position_weight=0.5), universe_id)


def check_candidate_feasibility(ids, constraints, strategy):
    try:
        ids = canonical_candidates(ids)
    except ValueError:
        return "INPUT_INVALID"
    if len(ids) < 2:
        return "INSUFFICIENT_ASSETS"
    if constraints is None:
        return "RISK_PROFILE_REQUIRED"
    if strategy not in {"EW", "MVO", "BL_ML"}:
        return "INPUT_INVALID"
    if "VFF" not in ids:
        return "DEFENSIVE_ASSET_REQUIRED"
    try:
        c = Constraints.model_validate(constraints)
    except ValueError:
        return "INPUT_INVALID"
    equities = sum(asset in EQUITY_IDS for asset in ids)
    count = len(ids) if strategy != "BL_ML" else min(equities, 5) + len(ids) - equities
    if not set(c.defensive_asset_ids) <= set(ids):
        return "INPUT_INVALID"
    defensive_count = len(c.defensive_asset_ids)
    cap = c.max_position_weight
    lower = max(c.min_defensive_weight, 1 - c.max_non_defensive_weight,
                1 - (count - defensive_count) * cap, 0)
    upper = min(1, defensive_count * cap)
    if count * cap < 1 - 1e-14 or lower > upper + 1e-14:
        return "CONSTRAINTS_INFEASIBLE"
    if strategy == "EW" and (
        1 / count > cap + 1e-13
        or defensive_count / count < c.min_defensive_weight - 1e-13
        or 1 - defensive_count / count > c.max_non_defensive_weight + 1e-13
    ):
        return "CONSTRAINTS_INFEASIBLE"
    return None
