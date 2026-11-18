"""Offline per-equity model v5; coverage never depends on a user's candidates."""

from datetime import date
import hashlib
from pathlib import Path
from uuid import uuid4

import numpy as np
import xgboost as xgb

from portfolio_contracts import canonical_hash, utcnow
from portfolio_core.assets import ASSET_IDS, EQUITY_IDS, CATALOG_VERSION
from quant_service import phase1
from quant_service.asset_ensemble import FEATURE_SCHEMA, MODEL_FAMILY
from quant_service.ml import AssetEnsembleManifest
from quant_service.model_worker import publish_json
from . import full_train


def fit_state(panel, fit_epoch=None):
    """Pin the latest ten-session epoch from the latest completed custom session."""
    t = panel.decision_index
    if (
        isinstance(t, bool)
        or not isinstance(t, (int, np.integer))
        or not 145 <= t < len(panel.dates)
    ):
        raise ValueError(
            "Insufficient history for a completed asset ensemble fit epoch"
        )
    if (
        panel.ids != list(ASSET_IDS)
        or panel.dates[0] != phase1.START
        or panel.dates != sorted(set(panel.dates))
        or panel.prices.shape != (len(panel.dates), 32)
        or panel.valid.shape != panel.prices.shape
        or panel.valid.dtype != np.bool_
    ):
        raise ValueError(
            "Invalid asset ensemble panel identity, calendar, or validity mask"
        )
    f = 145 + ((int(t) - 145) // 10) * 10
    if fit_epoch is not None and str(fit_epoch) != str(panel.dates[f]):
        raise ValueError(
            "Asset ensemble fit epoch conflicts with observed-session schedule"
        )
    end = f - 5
    prices = panel.prices[:end, :30]
    valid = panel.valid[:end, :30]
    normalized = np.where(valid & np.isfinite(prices), prices, 0.0)
    equity_hash = canonical_hash(
        dict(
            equity_ids=list(EQUITY_IDS),
            dates=list(map(str, panel.dates[:end])),
            prices_vnd=normalized.tolist(),
            valid=valid.tolist(),
        )
    )
    snapshot = panel.snapshot
    data_hash = canonical_hash(
        dict(
            model_family=MODEL_FAMILY,
            training_equity_hash=equity_hash,
            fit_epoch=str(panel.dates[f]),
            snapshot_id=snapshot["id"],
            snapshot_hash=snapshot["content_hash"],
        )
    )
    return dict(
        fit_index=f,
        fit_epoch=panel.dates[f],
        training_cutoff=panel.dates[f - 6],
        training_equity_hash=equity_hash,
        training_data_hash=data_hash,
    )


def train_asset_candidate(directory, equity_panel, fit_epoch: date):
    panel = equity_panel
    state = fit_state(panel, fit_epoch)
    end = state["fit_index"] - 5
    omitted = {}
    covered = []
    for j, asset in enumerate(EQUITY_IDS):
        prices = panel.prices[:end, j]
        if not panel.valid[:end, j].all():
            omitted[asset] = "ASSET_DATA_MISSING"
        elif not np.isfinite(prices).all() or np.any(prices <= 0):
            omitted[asset] = "INPUT_INVALID"
        elif len(prices) < 135:
            omitted[asset] = "HISTORY_INSUFFICIENT"
        else:
            covered.append(asset)
    if not covered:
        raise ValueError("No complete equity history for an asset ensemble")
    identity = str(uuid4())
    root = Path(directory) / f"phase1-{identity}"
    root.mkdir(parents=True, exist_ok=False)
    source_hashes = full_train.FROZEN_SOURCES | {
        "ml_platform/selected_train.py": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "ml_platform/full_train.py": hashlib.sha256(
            Path(full_train.__file__).read_bytes()
        ).hexdigest(),
        "quant_service/phase1.py": hashlib.sha256(
            Path(phase1.__file__).read_bytes()
        ).hexdigest(),
    }
    assets, splits, errors = {}, {}, []
    for asset in covered:
        column = panel.prices[:end, panel.ids.index(asset)]
        features, labels, indices = full_train.feature_arrays(column)
        details, split, error = full_train.fit_asset(
            root, asset, features, labels, indices, panel.dates
        )
        assets[asset] = details | dict(
            training_cutoff=state["training_cutoff"],
            training_data_hash=canonical_hash(
                dict(
                    asset_id=asset,
                    dates=list(map(str, panel.dates[:end])),
                    prices_vnd=column.tolist(),
                )
            ),
            source_hashes=source_hashes,
        )
        splits[asset] = split
        errors.extend(error.tolist())
    manifest = AssetEnsembleManifest(
        schema_version=5,
        model_id=identity,
        status="CANDIDATE",
        model_family=MODEL_FAMILY,
        core_version="0.1.0",
        xgboost_version=xgb.__version__,
        catalog_version=CATALOG_VERSION,
        catalog_asset_ids=list(ASSET_IDS),
        feature_schema_version=FEATURE_SCHEMA,
        feature_names=phase1.FEATURES,
        asset_ids=covered,
        covered_asset_ids=covered,
        omitted_assets=omitted,
        **{
            k: state[k]
            for k in (
                "fit_epoch",
                "training_cutoff",
                "training_equity_hash",
                "training_data_hash",
            )
        },
        training_snapshot_id=panel.snapshot["id"],
        training_snapshot_hash=panel.snapshot["content_hash"],
        baseline_run_id=full_train.BASELINE_RUN,
        baseline_manifest_sha256=full_train.BASELINE_MANIFEST,
        source_hashes=source_hashes,
        training_knowledge_cutoff=panel.feature_known_at,
        trained_at=utcnow(),
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
            mae=float(np.abs(errors).mean()),
            rmse=float(np.sqrt(np.mean(np.square(errors)))),
        ),
    )
    ref = publish_json(root, "manifest.json", manifest.model_dump(mode="json"))
    return ref | {"file": f"phase1-{identity}/" + ref["file"]}
