"""Chat local ownership and machine identities upgrade without rotating old state."""

import importlib.util
import base64
import json
from pathlib import Path

import httpx

from test_bootstrap import load_bootstrap
from test_p1_compose import service
from test_infra_upgrade import load_upgrade

ROOT = Path(__file__).resolve().parents[2]


def test_chat_credentials_database_and_machine_clients_are_additive(tmp_path):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    values = bootstrap.create_secrets()
    additions = {
        "CHAT_MIGRATOR_PASSWORD",
        "CHAT_RUNTIME_PASSWORD",
        "CHAT_CLIENT_SECRET",
        "PORTFOLIO_ACCOUNT_READER_SECRET",
    }
    assert additions <= values.keys()
    old = {key: value for key, value in values.items() if key not in additions}
    bootstrap.write_private(tmp_path / "secrets.json", json.dumps(old))
    upgraded = bootstrap.create_secrets()
    assert all(upgraded[key] == value for key, value in old.items())
    assert bootstrap.create_secrets() == upgraded
    sql = bootstrap.make_database_sql(upgraded)
    assert "CREATE DATABASE chat_db OWNER chat_owner" in sql
    assert "GRANT CONNECT ON DATABASE chat_db TO chat_migrator, chat_runtime" in sql
    realm = bootstrap.make_realm(upgraded, [], True)
    clients = {client["clientId"]: client for client in realm["clients"]}
    chat = clients["chat-service"]
    assert chat["serviceAccountsEnabled"] and not chat["directAccessGrantsEnabled"]
    assert not chat["standardFlowEnabled"]
    assert set(chat["defaultClientScopes"]) == {
        "basic",
        "chat:delegate",
        "market:chat:read",
    }
    assert {
        mapper["config"]["included.client.audience"]
        for mapper in chat["protocolMappers"]
    } == {"portfolio-api", "market-api"}
    for name in ("portfolio-web", "portfolio-test"):
        client = clients[name]
        assert {"chat:read", "chat:write"} <= set(client["defaultClientScopes"])
        assert any(
            m["config"].get("included.client.audience") == "chat-api"
            for m in client["protocolMappers"]
        )
    assert clients["chat-api"]["bearerOnly"]
    reader = clients["portfolio-account-reader"]
    assert reader["serviceAccountsEnabled"] and not reader["directAccessGrantsEnabled"]
    assert reader["defaultClientScopes"] == ["basic"]
    account = next(
        user
        for user in realm["users"]
        if user.get("serviceAccountClientId") == "portfolio-account-reader"
    )
    assert account["clientRoles"] == {"realm-management": ["view-users"]}
    assert not account.get("realmRoles")
    assert not any(
        user.get("serviceAccountClientId") == "chat-service" and user.get("realmRoles")
        for user in realm["users"]
    )


def test_chat_compose_has_owner_database_worker_and_bff_routes():
    source = (ROOT / "infra/local/compose.yaml").read_text()
    migration = service("chat-migrate")
    assert "services/chat/Dockerfile" in migration
    assert "chat_migrator:" in migration and "/chat_db" in migration
    assert "alembic" in migration
    assert "chat_runtime:" in source and "OIDC_AUDIENCE: chat-api" in source
    assert "127.0.0.1:8005:8000" in service("chat-api")
    worker = service("chat-worker")
    assert '"chat_service.worker"' in worker
    assert "chat-migrate: {condition: service_completed_successfully}" in worker
    assert "chat_job" in worker
    assert "BROKER_URL" not in worker
    assert "CHAT_CLIENT_SECRET:" in source
    assert "OIDC_ACCOUNT_READER_SECRET: ${PORTFOLIO_ACCOUNT_READER_SECRET" in source
    assert "CHAT_API_URL: http://chat-api:8000" in service("web")
    assert "chat:read chat:write" in service("web")


def test_setup_installs_and_validates_chat_editable_package(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "chat_setup", ROOT / "scripts/setup_software.py"
    )
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    assert "services/chat" in setup.PACKAGES
    monkeypatch.setattr(setup, "VENV", tmp_path)
    calls = []
    monkeypatch.setattr(
        setup, "run", lambda command, **kwargs: calls.append(command) or ""
    )
    assert setup.python_environment_ready()
    assert "portfolio-chat-service" in calls[0][2]


