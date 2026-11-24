"""Versioned wire types only; no shared business database models."""

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_serializer, model_validator


class ModelUnavailable(ValueError):
    """No compatible approved model; distinct from corrupt/expired market inputs."""


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def utcnow():
    return datetime.now(timezone.utc)


def aware(value: datetime):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Constraints(StrictModel):
    risk_aversion: FiniteFloat = Field(default=1.5, gt=0, le=100)
    max_position_weight: FiniteFloat = Field(default=0.5, gt=0, le=1)
    defensive_asset_ids: list[str] = Field(default_factory=list, max_length=100)
    min_defensive_weight: FiniteFloat = Field(default=0, ge=0, le=1)
    max_non_defensive_weight: FiniteFloat = Field(default=1, ge=0, le=1)


class ReadyInput(StrictModel):
    bundle_id: str = Field(min_length=1, max_length=100)
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_id: str
    model_bundle_id: str | None = None
    asset_ids: list[str] = Field(min_length=2, max_length=100)
    as_of_date: str
    valid_until: datetime
    demo: bool = False
    provenance: dict | None = None

    @field_validator("valid_until")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value


class DecisionContext(StrictModel):
    policy_version_id: str = Field(min_length=1, max_length=100)
    risk_profile: dict | None = None
    requested_strategy: Literal["EW", "MVO", "BL_ML", "HYBRID"]
    fallback_reason: str | None = None
    requested_constraints: Constraints | None = None


from .selection import SelectionContext  # noqa: E402


def system_hybrid_enabled():
    return os.environ.get("SYSTEM_HYBRID_ENABLED", "false").lower() == "true"


def system_hybrid_managed():
    return os.environ.get("SYSTEM_HYBRID_ENABLED", "false").lower() in {"true", "paused"}


class HybridPolicy(StrictModel):
    version: Literal["phase1-hybrid-profile-v1", "hybrid-growth-normal-mvo60-v1"]
    mvo_share: Annotated[FiniteFloat, Field(gt=0, lt=1)]


class OptimizeCommand(StrictModel):
    job_id: UUID
    owner_user_id: UUID
    portfolio_id: UUID
    portfolio_version: int = Field(ge=1)
    strategy: Literal["EW", "MVO", "BL_ML", "HYBRID"]
    core_version: Literal["0.1.0"] = "0.1.0"
    capital_vnd: str
    inputs: ReadyInput
    constraints: Constraints
    decision_context: DecisionContext | None = None
    selection_context: SelectionContext | None = None
    hybrid_policy: HybridPolicy | None = None
    deadline: datetime
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_hybrid_pin(self):
        if self.strategy == "HYBRID":
            if not self.hybrid_policy or not self.selection_context or not self.decision_context:
                raise ValueError("HYBRID requires a pinned policy, selection and decision context")
            decision = self.decision_context
            if decision.requested_strategy != "HYBRID" or decision.fallback_reason or not (decision.risk_profile or {}).get("version_id"):
                raise ValueError("HYBRID requires a confirmed risk revision and no fallback")
        elif self.hybrid_policy is not None:
            raise ValueError("Only HYBRID accepts a blend policy")
        return self

    @model_serializer(mode="wrap")
    def preserve_legacy_wire(self, handler):
        value = handler(self)
        if self.selection_context is None:
            value.pop("selection_context", None)
        if self.hybrid_policy is None:
            value.pop("hybrid_policy", None)
        return value

    def compute_hash(self):
        # Legacy queued commands predate decision_context; keep their hashes replayable.
        excluded = {"input_hash": True}
        if self.selection_context is None:
            excluded["selection_context"] = True
        if self.decision_context is None:
            excluded["decision_context"] = True
        elif self.decision_context.requested_constraints is None:
            excluded["decision_context"] = {"requested_constraints"}
        if self.inputs.provenance is None:
            excluded["inputs"] = {"provenance"}
        return canonical_hash(self.model_dump(mode="json", exclude=excluded))


class OptimizeResult(StrictModel):
    job_id: UUID
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: UUID
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["SUCCEEDED", "FAILED"]
    result: dict | None = None
    error: dict | None = None
    explanation_evidence: dict | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_wire(self, handler):
        value = handler(self)
        if self.explanation_evidence is None:
            value.pop("explanation_evidence", None)
        return value


class Envelope(StrictModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: Literal[1] = 1
    type: Literal[
        "quant.optimize.requested",
        "quant.optimization.completed",
        "market.ingestion.requested",
    ]
    producer: Literal["portfolio", "quant-serving", "market-data"]
    correlation_id: UUID
    occurred_at: datetime = Field(default_factory=utcnow)
    payload: dict

    @field_validator("event_id")
    @classmethod
    def valid_id(cls, value):
        return str(UUID(value))
