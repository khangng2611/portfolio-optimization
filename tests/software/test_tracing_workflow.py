"""Owner persistence and workflow tracing, with no broker or collector required."""

import importlib
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from alembic import command as migrations
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]
OWNERS = [
    ("portfolio", "portfolio_service", "Job", "job", "e725cea52e0e"),
    ("quant-serving", "quant_service", "Run", "numerical_run", "61ece06160ae"),
    ("market-data", "market_service", "IngestionJob", "ingestion_job", "10f6adda892e"),
]


@pytest.mark.parametrize("directory,module,entity,table,initial", OWNERS)
def test_owner_models_support_optional_trace_context(directory, module, entity, table, initial):
    models = importlib.import_module(f"{module}.models")
    for model in (getattr(models, entity), models.Outbox):
        assert "trace_context" in model.__table__.columns, model.__name__
        assert model.__table__.columns["trace_context"].nullable


@pytest.mark.parametrize("directory,module,entity,table,initial", OWNERS)
def test_additive_trace_migration_preserves_old_outbox_rows(
    directory, module, entity, table, initial, tmp_path, monkeypatch
):
    url = f"sqlite:///{tmp_path / 'owner.db'}"
    monkeypatch.setenv("MIGRATION_DATABASE_URL", url)
    config = Config(str(ROOT / "services" / directory / "alembic.ini"))
    migrations.upgrade(config, initial)
    engine = create_engine(url)
    with engine.begin() as connection:
        if directory == "market-data":
            connection.execute(text(
                "INSERT INTO outbox_event (event_id,payload,created_at) "
                "VALUES ('legacy-event','{}','2026-10-09 00:00:00')"
            ))
        else:
            connection.execute(text(
                "INSERT INTO outbox_event (event_id,payload) VALUES ('legacy-event','{}')"
            ))
    migrations.upgrade(config, "head")
    for owner_table in (table, "outbox_event"):
        columns = {column["name"]: column for column in inspect(engine).get_columns(owner_table)}
        assert "trace_context" in columns, owner_table
        assert columns["trace_context"]["nullable"]
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT payload,trace_context FROM outbox_event WHERE event_id='legacy-event'"
        )).one() == ("{}", None)
    migrations.downgrade(config, initial)
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT payload FROM outbox_event WHERE event_id='legacy-event'"
        )).scalar_one() == "{}"
    assert "trace_context" not in {column["name"] for column in inspect(engine).get_columns("outbox_event")}
    engine.dispose()


@pytest.fixture
def recorded_traces(monkeypatch):
    import service_observability
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", provider)
    monkeypatch.setattr(service_observability, "_tracer", provider.get_tracer("portfolio-services"))
    monkeypatch.setattr(service_observability, "_enabled", True)
    monkeypatch.setenv("OTEL_TRACES_ENABLED", "true")
    monkeypatch.setenv("TRACE_VIEWER_URL", "http://localhost:16686")
    yield exporter
    provider.shutdown()


def carrier(digit):
    return {"traceparent": f"00-{digit * 32}-0123456789abcdef-01"}


