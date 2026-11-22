"""Opt-in wire contracts for user candidate sets; catalog semantics stay in domain code."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, FiniteFloat, field_validator, model_validator

from . import Constraints, ReadyInput, StrictModel

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
AssetId = Annotated[str, Field(pattern=r"^[A-Z0-9_-]{1,64}$")]
Strategy = Literal["EW", "MVO", "BL_ML", "HYBRID"]
LIVE_NAV_POLICY = "user-selection-live-nav-v2"
DataPolicy = Literal["user-selection-data-v1", "user-selection-live-nav-v2"]
ReasonCode = Literal[
    "READY",
    "INSUFFICIENT_ASSETS",
    "RISK_PROFILE_REQUIRED",
    "ASSET_SELECTION_REQUIRED",
    "DEFENSIVE_ASSET_REQUIRED",
    "CONSTRAINTS_INFEASIBLE",
    "ASSET_DATA_MISSING",
    "ASSET_DATA_STALE",
    "VFF_STALE",
    "GOLD_STALE",
    "HISTORY_INSUFFICIENT",
    "MODEL_REVIEW_PENDING",
    "MODEL_COVERAGE_MISSING",
    "MODEL_EPOCH_MISMATCH",
    "NO_VALID_ML_VIEWS",
    "INPUT_INVALID",
    "INPUT_EXPIRED",
    "INPUT_UNAVAILABLE",
    "MODEL_UNAVAILABLE",
]


class CandidateSet(StrictModel):
    candidate_asset_ids: list[AssetId] = Field(min_length=1, max_length=32)

    @field_validator("candidate_asset_ids")
    @classmethod
    def unique(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate candidate asset IDs")
        return value


class RegimeInfo(StrictModel):
    regime: Literal["normal", "stress", "crisis"]
    vol_ratio: Annotated[FiniteFloat, Field(ge=0)]
    drawdown: FiniteFloat
    equity_momentum: FiniteFloat


class SelectionContext(CandidateSet):
    revision_id: UUID
    candidate_hash: Digest
    selection_policy_id: Literal["user-k5-v1"] = "user-k5-v1"
    risk_policy_id: Literal["custom-mixed-risk-v1"] = "custom-mixed-risk-v1"
    data_policy_id: DataPolicy = "user-selection-data-v1"
    regime_policy_id: Literal["candidate-regime-v1"] = "candidate-regime-v1"
    regime: RegimeInfo
    regime_input_hash: Digest
    decision_at: datetime
    decision_session: date
    valid_until: datetime

    @field_validator("decision_at", "valid_until")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone-aware selection time required")
        return value

    @model_validator(mode="after")
    def time_order(self):
        if self.decision_at >= self.valid_until:
            raise ValueError("Selection already expired")
        return self


class SelectionRevision(CandidateSet):
    revision_id: UUID
    portfolio_id: UUID
    portfolio_version: int = Field(ge=1)
    candidate_hash: Digest
    selection_policy_id: Literal["user-k5-v1"] = "user-k5-v1"
    risk_policy_id: Literal["custom-mixed-risk-v1"] = "custom-mixed-risk-v1"
    created_at: datetime


class SelectionProof(StrictModel):
    input_hash: Digest
    candidate_hash: Digest
    snapshot_hash: Digest
    panel_hash: Digest
    selection_policy_id: Literal["user-k5-v1"] = "user-k5-v1"
    applied_selection: Literal["equity-k5-v1", "all-candidates-v1"]
    decision_session: date
    selection_price_end_date: date
    active_asset_ids: list[AssetId] = Field(min_length=2, max_length=32)
    selected_equity_ids: list[AssetId] = Field(max_length=30)
    rejected_equity_ids: list[AssetId] = Field(max_length=30)
    selection_hash: Digest
    effective_constraints_hash: Digest


class StrategySelectionReadiness(StrictModel):
    strategy: Strategy
    can_submit: bool
    reason_code: ReasonCode


class SelectionReadiness(StrictModel):
    readiness_kind: Literal["user-selection-v1"] = "user-selection-v1"
    portfolio_version: int | None = Field(default=None, ge=1)
    revision_id: UUID | None = None
    candidate_hash: Digest | None = None
    candidate_asset_ids: list[AssetId] = Field(default_factory=list, max_length=32)
    can_submit: bool = False
    reason_code: ReasonCode = "INPUT_UNAVAILABLE"
    strategies: list[StrategySelectionReadiness] = Field(default_factory=list)
    asset_status: list[dict] = Field(default_factory=list, max_length=32)
    regime: RegimeInfo | None = None
    regime_input_hash: Digest | None = None
    effective_constraints: Constraints | None = None
    selection_valid_until: datetime | None = None
    decision_at: datetime | None = None
    decision_session: date | None = None
    inputs: ReadyInput | None = None
    checked_at: datetime | None = None


class AssetCatalogItem(StrictModel):
    asset_id: AssetId
    kind: Literal["stock", "gold", "fund"]
    display_name: str
    description: str | None = None
    unit: Literal["VND/share", "VND/tael", "VND/unit"]
    currency: Literal["VND"] = "VND"
    catalog_version: Literal["supported-assets-v1"] = "supported-assets-v1"
    data_status: Literal["UNKNOWN", "MISSING", "QUARANTINED", "FRESH", "STALE"] = (
        "UNKNOWN"
    )
    latest_observation_date: date | None = None
    eligible_observation_date: date | None = None
    available_at: datetime | None = None
    age_days: int | None = None
    checked_at: datetime | None = None
    ml_status: Literal["UNKNOWN", "NOT_COVERED", "REVIEW_PENDING", "COVERED"] = (
        "UNKNOWN"
    )
    approved_model_id: UUID | None = None
    model_manifest_hash: Digest | None = None
