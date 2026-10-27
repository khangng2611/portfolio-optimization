"""P1 identities and storage preserve prior credentials and owner boundaries."""

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
    clients = {
        c["clientId"]: c for c in bootstrap.make_realm(before, [], True)["clients"]
    }
    assert {"ml:read", "ml:train", "ml:review"} <= set(
        clients["portfolio-web"]["optionalClientScopes"]
    )
    for name, scope, audience in [
        ("ml-worker", "market:snapshot:read", "market-api"),
        ("quant-ml-reader", "ml:model:read", "ml-api"),
    ]:
        client = clients[name]
        assert client["serviceAccountsEnabled"]
        assert not client["directAccessGrantsEnabled"]
        assert set(client["defaultClientScopes"]) == {"basic", scope}
        assert [
            m["config"]["included.client.audience"] for m in client["protocolMappers"]
        ] == [audience]
