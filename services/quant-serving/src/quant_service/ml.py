"""Read-only, hash-pinned native model inference; no training in serving requests."""

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import numpy as np
from pydantic import Field, FiniteFloat, TypeAdapter, model_validator
import xgboost as xgb

from portfolio_contracts import ModelUnavailable, StrictModel, canonical_hash, utcnow
from . import phase1


Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Nonnegative = Annotated[FiniteFloat, Field(ge=0)]


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


class Phase1Member(ArtifactRef):
    seed: int
    best_iteration: int = Field(ge=0, lt=200)
    validation_rmse: Nonnegative


class Phase1Asset(StrictModel):
    scaler_mean: list[FiniteFloat] = Field(min_length=8, max_length=8)
    scaler_scale: list[Annotated[FiniteFloat, Field(gt=0)]] = Field(
        min_length=8, max_length=8
    )
    boosters: list[Phase1Member] = Field(min_length=5, max_length=5)


class Phase1Split(StrictModel):
    train_rows: int = Field(ge=100)
    validation_rows: int = Field(ge=2)
    purged_rows: int = Field(ge=0)
    train_label_end: date
    validation_start: date
    validation_end: date
    validation_label_end: date
    mae: Nonnegative
    rmse: Nonnegative
    r2: FiniteFloat

    @model_validator(mode="after")
    def temporal(self):
        if not (
            phase1.START
            <= self.train_label_end
            < self.validation_start
            <= self.validation_end
            < self.validation_label_end
            <= phase1.CUTOFF
        ):
            raise ValueError("Phase 1 label cutoff or train/validation overlap")
        return self


class Phase1Validation(StrictModel):
    method: Literal["phase1-chronological-80-20-label-purge-v1"]
    point_in_time_certified: Literal[False]
    train_rows: int
    validation_rows: int
    train_label_end: date
    validation_start: date
    mae: Nonnegative
    rmse: Nonnegative
    by_asset: dict[str, Phase1Split]


class Phase1Manifest(StrictModel):
    schema_version: Literal[3]
    model_id: str
    status: Literal["CANDIDATE", "APPROVED"]
    core_version: Literal["0.1.0"]
    xgboost_version: str
    feature_schema_version: Literal["phase1-equity-features-v1"]
    feature_names: list[str]
    asset_ids: list[str]
    training_cutoff: date
    training_data_hash: Digest
    training_history_hash: Digest
    baseline_run_id: Literal["availability-observed-contract-20261012T233110"]
    baseline_manifest_sha256: Digest
    source_hashes: dict[str, Digest] = Field(min_length=1)
    training_knowledge_cutoff: datetime
    trained_at: datetime
    demo: Literal[False]
    horizon_sessions: Literal[5]
    return_unit: Literal["five_session_simple_fraction"]
    assets: dict[str, Phase1Asset]
    validation: Phase1Validation
    approved_by: str | None = None
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def consistent(self):
        if (
            str(UUID(self.model_id)) != self.model_id
            or self.asset_ids != phase1.ASSETS
            or self.feature_names != phase1.FEATURES
            or set(self.assets) != set(self.asset_ids)
            or self.training_cutoff != phase1.CUTOFF
            or self.training_knowledge_cutoff.tzinfo is None
            or self.trained_at.tzinfo is None
            or not self.training_cutoff <= self.training_knowledge_cutoff.date()
            or not self.training_knowledge_cutoff <= self.trained_at <= utcnow()
        ):
            raise ValueError("Invalid Phase 1 model schema or knowledge provenance")
        for asset in self.asset_ids:
            members = self.assets[asset].boosters
            if tuple(member.seed for member in members) != phase1.SEEDS:
                raise ValueError("Invalid Phase 1 ensemble seeds/order")
            if any(member.file != f"{asset}-{member.seed}.ubj" for member in members):
                raise ValueError("Invalid Phase 1 booster filename")
        validation = self.validation
        splits = validation.by_asset.values()
        if (
            set(validation.by_asset) != set(self.asset_ids)
            or validation.train_rows != sum(split.train_rows for split in splits)
            or validation.validation_rows
            != sum(split.validation_rows for split in splits)
            or validation.train_label_end
            != max(split.train_label_end for split in splits)
            or validation.validation_start
            != min(split.validation_start for split in splits)
        ):
            raise ValueError("Inconsistent Phase 1 validation summary")
        if self.status == "APPROVED":
            if (
                not self.approved_by
                or not self.approved_by.strip()
                or self.approved_at is None
                or self.approved_at.tzinfo is None
                or not self.trained_at <= self.approved_at <= utcnow()
            ):
                raise ValueError("Invalid Phase 1 approval")
        elif self.approved_by is not None or self.approved_at is not None:
            raise ValueError("Candidate cannot contain Phase 1 approval metadata")
        return self


