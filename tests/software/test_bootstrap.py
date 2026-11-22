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


def test_auth_database_and_signing_key_are_separate_and_persistent(tmp_path):
    import base64
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    values = bootstrap.create_secrets()
    sql = bootstrap.make_database_sql(values)
    assert "CREATE DATABASE auth_db OWNER auth_owner" in sql
    assert "GRANT CONNECT ON DATABASE auth_db TO auth_migrator, auth_runtime" in sql
    assert "identity_db" not in sql
    key = bootstrap.signing_key()
    assert bootstrap.signing_key() == key
    assert load_pem_private_key(base64.b64decode(key), None).key_size == 2048
    assert (tmp_path / "auth-signing-key.b64").stat().st_mode & 0o777 == 0o600


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


def test_publication_uses_local_bundle_owner_without_changing_private_permissions(
    tmp_path, monkeypatch
):
    import os
    import sys

    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path / "generated"
    monkeypatch.setattr(sys, "argv", ["bootstrap.py"])
    previous_umask = os.umask(0o077)
    try:
        bootstrap.main()
        environment = dict(
            line.split("=", 1)
            for line in (bootstrap.GENERATED / ".env").read_text().splitlines()
            if line and not line.startswith("#")
        )
        assert environment["LOCAL_BUNDLE_UID"] == str(os.getuid())
        assert environment["LOCAL_BUNDLE_GID"] == str(os.getgid())
        before = (bootstrap.GENERATED / "secrets.json").read_bytes()
        bootstrap.main()
        assert (bootstrap.GENERATED / "secrets.json").read_bytes() == before
        assert bootstrap.GENERATED.stat().st_mode & 0o777 == 0o700
        assert (bootstrap.GENERATED / "bundles").stat().st_mode & 0o777 == 0o755
        assert (
            bootstrap.GENERATED / "bundles/.catalog.lock"
        ).stat().st_mode & 0o777 == 0o600
    finally:
        os.umask(previous_umask)
