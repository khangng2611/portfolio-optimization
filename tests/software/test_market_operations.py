"""Operator source registry, quarantine, and immutable publication boundaries."""

import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from test_market import headers, snapshot_body, submit
from test_market import market as market_fixture

market = market_fixture


def configure(market, content, **spec_changes):
    _, _, _, directory = market
    (directory / "stock.csv").write_text(content)
    catalog = json.loads((directory / "catalog.json").read_text())
    catalog["DEMO_STOCK"].update(
        sha256=hashlib.sha256(content.encode()).hexdigest(), **spec_changes
    )
    (directory / "catalog.json").write_text(json.dumps(catalog))
    return catalog["DEMO_STOCK"]["sha256"]


def register(market, sha=None, key="register-one", who="operator"):
    client, _, provider, _ = market
    return client.post(
        "/api/v1/market/datasets",
        json={
            "dataset_id": "DEMO_STOCK",
            "expected_sha256": sha or provider.spec("DEMO_STOCK")["sha256"],
        },
        headers=headers(who, key),
    )


def test_registry_pins_server_spec_and_replays_idempotently(market):
    client, sessions, _, directory = market
    inventory = client.get("/api/v1/market/dataset-inventory", headers=headers())
    assert inventory.status_code == 200
    assert inventory.json()[0]["dataset_id"] == "DEMO_STOCK"
    assert "path" not in inventory.text
    assert register(market, "0" * 64).status_code == 409
    first = register(market)
    assert first.status_code == 201, first.text
    assert register(market).json() == first.json()
    assert first.json()["start_date"] == snapshot_body()["start_date"]
    assert first.json()["calendar"] == "observed-sessions-only"
    catalog = json.loads((directory / "catalog.json").read_text())
    catalog["DEMO_STOCK"]["price_basis"] = "provider_adjusted"
    (directory / "catalog.json").write_text(json.dumps(catalog))
    # The durable registry retains the accepted interpretation after catalog edits.
    submit(market)
    listed = client.get(
        "/api/v1/market/datasets", headers=headers(), params={"limit": 1}
    )
    assert listed.json()[0]["price_basis"] == "unverified"
    assert listed.headers["X-Total-Count"] == "1"


@pytest.mark.parametrize(
    "route", ["dataset-inventory", "datasets", "ingestions", "snapshots"]
)
def test_operations_require_operator_role_and_bounded_lists(market, route):
    client, *_ = market
    assert (
        client.get("/api/v1/market/" + route, headers=headers("investor")).status_code
        == 403
    )
    assert (
        client.get(
            "/api/v1/market/" + route, headers=headers(), params={"limit": 101}
        ).status_code
        == 422
    )
    assert register(market, who="investor").status_code == 403


@pytest.mark.parametrize(
    "content,changes,code",
    [
        (
            "date,price,symbol\n2026-01-02,10,AAA\n2026-01-02,11,AAA\n",
            {},
            "DUPLICATE_OBSERVATION",
        ),
        (
            "date,price,symbol\n2026-01-02,10,AAA\n2026-01-03,broken,AAA\n",
            {},
            "INVALID_ROW",
        ),
        (
            "date,price,symbol\n2026-01-02,10,AAA\n",
            {"expected_sessions": ["2026-01-02", "2026-01-03"]},
            "MISSING_SESSIONS",
        ),
        (
            "date,price,symbol,source_unit\n2026-01-02,10,AAA,VND/tael\n",
            {},
            "UNIT_MISMATCH",
        ),
        (
            "date,price,symbol\n2026-01-02,10,AAA\n",
            {"price_basis": "nav"},
            "BASIS_MISMATCH",
        ),
        (
            "date,price,symbol,published_at\n2026-01-02,10,AAA,2026-01-01T00:00:00+00:00\n",
            {},
            "INVALID_KNOWN_AT",
        ),
    ],
)
def test_quality_quarantine_precedes_every_price_write(market, content, changes, code):
    from market_service.models import Asset, PriceRevision

    client, sessions, *_ = market
    configure(market, content, **changes)
    job, _ = submit(market)
    report = client.get(
        "/api/v1/market/ingestions/" + job["job_id"] + "/quality",
        headers=headers("other-operator"),
    )
    assert report.status_code == 200, report.text
    assert report.json()["status"] == "QUARANTINED"
    assert code in [f["code"] for f in report.json()["findings"]]
    assert "broken" not in report.text
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 0
    history = client.get(
        "/api/v1/market/ingestions", headers=headers("other-operator")
    ).json()
    assert history[0]["quality_status"] == "QUARANTINED"
    assert (
        client.post(
            "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
        ).status_code
        == 409
    )


