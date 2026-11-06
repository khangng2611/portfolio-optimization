"""ML-owned durable training, explicit review, and trusted artifact resolution."""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "services/ml-platform/src")
)
from datetime import timedelta
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from portfolio_contracts import utcnow
from service_auth import Principal, AuthError
from test_snapshot_inputs import snapshot_fixture
from ml_platform.main import create_app
from ml_platform.models import Base, TrainingJob, Model, Review
from ml_platform.worker import TrainingQueue, process_one, materialize_approvals

PATH = "/api/v1/ml"


class Identities:
    def verify(self, token):
        if token == "invalid":
            raise AuthError()
        roles, scopes = {"data-operator"}, {"ml:read", "ml:train"}
        if token == "reviewer":
            roles, scopes = {"model-reviewer"}, {"ml:read", "ml:review"}
        if token == "reader":
            roles, scopes = set(), {"ml:model:read"}
        if token == "investor":
            roles, scopes = {"investor"}, {"ml:read"}
        return Principal("issuer", token, frozenset(roles), frozenset(scopes))


def headers(who="operator", key="training-1", version=None):
    result = {"Authorization": "Bearer " + who, "Idempotency-Key": key}
    if version:
        result["If-Match"] = f'"{version}"'
    return result


@pytest.fixture
def ml(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/ml.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    directory = tmp_path / "models"
    client = TestClient(
        create_app(sessions=sessions, verifier=Identities(), directory=directory)
    )
    snapshot, rows, now = snapshot_fixture()
    pins = {
        "snapshot_id": snapshot["id"],
        "snapshot_hash": snapshot["content_hash"],
        "training_cutoff": (now.date() - timedelta(days=20)).isoformat(),
    }

    class Reader:
        def load(self, identity, digest):
            assert identity == pins["snapshot_id"] and digest == pins["snapshot_hash"]
            return snapshot, rows

    return client, sessions, directory, pins, Reader(), now


def candidate(ml):
    client, sessions, directory, pins, reader, now = ml
    job = client.post(PATH + "/training-jobs", json=pins, headers=headers()).json()
    assert process_one(TrainingQueue(sessions), directory, reader, now=utcnow())
    job = client.get(job["status_url"], headers=headers()).json()
    assert job["status"] == "SUCCEEDED", job
    return client.get(
        PATH + "/models/" + job["result"]["model_id"], headers=headers()
    ).json()


def test_enqueue_is_durable_idempotent_bounded_and_never_trains(ml):
    client, sessions, directory, pins, *_ = ml
    response = client.post(PATH + "/training-jobs", json=pins, headers=headers())
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "QUEUED" and job["attempts"] == 0 and not directory.exists()
    assert (
        client.post(PATH + "/training-jobs", json=pins, headers=headers()).json() == job
    )
    assert (
        client.post(
            PATH + "/training-jobs",
            json=pins | {"snapshot_hash": "0" * 64},
            headers=headers(),
        ).status_code
        == 409
    )
    assert client.get(job["status_url"], headers=headers("other")).status_code == 404
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(TrainingJob)) == 1
    for body in [
        pins | {"directory": "/private"},
        pins | {"lookback": 10},
        pins | {"min_returns": True},
        pins | {"training_cutoff": "2099-01-01"},
    ]:
        assert (
            client.post(
                PATH + "/training-jobs", json=body, headers=headers(key=str(uuid4()))
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "who,expected",
    [("invalid", 401), ("investor", 403), ("reviewer", 403), ("reader", 403)],
)
def test_training_role_scope_gate(ml, who, expected):
    client, _, _, pins, *_ = ml
    assert (
        client.post(
            PATH + "/training-jobs", json=pins, headers=headers(who)
        ).status_code
        == expected
    )


def test_training_candidate_has_real_provenance_and_requires_explicit_review(ml):
    client, sessions, directory, *_ = ml
    model = candidate(ml)
    assert (
        model["status"] == "CANDIDATE"
        and model["version"] == 1
        and not model["artifact_ready"]
    )
    assert (
        model["metadata"]["validation"]["method"]
        == "chronological-80-20-label-embargo-v1"
    )
    assert model["metadata"]["validation"]["rmse"] >= 0
    assert (
        model["metadata"]["validation"]["train_label_end"]
        < model["metadata"]["validation"]["validation_start"]
    )
    assert len(model["provenance"]["feature_schema_hash"]) == 64
    assert "file" not in str(model)
    uri = "/internal/v1/ml/models/" + model["model_id"] + "/manifest"
    assert client.get(uri, headers=headers("reader")).status_code == 409
    response = client.get(PATH + "/models?limit=1", headers=headers("reviewer"))
    assert (
        response.headers["X-Total-Count"] == "1"
        and response.json()[0]["model_id"] == model["model_id"]
    )


def test_review_is_immutable_idempotent_audited_and_worker_materialized(ml):
    client, sessions, directory, *_ = ml
    model = candidate(ml)
    uri = PATH + "/models/" + model["model_id"] + "/reviews"
    body = {"decision": "APPROVED", "reason": "Chronological validation inspected"}
    assert client.post(uri, json=body, headers=headers()).status_code == 403
    assert client.post(uri, json=body, headers=headers("reviewer")).status_code == 428
    response = client.post(uri, json=body, headers=headers("reviewer", version=1))
    assert response.status_code == 200, response.text
    approved = response.json()
    assert (
        approved["status"] == "APPROVED"
        and approved["version"] == 2
        and len(approved["reviews"]) == 1
    )
    assert (
        client.post(uri, json=body, headers=headers("reviewer", version=1)).json()
        == approved
    )
    assert (
        client.post(
            uri,
            json=body | {"decision": "REJECTED"},
            headers=headers("reviewer", version=1),
        ).status_code
        == 409
    )
    assert (
        client.post(
            uri, json=body, headers=headers("reviewer", key="second", version=1)
        ).status_code
        == 409
    )
    assert materialize_approvals(sessions, directory) == 1
    result = client.get(
        "/internal/v1/ml/models/" + model["model_id"] + "/manifest",
        headers=headers("reader"),
    )
    assert result.status_code == 200, result.text
    assert result.json()["manifest"]["file"].startswith("ml-models/")
    assert materialize_approvals(sessions, directory) == 0
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Review)) == 1