class FullSplit(Phase1Split):
    train_rows: int = Field(ge=1)

    @model_validator(mode="after")
    def temporal(self):
        if not (
            phase1.START
            <= self.train_label_end
            < self.validation_start
            <= self.validation_end
            < self.validation_label_end
            <= utcnow().date()
            and self.train_rows + self.validation_rows + self.purged_rows >= 100
        ):
            raise ValueError("Full Phase 1 label cutoff or train/validation overlap")
        return self


class FullValidation(Phase1Validation):
    by_asset: dict[str, FullSplit]


class FullManifest(StrictModel):
    schema_version: Literal[4]
    model_id: str
    status: Literal["CANDIDATE", "APPROVED"]
    core_version: Literal["0.1.0"]
    xgboost_version: str
    feature_schema_version: Literal["phase1-full-features-v1"]
    feature_names: list[str]
    asset_ids: list[str]
    full_asset_ids: list[str]
    active_asset_ids: list[str]
    selected_equity_ids: list[str]
    selection_id: Digest
    selection_epoch: date
    model_selection_id: Digest
    model_selection_epoch: date
    fit_epoch: date
    training_cutoff: date
    training_equity_hash: Digest
    training_snapshot_id: str
    training_snapshot_hash: Digest
    training_data_hash: Digest
    baseline_run_id: Literal["availability-observed-contract-20261012T233110"]
    baseline_manifest_sha256: Digest
    source_hashes: dict[str, Digest] = Field(min_length=1)
    training_knowledge_cutoff: datetime
    trained_at: datetime
    demo: Literal[False]
    horizon_sessions: Literal[5]
    return_unit: Literal["five_session_simple_fraction"]
    assets: dict[str, Phase1Asset]
    validation: FullValidation
    approved_by: str | None = None
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def consistent(self):
        from portfolio_core.phase1_full import ASSET_IDS, validate_active_assets

        validate_active_assets(self.full_asset_ids, self.active_asset_ids)
        validate_active_assets(self.full_asset_ids, self.asset_ids + ["GOLD", "VFF"])
        if (
            str(UUID(self.model_id)) != self.model_id
            or self.full_asset_ids != list(ASSET_IDS)
            or self.active_asset_ids != self.selected_equity_ids + ["GOLD", "VFF"]
            or self.feature_names != phase1.FEATURES
            or set(self.assets) != set(self.asset_ids)
            or not phase1.START <= self.model_selection_epoch <= self.fit_epoch
            or not self.model_selection_epoch <= self.selection_epoch
            or not self.training_cutoff
            < self.fit_epoch
            <= self.training_knowledge_cutoff.date()
            or self.training_knowledge_cutoff.tzinfo is None
            or self.trained_at.tzinfo is None
            or not self.training_knowledge_cutoff <= self.trained_at <= utcnow()
        ):
            raise ValueError(
                "Invalid full Phase 1 model identity or knowledge provenance"
            )
        for asset in self.asset_ids:
            members = self.assets[asset].boosters
            if tuple(member.seed for member in members) != phase1.SEEDS or any(
                member.file != f"{asset}-{member.seed}.ubj" for member in members
            ):
                raise ValueError(
                    "Invalid full Phase 1 ensemble seeds/order or filename"
                )
        validation = self.validation
        splits = list(validation.by_asset.values())
        if (
            set(validation.by_asset) != set(self.asset_ids)
            or any(s.validation_label_end != self.training_cutoff for s in splits)
            or validation.train_rows != sum(s.train_rows for s in splits)
            or validation.validation_rows != sum(s.validation_rows for s in splits)
            or validation.train_label_end != max(s.train_label_end for s in splits)
            or validation.validation_start != min(s.validation_start for s in splits)
        ):
            raise ValueError("Inconsistent full Phase 1 validation summary")
        if self.status == "APPROVED":
            if (
                not self.approved_by
                or not self.approved_by.strip()
                or self.approved_at is None
                or self.approved_at.tzinfo is None
                or not self.trained_at <= self.approved_at <= utcnow()
            ):
                raise ValueError("Invalid full Phase 1 approval")
        elif self.approved_by is not None or self.approved_at is not None:
            raise ValueError("Candidate cannot contain full Phase 1 approval metadata")
        return self


