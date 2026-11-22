"""Offline native full-universe ensemble fit; serving only reads its artifacts."""

from datetime import date
import hashlib
from pathlib import Path
from uuid import uuid4

import numpy as np
import xgboost as xgb

from portfolio_contracts import canonical_hash, utcnow
from portfolio_core.phase1_full import ASSET_IDS, EQUITY_IDS
from quant_service import phase1
from quant_service.ml import FullManifest
from quant_service.model_worker import publish_json

BASELINE_RUN = "availability-observed-contract-20261012T233110"
BASELINE_MANIFEST = "3f7457ae6c56ca6e02bcae5166cd7851e9a428d6e0b6859153c34937b55aedd6"
FROZEN_SOURCES = {
    "source_snapshot/config.py": "be34439d42aca71919c40df2d8b31dd191a0f58efad5f6ba712d29a708aa77bf",
    "source_snapshot/gen_view/xgboost/xgboost_core.py": "7cf20b62613811dfd63da9d83cfcb9b0e85283d8b13c1b6a6e64de01f29956af",
    "source_snapshot/gen_view/xgboost/config.py": "ad3c019196db20e3638d6163e25ab52266e9a960086a428eb48286f27a8f033e",
}


def training_hash(panel):
    state = panel.selection_state()
    return canonical_hash(
        dict(
            training_equity_hash=state["training_equity_hash"],
            model_selection_id=state["model_selection_id"],
            fit_epoch=state["fit_epoch"],
            model_equity_ids=state["model_equity_ids"],
            feature_schema_version="phase1-full-features-v1",
            snapshot_id=panel.snapshot["id"],
            snapshot_hash=panel.snapshot["content_hash"],
            policy="frozen-ensemble-42-46-80-20-label-purge-v1",
        )
    )


def training_arrays(panel, asset):
    """Original eight prefix features and five-session labels, ending at fit t-6."""
    state = panel.selection_state()
    end = state["fit_index"] - phase1.HORIZON
    if panel.ids != list(ASSET_IDS) or asset not in state["model_equity_ids"]:
        raise ValueError("Invalid full training asset order")
    return feature_arrays(panel.prices[:end, panel.ids.index(asset)])


def feature_arrays(prices_vnd):
    """Frozen prefix features and forward labels for one explicit VND price series."""
    prices = np.asarray(prices_vnd, dtype=float) / 1000
    if len(prices) < 135 or not np.isfinite(prices).all() or np.any(prices <= 0):
        raise ValueError("Insufficient or invalid full fitting price history")
    indices = np.arange(29, len(prices) - phase1.HORIZON)
    features = np.array([phase1.feature_row(prices[: i + 1]) for i in indices])
    labels = (prices[indices + 5] - prices[indices]) / prices[indices]
    if (
        len(indices) < 100
        or not np.isfinite(features).all()
        or not np.isfinite(labels).all()
    ):
        raise ValueError("Insufficient finite full training samples")
    return features, labels, indices


def fit_asset(directory, asset, features, labels, indices, dates):
    """Fit/export one complete five-seed ensemble using the frozen policy."""
    root = Path(directory)
    split = int(len(indices) * 0.8)
    retained = np.flatnonzero(indices[:split] + 5 < indices[split])
    mean = features[retained].mean(axis=0)
    scale = features[retained].std(axis=0, ddof=0)
    # Match StandardScaler's constant-feature convention.
    scale = np.where(scale == 0, 1.0, scale)
    normalized = (features - mean) / scale
    train = xgb.DMatrix(
        normalized[retained],
        label=labels[retained],
        feature_names=phase1.FEATURES,
        nthread=1,
    )
    validation = xgb.DMatrix(
        normalized[split:],
        label=labels[split:],
        feature_names=phase1.FEATURES,
        nthread=1,
    )
    members, predictions = [], []
    for i, seed in enumerate(phase1.SEEDS):
        model = xgb.train(
            dict(
                objective="reg:squarederror",
                max_depth=4,
                learning_rate=0.05,
                seed=seed,
                subsample=0.8,
                colsample_bytree=0.7 + 0.05 * i,
                nthread=1,
                tree_method="hist",
                device="cpu",
            ),
            train,
            num_boost_round=200,
            evals=[(validation, "validation_0")],
            early_stopping_rounds=10,
            verbose_eval=False,
        )
        native = bytes(model.save_raw(raw_format="ubj"))
        name = f"{asset}-{seed}.ubj"
        with (root / name).open("xb") as stream:
            stream.write(native)
        members.append(
            dict(
                file=name,
                sha256=hashlib.sha256(native).hexdigest(),
                seed=seed,
                best_iteration=model.best_iteration,
                validation_rmse=float(model.best_score),
            )
        )
        predictions.append(
            model.predict(validation, iteration_range=(0, model.best_iteration + 1))
        )
    error = np.mean(predictions, axis=0) - labels[split:]
    denominator = np.sum((labels[split:] - labels[split:].mean()) ** 2)
    split_details = dict(
        train_rows=len(retained),
        validation_rows=len(indices) - split,
        purged_rows=split - len(retained),
        train_label_end=dates[indices[retained[-1]] + 5],
        validation_start=dates[indices[split]],
        validation_end=dates[indices[-1]],
        validation_label_end=dates[indices[-1] + 5],
        mae=float(np.abs(error).mean()),
        rmse=float(np.sqrt(np.mean(error**2))),
        r2=float(1 - np.sum(error**2) / denominator) if denominator > 0 else 0.0,
    )
    asset_details = dict(
        scaler_mean=mean.tolist(), scaler_scale=scale.tolist(), boosters=members
    )
    return asset_details, split_details, error