@pytest.fixture
def traced_pipeline(recorded_traces, tmp_path):
    import hashlib
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from portfolio_contracts import utcnow
    from portfolio_service.api import create_app
    from portfolio_service.models import Base as PortfolioBase
    from quant_service.models import Base as QuantBase
    from quant_service.artifacts import ArtifactCatalog
    from service_auth import Principal

    bundle = {
        "schema_version": 1, "bundle_id": "trace-fixture", "universe_id": "DEMO",
        "snapshot_id": "snapshot-v1", "model_bundle_id": None, "model_status": None,
        "as_of_date": "2026-09-25", "valid_until": (utcnow() + timedelta(hours=1)).isoformat(),
        "demo": True, "strategies": ["MVO"],
        "numerical": {
            "asset_ids": ["AAA", "BBB", "VFF"],
            "mean_returns": [0.001, 0.0005, 0.0001],
            "covariance": [[0.0004, 0, 0], [0, 0.0003, 0], [0, 0, 0.00005]],
        },
    }
    data = json.dumps(bundle).encode()
    (tmp_path / "bundle.json").write_bytes(data)
    (tmp_path / "catalog.json").write_text(json.dumps({"bundles": [
        {"file": "bundle.json", "sha256": hashlib.sha256(data).hexdigest()}
    ]}))
    catalog = ArtifactCatalog(tmp_path, allow_demo=True)

    class Resolver:
        def ready(self, universe, strategy):
            return catalog.ready(universe, strategy).model_dump(mode="json")

    class Verifier:
        def verify(self, token):
            return Principal("https://identity", token, frozenset({"investor"}),
                             frozenset({"portfolio:read", "portfolio:write"}))

    factories = []
    for name, metadata in (("portfolio", PortfolioBase.metadata), ("quant", QuantBase.metadata)):
        engine = create_engine(f"sqlite:///{tmp_path / (name + '.db')}",
                               connect_args={"check_same_thread": False})
        metadata.create_all(engine)
        factories.append(sessionmaker(engine, expire_on_commit=False))
    with TestClient(create_app(sessions=factories[0], verifier=Verifier(), resolver=Resolver())) as client:
        yield client, factories[0], factories[1], catalog


def submit_recommendation(client, trace_headers=None, key="trace-job", portfolio_id=None):
    headers = {"Authorization": "Bearer PRIVATE_TOKEN_SENTINEL", **(trace_headers or {})}
    if portfolio_id is None:
        created = client.post("/api/v1/portfolios", headers=headers,
                              json={"name": "PRIVATE_NAME_SENTINEL", "capital_vnd": "91234567",
                                    "max_position_weight": 0.6})
        assert created.status_code == 201, created.text
        portfolio_id = created.json()["id"]
    response = client.post(f"/api/v1/portfolios/{portfolio_id}/recommendations",
                           headers=headers | {"Idempotency-Key": key}, json={"strategy": "MVO"})
    assert response.status_code == 202, response.text
    return portfolio_id, response


def test_http_job_outbox_replay_poll_and_legacy_trace_metadata(traced_pipeline, recorded_traces):
    from sqlalchemy import select
    from portfolio_contracts import OptimizeCommand
    from portfolio_service.models import Job, Outbox
    from service_observability import trace_id

    client, sessions, _, _ = traced_pipeline
    pid, first = submit_recommendation(client, carrier("1"))
    accepted = first.json()
    assert accepted["job_trace_id"] == "1" * 32
    assert accepted["job_trace_url"] == f"http://localhost:16686/trace/{'1' * 32}"
    assert first.headers["X-Trace-ID"] == "1" * 32
    _, replay = submit_recommendation(client, carrier("2"), portfolio_id=pid)
    assert replay.json() == accepted
    assert replay.headers["X-Trace-ID"] == "2" * 32
    replay_spans = [s for s in recorded_traces.get_finished_spans() if s.context.trace_id == int("2" * 32, 16)]
    assert any(s.attributes.get("outcome") == "duplicate" and s.attributes.get("job.id") == accepted["job_id"] for s in replay_spans)
    with sessions() as session:
        job = session.get(Job, accepted["job_id"])
        outbox = session.scalar(select(Outbox))
        assert job.trace_context == outbox.trace_context
        assert trace_id(outbox.trace_context) == accepted["job_trace_id"]
        assert "trace_context" not in outbox.payload and "traceparent" not in json.dumps(job.input)
        assert OptimizeCommand.model_validate(job.input).compute_hash() == job.input_hash
    state = client.get(f"/api/v1/jobs/portfolio/{accepted['job_id']}",
                       headers={"Authorization": "Bearer PRIVATE_TOKEN_SENTINEL", **carrier("3")})
    assert state.json()["job_trace_id"] == "1" * 32
    assert state.headers["X-Trace-ID"] == "3" * 32
    poll_spans = [s for s in recorded_traces.get_finished_spans() if s.context.trace_id == int("3" * 32, 16)]
    assert any(link.context.trace_id == int("1" * 32, 16) for s in poll_spans for link in s.links)
    with sessions.begin() as session:
        session.get(Job, accepted["job_id"]).trace_context = None
    legacy = client.get(f"/api/v1/jobs/portfolio/{accepted['job_id']}",
                        headers={"Authorization": "Bearer PRIVATE_TOKEN_SENTINEL"})
    assert legacy.json()["job_trace_id"] is None and legacy.json()["job_trace_url"] is None


