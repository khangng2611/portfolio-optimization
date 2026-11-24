"""Versioned questionnaire-to-policy mapping, owned by Portfolio, not the browser."""

from typing import Annotated, Literal

from pydantic import Field

from portfolio_contracts import Constraints, StrictModel
from portfolio_contracts.assets import canonical_candidates, EQUITY_IDS


class RiskInputs(StrictModel):
    horizon_months: int = Field(ge=1, le=600, strict=True)
    liquidity_need: Literal["low", "medium", "high"]
    loss_tolerance: Literal["low", "medium", "high"]


class LegacyRiskAnswers(RiskInputs):
    questionnaire_version: Literal["risk-v1"]
    experience: Literal["beginner", "experienced"]


class QuantifiedRiskAnswers(RiskInputs):
    questionnaire_version: Literal["risk-v2"]
    reserve_months: Literal["under_3", "3_to_under_6", "at_least_6"]
    experience: Literal["beginner", "experienced"] | None = None


RiskAnswers = Annotated[LegacyRiskAnswers | QuantifiedRiskAnswers, Field(discriminator="questionnaire_version")]


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
    levels = {"low": 0, "medium": 1, "high": 2}
    factors = {
        "horizon_months": horizon,
        "liquidity_need": 2 - levels[answers.liquidity_need],
        "loss_tolerance": levels[answers.loss_tolerance],
    }
    quantified = isinstance(answers, QuantifiedRiskAnswers)
    if quantified:
        factors["reserve_months"] = {"under_3": 0, "3_to_under_6": 1, "at_least_6": 2}[answers.reserve_months]
    else:
        factors["experience"] = 1 if answers.experience == "beginner" else 2
    score = min(factors.values())
    profile = ("conservative", "balanced", "growth")[score]
    policy = "custom-mixed-risk" if universe_id == "USER_SELECTED" else "risk-policy"
    return {
        "profile": profile,
        "answers": answers.model_dump(exclude_none=True),
        "mapping_version": f"{policy}-v{2 if quantified else 1}",
        **({"score": score, "determining_factors": [key for key, value in factors.items() if value == score]} if quantified else {}),
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
