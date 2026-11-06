"""Versioned questionnaire-to-policy mapping, owned by Portfolio, not the browser."""

from typing import Literal

from pydantic import Field

from portfolio_contracts import Constraints, StrictModel


class RiskAnswers(StrictModel):
    questionnaire_version: Literal["risk-v1"]
    horizon_months: int = Field(ge=1, le=600, strict=True)
    liquidity_need: Literal["low", "medium", "high"]
    loss_tolerance: Literal["low", "medium", "high"]
    experience: Literal["beginner", "experienced"]


def risk_policy(answers: RiskAnswers):
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
        "mapping_version": "risk-policy-v1",
    }, Constraints(risk_aversion=(6.0, 3.0, 1.5)[score], max_position_weight=0.5)
