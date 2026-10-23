"""Disposable local configuration keeps existing credentials and input identities."""

import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re

import pytest
from quant_service.artifacts import ArtifactCatalog


ROOT = Path(__file__).resolve().parents[2]


def load_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "local_bootstrap", ROOT / "infra/local/bootstrap.py"
    )
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    return bootstrap


def test_demo_refresh_preserves_queued_jobs_pinned_bundle(tmp_path):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    bootstrap.create_bundle(refresh=False)
    catalog = ArtifactCatalog(tmp_path / "bundles", allow_demo=True)
    old = catalog.ready("DEMO", "MVO")
    bootstrap.create_bundle(refresh=True)
    current = catalog.ready("DEMO", "MVO")
    assert current.bundle_id != old.bundle_id
    assert catalog.load(old, "MVO")["asset_ids"] == old.asset_ids


def test_legacy_secrets_gain_market_credentials_without_rotating_existing_values(
    tmp_path,
):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    old = bootstrap.create_secrets()
    market_names = {
        "MARKET_MIGRATOR_PASSWORD",
        "MARKET_RUNTIME_PASSWORD",
        "MARKET_PUBLISHER_PASSWORD",
        "MARKET_CONSUMER_PASSWORD",
    }
    legacy = {name: value for name, value in old.items() if name not in market_names}
    bootstrap.write_private(tmp_path / "secrets.json", json.dumps(legacy))
    upgraded = bootstrap.create_secrets()
    assert market_names <= upgraded.keys()
    assert all(upgraded[name] == value for name, value in legacy.items())
    assert bootstrap.create_secrets() == upgraded
    assert (tmp_path / "secrets.json").stat().st_mode & 0o777 == 0o600


def test_missing_existing_password_requires_restore_instead_of_rotation(tmp_path):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    values = bootstrap.create_secrets()
    values.pop("PORTFOLIO_RUNTIME_PASSWORD")
    bootstrap.write_private(tmp_path / "secrets.json", json.dumps(values))
    before = (tmp_path / "secrets.json").read_bytes()
    with pytest.raises(SystemExit, match="restore"):
        bootstrap.create_secrets()
    assert (tmp_path / "secrets.json").read_bytes() == before


def test_market_audience_and_scopes_are_available_only_to_disposable_test_client(
    tmp_path,
):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    values = bootstrap.create_secrets()
    realm = bootstrap.make_realm(values, [], test_client=True)
    clients = {client["clientId"]: client for client in realm["clients"]}
    assert {"market:read", "market:write"} <= {
        scope["name"] for scope in realm["clientScopes"]
    }
    assert clients["market-api"]["bearerOnly"] is True
    test = clients["portfolio-test"]
    assert {"market:read", "market:write"} <= set(test["defaultClientScopes"])
    assert {"portfolio-api", "market-api"} == {
        mapper["config"]["included.client.audience"]
        for mapper in test["protocolMappers"]
    }
    web = clients["portfolio-web"]
    assert not {"market:read", "market:write"} & set(web["defaultClientScopes"])
    assert [
        mapper["config"]["included.client.audience"]
        for mapper in web["protocolMappers"]
    ] == ["portfolio-api"]
    assert "portfolio-test" not in {
        client["clientId"]
        for client in bootstrap.make_realm(values, [], test_client=False)["clients"]
    }


def test_every_token_issuing_client_provides_a_subject_for_api_ownership(tmp_path):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    realm = bootstrap.make_realm(bootstrap.create_secrets(), [], test_client=True)
    scopes = {scope["name"]: scope for scope in realm["clientScopes"]}
    for client in realm["clients"]:
        if client.get("bearerOnly"):
            continue
        mappers = list(client.get("protocolMappers", []))
        for scope in client["defaultClientScopes"]:
            mappers.extend(scopes[scope].get("protocolMappers", []))
        assert any(
            mapper["protocolMapper"] == "oidc-sub-mapper"
            and mapper["config"]["access.token.claim"] == "true"
            for mapper in mappers
        ), client["clientId"]


def test_market_broker_users_cannot_write_read_or_declare_another_owners_resources(
    tmp_path,
):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    definitions = bootstrap.make_rabbit_definitions(bootstrap.create_secrets())
    permissions = {item["user"]: item for item in definitions["permissions"]}
    publisher, consumer = (
        permissions["market_publisher"],
        permissions["market_consumer"],
    )
    assert re.fullmatch(publisher["write"], "market.commands")
    assert re.fullmatch(consumer["read"], "market.ingest.v1")
    for resource in [
        "portfolio.commands",
        "portfolio.events",
        "portfolio.results.v1",
        "quant.optimize.v1",
        "market.ingest.v1.dead",
    ]:
        assert re.fullmatch(publisher["write"], resource) is None
        assert re.fullmatch(consumer["read"], resource) is None
    for item in [publisher, consumer]:
        assert re.fullmatch(item["configure"], "market.ingest.v1") is None
    assert re.fullmatch(publisher["read"], "market.ingest.v1") is None
    assert re.fullmatch(consumer["write"], "market.commands") is None
    queues = {item["name"]: item for item in definitions["queues"]}
    assert queues["market.ingest.v1"]["durable"] is True
    assert queues["market.ingest.v1"]["arguments"] == {
        "x-queue-type": "quorum",
        "x-delivery-limit": 3,
        "x-dead-letter-exchange": "portfolio.dead",
    }
    assert queues["market.ingest.v1.dead"]["arguments"]["x-queue-type"] == "quorum"
    assert any(
        re.search(policy["pattern"], "market.ingest.v1")
        and policy["definition"]["dead-letter-strategy"] == "at-least-once"
        for policy in definitions["policies"]
    )


def test_market_demo_catalog_pins_immutable_current_csv_and_preserves_prior_file(
    tmp_path,
):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    bootstrap.create_market_dataset(refresh=False)
    catalog = tmp_path / "datasets/catalog.json"
    first = json.loads(catalog.read_text())["DEMO_STOCK"]
    csv_path = tmp_path / "datasets" / first["path"]
    before = csv_path.read_bytes()
    assert first["sha256"] == hashlib.sha256(before).hexdigest()
    assert first["asset_id"] == "DEMO_STOCK"
    assert first["kind"] == "stock"
    assert first["source_unit"] == "VND/share"
    rows = list(csv.DictReader(before.decode().splitlines()))
    assert rows[-1]["date"] == datetime.now(timezone.utc).date().isoformat()
    assert len(rows) == 2
    bootstrap.create_market_dataset(refresh=True)
    second = json.loads(catalog.read_text())["DEMO_STOCK"]
    assert second["path"] != first["path"]
    assert csv_path.read_bytes() == before