def train_full_candidate(directory, panel, training_cutoff: date):
    state = panel.selection_state()
    if str(training_cutoff) != state["training_cutoff"]:
        raise ValueError("Full training cutoff must match the completed fit epoch")
    end = state["fit_index"] - 5
    expected = canonical_hash(
        {
            "dates": list(map(str, panel.dates[:end])),
            "equity_ids": list(EQUITY_IDS),
            "prices_vnd": panel.prices[:end, :30].tolist(),
        }
    )
    if (
        expected != state["training_equity_hash"]
        or panel.dates[end - 1] != training_cutoff
    ):
        raise ValueError("Full training equity hash or cutoff mismatch")
    identity = str(uuid4())
    root = Path(directory) / f"phase1-{identity}"
    root.mkdir(parents=True, exist_ok=False)
    assets, splits, all_errors = {}, {}, []
    for asset in state["model_equity_ids"]:
        features, labels, indices = training_arrays(panel, asset)
        details, split_details, error = fit_asset(
            root, asset, features, labels, indices, panel.dates
        )
        assets[asset] = details
        splits[asset] = split_details
        all_errors.extend(error.tolist())
    now = utcnow()
    manifest = FullManifest(
        schema_version=4,
        model_id=identity,
        status="CANDIDATE",
        core_version="0.1.0",
        xgboost_version=xgb.__version__,
        feature_schema_version="phase1-full-features-v1",
        feature_names=phase1.FEATURES,
        asset_ids=state["model_equity_ids"],
        full_asset_ids=list(ASSET_IDS),
        active_asset_ids=state["active_asset_ids"],
        selected_equity_ids=state["selected_equity_ids"],
        **{
            key: state[key]
            for key in (
                "selection_id",
                "selection_epoch",
                "model_selection_id",
                "model_selection_epoch",
                "fit_epoch",
                "training_equity_hash",
            )
        },
        training_cutoff=training_cutoff,
        training_snapshot_id=panel.snapshot["id"],
        training_snapshot_hash=panel.snapshot["content_hash"],
        training_data_hash=training_hash(panel),
        baseline_run_id=BASELINE_RUN,
        baseline_manifest_sha256=BASELINE_MANIFEST,
        source_hashes=FROZEN_SOURCES
        | {
            "ml_platform/full_train.py": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "quant_service/phase1.py": hashlib.sha256(
                Path(phase1.__file__).read_bytes()
            ).hexdigest(),
        },
        training_knowledge_cutoff=panel.feature_known_at,
        trained_at=now,
        demo=False,
        horizon_sessions=5,
        return_unit="five_session_simple_fraction",
        assets=assets,
        validation=dict(
            method="phase1-chronological-80-20-label-purge-v1",
            point_in_time_certified=False,
            by_asset=splits,
            train_rows=sum(s["train_rows"] for s in splits.values()),
            validation_rows=sum(s["validation_rows"] for s in splits.values()),
            train_label_end=max(s["train_label_end"] for s in splits.values()),
            validation_start=min(s["validation_start"] for s in splits.values()),
            mae=float(np.abs(all_errors).mean()),
            rmse=float(np.sqrt(np.mean(np.square(all_errors)))),
        ),
    )
    reference = publish_json(root, "manifest.json", manifest.model_dump(mode="json"))
    return reference | {"file": f"phase1-{identity}/" + reference["file"]}
