"""Native XGBoost inference and allocator parity on a pinned synthetic feature batch."""

import copy
import hashlib
import json
from datetime import date, timedelta

import numpy as np
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from portfolio_contracts import Envelope, OptimizeCommand, utcnow
from portfolio_core import allocate
from quant_service.artifacts import ArtifactCatalog
from quant_service.models import Base, Run
from quant_service.workflow import execute
from test_quant import command


def dataset():
    start = date.today() - timedelta(days=60)
    return {
        "schema_version": 1,
        "horizon_sessions": 1,
        "return_unit": "daily_simple_fraction",
        "asset_ids": ["AAA", "BBB", "VFF"],
        "feature_names": ["momentum", "volatility"],
        "feature_schema_version": "synthetic-features-v1",
        "snapshot_id": "training-synthetic-v1",
        "demo": True,
        "training_cutoff": (start + timedelta(days=30)).isoformat(),
        "features": [[i / 100, (i % 3 + 1) / 100] for i in range(24)],
        "targets": [i / 10000 for i in range(24)],
        "feature_dates": [(start + timedelta(days=i)).isoformat() for i in range(24)],
        "label_available_dates": [
            (start + timedelta(days=i + 1)).isoformat() for i in range(24)
        ],
    }


@pytest.fixture
def ml_catalog(tmp_path):
    from quant_service.model_worker import train_candidate, approve_candidate

    candidate = train_candidate(tmp_path, dataset())
    approved = approve_candidate(tmp_path, candidate, reviewer="local-test-reviewer")
    inference = {
        "manifest": approved,
        "feature_schema_version": "synthetic-features-v1",
        "feature_names": ["momentum", "volatility"],
        "asset_ids": ["AAA", "BBB", "VFF"],
        "feature_date": utcnow().date().isoformat(),
        "rows": [[0.02, 0.01], [0.03, 0.02], [0.01, 0.03]],
    }
    value = {
        "schema_version": 1,
        "bundle_id": "inference-v1",
        "universe_id": "DEMO",
        "snapshot_id": "synthetic-inference",
        "model_bundle_id": approved["sha256"],
        "as_of_date": utcnow().date().isoformat(),
        "valid_until": (utcnow() + timedelta(hours=1)).isoformat(),
        "demo": True,
        "strategies": ["EW", "MVO", "BL_ML"],
        "ml_inference": inference,
        "numerical": {
            "asset_ids": ["AAA", "BBB", "VFF"],
            "mean_returns": [0.001, 0.0005, 0.0001],
            "covariance": [[0.0004, 0, 0], [0, 0.0003, 0], [0, 0, 0.00005]],
            "market_weights": [1 / 3] * 3,
        },
    }
    write_bundle(tmp_path, value)
    return ArtifactCatalog(tmp_path, allow_demo=True), tmp_path, value, candidate


def write_bundle(path, value):
    data = json.dumps(value, allow_nan=False).encode()
    (path / "bundle.json").write_bytes(data)
    (path / "catalog.json").write_text(
        json.dumps(
            {
                "bundles": [
                    {"file": "bundle.json", "sha256": hashlib.sha256(data).hexdigest()}
                ]
            }
        )
    )


def test_trained_approved_model_inference_and_one_step_parity(ml_catalog):
    import xgboost as xgb

    catalog, path, value, _ = ml_catalog
    ready = catalog.ready("DEMO", "BL_ML")
    numerical = catalog.load(ready, "BL_ML")
    manifest = json.loads(
        (path / value["ml_inference"]["manifest"]["file"]).read_text()
    )
    booster = xgb.Booster()
    booster.load_model(path / manifest["model"]["file"])
    rows = (
        np.array(value["ml_inference"]["rows"]) - manifest["scaler_mean"]
    ) / manifest["scaler_scale"]
    predicted = booster.predict(
        xgb.DMatrix(rows, feature_names=value["ml_inference"]["feature_names"])
    )
    assert numerical["views_q"] == pytest.approx(predicted.tolist())
    assert numerical["views_p"] == np.eye(3).tolist()
    c = command(catalog).model_dump(mode="json")
    c.update(strategy="BL_ML", inputs=ready.model_dump(mode="json"))
    request = OptimizeCommand.model_validate(c)
    request.input_hash = request.compute_hash()
    engine = create_engine(f"sqlite:///{path}/quant.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    execute(
        sessions,
        catalog,
        Envelope(
            type="quant.optimize.requested",
            producer="portfolio",
            correlation_id=request.job_id,
            payload=request.model_dump(mode="json"),
        ),
    )
    expected = allocate(
        {k: v for k, v in numerical.items() if k != "inference_provenance"}
        | {"strategy": "BL_ML", "constraints": request.constraints.model_dump()}
    )
    with sessions() as session:
        result = session.scalar(select(Run)).payload
        assert result["status"] == "SUCCEEDED", result
        assert result["result"]["weights"] == pytest.approx(
            expected["weights"], abs=1e-10
        )
        assert (
            result["result"]["diagnostics"]["inference"]["model_manifest_hash"]
            == ready.model_bundle_id
        )
        assert result["result"]["diagnostics"]["inference"]["feature_batch_hash"]


