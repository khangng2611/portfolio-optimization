"""Versioned wire types only; no shared business database models."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator


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

    @field_validator("valid_until")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value


class OptimizeCommand(StrictModel):
    job_id: UUID
    owner_user_id: UUID
    portfolio_id: UUID
    portfolio_version: int = Field(ge=1)
    strategy: Literal["EW", "MVO", "BL_ML"]
    core_version: Literal["0.1.0"] = "0.1.0"
    capital_vnd: str
    inputs: ReadyInput
    constraints: Constraints
    deadline: datetime
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    def compute_hash(self):
        return canonical_hash(self.model_dump(mode="json", exclude={"input_hash"}))


class OptimizeResult(StrictModel):
    job_id: UUID
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: UUID
    bundle_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["SUCCEEDED", "FAILED"]
    result: dict | None = None
    error: dict | None = None


class Envelope(StrictModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: Literal[1] = 1
    type: Literal["quant.optimize.requested", "quant.optimization.completed"]
    producer: Literal["portfolio", "quant-serving"]
    correlation_id: UUID
    occurred_at: datetime = Field(default_factory=utcnow)
    payload: dict

    @field_validator("event_id")
    @classmethod
    def valid_id(cls, value):
        return str(UUID(value))
