import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from portfolio_contracts import Constraints, Envelope, OptimizeCommand, utcnow
from quant_service.artifacts import ArtifactCatalog
from quant_service.models import Base, Run, Outbox
from quant_service.workflow import execute


@pytest.fixture
def catalog(tmp_path):
    value = {
        "schema_version": 1,
        "bundle_id": "demo-v1",
        "universe_id": "DEMO",
        "snapshot_id": "snapshot-v1",
        "model_bundle_id": None,
        "model_status": None,
        "as_of_date": "2026-09-25",
        "valid_until": (utcnow() + timedelta(hours=1)).isoformat(),
        "demo": True,
        "strategies": ["EW", "MVO"],
        "numerical": {
            "asset_ids": ["AAA", "BBB", "VFF"],
            "mean_returns": [0.001, 0.0005, 0.0001],
            "covariance": [[0.0004, 0, 0], [0, 0.0003, 0], [0, 0, 0.00005]],
        },
    }
    data = json.dumps(value).encode()
    (tmp_path / "bundle.json").write_bytes(data)
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "bundles": [
                    {"file": "bundle.json", "sha256": hashlib.sha256(data).hexdigest()}
                ]
            }
        )
    )
    return ArtifactCatalog(tmp_path, allow_demo=True), tmp_path


def command(catalog):
    ready = catalog.ready("DEMO", "MVO")
    value = OptimizeCommand(
        job_id=uuid4(),
        owner_user_id=uuid4(),
        portfolio_id=uuid4(),
        portfolio_version=1,
        strategy="MVO",
        capital_vnd="100000000",
        inputs=ready,
        constraints=Constraints(max_position_weight=0.6),
        deadline=utcnow() + timedelta(seconds=60),
        input_hash="0" * 64,
    )
    value.input_hash = value.compute_hash()
    return value


def test_manifest_integrity_and_demo_opt_in(catalog):
    catalog, path = catalog
    assert catalog.ready("DEMO", "MVO").demo is True
    with pytest.raises(ValueError):
        ArtifactCatalog(path).ready("DEMO", "MVO")
    (path / "bundle.json").write_text("{}")
    with pytest.raises(ValueError):
        catalog.ready("DEMO", "MVO")


def test_missing_ml_model_fails_closed(catalog):
    catalog, _ = catalog
    with pytest.raises(ValueError):
        catalog.ready("DEMO", "BL_ML")


def test_path_traversal_and_expiry(catalog):
    catalog, path = catalog
    value = json.loads((path / "bundle.json").read_text())
    value["valid_until"] = "2020-01-01T00:00:00+00:00"
    data = json.dumps(value).encode()
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
    with pytest.raises(ValueError):
        catalog.ready("DEMO", "MVO")
    (path / "catalog.json").write_text(
        json.dumps({"bundles": [{"file": "../outside.json", "sha256": "a" * 64}]})
    )
    with pytest.raises(ValueError):
        catalog.ready("DEMO", "MVO")


def test_durable_numerical_result_and_duplicate_commands(catalog, tmp_path):
    catalog, _ = catalog
    engine = create_engine(f"sqlite:///{tmp_path}/quant.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    request = command(catalog)
    event = Envelope(
        type="quant.optimize.requested",
        producer="portfolio",
        correlation_id=request.job_id,
        payload=request.model_dump(mode="json"),
    )
    execute(sessions, catalog, event)
    execute(sessions, catalog, event)
    execute(sessions, catalog, event.model_copy(update={"event_id": str(uuid4())}))
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 1
        assert session.scalar(select(func.count()).select_from(Outbox)) == 1
        run = session.scalar(select(Run))
        assert run.payload["status"] == "SUCCEEDED"
        assert abs(sum(run.payload["result"]["weights"]) - 1) < 1e-7
        assert max(run.payload["result"]["weights"]) <= 0.6000001


def test_corrupt_input_hash_is_rejected_before_computing(catalog, tmp_path):
    catalog, _ = catalog
    request = command(catalog)
    request.constraints.risk_aversion = 50
    event = Envelope(
        type="quant.optimize.requested",
        producer="portfolio",
        correlation_id=request.job_id,
        payload=request.model_dump(mode="json"),
    )
    with pytest.raises(ValueError):
        execute(None, catalog, event)


def test_numerical_failure_persists_failed_event(catalog, tmp_path):
    catalog, _ = catalog
    engine = create_engine(f"sqlite:///{tmp_path}/failed.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    request = command(catalog)
    request.constraints.max_position_weight = 0.1
    request.input_hash = request.compute_hash()
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
    with sessions() as session:
        assert session.scalar(select(Run)).payload["status"] == "FAILED"
        assert session.scalar(select(Outbox)).payload["payload"]["error"]["code"]
