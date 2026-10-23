"""Local reconciliation is additive and can be repeated on an imported realm."""

import importlib.util
import json
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]


def load_upgrade():
    spec = importlib.util.spec_from_file_location(
        "infra.local.upgrade", ROOT / "infra/local/upgrade.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_realm_gains_market_test_access_without_changing_users_web_or_secrets():
    upgrade = load_upgrade()
    state = {
        "users": [{"id": "alice-id", "username": "alice", "password": "keep-password"}],
        "scopes": [{"id": "portfolio-read", "name": "portfolio:read"}],
        "clients": {
            "web-id": {
                "id": "web-id",
                "clientId": "portfolio-web",
                "secret": "keep-web-secret",
                "directAccessGrantsEnabled": False,
            },
            "test-id": {
                "id": "test-id",
                "clientId": "portfolio-test",
                "secret": "keep-test-secret",
                "directAccessGrantsEnabled": True,
            },
        },
        "defaults": {"test-id": [{"id": "portfolio-read", "name": "portfolio:read"}]},
        "mappers": {
            "test-id": [
                {
                    "id": "portfolio-aud",
                    "name": "audience-portfolio-api",
                    "config": {"included.client.audience": "portfolio-api"},
                }
            ]
        },
    }
    original_users = json.dumps(state["users"])
    original_web = json.dumps(state["clients"]["web-id"])

    def serve(request):
        path = request.url.path.removeprefix("/admin/realms/portfolio")
        method = request.method
        payload = json.loads(request.content) if request.content else None
        if path == "/client-scopes":
            if method == "GET":
                return httpx.Response(200, json=state["scopes"])
            state["scopes"].append(dict(payload, id=payload["name"]))
            return httpx.Response(201)
        if path == "/clients":
            if method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        client
                        for client in state["clients"].values()
                        if client["clientId"] == request.url.params["clientId"]
                    ],
                )
            state["clients"][payload["clientId"]] = dict(
                payload, id=payload["clientId"]
            )
            return httpx.Response(201)
        parts = path.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "clients":
            identity = parts[1]
            if parts[2] == "default-client-scopes":
                if method == "GET":
                    return httpx.Response(200, json=state["defaults"].get(identity, []))
                scope = next(
                    scope for scope in state["scopes"] if scope["id"] == parts[3]
                )
                state["defaults"].setdefault(identity, []).append(scope)
                return httpx.Response(204)
            if parts[2:] == ["protocol-mappers", "models"]:
                if method == "GET":
                    return httpx.Response(200, json=state["mappers"].get(identity, []))
                state["mappers"].setdefault(identity, []).append(
                    dict(payload, id=payload["name"])
                )
                return httpx.Response(201)
        raise AssertionError(
            f"Unexpected or destructive identity request: {method} {path}"
        )

    with httpx.Client(
        base_url="http://localhost:8080", transport=httpx.MockTransport(serve)
    ) as client:
        upgrade.reconcile_identity(
            client,
            {
                "TEST_CLIENT_SECRET": "unused-current-secret",
                "OIDC_CLIENT_SECRET": "unused-web-secret",
                "QUANT_CLIENT_SECRET": "unused-quant-secret",
            },
            test_client=True,
        )
        after_first = json.dumps(state, sort_keys=True)
        upgrade.reconcile_identity(
            client,
            {
                "TEST_CLIENT_SECRET": "unused-current-secret",
                "OIDC_CLIENT_SECRET": "unused-web-secret",
                "QUANT_CLIENT_SECRET": "unused-quant-secret",
            },
            test_client=True,
        )
    assert json.dumps(state, sort_keys=True) == after_first
    assert json.dumps(state["users"]) == original_users
    assert json.dumps(state["clients"]["web-id"]) == original_web
    assert state["clients"]["test-id"]["secret"] == "keep-test-secret"
    assert {scope["name"] for scope in state["defaults"]["test-id"]} == {
        "basic",
        "portfolio:read",
        "market:read",
        "market:write",
    }
    for client_id in ("web-id", "portfolio-service"):
        assert "basic" in {scope["name"] for scope in state["defaults"][client_id]}
    basic = next(scope for scope in state["scopes"] if scope["name"] == "basic")
    assert any(
        mapper["protocolMapper"] == "oidc-sub-mapper"
        and mapper["config"]["access.token.claim"] == "true"
        for mapper in basic["protocolMappers"]
    )
    assert {
        mapper["config"]["included.client.audience"]
        for mapper in state["mappers"]["test-id"]
    } == {"portfolio-api", "market-api"}
    assert state["clients"]["market-api"]["bearerOnly"] is True


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


def test_disabled_test_client_flag_never_creates_or_changes_a_password_grant_client():
    upgrade = load_upgrade()
    clients = []
    scopes = [
        {"id": "market-read", "name": "market:read"},
        {"id": "market-write", "name": "market:write"},
    ]

    def serve(request):
        path = request.url.path.removeprefix("/admin/realms/portfolio")
        assert "portfolio-test" not in str(request.url)
        if path == "/client-scopes":
            if request.method == "GET":
                return httpx.Response(200, json=scopes)
            value = json.loads(request.content)
            assert value["name"] == "basic"
            scopes.append(dict(value, id="basic"))
            return httpx.Response(201)
        if path == "/clients":
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        c
                        for c in clients
                        if c["clientId"] == request.url.params["clientId"]
                    ],
                )
            value = json.loads(request.content)
            assert value["clientId"] in {
                "market-api",
                "portfolio-web",
                "portfolio-service",
            }
            assert not value.get("directAccessGrantsEnabled", False)
            clients.append(dict(value, id=value["clientId"]))
            return httpx.Response(201)
        if path.endswith("/default-client-scopes") and request.method == "GET":
            return httpx.Response(200, json=[])
        if path.endswith("/default-client-scopes/basic") and request.method == "PUT":
            return httpx.Response(204)
        raise AssertionError(
            "Disabled test-client setting caused an unexpected identity mutation"
        )

    with httpx.Client(
        base_url="http://localhost:8080", transport=httpx.MockTransport(serve)
    ) as client:
        upgrade.reconcile_identity(
            client,
            {"OIDC_CLIENT_SECRET": "unused", "QUANT_CLIENT_SECRET": "unused"},
            test_client=False,
        )
    assert {c["clientId"] for c in clients} == {
        "market-api",
        "portfolio-web",
        "portfolio-service",
    }
    assert not any(c.get("directAccessGrantsEnabled", False) for c in clients)