class CoveredAsset(Phase1Asset):
    training_cutoff: date
    training_data_hash: Digest
    source_hashes: dict[str, Digest] = Field(min_length=1)


class AssetEnsembleManifest(StrictModel):
    schema_version: Literal[5]
    model_id: str
    status: Literal["CANDIDATE", "APPROVED"]
    model_family: Literal["phase1-asset-ensemble-v5"]
    core_version: Literal["0.1.0"]
    xgboost_version: str
    catalog_version: Literal["supported-assets-v1"]
    catalog_asset_ids: list[str]
    feature_schema_version: Literal["phase1-asset-features-v1"]
    feature_names: list[str]
    asset_ids: list[str] = Field(min_length=1, max_length=30)
    covered_asset_ids: list[str]
    omitted_assets: dict[
        str, Literal["ASSET_DATA_MISSING", "HISTORY_INSUFFICIENT", "INPUT_INVALID"]
    ]
    fit_epoch: date
    training_cutoff: date
    training_equity_hash: Digest
    training_snapshot_id: str
    training_snapshot_hash: Digest
    training_data_hash: Digest
    baseline_run_id: Literal["availability-observed-contract-20261012T233110"]
    baseline_manifest_sha256: Digest
    source_hashes: dict[str, Digest] = Field(min_length=1)
    training_knowledge_cutoff: datetime
    trained_at: datetime
    demo: Literal[False]
    horizon_sessions: Literal[5]
    return_unit: Literal["five_session_simple_fraction"]
    assets: dict[str, CoveredAsset]
    validation: FullValidation
    approved_by: str | None = None
    approved_at: datetime | None = None

    @model_validator(mode="after")
    def consistent(self):
        from portfolio_core.assets import ASSET_IDS, EQUITY_IDS

        if (
            str(UUID(self.model_id)) != self.model_id
            or self.catalog_asset_ids != list(ASSET_IDS)
            or self.asset_ids != [a for a in EQUITY_IDS if a in self.asset_ids]
            or self.covered_asset_ids != self.asset_ids
            or set(self.omitted_assets) != set(EQUITY_IDS) - set(self.asset_ids)
            or set(self.assets) != set(self.asset_ids)
            or self.feature_names != phase1.FEATURES
            or not phase1.START <= self.training_cutoff < self.fit_epoch
            or self.training_knowledge_cutoff.tzinfo is None
            or self.trained_at.tzinfo is None
            or not self.fit_epoch <= self.training_knowledge_cutoff.date()
            or not self.training_knowledge_cutoff <= self.trained_at <= utcnow()
        ):
            raise ValueError("Invalid asset ensemble coverage or training provenance")
        for asset, ensemble in self.assets.items():
            if (
                ensemble.training_cutoff != self.training_cutoff
                or tuple(m.seed for m in ensemble.boosters) != phase1.SEEDS
                or any(m.file != f"{asset}-{m.seed}.ubj" for m in ensemble.boosters)
            ):
                raise ValueError("Invalid asset ensemble epoch, members, or paths")
        validation = self.validation
        splits = list(validation.by_asset.values())
        if (
            set(validation.by_asset) != set(self.asset_ids)
            or any(s.validation_label_end != self.training_cutoff for s in splits)
            or validation.train_rows != sum(s.train_rows for s in splits)
            or validation.validation_rows != sum(s.validation_rows for s in splits)
            or validation.train_label_end != max(s.train_label_end for s in splits)
            or validation.validation_start != min(s.validation_start for s in splits)
        ):
            raise ValueError("Inconsistent asset ensemble validation")
        if self.status == "APPROVED":
            if (
                not self.approved_by
                or not self.approved_by.strip()
                or self.approved_at is None
                or self.approved_at.tzinfo is None
                or not self.trained_at <= self.approved_at <= utcnow()
            ):
                raise ValueError("Invalid asset ensemble approval")
        elif self.approved_by is not None or self.approved_at is not None:
            raise ValueError("Candidate cannot contain approval metadata")
        return self