def test_success_report_snapshot_history_and_checksum_failure(market):
    client, sessions, provider, directory = market
    job, _ = submit(market)
    report = client.get(
        f"/api/v1/market/ingestions/{job['job_id']}/quality", headers=headers()
    ).json()
    assert report["status"] == "PASS"
    assert report["row_count"] == 1
    created = client.post(
        "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
    )
    assert created.status_code == 201, created.text
    assert created.json()["quality_status"] == "PASS"
    assert (
        client.get("/api/v1/market/snapshots", headers=headers()).json()[0]["id"]
        == created.json()["id"]
    )
    accepted = client.post(
        "/api/v1/market/ingestions",
        json={"dataset_id": "DEMO_STOCK"},
        headers=headers(key=str(uuid4())),
    )
    (directory / "stock.csv").write_text("private malformed content")
    from market_service.models import Outbox
    from market_service.workflow import execute
    from portfolio_contracts import Envelope

    with sessions() as session:
        event = Envelope.model_validate(
            session.scalars(select(Outbox).order_by(Outbox.created_at.desc()))
            .first()
            .payload
        )
    execute(sessions, provider, event)
    report = client.get(
        f"/api/v1/market/ingestions/{accepted.json()['job_id']}/quality",
        headers=headers(),
    ).json()
    assert report["status"] == "QUARANTINED"
    assert report["findings"][0]["code"] == "CHECKSUM_MISMATCH"


def test_registration_rejects_user_paths_and_idempotency_rebinding(market):
    client, _, provider, _ = market
    assert register(market).status_code == 201
    assert register(market, "0" * 64).status_code == 409
    assert register(market, "0" * 64, key="different-key").status_code == 409
    response = client.post(
        "/api/v1/market/datasets",
        json={
            "dataset_id": "DEMO_STOCK",
            "expected_sha256": provider.spec("DEMO_STOCK")["sha256"],
            "path": "/private/source.csv",
        },
        headers=headers(key="no-path"),
    )
    assert response.status_code == 422
    assert (
        client.post(
            "/api/v1/market/datasets",
            json={
                "dataset_id": "DEMO_STOCK",
                "expected_sha256": provider.spec("DEMO_STOCK")["sha256"],
            },
            headers=headers(),
        ).status_code
        == 400
    )


def test_operator_without_market_scope_cannot_read_inventory(market):
    from fastapi.testclient import TestClient
    from market_service.api import create_app
    from service_auth import Principal

    _, sessions, provider, _ = market

    class NoScope:
        def verify(self, token):
            return Principal("issuer", token, frozenset({"data-operator"}), frozenset())

    client = TestClient(
        create_app(sessions=sessions, verifier=NoScope(), provider=provider)
    )
    assert (
        client.get("/api/v1/market/dataset-inventory", headers=headers()).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/market/datasets",
            json={"dataset_id": "DEMO_STOCK", "expected_sha256": "0" * 64},
            headers=headers(key="missing-scope"),
        ).status_code
        == 403
    )


def test_snapshot_quality_gate_rejects_unapproved_selected_revisions(market):
    from market_service.models import QualityReport

    client, sessions, *_ = market
    job, _ = submit(market)
    with sessions.begin() as session:
        report = session.get(QualityReport, job["job_id"])
        report.status = "QUARANTINED"
    response = client.post(
        "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
    )
    assert response.status_code == 409
    assert "passed quality" in response.json()["error"]["message"]


def test_quality_findings_bound_and_snapshot_legacy_rows_remain_usable(market):
    from market_service.models import PriceRevision

    client, sessions, *_ = market
    submit(market)
    with sessions.begin() as session:
        row = session.scalar(select(PriceRevision))
        row.ingestion_job_id = (
            None  # Existing immutable history predates quality lineage migration.
        )
    assert (
        client.post(
            "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
        ).status_code
        == 201
    )
    configure(market, "date,price,symbol\n" + "2026-01-02,broken,AAA\n" * 120)
    # New immutable pin required for new bytes.
    _, _, _, directory = market
    catalog = json.loads((directory / "catalog.json").read_text())
    catalog["BAD_SOURCE"] = catalog["DEMO_STOCK"]
    (directory / "catalog.json").write_text(json.dumps(catalog))
    job, _ = submit(market, {"dataset_id": "BAD_SOURCE"})
    report = client.get(
        f"/api/v1/market/ingestions/{job['job_id']}/quality", headers=headers()
    ).json()
    assert report["status"] == "QUARANTINED"
    assert len(report["findings"]) == 100


def test_snapshot_revalidates_selected_units_against_asset_definition(market):
    from market_service.models import PriceRevision

    client, sessions, *_ = market
    submit(market)
    with sessions.begin() as session:
        session.scalar(select(PriceRevision)).unit = "VND/tael"
    response = client.post(
        "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
    )
    assert response.status_code == 409