def test_tampered_candidate_cannot_be_approved(ml):
    client, sessions, directory, *_ = ml
    model = candidate(ml)
    with sessions() as db:
        ref = db.get(Model, model["model_id"]).candidate_ref
    (directory / ref["file"]).write_text("{}")
    result = client.post(
        PATH + "/models/" + model["model_id"] + "/reviews",
        json={"decision": "APPROVED", "reason": "Review"},
        headers=headers("reviewer", version=1),
    )
    assert result.status_code == 409
    assert (
        client.get(PATH + "/models/" + model["model_id"], headers=headers()).json()[
            "status"
        ]
        == "CANDIDATE"
    )


def test_failed_market_io_retries_and_expired_lease_is_fenced(ml):
    _, sessions, directory, pins, _, now = ml
    queue = TrainingQueue(sessions)
    job = queue.enqueue("retry", pins, now=now, max_attempts=2)

    class Offline:
        def load(self, *args):
            raise httpx.ConnectError("secret private token")

    process_one(queue, directory, Offline(), now=now)
    retry = queue.get(job.id)
    assert retry.status == "RETRY" and retry.safe_error == "MARKET_UNAVAILABLE"
    assert queue.claim(now=now) is None
    old = queue.claim(now=now + timedelta(seconds=31), lease_seconds=1)
    assert old.attempts == 2
    assert queue.claim(now=now + timedelta(seconds=33)) is None
    assert queue.get(job.id).status == "FAILED"
    assert not queue.fail(
        old, "TRAINING_INVALID", now=now + timedelta(seconds=33), permanent=True
    )


def test_approved_model_manifest_serves_from_readonly_quant_subdirectory(ml):
    from quant_service.snapshot_publisher import publish_snapshot
    from quant_service.artifacts import ArtifactCatalog

    client, sessions, directory, pins, reader, _ = ml
    model = candidate(ml)
    client.post(
        PATH + "/models/" + model["model_id"] + "/reviews",
        json={"decision": "APPROVED", "reason": "Validation reviewed"},
        headers=headers("reviewer", version=1),
    )
    materialize_approvals(sessions, directory)
    # Reproduce the production sibling mount /bundles/ml-models.
    (directory.parent / "ml-models").symlink_to(directory, target_is_directory=True)
    ref = client.get(
        "/internal/v1/ml/models/" + model["model_id"] + "/manifest",
        headers=headers("reader"),
    ).json()["manifest"]
    snapshot, rows = reader.load(pins["snapshot_id"], pins["snapshot_hash"])
    published = publish_snapshot(
        directory.parent,
        snapshot,
        rows,
        expected_hash=pins["snapshot_hash"],
        universe_id="REAL",
        model=ref,
    )
    assert (
        ArtifactCatalog(directory.parent).ready("REAL", "BL_ML").bundle_id
        == published["bundle_id"]
    )


