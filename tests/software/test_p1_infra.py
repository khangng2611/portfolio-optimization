"""P1 identities and storage preserve prior credentials and owner boundaries."""

from auth_service.api import ROLE_SCOPES, SERVICE_SCOPES
from test_bootstrap import load_bootstrap


def test_ml_storage_and_scoped_service_identities_are_additive(tmp_path):
    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    before = bootstrap.create_secrets()
    assert {
        "ML_RUNTIME_PASSWORD",
        "ML_MIGRATOR_PASSWORD",
        "ML_MARKET_READER_CLIENT_SECRET",
        "ML_READER_CLIENT_SECRET",
    } <= before.keys()
    assert bootstrap.create_secrets() == before
    sql = bootstrap.make_database_sql(before)
    assert "CREATE DATABASE ml_db OWNER ml_owner" in sql
    assert "GRANT CONNECT ON DATABASE ml_db TO ml_migrator, ml_runtime" in sql
    assert {"ml:read", "ml:train"} <= set(ROLE_SCOPES["data-operator"])
    assert {"ml:read", "ml:review"} <= set(ROLE_SCOPES["model-reviewer"])
    assert SERVICE_SCOPES["ml-worker"] == {"market:snapshot:read": "market-api"}
    assert SERVICE_SCOPES["quant-ml-reader"] == {"ml:model:read": "ml-api"}
