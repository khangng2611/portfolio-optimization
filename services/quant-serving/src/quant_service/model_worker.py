"""Offline model worker. Its output is a candidate until an explicit local approval.

This filesystem publication adapter is intentionally separate from the API/optimizer
consumer; it is not a replacement for the future owner ML Platform/registry service.
"""

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import numpy as np
from pydantic import Field, FiniteFloat, model_validator
import xgboost as xgb

from portfolio_contracts import StrictModel, canonical_hash, utcnow
from .ml import ModelManifest, read_artifact


class TrainingData(StrictModel):
    schema_version: Literal[1, 2]
    horizon_sessions: Literal[1]
    return_unit: Literal["daily_simple_fraction"]
    asset_ids: list[str] = Field(min_length=2, max_length=100)
    feature_names: list[str] = Field(min_length=1, max_length=100)
    feature_schema_version: str
    snapshot_id: str
    demo: bool
    training_cutoff: date
    features: list[list[FiniteFloat]] = Field(min_length=10, max_length=100_000)
    targets: list[FiniteFloat]
    feature_dates: list[date]
    label_available_dates: list[date] | None = None
    label_dates: list[date] | None = None
    feature_known_at: list[datetime] | None = None
    label_known_at: list[datetime] | None = None
    knowledge_cutoff: datetime | None = None
    snapshot_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @property
    def economic_labels(self):
        return (
            self.label_dates if self.schema_version == 2 else self.label_available_dates
        )

    @model_validator(mode="after")
    def timing(self):
        n = len(self.features)
        labels = self.economic_labels
        if labels is None:
            raise ValueError("Label timing contract required")
        if self.schema_version == 2:
            if (
                self.demo
                or not self.snapshot_hash
                or self.label_available_dates is not None
                or self.knowledge_cutoff is None
                or self.knowledge_cutoff.tzinfo is None
                or self.knowledge_cutoff > utcnow()
                or self.feature_known_at is None
                or self.label_known_at is None
                or len(self.feature_known_at) != n
                or len(self.label_known_at) != n
            ):
                raise ValueError("Complete real-data knowledge provenance required")
            for day, label, f_known, l_known in zip(
                self.feature_dates, labels, self.feature_known_at, self.label_known_at
            ):
                if (
                    f_known.tzinfo is None
                    or l_known.tzinfo is None
                    or not f_known <= l_known <= self.knowledge_cutoff
                    or f_known.date() < day
                    or l_known.date() < label
                ):
                    raise ValueError("Training data unavailable at knowledge cutoff")
        if not n == len(self.targets) == len(self.feature_dates) == len(labels):
            raise ValueError("Training row alignment mismatch")
        if (
            self.training_cutoff > utcnow().date()
            or any(
                not f < label <= self.training_cutoff
                for f, label in zip(self.feature_dates, labels)
            )
            or self.feature_dates != sorted(self.feature_dates)
        ):
            raise ValueError("Unsorted features or labels unavailable at cutoff")
        if any(len(row) != len(self.feature_names) for row in self.features):
            raise ValueError("Training feature shape mismatch")
        if len(set(self.feature_names)) != len(self.feature_names) or len(
            set(self.asset_ids)
        ) != len(self.asset_ids):
            raise ValueError("Duplicate schema identifiers")
        return self


def publish_json(directory, name, value):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    # Unique identities and exclusive creation never overwrite a published artifact.
    with (root / name).open("xb") as stream:
        stream.write(data)
    return {"file": name, "sha256": hashlib.sha256(data).hexdigest()}


def train_candidate(directory, raw):
    data = TrainingData.model_validate(raw)
    split = int(len(data.features) * 0.8)
    validation_start = data.feature_dates[split]
    training = [i for i in range(split) if data.economic_labels[i] < validation_start]
    if len(training) < 5 or len(data.features) - split < 2:
        raise ValueError("Insufficient temporally separated train/validation rows")
    features = np.asarray(data.features, dtype=float)
    labels = np.asarray(data.targets, dtype=float)
    mean, scale = features[training].mean(axis=0), features[training].std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    normalized = (features - mean) / scale
    model = xgb.train(
        {
            "objective": "reg:squarederror",
            "max_depth": 2,
            "eta": 0.1,
            "seed": 0,
            "nthread": 1,
            "tree_method": "hist",
            "device": "cpu",
        },
        xgb.DMatrix(
            normalized[training],
            label=labels[training],
            feature_names=data.feature_names,
        ),
        num_boost_round=20,
    )
    predicted = model.predict(
        xgb.DMatrix(normalized[split:], feature_names=data.feature_names)
    )
    difference = predicted - labels[split:]
    identity = str(uuid4())
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    model_file = f"{identity}.ubj"
    native = bytes(model.save_raw(raw_format="ubj"))
    with (root / model_file).open("xb") as stream:
        stream.write(native)
    manifest = ModelManifest(
        schema_version=data.schema_version,
        model_id=identity,
        status="CANDIDATE",
        model={"file": model_file, "sha256": hashlib.sha256(native).hexdigest()},
        core_version="0.1.0",
        xgboost_version=xgb.__version__,
        feature_schema_version=data.feature_schema_version,
        feature_names=data.feature_names,
        asset_ids=data.asset_ids,
        scaler_mean=mean.tolist(),
        scaler_scale=scale.tolist(),
        training_cutoff=data.training_cutoff,
        training_snapshot_id=data.snapshot_id,
        training_data_hash=canonical_hash(data.model_dump(mode="json")),
        horizon_sessions=1,
        return_unit="daily_simple_fraction",
        confidence=0.5,
        demo=data.demo,
        training_snapshot_hash=data.snapshot_hash,
        training_knowledge_cutoff=data.knowledge_cutoff,
        trained_at=utcnow() if data.schema_version == 2 else None,
        validation={
            "method": "chronological-80-20-label-embargo-v1",
            "train_rows": len(training),
            "validation_rows": len(features) - split,
            "train_label_end": max(
                data.economic_labels[i] for i in training
            ).isoformat(),
            "validation_start": validation_start.isoformat(),
            "mae": float(np.abs(difference).mean()),
            "rmse": float(np.sqrt(np.mean(difference**2))),
            "point_in_time_certified": False,
        },
    )
    return publish_json(
        root, f"{identity}.candidate.json", manifest.model_dump(mode="json")
    )


def approve_candidate(directory, reference, *, reviewer):
    if not reviewer.strip():
        raise ValueError("Explicit reviewer identity required")
    manifest = ModelManifest.model_validate_json(read_artifact(directory, reference))
    if manifest.status != "CANDIDATE":
        raise ValueError("Only a candidate can be approved")
    read_artifact(
        directory, manifest.model, suffixes=(".json", ".ubj"), max_bytes=20_000_000
    )
    approved = ModelManifest.model_validate(
        manifest.model_dump()
        | {
            "status": "APPROVED",
            "approved_by": reviewer.strip(),
            "approved_at": utcnow(),
        }
    )
    return publish_json(
        directory,
        f"{manifest.model_id}.{uuid4()}.approved.json",
        approved.model_dump(mode="json"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    commands = parser.add_subparsers(dest="operation", required=True)
    train = commands.add_parser("train")
    train.add_argument("--dataset", required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("--candidate", required=True)
    approve.add_argument("--sha256", required=True)
    approve.add_argument("--reviewer", required=True)
    args = parser.parse_args()
    if args.operation == "train":
        result = train_candidate(
            args.directory, json.loads(Path(args.dataset).read_text())
        )
    else:
        result = approve_candidate(
            args.directory,
            {"file": args.candidate, "sha256": args.sha256},
            reviewer=args.reviewer,
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
