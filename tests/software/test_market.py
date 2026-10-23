import hashlib
import json
from datetime import timedelta
from importlib.util import find_spec
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from portfolio_contracts import Envelope, utcnow
from service_auth import AuthError, Principal


class Identities:
    def verify(self, token):
        if token == "invalid":
            raise AuthError()
        return Principal(
            "https://identity/portfolio",
            token,
            frozenset({"investor" if token == "investor" else "data-operator"}),
            frozenset({"market:read", "market:write"}),
        )


@pytest.fixture
def market(tmp_path):
    assert find_spec("market_service"), "Market Data owner service is missing"
    from market_service.api import create_app
    from market_service.models import Base
    from market_service.providers import CsvProvider

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    content = f"date,price,symbol\n{utcnow().date()},12.5,AAA\n"
    (tmp_path / "stock.csv").write_text(content)
    registry = {
        "DEMO_STOCK": {
            "path": "stock.csv",
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "asset_id": "AAA",
            "kind": "stock",
            "source_unit": "thousand_VND/share",
            "provider": "fixture",
            "price_column": "price",
        }
    }
    (tmp_path / "catalog.json").write_text(json.dumps(registry))
    provider = CsvProvider(tmp_path)
    client = TestClient(
        create_app(sessions=sessions, verifier=Identities(), provider=provider)
    )
    return client, sessions, provider, tmp_path


def headers(who="operator", key=None):
    value = {"Authorization": f"Bearer {who}"}
    if key:
        value["Idempotency-Key"] = key
    return value


def observation(price="12500", **overrides):
    return {
        "asset_id": "AAA",
        "kind": "stock",
        "observation_date": utcnow().date().isoformat(),
        "price": price,
        "source_unit": "VND/share",
        "provider": "fixture",
        "published_at": (utcnow() - timedelta(minutes=1)).isoformat(),
    } | overrides


def submit(market, body=None, key=None):
    client, sessions, provider, _ = market
    response = client.post(
        "/api/v1/market/ingestions",
        json=body or {"dataset_id": "DEMO_STOCK"},
        headers=headers(key=key or str(uuid4())),
    )
    assert response.status_code == 202, response.text
    from market_service.models import Outbox
    from market_service.workflow import execute

    with sessions() as session:
        row = session.scalars(select(Outbox).order_by(Outbox.created_at.desc())).first()
        event = Envelope.model_validate(row.payload)
    execute(sessions, provider, event)
    return response.json(), event


def test_market_role_and_owner_boundary(market):
    client, *_ = market
    body = {"dataset_id": "DEMO_STOCK"}
    assert client.post("/api/v1/market/ingestions", json=body).status_code == 401
    assert (
        client.post(
            "/api/v1/market/ingestions", json=body, headers=headers("investor", "key-1")
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/market/assets", headers=headers("invalid")).status_code
        == 401
    )
    job, _ = submit(market)
    assert (
        client.get(job["status_url"], headers=headers("other-operator")).status_code
        == 404
    )
    assert (
        client.get(job["status_url"], headers=headers()).json()["status"] == "SUCCEEDED"
    )


def test_ingestion_idempotency_atomic_outbox_and_duplicate_delivery(market):
    client, sessions, provider, _ = market
    body = {"dataset_id": "DEMO_STOCK"}
    first = client.post(
        "/api/v1/market/ingestions", json=body, headers=headers(key="same-key")
    )
    assert first.status_code == 202
    assert (
        client.post(
            "/api/v1/market/ingestions", json=body, headers=headers(key="same-key")
        ).json()
        == first.json()
    )
    assert (
        client.post(
            "/api/v1/market/ingestions",
            json={"observations": [observation()]},
            headers=headers(key="same-key"),
        ).status_code
        == 409
    )
    from market_service.models import Inbox, IngestionJob, Outbox, PriceRevision
    from market_service.workflow import execute

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(IngestionJob)) == 1
        assert session.scalar(select(func.count()).select_from(Outbox)) == 1
        event = Envelope.model_validate(session.scalar(select(Outbox)).payload)
    execute(sessions, provider, event)
    execute(sessions, provider, event)
    execute(sessions, provider, event.model_copy(update={"event_id": str(uuid4())}))
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 1
        assert session.scalar(select(func.count()).select_from(Inbox)) == 2
        revision = session.scalar(select(PriceRevision))
        assert float(revision.price_vnd) == 12500
        assert revision.unit == "VND/share"


