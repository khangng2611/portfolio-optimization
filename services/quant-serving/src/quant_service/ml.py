"""Read-only, hash-pinned native model inference; no training in serving requests."""

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import Field, FiniteFloat, model_validator
import xgboost as xgb

from portfolio_contracts import ModelUnavailable, StrictModel, canonical_hash, utcnow


class ArtifactRef(StrictModel):
    file: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ModelManifest(StrictModel):
    schema_version: Literal[1, 2]
    model_id: str
    status: Literal["CANDIDATE", "APPROVED"]
    model: ArtifactRef
    core_version: Literal["0.1.0"]
    xgboost_version: str
    feature_schema_version: str
    feature_names: list[str] = Field(min_length=1, max_length=100)
    asset_ids: list[str] = Field(min_length=2, max_length=100)
    scaler_mean: list[FiniteFloat]
    scaler_scale: list[FiniteFloat]
    training_cutoff: date
    training_snapshot_id: str
    training_data_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    horizon_sessions: Literal[1]
    return_unit: Literal["daily_simple_fraction"]
    confidence: FiniteFloat = Field(gt=0, le=1)
    demo: bool
    validation: dict
    approved_by: str | None = None
    approved_at: datetime | None = None
    training_snapshot_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    training_knowledge_cutoff: datetime | None = None
    trained_at: datetime | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.schema_version == 2 and (
            self.demo
            or not self.training_snapshot_hash
            or self.training_knowledge_cutoff is None
            or self.trained_at is None
            or self.training_knowledge_cutoff.tzinfo is None
            or self.trained_at.tzinfo is None
            or not self.training_knowledge_cutoff <= self.trained_at <= utcnow()
        ):
            raise ValueError("Invalid model knowledge provenance")
        if len(self.feature_names) != len(set(self.feature_names)) or len(
            self.asset_ids
        ) != len(set(self.asset_ids)):
            raise ValueError("Duplicate schema identifiers")
        if (
            len(self.scaler_mean) != len(self.feature_names)
            or len(self.scaler_scale) != len(self.feature_names)
            or any(s <= 0 for s in self.scaler_scale)
        ):
            raise ValueError("Invalid scaler shape/scale")
        if self.status == "APPROVED" and (
            not self.approved_by
            or not self.approved_by.strip()
            or self.approved_at is None
            or self.approved_at.tzinfo is None
            or self.approved_at > utcnow()
        ):
            raise ValueError("Invalid approval")
        return self


class FeatureBatch(StrictModel):
    manifest: ArtifactRef
    feature_schema_version: str
    feature_names: list[str]
    asset_ids: list[str]
    feature_date: date
    rows: list[list[FiniteFloat]]
    feature_known_at: datetime | None = None


def read_artifact(directory, reference, *, suffixes=(".json",), max_bytes=2_000_000):
    ref = ArtifactRef.model_validate(reference)
    root = Path(directory).resolve()
    path = (root / ref.file).resolve()
    if not path.is_relative_to(root) or path.suffix not in suffixes:
        raise ValueError("Invalid artifact path/format")
    try:
        if path.stat().st_size > max_bytes:
            raise ValueError("Artifact too large")
        data = path.read_bytes()
    except OSError as exc:
        raise ModelUnavailable("Referenced model artifact unavailable") from exc
    if hashlib.sha256(data).hexdigest() != ref.sha256:
        raise ValueError("Model artifact checksum mismatch")
    return data


def infer(directory, value, *, allow_demo=False):
    batch = FeatureBatch.model_validate(value["ml_inference"])
    manifest = ModelManifest.model_validate_json(
        read_artifact(directory, batch.manifest)
    )
    if manifest.schema_version == 2:
        from .snapshot_inputs import timestamp

        decision_at = timestamp(value["decision_at"])
        if (
            batch.feature_known_at is None
            or batch.feature_known_at.tzinfo is None
            or not batch.feature_known_at <= decision_at <= utcnow()
            or manifest.trained_at > decision_at
            or (manifest.approved_at is not None and manifest.approved_at > decision_at)
            or batch.feature_known_at.date() < batch.feature_date
        ):
            raise ValueError("Features or model unavailable at decision time")
    if manifest.status != "APPROVED":
        raise ModelUnavailable("Model is not approved")
    ids = value["numerical"]["asset_ids"]
    if (
        batch.manifest.sha256 != value.get("model_bundle_id")
        or batch.asset_ids != ids
        or manifest.asset_ids != ids
        or batch.feature_names != manifest.feature_names
        or batch.feature_schema_version != manifest.feature_schema_version
        or batch.feature_date != date.fromisoformat(value["as_of_date"])
        or batch.feature_date > utcnow().date()
        or manifest.training_cutoff >= batch.feature_date
        or manifest.xgboost_version != xgb.__version__
        or manifest.demo != value["demo"]
        or (manifest.demo and not allow_demo)
    ):
        raise ValueError("Model/feature identity, cutoff or runtime mismatch")
    rows = np.asarray(batch.rows, dtype=float)
    if (
        rows.shape != (len(ids), len(manifest.feature_names))
        or not np.isfinite(rows).all()
    ):
        raise ValueError("Invalid feature matrix")
    rows = (rows - manifest.scaler_mean) / manifest.scaler_scale
    if not np.isfinite(rows).all():
        raise ValueError("Invalid scaled features")
    native = read_artifact(
        directory, manifest.model, suffixes=(".json", ".ubj"), max_bytes=20_000_000
    )
    try:
        booster = xgb.Booster(params={"nthread": 1, "device": "cpu"})
        booster.load_model(bytearray(native))
        q = booster.predict(xgb.DMatrix(rows, feature_names=manifest.feature_names))
    except xgb.core.XGBoostError as exc:
        raise ValueError("Native model inference failed") from exc
    if q.shape != (len(ids),) or not np.isfinite(q).all():
        raise ValueError("Invalid model predictions")
    provenance = {
        "model_manifest_hash": batch.manifest.sha256,
        "model_sha256": manifest.model.sha256,
        "model_id": manifest.model_id,
        "feature_schema_version": manifest.feature_schema_version,
        "feature_batch_hash": canonical_hash(batch.model_dump(mode="json")),
        "training_cutoff": manifest.training_cutoff.isoformat(),
        "return_unit": manifest.return_unit,
        "horizon_sessions": manifest.horizon_sessions,
        "confidence_policy": "fixed-v1",
        "approved_by": manifest.approved_by,
    }
    if manifest.schema_version == 2:
        provenance |= {
            "training_snapshot_hash": manifest.training_snapshot_hash,
            "training_knowledge_cutoff": manifest.training_knowledge_cutoff.isoformat(),
            "trained_at": manifest.trained_at.isoformat(),
        }
    return value["numerical"] | {
        "views_p": np.eye(len(ids)).tolist(),
        "views_q": q.tolist(),
        "view_confidences": [manifest.confidence] * len(ids),
    }, provenance