def test_inventory_reports_sql_registration_for_only_requested_page(market):
    client, _, _, directory = market
    before = client.get("/api/v1/market/dataset-inventory", headers=headers()).json()
    assert before[0]["registered"] is False
    assert before[0]["registered_sha256"] is None
    accepted = register(market)
    assert accepted.status_code == 201
    catalog = json.loads((directory / "catalog.json").read_text())
    catalog["ANOTHER"] = catalog["DEMO_STOCK"]
    (directory / "catalog.json").write_text(json.dumps(catalog))
    page = client.get(
        "/api/v1/market/dataset-inventory",
        params={"offset": 1, "limit": 1},
        headers=headers(),
    )
    assert page.headers["X-Total-Count"] == "2"
    assert len(page.json()) == 1
    assert page.json()[0]["dataset_id"] == "DEMO_STOCK"
    assert page.json()[0]["registered"] is True
    assert page.json()[0]["registered_sha256"] == accepted.json()["sha256"]


def test_registration_uses_exact_spec_verified_against_expected_checksum(
    market, monkeypatch
):
    client, _, provider, _ = market
    original = provider.spec("DEMO_STOCK")
    calls = []

    def changing_catalog(dataset_id):
        calls.append(dataset_id)
        return original if len(calls) == 1 else original | {"sha256": "f" * 64}

    monkeypatch.setattr(provider, "spec", changing_catalog)
    response = client.post(
        "/api/v1/market/datasets",
        json={"dataset_id": "DEMO_STOCK", "expected_sha256": original["sha256"]},
        headers=headers(key="stable-spec"),
    )
    assert response.status_code == 201
    assert response.json()["sha256"] == original["sha256"]
    assert len(calls) == 1


def test_deadline_and_legacy_terminal_jobs_report_quality_not_checked(market):
    from datetime import timedelta
    from portfolio_contracts import utcnow
    from market_service.models import IngestionJob, QualityReport

    client, sessions, *_ = market
    accepted = client.post(
        "/api/v1/market/ingestions",
        json={"dataset_id": "DEMO_STOCK"},
        headers=headers(key="deadline-quality"),
    ).json()
    with sessions.begin() as session:
        session.get(IngestionJob, accepted["job_id"]).deadline = utcnow() - timedelta(
            seconds=1
        )
    assert (
        client.get(accepted["status_url"], headers=headers()).json()["status"]
        == "FAILED"
    )
    response = client.get(
        f"/api/v1/market/ingestions/{accepted['job_id']}/quality", headers=headers()
    )
    assert response.json()["status"] == "NOT_CHECKED"
    with sessions() as session:
        assert session.get(QualityReport, accepted["job_id"]).status == "NOT_CHECKED"
    historical, _ = submit(market)
    with sessions.begin() as session:
        session.delete(session.get(QualityReport, historical["job_id"]))
    response = client.get(
        f"/api/v1/market/ingestions/{historical['job_id']}/quality", headers=headers()
    )
    assert response.json()["status"] == "NOT_CHECKED"
    assert response.json()["findings"][0]["code"] == "QUALITY_NOT_CHECKED"
    statuses = {
        row["job_id"]: row["quality_status"]
        for row in client.get("/api/v1/market/ingestions", headers=headers()).json()
    }
    assert statuses[historical["job_id"]] == "NOT_CHECKED"


def test_concurrent_first_registration_resolves_single_postgresql_pin(market):
    """An isolated schema exercises real unique-index blocking across transactions."""
    import os
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from market_service.models import Actor, Base, RegisteredDataset
    from market_service.registry import bootstrap

    url = os.environ.get("MARKET_CONCURRENCY_DATABASE_URL")
    if not url:
        pytest.skip("Set MARKET_CONCURRENCY_DATABASE_URL for PostgreSQL race coverage")
    schema = "market_registry_test_" + uuid4().hex
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        with sessions.begin() as session:
            actors = [Actor(issuer="test", subject=str(i)) for i in range(2)]
            session.add_all(actors)
            session.flush()
            actor_ids = [actor.id for actor in actors]
        barrier = Barrier(2)
        original_spec = market[2].spec("DEMO_STOCK")

        class RacingProvider:
            def spec(self, dataset_id):
                barrier.wait(timeout=10)
                return original_spec

            def coverage(self, spec):
                return market[2].coverage(spec)

        provider = RacingProvider()

        def register_actor(actor_id):
            with sessions.begin() as session:
                row = bootstrap(session, provider, "DEMO_STOCK", actor_id)
                return row.sha256, row.registered_by

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(register_actor, actor_ids))
        assert results[0] == results[1]
        assert results[0][0] == original_spec["sha256"]
        with sessions() as session:
            assert (
                session.scalar(select(func.count()).select_from(RegisteredDataset)) == 1
            )
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        control.dispose()