def test_rejected_model_never_becomes_resolvable_or_reversible(ml):
    client, sessions, directory, *_ = ml
    model = candidate(ml)
    uri = PATH + "/models/" + model["model_id"] + "/reviews"
    result = client.post(
        uri,
        json={"decision": "REJECTED", "reason": "Insufficient validation evidence"},
        headers=headers("reviewer", version=1),
    )
    assert result.status_code == 200 and result.json()["status"] == "REJECTED"
    assert materialize_approvals(sessions, directory) == 0
    assert (
        client.get(
            "/internal/v1/ml/models/" + model["model_id"] + "/manifest",
            headers=headers("reader"),
        ).status_code
        == 409
    )
    assert (
        client.post(
            uri,
            json={"decision": "APPROVED", "reason": "Changed mind"},
            headers=headers("reviewer", key="again", version=2),
        ).status_code
        == 409
    )


@pytest.mark.parametrize("attempt_bound", [1, 2])
def test_final_attempt_recovers_completed_artifact_receipt_without_market_io(
    ml, attempt_bound
):
    from sqlalchemy import delete, update

    client, sessions, directory, pins, reader, now = ml
    model = candidate(ml)
    # Reproduce crash after immutable artifact publication and before DB commit.
    with sessions() as session:
        session.execute(delete(Model).where(Model.id == model["model_id"]))
        session.execute(
            update(TrainingJob)
            .where(TrainingJob.id == model["training_job_id"])
            .values(
                status="RUNNING",
                result=None,
                max_attempts=attempt_bound,
                attempts=1,
                lease_until=now - timedelta(seconds=1),
            )
        )
        session.commit()

    class Offline:
        def load(self, *args):
            raise AssertionError("Recovery must use completed immutable receipt")

    process_one(TrainingQueue(sessions), directory, Offline(), now=utcnow())
    with sessions() as session:
        job = session.get(TrainingJob, model["training_job_id"])
        assert job.status == "SUCCEEDED"
        assert job.result == {"model_id": model["model_id"]}
        assert session.get(Model, model["model_id"]).status == "CANDIDATE"


def test_ml_migration_matches_owned_metadata(tmp_path, monkeypatch):
    from alembic.config import Config
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    database = "sqlite:///" + str(tmp_path / "migrated.db")
    monkeypatch.setenv("DATABASE_URL", database)
    config = Config(
        str(Path(__file__).resolve().parents[2] / "services/ml-platform/alembic.ini")
    )
    command.upgrade(config, "head")
    with create_engine(database).connect() as connection:
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
    command.downgrade(config, "base")


def test_corrupt_approved_candidate_does_not_block_other_models(ml):
    client, sessions, directory, pins, reader, _ = ml
    first = candidate(ml)
    second_job = client.post(
        PATH + "/training-jobs", json=pins, headers=headers(key="second-training")
    ).json()
    process_one(TrainingQueue(sessions), directory, reader, now=utcnow())
    second = client.get(second_job["status_url"], headers=headers()).json()["result"][
        "model_id"
    ]
    for identity in (first["model_id"], second):
        assert (
            client.post(
                PATH + "/models/" + identity + "/reviews",
                json={"decision": "APPROVED", "reason": "Validation reviewed"},
                headers=headers("reviewer", key=identity, version=1),
            ).status_code
            == 200
        )
    with sessions() as session:
        ref = session.get(Model, first["model_id"]).candidate_ref
    (directory / ref["file"]).write_text("{}")
    assert materialize_approvals(sessions, directory) == 1
    assert (
        client.get(
            "/internal/v1/ml/models/" + second + "/manifest", headers=headers("reader")
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/internal/v1/ml/models/" + first["model_id"] + "/manifest",
            headers=headers("reader"),
        ).status_code
        == 409
    )


def test_reviewer_cannot_approve_model_from_incompatible_runtime(ml):
    import json
    import hashlib

    client, sessions, directory, *_ = ml
    model = candidate(ml)
    with sessions() as session:
        row = session.get(Model, model["model_id"])
        path = directory / row.candidate_ref["file"]
        value = json.loads(path.read_text())
        value["xgboost_version"] = "0.0.0"
        data = json.dumps(value, sort_keys=True).encode()
        path.write_bytes(data)
        row.candidate_ref = row.candidate_ref | {
            "sha256": hashlib.sha256(data).hexdigest()
        }
        session.commit()
    result = client.post(
        PATH + "/models/" + model["model_id"] + "/reviews",
        json={"decision": "APPROVED", "reason": "Inspect"},
        headers=headers("reviewer", version=1),
    )
    assert result.status_code == 409
