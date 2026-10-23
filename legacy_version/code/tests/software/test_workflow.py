import copy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from service_auth import Principal
from portfolio_service.api import create_app
from portfolio_service.models import Base, Job, Outbox, Recommendation
from portfolio_service.workflow import consume_result
from portfolio_contracts import OptimizeResult, Envelope


class Verifier:
    def verify(self, token):
        return Principal(
            "https://identity",
            token,
            frozenset({"system-admin" if token == "admin" else "investor"}),
            frozenset({"portfolio:read", "portfolio:write"}),
        )


class Resolver:
    def ready(self, universe_id, strategy):
        return {
            "bundle_id": "fixture-v1",
            "bundle_hash": "a" * 64,
            "snapshot_id": "snapshot-v1",
            "model_bundle_id": None,
            "asset_ids": ["AAA", "BBB", "VFF"],
            "as_of_date": "2026-09-25",
            "valid_until": (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat(),
            "demo": True,
        }


@pytest.fixture
def stack(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path}/portfolio.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    app = create_app(sessions=sessions, verifier=Verifier(), resolver=Resolver())
    with TestClient(app) as client:
        yield client, sessions


def headers(user="alice", **extra):
    return {"Authorization": f"Bearer {user}", **extra}


def portfolio(client):
    response = client.post(
        "/api/v1/portfolios",
        headers=headers(),
        json={
            "name": "Thử nghiệm",
            "capital_vnd": "100000000",
            "universe_id": "DEMO",
            "risk_aversion": 1.5,
            "max_position_weight": 0.6,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def enqueue(client, pid, key="test-key", body=None):
    return client.post(
        f"/api/v1/portfolios/{pid}/recommendations",
        headers=headers(**{"Idempotency-Key": key}),
        json=body or {"strategy": "MVO"},
    )


def test_authentication_required(stack):
    client, _ = stack
    assert client.get("/api/v1/portfolios").status_code == 401


def test_owner_checks_include_admin_and_forged_owner(stack):
    client, _ = stack
    pid = portfolio(client)
    for other in ("bob", "admin"):
        assert (
            client.get(f"/api/v1/portfolios/{pid}", headers=headers(other)).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/portfolios/{pid}/recommendations",
                headers=headers(other, **{"Idempotency-Key": "attack"}),
                json={"strategy": "MVO"},
            ).status_code
            == 404
        )
        assert client.get("/api/v1/portfolios", headers=headers(other)).json() == []
    assert (
        client.post(
            "/api/v1/portfolios",
            headers=headers(),
            json={"name": "Fake", "capital_vnd": "10", "owner_user_id": "bob"},
        ).status_code
        == 422
    )


def test_idempotency_transaction_and_conflict(stack):
    client, sessions = stack
    pid = portfolio(client)
    first = enqueue(client, pid)
    assert first.status_code == 202, first.text
    assert enqueue(client, pid).json() == first.json()
    assert enqueue(client, pid, body={"strategy": "EW"}).status_code == 409
    assert (
        client.post(
            f"/api/v1/portfolios/{pid}/recommendations",
            headers=headers(),
            json={"strategy": "MVO"},
        ).status_code
        == 400
    )
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert session.scalar(select(func.count()).select_from(Outbox)) == 1


def test_outbox_keeps_same_event_when_publish_confirmation_is_lost(stack, monkeypatch):
    from portfolio_service import worker

    client, sessions = stack
    pid = portfolio(client)
    job_id = enqueue(client, pid).json()["job_id"]
    delivered = []

    def uncertain_publish(connection, owner, event):
        delivered.append(event["event_id"])
        raise ConnectionError("Broker acknowledgement lost after delivery")

    monkeypatch.setattr(worker, "publish", uncertain_publish)
    with pytest.raises(ConnectionError):
        worker.dispatch_once(sessions, None)
    with sessions() as session:
        assert session.scalar(select(Outbox)).published_at is None
        assert session.get(Job, job_id).status == "QUEUED"

    def confirmed_publish(connection, owner, event):
        delivered.append(event["event_id"])

    monkeypatch.setattr(worker, "publish", confirmed_publish)
    worker.dispatch_once(sessions, None)
    worker.dispatch_once(sessions, None)
    assert len(delivered) == 2 and delivered[0] == delivered[1]
    with sessions() as session:
        assert session.scalar(select(Outbox)).published_at is not None


def test_job_deadline_transitions_to_failure_on_owner_read(stack):
    client, sessions = stack
    pid = portfolio(client)
    job_id = enqueue(client, pid).json()["job_id"]
    with sessions.begin() as session:
        session.get(Job, job_id).deadline = datetime.now(timezone.utc) - timedelta(
            seconds=1
        )
    state = client.get(f"/api/v1/jobs/portfolio/{job_id}", headers=headers()).json()
    assert state["status"] == "FAILED"
    assert state["error"]["code"] == "DEADLINE_EXCEEDED"


def test_result_persistence_duplicate_and_owner_scoped_reads(stack):
    client, sessions = stack
    pid = portfolio(client)
    job_id = enqueue(client, pid).json()["job_id"]
    with sessions() as session:
        job = session.get(Job, job_id)
        result = OptimizeResult(
            job_id=job_id,
            input_hash=job.input_hash,
            run_id=str(uuid4()),
            bundle_hash="a" * 64,
            status="SUCCEEDED",
            result={
                "strategy": "MVO",
                "asset_ids": ["AAA", "BBB", "VFF"],
                "weights": [0.4, 0.3, 0.3],
                "status": "optimal",
                "core_version": "0.1.0",
                "diagnostics": {},
            },
        )
    event = Envelope(
        type="quant.optimization.completed",
        producer="quant-serving",
        correlation_id=job_id,
        payload=result.model_dump(mode="json"),
    )
    consume_result(sessions, event)
    consume_result(sessions, event)
    consume_result(sessions, event.model_copy(update={"event_id": str(uuid4())}))
    state = client.get(f"/api/v1/jobs/portfolio/{job_id}", headers=headers()).json()
    assert state["status"] == "SUCCEEDED"
    recommendation = client.get(
        f"/api/v1/recommendations/{state['recommendation_id']}", headers=headers()
    ).json()
    assert recommendation["weights"] == ["0.4", "0.3", "0.3"]
    assert recommendation["data_snapshot_id"] == "snapshot-v1"
    assert recommendation["demo"] is True
    for path in (
        f"/api/v1/jobs/portfolio/{job_id}",
        f"/api/v1/recommendations/{state['recommendation_id']}",
    ):
        assert client.get(path, headers=headers("bob")).status_code == 404
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 1


def test_rejects_mismatched_result_and_invalid_weights(stack):
    client, sessions = stack
    pid = portfolio(client)
    job_id = enqueue(client, pid).json()["job_id"]
    with sessions() as session:
        job = session.get(Job, job_id)
        data = {
            "job_id": job_id,
            "input_hash": job.input_hash,
            "run_id": str(uuid4()),
            "bundle_hash": "a" * 64,
            "status": "SUCCEEDED",
            "result": {
                "strategy": "MVO",
                "asset_ids": ["AAA", "BBB", "VFF"],
                "weights": [0.9, 0.1, 0.0],
                "core_version": "0.1.0",
                "status": "optimal",
                "diagnostics": {},
            },
        }
    wrong = copy.deepcopy(data)
    wrong["input_hash"] = "b" * 64
    with pytest.raises(ValueError):
        consume_result(
            sessions,
            Envelope(
                type="quant.optimization.completed",
                producer="quant-serving",
                correlation_id=job_id,
                payload=wrong,
            ),
        )
    consume_result(
        sessions,
        Envelope(
            type="quant.optimization.completed",
            producer="quant-serving",
            correlation_id=job_id,
            payload=data,
        ),
    )
    assert (
        client.get(f"/api/v1/jobs/portfolio/{job_id}", headers=headers()).json()[
            "status"
        ]
        == "FAILED"
    )


def test_public_cannot_inject_optimizer_or_model_inputs(stack):
    client, _ = stack
    pid = portfolio(client)
    assert (
        enqueue(
            client,
            pid,
            body={
                "strategy": "MVO",
                "covariance": [[1]],
                "model_bundle_id": "attacker",
            },
        ).status_code
        == 422
    )
    assert enqueue(client, pid, body={"strategy": "UNSUPPORTED"}).status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("strategy", "EW"),
        ("status", "infeasible"),
        ("core_version", "99.0.0"),
        ("diagnostics", {"objective": float("nan")}),
    ],
)
def test_contradictory_quant_result_fails_without_persisting(stack, field, value):
    client, sessions = stack
    pid = portfolio(client)
    job_id = enqueue(client, pid).json()["job_id"]
    result = {
        "asset_ids": ["AAA", "BBB", "VFF"],
        "weights": [0.4, 0.3, 0.3],
        "strategy": "MVO",
        "status": "optimal",
        "core_version": "0.1.0",
        "diagnostics": {},
        field: value,
    }
    with sessions() as session:
        job = session.get(Job, job_id)
        payload = OptimizeResult(
            job_id=job_id,
            input_hash=job.input_hash,
            run_id=uuid4(),
            bundle_hash="a" * 64,
            status="SUCCEEDED",
            result=result,
        )
    consume_result(
        sessions,
        Envelope(
            type="quant.optimization.completed",
            producer="quant-serving",
            correlation_id=job_id,
            payload=payload.model_dump(),
        ),
    )
    job = client.get(f"/api/v1/jobs/portfolio/{job_id}", headers=headers()).json()
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "INVALID_QUANT_RESULT"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 0


def test_recommendation_history_and_versioned_portfolio_update(stack):
    client, _ = stack
    pid = portfolio(client)
    assert (
        client.get(
            f"/api/v1/portfolios/{pid}/recommendations", headers=headers()
        ).json()
        == []
    )
    assert (
        client.get(
            f"/api/v1/portfolios/{pid}/recommendations", headers=headers("bob")
        ).status_code
        == 404
    )
    response = client.patch(
        f"/api/v1/portfolios/{pid}", headers=headers(), json={"name": "Updated"}
    )
    assert response.status_code == 428
    response = client.patch(
        f"/api/v1/portfolios/{pid}",
        headers=headers(**{"If-Match": '"1"'}),
        json={"max_position_weight": 0.4},
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert response.json()["constraints"]["max_position_weight"] == 0.4
    assert response.headers["etag"] == '"2"'
    assert (
        client.patch(
            f"/api/v1/portfolios/{pid}",
            headers=headers(**{"If-Match": '"1"'}),
            json={"name": "Stale"},
        ).status_code
        == 412
    )
    assert (
        client.patch(
            f"/api/v1/portfolios/{pid}",
            headers=headers("bob", **{"If-Match": '"2"'}),
            json={"name": "Attack"},
        ).status_code
        == 404
    )