def test_dispatch_restart_result_chain_and_duplicates_do_not_rerun_solver(
    traced_pipeline, recorded_traces, monkeypatch
):
    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker
    from portfolio_contracts import Envelope
    from portfolio_service import worker as portfolio_worker
    from portfolio_service.models import Job, Recommendation
    from portfolio_service.workflow import consume_result
    from quant_service import worker as quant_worker
    from quant_service.models import Outbox as QuantOutbox, Run
    from quant_service.workflow import execute
    from service_observability import capture_context, span, trace_id

    client, portfolio_sessions, quant_sessions, catalog = traced_pipeline
    pid, first = submit_recommendation(client, carrier("4"))
    job_id = first.json()["job_id"]
    commands, results = [], []

    def publisher(target):
        def confirmed(connection, owner, payload):
            target.append((Envelope.model_validate(payload), capture_context()))
        return confirmed

    # A fresh session factory starts dispatch after the submission transaction ended.
    restarted = sessionmaker(portfolio_sessions.kw["bind"], expire_on_commit=False)
    monkeypatch.setattr(portfolio_worker, "publish", publisher(commands))
    portfolio_worker.dispatch_once(restarted, None)
    assert trace_id(commands[0][1]) == "4" * 32
    with span("test.command.consume", carrier=commands[0][1]):
        execute(quant_sessions, catalog, commands[0][0])
        execute(quant_sessions, catalog, commands[0][0])
        execute(quant_sessions, catalog, commands[0][0].model_copy(update={"event_id": str(uuid4())}))
    with quant_sessions() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 1
        assert session.scalar(select(func.count()).select_from(QuantOutbox)) == 1
        assert trace_id(session.scalar(select(Run)).trace_context) == "4" * 32
        assert trace_id(session.scalar(select(QuantOutbox)).trace_context) == "4" * 32
    monkeypatch.setattr(quant_worker, "publish", publisher(results))
    quant_worker.dispatch_once(quant_sessions, None)
    assert trace_id(results[0][1]) == "4" * 32
    with span("test.result.consume", carrier=results[0][1]):
        consume_result(portfolio_sessions, results[0][0])
        consume_result(portfolio_sessions, results[0][0])
    with portfolio_sessions() as session:
        assert session.get(Job, job_id).status == "SUCCEEDED"
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 1
    result = client.get(f"/api/v1/recommendations/{job_id}",
                        headers={"Authorization": "Bearer PRIVATE_TOKEN_SENTINEL", **carrier("5")})
    assert result.json()["job_trace_id"] == "4" * 32
    history = client.get(f"/api/v1/portfolios/{pid}/recommendations",
                         headers={"Authorization": "Bearer PRIVATE_TOKEN_SENTINEL"})
    assert history.json()[0]["job_trace_id"] == "4" * 32
    assert client.get(f"/api/v1/recommendations/{job_id}",
                      headers={"Authorization": "Bearer another-owner"}).status_code == 404
    spans = recorded_traces.get_finished_spans()
    assert any(s.name == "test.command.consume" and s.attributes.get("outcome") == "duplicate_job" for s in spans)
    assert any(s.name == "test.result.consume" and s.attributes.get("outcome") == "duplicate_delivery" for s in spans)
    stages = [s for s in spans if s.name in {
        "outbox.dispatch", "quant.inputs.load", "portfolio_core.allocate",
        "quant.result.persist", "portfolio.result.validate", "portfolio.result.persist",
    }]
    assert {s.name for s in stages} == {
        "outbox.dispatch", "quant.inputs.load", "portfolio_core.allocate",
        "quant.result.persist", "portfolio.result.validate", "portfolio.result.persist",
    }
    assert len([s for s in stages if s.name == "portfolio_core.allocate"]) == 1
    assert all(s.context.trace_id == int("4" * 32, 16) for s in stages)
    exported = json.dumps([dict(s.attributes) for s in spans])
    assert all(value not in exported for value in ("PRIVATE_TOKEN_SENTINEL", "PRIVATE_NAME_SENTINEL", "91234567"))


