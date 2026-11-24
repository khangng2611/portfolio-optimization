from uuid import uuid4
from fastapi.testclient import TestClient
from portfolio_contracts import utcnow
from market_service.api import create_app
from service_auth import Principal
from test_market import market as market_fixture

market = market_fixture


class ChatVerifier:
    def verify(self, token):
        return Principal(
            "issuer", str(uuid4()), frozenset(), frozenset({"market:chat:read"}), token
        )


def test_market_tool_auth_and_canonical_freshness(market):  # noqa: F811
    _, sessions, provider, _ = market
    c = TestClient(
        create_app(sessions=sessions, verifier=ChatVerifier(), provider=provider)
    )
    path = "/internal/v1/chat/market-facts"
    assert c.get(path).status_code == 401
    assert c.get(path, headers={"Authorization": "Bearer attacker"}).status_code == 403
    r = c.get(path, headers={"Authorization": "Bearer chat-service"})
    assert r.status_code == 200, r.text
    assert r.json()["observations"] == []
    assert r.json()["status"] == "NO_OBSERVATIONS"
    assert r.json()["checked_at"].startswith(str(utcnow().date()))


def test_gold_quote_selects_latest_eligible_gold_revision(market, monkeypatch):  # noqa: F811
    from datetime import datetime, timedelta, timezone
    from market_service.models import PriceRevision
    from market_service.phase1_sources import GOLD_PROVIDER

    _, sessions, provider, _ = market
    client = TestClient(create_app(sessions=sessions, verifier=ChatVerifier(), provider=provider))
    path = "/internal/v1/chat/market-facts?asset_id=GOLD"
    headers = {"Authorization": "Bearer chat-service"}
    now = datetime(2026, 11, 22, 18, tzinfo=timezone.utc)
    monkeypatch.setattr("market_service.api.utcnow", lambda: now)
    old = now.date() - timedelta(days=4)
    empty = client.get(path, headers=headers).json()
    assert empty["scope"] == "gold_quote"
    assert empty["local_date"] == "2026-11-23"
    assert empty["observations"] == []
    base = dict(asset_id="GOLD", provider=GOLD_PROVIDER, observation_date=old,
                price_vnd=100000000, revision=1, content_hash="a"*64, unit="VND/tael",
                source_unit="VND/tael", price_type="close", price_basis="raw_close",
                available_at=now-timedelta(minutes=3), data_origin="real")
    with sessions.begin() as db:
        for changes in [{}, {"revision": 2, "price_vnd": 101000000},
                        {"revision": 3, "available_at": now+timedelta(days=1)},
                        {"observation_date": now.date(), "data_origin": "demo"},
                        {"observation_date": now.date(), "provider": "other"},
                        {"asset_id": "FPT", "observation_date": now.date()}]:
            db.add(PriceRevision(**(base | changes)))
    rows = client.get(path, headers=headers).json()["observations"]
    assert [(r["asset_id"], r["observation_date"], r["revision"]) for r in rows] == [("GOLD", str(old), 2)]
    assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 403


def test_equity_quote_only_returns_eligible_observations_for_requested_ticker(market):  # noqa: F811
    from datetime import timedelta
    from market_service.models import PriceRevision

    _, sessions, provider, _ = market
    client = TestClient(create_app(sessions=sessions, verifier=ChatVerifier(), provider=provider))
    path, headers = "/internal/v1/chat/market-facts", {"Authorization": "Bearer chat-service"}
    now = utcnow()
    base = dict(asset_id="FPT", provider="test-source", observation_date=now.date(), price_vnd=48500,
                revision=1, content_hash="f"*64, unit="VND/share", source_unit="VND/share",
                price_type="close", price_basis="unadjusted", available_at=now, data_origin="real")
    with sessions.begin() as db:
        for change in [{}, {"asset_id": "VCB"}, {"observation_date": now.date() - timedelta(days=2)},
                       {"revision": 2, "available_at": now + timedelta(days=1)}]:
            db.add(PriceRevision(**(base | change)))
    facts = client.get(path, params={"asset_id": "FPT"}, headers=headers).json()
    assert facts["scope"] == "equity_quote" and facts["asset_id"] == "FPT"
    assert [(r["asset_id"], r["revision"]) for r in facts["observations"]] == [("FPT", 1)]
    assert client.get(path, params={"asset_id": "MBB"}, headers=headers).json()["observations"] == []
    assert client.get(path, params={"asset_id": "NOT_A_TICKER"}, headers=headers).status_code == 422

    for days, observed in [(2, 2), (20, 0)]:
        requested = str(now.date() - timedelta(days=days))
        facts = client.get(path, params={"asset_id": "FPT", "requested_date": requested}, headers=headers).json()
        assert facts["requested_date"] == requested
        assert facts["observations"][0]["observation_date"] == str(now.date() - timedelta(days=observed))


def test_description_scoped_to_requested_equity(market):
    from market_service.models import Asset
    _, sessions, provider, _ = market
    client = TestClient(create_app(sessions=sessions, verifier=ChatVerifier(), provider=provider))
    path = "/internal/v1/chat/market-facts"
    params = {"asset_id": "MBB", "description": True}
    with sessions.begin() as db:
        row = db.get(Asset, "MBB")
        if row is None:
            row = Asset(id="MBB", kind="stock", unit="VND/share")
            db.add(row)
        row.display_name, row.description = "Ngân hàng MB", "Dịch vụ ngân hàng."
    headers = {"Authorization":"Bearer chat-service"}
    assert client.get(path, params=params).status_code == 401
    facts = client.get(path, params=params, headers=headers).json()
    assert (facts["scope"], facts["asset_id"], facts["display_name"]) == ("asset_description","MBB","Ngân hàng MB")
    assert client.get(path,params=params | {"requested_date":"2026-11-01"},headers=headers).status_code == 422