@pytest.mark.parametrize(
    "mutation",
    [
        "candidate",
        "feature_order",
        "asset_order",
        "future_feature",
        "before_cutoff",
        "model_identity",
        "checksum",
        "nan",
        "path",
    ],
)
def test_invalid_or_unapproved_model_batch_is_never_ready(ml_catalog, mutation):
    catalog, path, original, candidate = ml_catalog
    value = copy.deepcopy(original)
    batch = value["ml_inference"]
    if mutation == "candidate":
        batch["manifest"] = candidate
        value["model_bundle_id"] = candidate["sha256"]
    if mutation == "feature_order":
        batch["feature_names"].reverse()
    if mutation == "asset_order":
        batch["asset_ids"].reverse()
    if mutation == "future_feature":
        batch["feature_date"] = (date.today() + timedelta(days=1)).isoformat()
    if mutation == "before_cutoff":
        batch["feature_date"] = "2000-01-01"
    if mutation == "model_identity":
        value["model_bundle_id"] = "b" * 64
    if mutation == "checksum":
        batch["manifest"]["sha256"] = "b" * 64
    if mutation == "nan":
        batch["rows"][0][0] = "NaN"
    if mutation == "path":
        batch["manifest"]["file"] = "../outside.json"
    write_bundle(path, value)
    with pytest.raises(ValueError):
        catalog.ready("DEMO", "BL_ML")


def test_native_model_tampering_is_detected_on_pinned_load(ml_catalog):
    catalog, path, value, _ = ml_catalog
    ready = catalog.ready("DEMO", "BL_ML")
    manifest = json.loads(
        (path / value["ml_inference"]["manifest"]["file"]).read_text()
    )
    (path / manifest["model"]["file"]).write_text("tampered")
    with pytest.raises(ValueError):
        catalog.load(ready, "BL_ML")


def test_training_rejects_labels_unavailable_at_cutoff_and_keeps_candidate_immutable(
    tmp_path,
):
    from quant_service.model_worker import train_candidate, approve_candidate

    value = dataset()
    value["label_available_dates"][-1] = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        train_candidate(tmp_path, value)
    candidate = train_candidate(tmp_path, dataset())
    before = (tmp_path / candidate["file"]).read_bytes()
    with pytest.raises(ValueError):
        approve_candidate(tmp_path, candidate, reviewer=" ")
    approved = approve_candidate(tmp_path, candidate, reviewer="reviewer")
    assert approved != candidate
    assert (tmp_path / candidate["file"]).read_bytes() == before
    manifest = json.loads((tmp_path / approved["file"]).read_text())
    assert manifest["status"] == "APPROVED"
    assert (
        manifest["validation"]["train_label_end"]
        < manifest["validation"]["validation_start"]
    )


@pytest.mark.parametrize(
    "field,value", [("horizon_sessions", 5), ("return_unit", "annual_percent")]
)
def test_training_never_labels_incompatible_targets_as_daily(tmp_path, field, value):
    from quant_service.model_worker import train_candidate

    assert train_candidate(tmp_path, dataset())["sha256"]
    raw = dataset()
    raw[field] = value
    with pytest.raises(ValueError):
        train_candidate(tmp_path, raw)