def test_job_and_context_roll_back_together_when_commit_fails(traced_pipeline):
    from sqlalchemy import event, func, select
    from sqlalchemy.exc import SQLAlchemyError
    from portfolio_service.models import Job, Outbox

    client, sessions, _, _ = traced_pipeline
    def reject_outbox(session, flush_context, instances):
        if any(isinstance(row, Outbox) for row in session.new):
            raise SQLAlchemyError("PRIVATE_DATABASE_DETAIL")

    created = client.post("/api/v1/portfolios", headers={"Authorization": "Bearer PRIVATE_TOKEN_SENTINEL"},
                          json={"name": "rollback", "capital_vnd": "100", "max_position_weight": 0.6})
    event.listen(sessions.class_, "before_flush", reject_outbox)
    try:
        response = client.post(f"/api/v1/portfolios/{created.json()['id']}/recommendations",
                               headers={"Authorization": "Bearer PRIVATE_TOKEN_SENTINEL", "Idempotency-Key": "rollback", **carrier("6")},
                               json={"strategy": "MVO"})
        assert response.status_code == 503
    finally:
        event.remove(sessions.class_, "before_flush", reject_outbox)
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.scalar(select(func.count()).select_from(Outbox)) == 0


def test_ready_resolver_injects_only_current_trace_into_quant_http(recorded_traces, monkeypatch):
    import httpx
    from portfolio_service.runtime import QuantResolver
    from service_observability import span, trace_id

    monkeypatch.setenv("OIDC_TOKEN_URL", "https://identity/token")
    monkeypatch.setenv("QUANT_CLIENT_SECRET", "PRIVATE_CLIENT_SECRET")
    monkeypatch.setenv("QUANT_API_URL", "http://quant-api")
    sent = []
    def token(*args, **kwargs):
        return httpx.Response(200, json={"access_token": "PRIVATE_ACCESS_TOKEN", "expires_in": 3600},
                              request=httpx.Request("POST", args[0]))
    def ready(*args, **kwargs):
        sent.append(kwargs["headers"])
        return httpx.Response(200, json={"bundle_id": "fixture"}, request=httpx.Request("GET", args[0]))
    monkeypatch.setattr(httpx, "post", token)
    monkeypatch.setattr(httpx, "get", ready)
    with span("resolver.parent", carrier=carrier("7")):
        assert QuantResolver().ready("DEMO", "MVO") == {"bundle_id": "fixture"}
    assert trace_id(sent[0]) == "7" * 32
    assert sent[0]["Authorization"] == "Bearer PRIVATE_ACCESS_TOKEN"
    assert "baggage" not in sent[0]


