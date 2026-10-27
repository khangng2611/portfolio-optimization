from datetime import date
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from portfolio_contracts import utcnow


class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshot_id: UUID
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    training_cutoff: date
    max_age_days: int = Field(default=7, strict=True, ge=1, le=30)
    lookback: int = Field(default=252, strict=True, ge=20, le=2520)
    min_returns: int = Field(default=60, strict=True, ge=20, le=2520)

    @model_validator(mode="after")
    def bounded(self):
        if self.training_cutoff >= utcnow().date() or self.min_returns > self.lookback:
            raise ValueError("Invalid training policy/cutoff")
        return self


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def reason_required(self):
        if not self.reason.strip():
            raise ValueError("Review reason required")
        return self
