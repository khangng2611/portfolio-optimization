"""Market wire DTOs; observation revisions and persistence belong to Market only."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from . import StrictModel, utcnow

UNITS = {"stock": "VND/share", "fund": "VND/unit", "gold": "VND/tael"}


class Observation(StrictModel):
    asset_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    kind: Literal["stock", "fund", "gold"]
    observation_date: date
    price: Decimal = Field(
        gt=0, le=Decimal("100000000000000000"), max_digits=24, decimal_places=6
    )
    source_unit: str
    provider: str = Field(min_length=1, max_length=100)
    published_at: datetime | None = None
    price_type: Literal["close", "nav", "bid", "ask", "midpoint"] = "close"

    @model_validator(mode="after")
    def valid_observation(self):
        unit = UNITS[self.kind]
        if self.source_unit not in {unit, "thousand_" + unit}:
            raise ValueError("Asset kind and price unit must agree")
        if self.observation_date > utcnow().date():
            raise ValueError("Future observations are not available")
        if self.published_at is not None:
            if self.published_at.tzinfo is None or self.published_at > utcnow():
                raise ValueError(
                    "Publication requires an available, timezone-aware timestamp"
                )
            if self.published_at.date() < self.observation_date:
                raise ValueError("Publication cannot precede observation date")
        if self.price * (
            1000 if self.source_unit.startswith("thousand_") else 1
        ) > Decimal("999999999999999999"):
            raise ValueError("Normalized price exceeds storage precision")
        return self


class IngestionRequest(StrictModel):
    dataset_id: str | None = Field(default=None, pattern=r"^[A-Z0-9_-]{1,64}$")
    observations: list[Observation] | None = Field(
        default=None, min_length=1, max_length=5000
    )

    @model_validator(mode="after")
    def single_source(self):
        if (self.dataset_id is None) == (self.observations is None):
            raise ValueError("Supply either a registered dataset ID or observations")
        if self.observations:
            keys = [
                (o.asset_id, o.observation_date, o.provider, o.price_type)
                for o in self.observations
            ]
            if len(keys) != len(set(keys)):
                raise ValueError(
                    "One ingestion cannot contain conflicting observation keys"
                )
        return self


class IngestCommand(StrictModel):
    job_id: UUID
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    request: IngestionRequest
    dataset_spec: dict | None = None


class SnapshotRequest(StrictModel):
    asset_ids: list[str] = Field(min_length=1, max_length=100)
    start_date: date
    end_date: date
    as_of_date: date
    max_age_days: int = Field(default=7, ge=0, le=365)

    @model_validator(mode="after")
    def valid_window(self):
        import re

        if any(not re.fullmatch(r"[A-Z0-9_-]{1,64}", a) for a in self.asset_ids):
            raise ValueError("Invalid asset ID")
        if len(set(self.asset_ids)) != len(self.asset_ids):
            raise ValueError("Asset order must be unique")
        if not self.start_date <= self.end_date <= self.as_of_date <= utcnow().date():
            raise ValueError("Invalid snapshot date window")
        if (self.end_date - self.start_date).days > 3650:
            raise ValueError("Snapshot window cannot exceed ten years")
        return self