def test_reimport_is_deduplicated_and_correction_keeps_original(market):
    from market_service.models import PriceRevision

    _, sessions, _, _ = market
    submit(market)
    submit(market)
    submit(market, {"observations": [observation("13000")]})
    with sessions() as session:
        revisions = list(
            session.scalars(select(PriceRevision).order_by(PriceRevision.revision))
        )
        assert [float(row.price_vnd) for row in revisions] == [12500, 13000]
        assert [row.revision for row in revisions] == [1, 2]


def test_price_reverting_to_an_older_value_creates_new_revision(market):
    from market_service.models import PriceRevision

    _, sessions, _, _ = market
    submit(market)
    submit(market, {"observations": [observation("13000")]})
    submit(market, {"observations": [observation("12500")]})
    with sessions() as session:
        rows = list(
            session.scalars(select(PriceRevision).order_by(PriceRevision.revision))
        )
        assert [float(row.price_vnd) for row in rows] == [12500, 13000, 12500]


def test_invalid_batch_rolls_back_assets_and_prices(market):
    from market_service.models import Asset, PriceRevision

    client, sessions, _, _ = market
    body = {
        "observations": [
            observation(asset_id="AAA"),
            observation(
                asset_id="AAA",
                kind="fund",
                source_unit="VND/unit",
                observation_date=(utcnow().date() - timedelta(days=1)).isoformat(),
            ),
        ]
    }
    job, _ = submit(market, body)
    assert client.get(job["status_url"], headers=headers()).json()["status"] == "FAILED"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 0


def test_historical_snapshot_cannot_use_later_ingested_data(market):
    client, *_ = market
    yesterday = (utcnow().date() - timedelta(days=1)).isoformat()
    submit(
        market,
        {"observations": [observation(observation_date=yesterday, published_at=None)]},
    )
    response = client.post(
        "/api/v1/market/snapshots",
        json=snapshot_body(
            start_date=yesterday, end_date=yesterday, as_of_date=yesterday
        ),
        headers=headers(),
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "kind,unit,asset,price_type",
    [
        ("fund", "thousand_VND/unit", "VFF", "nav"),
        ("gold", "thousand_VND/tael", "GOLD", "ask"),
    ],
)
def test_fund_and_gold_ingestion_has_explicit_units(
    market, kind, unit, asset, price_type
):
    client, *_ = market
    submit(
        market,
        {
            "observations": [
                observation(
                    "12.5",
                    kind=kind,
                    source_unit=unit,
                    asset_id=asset,
                    price_type=price_type,
                )
            ]
        },
    )
    response = client.get(
        "/api/v1/market/prices",
        params={
            "asset_id": asset,
            "start_date": utcnow().date().isoformat(),
            "end_date": utcnow().date().isoformat(),
        },
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()[0]["price_vnd"] == "12500.000000"
    assert response.json()[0]["unit"] == unit.removeprefix("thousand_")
    assert response.json()[0]["price_type"] == price_type


def test_snapshot_rejects_large_missing_interval(market):
    client, *_ = market
    old = (utcnow().date() - timedelta(days=30)).isoformat()
    submit(market, {"observations": [observation(observation_date=old), observation()]})
    response = client.post(
        "/api/v1/market/snapshots",
        json=snapshot_body(start_date=old),
        headers=headers(),
    )
    assert response.status_code == 409


def test_snapshot_does_not_mix_providers(market):
    client, *_ = market
    submit(
        market,
        {"observations": [observation(), observation(provider="different-provider")]},
    )
    assert (
        client.post(
            "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
        ).status_code
        == 409
    )


def test_dataset_checksum_is_pinned_at_enqueue_and_failure_is_visible(market):
    client, sessions, provider, directory = market
    from market_service.models import Outbox, PriceRevision
    from market_service.workflow import execute

    accepted = client.post(
        "/api/v1/market/ingestions",
        json={"dataset_id": "DEMO_STOCK"},
        headers=headers(key="hash-pinned"),
    )
    assert accepted.status_code == 202
    (directory / "stock.csv").write_text("date,price\n2026-10-09,999\n")
    with sessions() as session:
        event = Envelope.model_validate(session.scalar(select(Outbox)).payload)
    execute(sessions, provider, event)
    job = client.get(accepted.json()["status_url"], headers=headers()).json()
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "INVALID_DATASET"
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(PriceRevision)) == 0


