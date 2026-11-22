"""Chat local ownership and machine identities upgrade without rotating old state."""

import importlib.util
import json
import sys
from pathlib import Path

from test_bootstrap import load_bootstrap
from test_p1_compose import service
from auth_service.api import BASE_SCOPES, SERVICE_SCOPES

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
    assert SERVICE_SCOPES["chat-service"] == {
        "chat:delegate": "portfolio-api",
        "market:chat:read": "market-api",
        "knowledge:retrieve": "knowledge-api",
    }
    assert {"chat:read", "chat:write"} <= set(BASE_SCOPES)


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
    assert "AUTH_ACCOUNT_READER_SECRET: ${PORTFOLIO_ACCOUNT_READER_SECRET" in source
    assert "CHAT_API_URL: http://chat-api:8000" in service("web")
    assert "AUTH_API_URL: http://auth-api:8000" in service("web")


def test_setup_installs_and_validates_chat_editable_package(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "chat_setup", ROOT / "scripts/setup_software.py"
    )
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    assert "services/chat" in setup.PACKAGES
    monkeypatch.setattr(setup, "VENV", tmp_path)
    monkeypatch.setattr(setup, "PYTHON", Path(sys.executable))
    calls = []
    monkeypatch.setattr(
        setup, "run", lambda command, **kwargs: calls.append(command) or ""
    )
    assert setup.python_environment_ready()
    assert "portfolio-chat-service" in calls[0][2]