def test_account_reader_role_reconciliation_adds_only_view_users_and_is_idempotent():
    upgrade = load_upgrade()
    assigned = []
    mutations = []
    role = {
        "id": "view-id",
        "name": "view-users",
        "clientRole": True,
        "containerId": "management-id",
    }

    def serve(request):
        path = request.url.path.removeprefix(upgrade.REALM)
        if path == "/clients" and request.method == "GET":
            assert request.url.params["clientId"] == "realm-management"
            return httpx.Response(
                200, json=[{"id": "management-id", "clientId": "realm-management"}]
            )
        if path == "/clients/reader-id/service-account-user":
            return httpx.Response(200, json={"id": "reader-user"})
        if path == "/clients/management-id/roles/view-users":
            return httpx.Response(200, json=role)
        if path == "/users/reader-user/role-mappings/clients/management-id":
            if request.method == "GET":
                return httpx.Response(200, json=assigned)
            assert request.method == "POST"
            payload = json.loads(request.content)
            assert payload == [role]
            assigned.extend(payload)
            mutations.append(path)
            return httpx.Response(204)
        raise AssertionError(f"Unexpected identity request: {request.method} {path}")

    with httpx.Client(
        base_url="http://localhost:8080", transport=httpx.MockTransport(serve)
    ) as client:
        upgrade.reconcile_account_reader_role(client, "reader-id")
        upgrade.reconcile_account_reader_role(client, "reader-id")
    assert assigned == [role]
    assert len(mutations) == 1


def test_live_boundary_verifies_chat_and_account_reader_machine_claims(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "chat_boundaries", ROOT / "infra/local/verify_boundaries.py"
    )
    boundaries = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boundaries)
    generated = tmp_path / ".generated"
    generated.mkdir()
    (generated / "accounts.json").write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "alice",
                        "password": "local-pass",
                        "roles": ["investor"],
                    }
                ]
            }
        )
    )
    (generated / "settings.json").write_text(json.dumps({"test_client": False}))
    monkeypatch.setattr(boundaries, "ROOT", tmp_path)
    requested = []

    def token(claims):
        payload = (
            base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        )
        return "unused." + payload + ".unused"

    def serve(request):
        from urllib.parse import parse_qs

        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200, json={"issuer": "http://localhost:8080/realms/portfolio"}
            )
        if path.endswith("/token"):
            data = parse_qs(request.content.decode())
            name = data["client_id"][0]
            requested.append(name)
            if name == "portfolio-web":
                return httpx.Response(400, json={"error": "unauthorized_client"})
            assert data["grant_type"] == ["client_credentials"]
            if name == "chat-service":
                claims = {
                    "aud": ["portfolio-api", "market-api"],
                    "scope": "chat:delegate market:chat:read",
                }
            else:
                assert name == "portfolio-account-reader"
                claims = {
                    "resource_access": {"realm-management": {"roles": ["view-users"]}}
                }
            return httpx.Response(200, json={"access_token": token(claims)})
        if path == "/admin/realms/portfolio/users":
            assert request.method == "GET" and request.url.params["username"] == "alice"
            return httpx.Response(200, json=[{"id": "alice-id"}])
        if path == "/admin/realms/portfolio/users/alice-id":
            assert request.method == "GET"
            return httpx.Response(200, json={"id": "alice-id", "enabled": True})
        if (
            path
            == "/admin/realms/portfolio/users/alice-id/role-mappings/realm/composite"
        ):
            assert request.method == "GET"
            return httpx.Response(200, json=[{"name": "investor"}])
        raise AssertionError(f"Unexpected boundary request: {request.method} {path}")

    original_client = httpx.Client
    monkeypatch.setattr(
        boundaries.httpx,
        "Client",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(serve), **kwargs
        ),
    )
    boundaries.verify_identity(
        {
            "OIDC_CLIENT_SECRET": "web",
            "CHAT_CLIENT_SECRET": "chat",
            "PORTFOLIO_ACCOUNT_READER_SECRET": "reader",
        }
    )
    assert requested == ["portfolio-web", "chat-service", "portfolio-account-reader"]
