from pathlib import Path
from auth_service.api import ROLE_SCOPES, SERVICE_SCOPES
from test_bootstrap import load_bootstrap
from test_p1_compose import service

ROOT = Path(__file__).resolve().parents[2]


def test_knowledge_is_separate_cluster_and_additive_identity(tmp_path):
    b = load_bootstrap()
    b.GENERATED = tmp_path
    values = b.create_secrets()
    before = dict(values)
    assert "KNOWLEDGE_RUNTIME_PASSWORD" in values
    assert b.create_secrets() == before
    sql = b.make_knowledge_database_sql(values)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE DATABASE knowledge_db OWNER knowledge_owner" in sql
    assert {"knowledge:read", "knowledge:write"} <= set(ROLE_SCOPES["data-operator"])
    assert SERVICE_SCOPES["chat-service"]["knowledge:retrieve"] == "knowledge-api"
    pg = service("knowledge-postgres")
    assert "ports:" not in pg and "knowledge-data:" in pg
    assert "postgres-data:" not in pg
    assert "127.0.0.1:8006:8000" in service("knowledge-api")
    assert "OPENAI_API_KEY" not in service("knowledge-api")