_manifest_schema = TypeAdapter(
    Annotated[
        ModelManifest | Phase1Manifest | FullManifest | AssetEnsembleManifest,
        Field(discriminator="schema_version"),
    ]
)


def parse_manifest(data):
    return _manifest_schema.validate_json(data)


class FeatureBatch(StrictModel):
    manifest: ArtifactRef
    feature_schema_version: str
    feature_names: list[str]
    asset_ids: list[str]
    feature_date: date
    rows: list[list[FiniteFloat]]
    feature_known_at: datetime | None = None


class Phase1FeatureBatch(FeatureBatch):
    history_start: date
    training_history_hash: Digest
    daily_volatility: list[Nonnegative] = Field(min_length=3, max_length=3)


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


def load_booster(data):
    try:
        booster = xgb.Booster(params={"nthread": 1, "device": "cpu"})
        booster.load_model(bytearray(data))
        return booster
    except xgb.core.XGBoostError as exc:
        raise ValueError("Native model artifact invalid") from exc


def phase1_booster(data, member, features):
    booster = load_booster(data)
    if (
        booster.feature_names != features
        or booster.attr("best_iteration") != str(member.best_iteration)
        or member.best_iteration >= booster.num_boosted_rounds()
    ):
        raise ValueError("Phase 1 booster schema or best iteration mismatch")
    return booster


def native_data(directory, ref, *, suffixes=(".ubj",)):
    return read_artifact(directory, ref, suffixes=suffixes, max_bytes=20_000_000)


def validate_native_files(directory, manifest, *, suffixes=(".ubj",), load=False):
    if manifest.schema_version not in (3, 4, 5):
        native_data(directory, manifest.model, suffixes=suffixes)
        return
    for asset in manifest.asset_ids:
        for member in manifest.assets[asset].boosters:
            native = native_data(
                directory, member.model_dump(include={"file", "sha256"})
            )
            if load:
                phase1_booster(native, member, manifest.feature_names)


def phase1_predictions(directory, manifest, rows, *, asset_ids=None):
    ids = manifest.asset_ids if asset_ids is None else asset_ids
    rows = np.asarray(rows, dtype=float)
    if (
        len(set(ids)) != len(ids)
        or not set(ids) <= set(manifest.asset_ids)
        or rows.shape != (len(ids), len(manifest.feature_names))
        or not np.isfinite(rows).all()
    ):
        raise ValueError("Invalid ensemble asset/feature alignment")
    predictions = []
    for asset, row in zip(ids, rows):
        ensemble = manifest.assets[asset]
        scaled = (row - ensemble.scaler_mean) / ensemble.scaler_scale
        if not np.isfinite(scaled).all():
            raise ValueError("Invalid Phase 1 scaled features")
        matrix = xgb.DMatrix([scaled], feature_names=manifest.feature_names, nthread=1)
        members = []
        for member in ensemble.boosters:
            native = native_data(
                directory, member.model_dump(include={"file", "sha256"})
            )
            booster = phase1_booster(native, member, manifest.feature_names)
            members.append(
                booster.predict(matrix, iteration_range=(0, member.best_iteration + 1))[
                    0
                ]
            )
        predictions.append(members)
    return predictions