def test_registration_rejects_different_pin_won_during_bootstrap(market, monkeypatch):
    from market_service import api
    from market_service.models import RegisteredDataset
    from portfolio_contracts import utcnow

    client, _, provider, _ = market
    spec = provider.spec("DEMO_STOCK")
    winner = RegisteredDataset(
        dataset_id="DEMO_STOCK",
        sha256="f" * 64,
        spec=spec | {"sha256": "f" * 64},
        registered_by="other-operator",
        registered_at=utcnow(),
    )
    monkeypatch.setattr(api, "bootstrap", lambda *args, **kwargs: winner)
    response = client.post(
        "/api/v1/market/datasets",
        json={"dataset_id": "DEMO_STOCK", "expected_sha256": spec["sha256"]},
        headers=headers(key="race-loser"),
    )
    assert response.status_code == 409


def test_worker_deadline_persists_terminal_unchecked_quality(market):
    from datetime import timedelta
    from portfolio_contracts import Envelope, utcnow
    from market_service.models import IngestionJob, Outbox, QualityReport
    from market_service.workflow import execute

    client, sessions, provider, _ = market
    accepted = client.post(
        "/api/v1/market/ingestions",
        json={"dataset_id": "DEMO_STOCK"},
        headers=headers(key="worker-deadline"),
    ).json()
    with sessions.begin() as session:
        session.get(IngestionJob, accepted["job_id"]).deadline = utcnow() - timedelta(
            seconds=1
        )
        event = Envelope.model_validate(session.scalar(select(Outbox)).payload)
    execute(sessions, provider, event)
    with sessions() as session:
        assert session.get(IngestionJob, accepted["job_id"]).status == "FAILED"
        assert session.get(QualityReport, accepted["job_id"]).status == "NOT_CHECKED"


@pytest.mark.parametrize("poll_route", ["quality", "ingestion-list"])
def test_operator_polling_expires_queued_job_without_worker_or_legacy_status_get(
    market, poll_route
):
    from datetime import timedelta
    from portfolio_contracts import utcnow
    from market_service.models import IngestionJob, QualityReport

    client, sessions, *_ = market
    accepted = client.post(
        "/api/v1/market/ingestions",
        json={"dataset_id": "DEMO_STOCK"},
        headers=headers(key="operator-poll-expiry"),
    ).json()
    with sessions.begin() as session:
        session.get(IngestionJob, accepted["job_id"]).deadline = utcnow() - timedelta(
            seconds=1
        )
    # No worker delivery and no owner job GET: these are the actual operator UI polling routes.
    if poll_route == "quality":
        response = client.get(
            f"/api/v1/market/ingestions/{accepted['job_id']}/quality",
            headers=headers("other-operator"),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "NOT_CHECKED"
    else:
        response = client.get(
            "/api/v1/market/ingestions", headers=headers("other-operator")
        )
        assert response.status_code == 200
        row = next(
            row for row in response.json() if row["job_id"] == accepted["job_id"]
        )
        assert row["status"] == "FAILED"
        assert row["error"]["code"] == "DEADLINE_EXCEEDED"
        assert row["quality_status"] == "NOT_CHECKED"
    with sessions() as session:
        job = session.get(IngestionJob, accepted["job_id"])
        assert job.status == "FAILED"
        assert job.error["code"] == "DEADLINE_EXCEEDED"
        assert session.get(QualityReport, job.id).status == "NOT_CHECKED"


def test_deadline_reconciliation_refreshes_worker_success_before_expiring(market):
    from datetime import timedelta
    from portfolio_contracts import utcnow
    from market_service.models import IngestionJob, QualityReport
    from market_service.quality import terminal_quality

    client, sessions, *_ = market
    accepted = client.post(
        "/api/v1/market/ingestions",
        json={"dataset_id": "DEMO_STOCK"},
        headers=headers(key="deadline-success-race"),
    ).json()
    with sessions.begin() as session:
        session.get(IngestionJob, accepted["job_id"]).deadline = utcnow() - timedelta(
            seconds=1
        )
    with sessions.begin() as poller:
        stale_job = poller.get(IngestionJob, accepted["job_id"])
        assert stale_job.status == "QUEUED"
        with sessions.begin() as worker:
            worker.get(IngestionJob, accepted["job_id"]).status = "SUCCEEDED"
            worker.add(
                QualityReport(
                    job_id=accepted["job_id"], status="PASS", report={"status": "PASS"}
                )
            )
        quality = terminal_quality(poller, stale_job)
        assert stale_job.status == "SUCCEEDED"
        assert quality.status == "PASS"
    with sessions() as session:
        assert session.get(IngestionJob, accepted["job_id"]).status == "SUCCEEDED"
