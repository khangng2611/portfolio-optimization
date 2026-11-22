"""Explanation sidecars are independent of canonical numerical facts."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, FiniteFloat, model_validator, model_serializer

from . import StrictModel, canonical_hash

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Asset = Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,32}$")]
Assets = Annotated[list[Asset], Field(min_length=1, max_length=32)]


class FeatureEvidence(StrictModel):
    name: Literal[
        "momentum_5",
        "momentum_10",
        "momentum_20",
        "rsi_14",
        "ma_ratio_10_30",
        "volatility_20",
        "macd_hist",
        "price_std_20",
    ]
    value: FiniteFloat
    unit: Literal["fraction", "index", "thousand_vnd"]

    @model_validator(mode="after")
    def units(self):
        expected = (
            "index"
            if self.name == "rsi_14"
            else "thousand_vnd"
            if self.name == "macd_hist"
            else "fraction"
        )
        if self.unit != expected:
            raise ValueError("Feature unit mismatch")
        return self


class ViewEvidence(StrictModel):
    source_kind: Literal["ML", "POLICY", "USER"]
    status: Literal["APPLIED", "BELOW_THRESHOLD"]
    coefficients: dict[Asset, FiniteFloat] = Field(min_length=1, max_length=32)
    raw_mean_return: FiniteFloat | None = None
    member_std: Annotated[FiniteFloat, Field(ge=0)] | None = None
    horizon_sessions: Literal[5] | None = None
    raw_return_unit: Literal["simple_fraction"] | None = None
    confidence_base: Annotated[FiniteFloat, Field(gt=0, le=1)] | None = None
    confidence_applied: Annotated[FiniteFloat, Field(gt=0, le=1)] | None = None
    applied_q_daily: FiniteFloat | None = None
    transform_version: Literal["phase1-option-b-v1", "vff-relative-policy-v1"]

    @model_validator(mode="after")
    def consistent(self):
        if not any(self.coefficients.values()):
            raise ValueError("Empty view")
        if self.source_kind == "POLICY":
            coefficients = self.coefficients
            count = len(coefficients) - 1
            if (
                self.transform_version != "vff-relative-policy-v1"
                or coefficients.get("VFF") != 1
                or count < 1
                or any(
                    abs(w + 1 / count) > 1e-12
                    for a, w in coefficients.items()
                    if a != "VFF"
                )
                or self.applied_q_daily not in (0.05 / 252, 0.1 / 252)
            ):
                raise ValueError("Unsupported policy view evidence")
        if self.source_kind == "ML" and any(
            v is None
            for v in (
                self.raw_mean_return,
                self.member_std,
                self.horizon_sessions,
                self.raw_return_unit,
                self.confidence_base,
            )
        ):
            raise ValueError("Missing raw ML evidence")
        if self.status == "APPLIED" and (
            self.applied_q_daily is None or self.confidence_applied is None
        ):
            raise ValueError("Missing applied view")
        if self.status == "BELOW_THRESHOLD" and (
            self.applied_q_daily is not None or self.confidence_applied is not None
        ):
            raise ValueError("Suppressed view cannot be applied")
        return self


class RegimeEvidence(StrictModel):
    scope: Literal["candidate-basket"] = "candidate-basket"
    asset_ids: Assets
    regime: Literal["normal", "stress", "crisis"]
    vol_ratio: Annotated[FiniteFloat, Field(ge=0)]
    drawdown: FiniteFloat
    equity_momentum: FiniteFloat
    observed_sessions: Annotated[int, Field(ge=2)]
    volatility_windows: tuple[Literal[20], Literal[120]] = (20, 120)
    trend_window: Literal[60] = 60


class OptimizationExplanationEvidence(StrictModel):
    schema_version: Literal["optimization-explanation-v1"] = (
        "optimization-explanation-v1"
    )
    status: Literal["COMPLETE", "PARTIAL"]
    job_id: str = Field(max_length=36)
    run_id: str = Field(max_length=36)
    input_hash: Digest
    bundle_hash: Digest
    snapshot_id: str = Field(max_length=100)
    model_bundle_id: str | None = Field(default=None, max_length=100)
    asset_ids: Assets
    active_asset_ids: Assets
    decision_at: datetime | None = None
    history_end_date: date | None = None
    regime_end_date: date | None = None
    covariance_end_date: date | None = None
    snapshot_hash: Digest | None = None
    model_id: str | None = Field(default=None, max_length=36)
    fit_epoch: date | None = None
    trained_at: datetime | None = None
    training_cutoff: date | None = None
    selection_hash: Digest | None = None
    feature_schema: str | None = Field(default=None, max_length=100)
    features: dict[Asset, Annotated[list[FeatureEvidence], Field(max_length=8)]] = (
        Field(default_factory=dict, max_length=32)
    )
    views: list[ViewEvidence] = Field(default_factory=list, max_length=64)
    regime: RegimeEvidence | None = None
    limitations: list[
        Literal["NOT_RETAINED", "ATTRIBUTION_NOT_AVAILABLE", "PIT_NOT_CERTIFIED"]
    ] = Field(default_factory=list, max_length=3)
    evidence_hash: Digest | None = None

    @model_serializer(mode="wrap")
    def preserve_existing_sidecar(self, handler):
        body = handler(self)
        # Additive pins must not change already sealed v1 receipts when absent.
        for key in (
            "regime_end_date",
            "covariance_end_date",
            "snapshot_hash",
            "model_id",
            "fit_epoch",
            "trained_at",
            "training_cutoff",
        ):
            if key not in self.model_fields_set:
                body.pop(key, None)
        return body

    @model_validator(mode="after")
    def aligned(self):
        for ids in (self.asset_ids, self.active_asset_ids):
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate assets")
        if self.active_asset_ids != [
            a for a in self.asset_ids if a in self.active_asset_ids
        ] or not set(self.features) <= set(self.active_asset_ids):
            raise ValueError("Unaligned assets")
        for asset, features in self.features.items():
            if len({f.name for f in features}) != len(features):
                raise ValueError("Duplicate features")
        if any(
            not set(v.coefficients) <= set(self.active_asset_ids) for v in self.views
        ):
            raise ValueError("Unaligned view")
        if self.regime and self.regime.asset_ids != self.asset_ids:
            raise ValueError("Wrong regime scope")
        if self.status == "COMPLETE" and (
            not self.features
            or not self.views
            or self.regime is None
            or self.history_end_date is None
        ):
            raise ValueError("Incomplete evidence")
        return self

    def seal(self):
        body = self.model_dump(mode="json", exclude={"evidence_hash"})
        return body | {"evidence_hash": canonical_hash(body)}

    def checked(self):
        if self.evidence_hash != self.seal()["evidence_hash"]:
            raise ValueError("Evidence hash mismatch")
        return self


class RecommendationEvidence(StrictModel):
    schema_version: Literal["recommendation-evidence-v1"] = "recommendation-evidence-v1"
    recommendation_id: str
    run_id: str
    facts_hash: Digest
    status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    quant: OptimizationExplanationEvidence | None = None
    limitations: list[str] = Field(default_factory=list, max_length=4)
    evidence_hash: Digest | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "COMPLETE" and (
            self.quant is None or self.quant.status != "COMPLETE"
        ):
            raise ValueError("Complete response requires complete Quant evidence")
        if self.status == "UNAVAILABLE" and self.quant is not None:
            raise ValueError("Unavailable evidence cannot expose Quant data")
        if self.quant and (
            self.quant.job_id != self.recommendation_id
            or self.quant.run_id != self.run_id
        ):
            raise ValueError("Quant evidence identity mismatch")
        return self

    def seal(self):
        body = self.model_dump(mode="json", exclude={"evidence_hash"})
        return body | {"evidence_hash": canonical_hash(body)}

    def checked(self):
        if self.evidence_hash != self.seal()["evidence_hash"]:
            raise ValueError("Recommendation evidence hash mismatch")
        if self.quant:
            self.quant.checked()
        return self