def infer(directory, value, *, allow_demo=False):
    reference = ArtifactRef.model_validate(value["ml_inference"]["manifest"])
    manifest = parse_manifest(read_artifact(directory, reference))
    if manifest.schema_version == 5:
        raise ValueError("Asset ensembles require pinned candidate inference")
    if manifest.schema_version == 4:
        from .full import infer_full

        native_directory = (Path(directory).resolve() / reference.file).resolve().parent
        return infer_full(native_directory, value, manifest, reference)
    is_phase1 = manifest.schema_version == 3
    batch = (Phase1FeatureBatch if is_phase1 else FeatureBatch).model_validate(
        value["ml_inference"]
    )
    if manifest.schema_version in (2, 3):
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
    as_of = date.fromisoformat(value["as_of_date"])
    if is_phase1:
        max_age = value["provenance"]["max_data_age_days"]
        if (
            type(max_age) is not int
            or not 1 <= max_age <= 30
            or (utcnow().date() - as_of).days > max_age
            or timestamp(value["valid_until"]) <= utcnow()
        ):
            raise ValueError("Phase 1 snapshot expired")
        if (
            value["universe_id"] != phase1.UNIVERSE
            or batch.history_start != phase1.START
            or batch.training_history_hash != manifest.training_history_hash
            or not 1 <= (as_of - batch.feature_date).days <= 14
            or not as_of <= batch.feature_known_at.date()
        ):
            raise ValueError(
                "Phase 1 universe, history, observation lag or availability mismatch"
            )
    if (
        batch.manifest.sha256 != value.get("model_bundle_id")
        or batch.asset_ids != ids
        or manifest.asset_ids != ids
        or batch.feature_names != manifest.feature_names
        or batch.feature_schema_version != manifest.feature_schema_version
        or (not is_phase1 and batch.feature_date != as_of)
        or as_of > utcnow().date()
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
    # Model-native references belong to the hash-pinned manifest directory.
    # Root-level legacy CLI manifests keep exactly their previous resolution.
    native_directory = (
        (Path(directory).resolve() / batch.manifest.file).resolve().parent
    )
    provenance = {
        "model_manifest_hash": batch.manifest.sha256,
        "model_id": manifest.model_id,
        "feature_schema_version": manifest.feature_schema_version,
        "feature_batch_hash": canonical_hash(batch.model_dump(mode="json")),
        "training_cutoff": manifest.training_cutoff.isoformat(),
        "return_unit": manifest.return_unit,
        "horizon_sessions": manifest.horizon_sessions,
        "approved_by": manifest.approved_by,
    }
    if is_phase1:
        predictions = phase1_predictions(native_directory, manifest, rows)
        forecasts = [phase1.ensemble_forecast(members) for members in predictions]
        views = phase1.option_b(forecasts, batch.daily_volatility)
        return value["numerical"] | views, provenance | {
            "confidence_policy": "phase1-ensemble-disagreement-v1",
            "view_policy": "phase1-option-b-daily-v1",
            "view_return_unit": "daily_simple_fraction",
            "feature_date": batch.feature_date.isoformat(),
            "feature_known_at": batch.feature_known_at.isoformat(),
            "training_data_hash": manifest.training_data_hash,
            "trained_at": manifest.trained_at.isoformat(),
            "booster_sha256": {
                asset: [member.sha256 for member in manifest.assets[asset].boosters]
                for asset in ids
            },
        }
    rows = (rows - manifest.scaler_mean) / manifest.scaler_scale
    if not np.isfinite(rows).all():
        raise ValueError("Invalid scaled features")
    native = native_data(native_directory, manifest.model, suffixes=(".json", ".ubj"))
    try:
        q = load_booster(native).predict(
            xgb.DMatrix(rows, feature_names=manifest.feature_names)
        )
    except xgb.core.XGBoostError as exc:
        raise ValueError("Native model inference failed") from exc
    if q.shape != (len(ids),) or not np.isfinite(q).all():
        raise ValueError("Invalid model predictions")
    provenance |= {
        "model_sha256": manifest.model.sha256,
        "confidence_policy": "fixed-v1",
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