def test_market_ingestion_trace_replay_retry_and_normalized_persistence(recorded_traces, tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select
    from sqlalchemy.orm import sessionmaker
    from market_service.api import create_app
    from market_service.models import Base, IngestionJob, Outbox, PriceRevision
    from market_service.worker import dispatch_once
    from market_service.workflow import execute
    from portfolio_contracts import Envelope, canonical_hash, utcnow
    from service_auth import Principal
    from service_observability import capture_context, span, trace_id

    class Verifier:
        def verify(self, token):
            return Principal("https://identity", token, frozenset({"data-operator"}),
                             frozenset({"market:read", "market:write"}))

    engine = create_engine(f"sqlite:///{tmp_path / 'market.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    body = {"observations": [{
        "asset_id": "AAA", "kind": "stock", "observation_date": utcnow().date().isoformat(),
        "price": "12.5", "source_unit": "thousand_VND/share", "provider": "fixture",
        "published_at": (utcnow() - timedelta(minutes=1)).isoformat(),
    }]}
    auth = {"Authorization": "Bearer PRIVATE_MARKET_TOKEN", "Idempotency-Key": "ingestion-trace"}
    with TestClient(create_app(sessions=sessions, verifier=Verifier(), provider=None)) as client:
        first = client.post("/api/v1/market/ingestions", headers=auth | carrier("8"), json=body)
        assert first.status_code == 202, first.text
        assert first.json()["job_trace_id"] == "8" * 32
        replay = client.post("/api/v1/market/ingestions", headers=auth | carrier("9"), json=body)
        assert replay.json() == first.json()
        job_id = first.json()["job_id"]
        with sessions() as session:
            job, row = session.get(IngestionJob, job_id), session.scalar(select(Outbox))
            assert job.trace_context == row.trace_context
            assert trace_id(row.trace_context) == "8" * 32
            assert job.request_hash == canonical_hash(job.input["request"])
        attempts = []
        def publisher(connection, owner, payload):
            attempts.append((Envelope.model_validate(payload), capture_context()))
            if len(attempts) == 1:
                raise ConnectionError("PRIVATE_BROKER_DETAIL")
        with pytest.raises(ConnectionError):
            dispatch_once(sessions, None, publisher=publisher)
        with sessions() as session:
            assert session.scalar(select(Outbox)).published_at is None
        restarted = sessionmaker(engine, expire_on_commit=False)
        dispatch_once(restarted, None, publisher=publisher)
        assert attempts[0][0].event_id == attempts[1][0].event_id
        assert all(trace_id(context) == "8" * 32 for _, context in attempts)
        assert attempts[0][1] != attempts[1][1]
        with span("test.market.consume", carrier=attempts[1][1]):
            execute(sessions, None, attempts[1][0])
            execute(sessions, None, attempts[1][0])
        with sessions() as session:
            assert session.get(IngestionJob, job_id).status == "SUCCEEDED"
            assert session.scalar(select(func.count()).select_from(PriceRevision)) == 1
            assert float(session.scalar(select(PriceRevision)).price_vnd) == 12500
        state = client.get(f"/api/v1/jobs/market/{job_id}",
                           headers={"Authorization": "Bearer PRIVATE_MARKET_TOKEN", **carrier("a")})
        assert state.json()["job_trace_id"] == "8" * 32
        assert state.headers["X-Trace-ID"] == "a" * 32
    stages = [s for s in recorded_traces.get_finished_spans() if s.name in {
        "outbox.dispatch", "market.ingestion.normalize", "market.ingestion.persist"
    }]
    assert {s.name for s in stages} == {"outbox.dispatch", "market.ingestion.normalize", "market.ingestion.persist"}
    assert len([s for s in stages if s.name == "outbox.dispatch"]) == 2
    assert all(s.context.trace_id == int("8" * 32, 16) for s in stages)
    assert "PRIVATE_BROKER_DETAIL" not in json.dumps([
        dict(event.attributes or {}) for s in stages for event in s.events
    ])


def test_disabled_tracing_creates_no_origin_reference_and_keeps_job_valid(traced_pipeline, monkeypatch):
    import service_observability
    from portfolio_contracts import OptimizeCommand
    from portfolio_service.models import Job

    monkeypatch.setattr(service_observability, "_enabled", False)
    client, sessions, _, _ = traced_pipeline
    _, response = submit_recommendation(client, carrier("b"))
    assert response.json()["job_trace_id"] is None
    assert response.json()["job_trace_url"] is None
    with sessions() as session:
        job = session.get(Job, response.json()["job_id"])
        assert job.trace_context is None
        assert OptimizeCommand.model_validate(job.input).compute_hash() == job.input_hash