def snapshot_body(**overrides):
    today = utcnow().date().isoformat()
    return {
        "asset_ids": ["AAA"],
        "start_date": today,
        "end_date": today,
        "as_of_date": today,
        "max_age_days": 7,
    } | overrides


def test_snapshot_immutable_hash_and_content_after_correction(market):
    client, *_ = market
    submit(market)
    first = client.post(
        "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
    )
    assert first.status_code == 201, first.text
    repeated = client.post(
        "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
    ).json()
    assert repeated["id"] == first.json()["id"]
    original = client.get(
        f"/api/v1/market/snapshots/{first.json()['id']}/observations", headers=headers()
    ).json()
    submit(market, {"observations": [observation("13000")]})
    second = client.post(
        "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
    ).json()
    assert second["content_hash"] != first.json()["content_hash"]
    assert (
        client.get(
            f"/api/v1/market/snapshots/{first.json()['id']}/observations",
            headers=headers(),
        ).json()
        == original
    )
    assert original[0]["price_vnd"] == "12500.000000"


def test_snapshot_missing_stale_and_future_publication_are_rejected(market):
    client, *_ = market
    assert (
        client.post(
            "/api/v1/market/snapshots", json=snapshot_body(), headers=headers()
        ).status_code
        == 409
    )
    old = (utcnow().date() - timedelta(days=10)).isoformat()
    submit(market, {"observations": [observation(observation_date=old)]})
    assert (
        client.post(
            "/api/v1/market/snapshots",
            json=snapshot_body(start_date=old),
            headers=headers(),
        ).status_code
        == 409
    )
    future = (utcnow() + timedelta(days=1)).isoformat()
    assert (
        client.post(
            "/api/v1/market/ingestions",
            json={"observations": [observation(published_at=future)]},
            headers=headers(key="future"),
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "change",
    [
        {"price": "NaN"},
        {"source_unit": "VND/tael"},
        {"published_at": "2026-10-09T12:00:00"},
        {"asset_id": "../../evil"},
    ],
)
def test_invalid_observations_never_enqueue(market, change):
    client, *_ = market
    assert (
        client.post(
            "/api/v1/market/ingestions",
            json={"observations": [observation(**change)]},
            headers=headers(key="invalid-input"),
        ).status_code
        == 422
    )


def test_csv_path_escape_and_unknown_dataset_are_rejected(market):
    client, _, _, directory = market
    assert (
        client.post(
            "/api/v1/market/ingestions",
            json={"dataset_id": "unknown"},
            headers=headers(key="unknown"),
        ).status_code
        == 422
    )
    registry = json.loads((directory / "catalog.json").read_text())
    registry["DEMO_STOCK"]["path"] = "../outside.csv"
    (directory / "catalog.json").write_text(json.dumps(registry))
    assert (
        client.post(
            "/api/v1/market/ingestions",
            json={"dataset_id": "DEMO_STOCK"},
            headers=headers(key="escape"),
        ).status_code
        == 422
    )


def test_failed_publish_retains_outbox_for_retry(market):
    from market_service.worker import dispatch_once
    from market_service.models import Outbox

    client, sessions, _, _ = market
    assert (
        client.post(
            "/api/v1/market/ingestions",
            json={"dataset_id": "DEMO_STOCK"},
            headers=headers(key="offline-broker"),
        ).status_code
        == 202
    )

    def unavailable(*args):
        raise ConnectionError("broker unavailable")

    with pytest.raises(ConnectionError):
        dispatch_once(sessions, None, publisher=unavailable)
    with sessions() as session:
        assert session.scalar(select(Outbox)).published_at is None


def test_swagger_advertises_bearer_authorize(market):
    client, *_ = market
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/api/v1/market/ingestions"]["post"]["security"] == [
        {"HTTPBearer": []}
    ]
    assert not schema["paths"]["/health/live"]["get"].get("security")
