"""Local broker reconciliation is additive and repeatable."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_upgrade():
    spec = importlib.util.spec_from_file_location(
        "infra.local.upgrade", ROOT / "infra/local/upgrade.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_broker_upgrade_payload_does_not_replace_an_existing_owners_users():
    upgrade = load_upgrade()
    values = {
        "RABBITMQ_ADMIN_PASSWORD": "admin",
        "PORTFOLIO_PUBLISHER_PASSWORD": "p-pub",
        "PORTFOLIO_CONSUMER_PASSWORD": "p-con",
        "QUANT_PUBLISHER_PASSWORD": "q-pub",
        "QUANT_CONSUMER_PASSWORD": "q-con",
        "MARKET_PUBLISHER_PASSWORD": "m-pub",
        "MARKET_CONSUMER_PASSWORD": "m-con",
    }
    definitions = upgrade.market_broker_definitions(values)
    assert {user["name"] for user in definitions["users"]} == {
        "market_publisher",
        "market_consumer",
    }
    assert {item["user"] for item in definitions["permissions"]} == {
        "market_publisher",
        "market_consumer",
    }
    assert {item["name"] for item in definitions["exchanges"]} == {"market.commands"}
    assert {item["name"] for item in definitions["queues"]} == {
        "market.ingest.v1",
        "market.ingest.v1.dead",
    }
