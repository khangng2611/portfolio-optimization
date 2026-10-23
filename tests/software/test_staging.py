"""Staging rejects insecure endpoints, unversioned images and missing credentials."""

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_validator():
    spec = importlib.util.spec_from_file_location(
        "staging_validate", ROOT / "infra/staging/validate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def staging_values():
    return {
        "WEB_IMAGE": "registry.example.invalid/web:0.1.0",
        "PORTFOLIO_IMAGE": "registry.example.invalid/portfolio:0.1.0",
        "QUANT_IMAGE": "registry.example.invalid/quant:0.1.0",
        "MARKET_IMAGE": "registry.example.invalid/market:0.1.0",
        "APP_ORIGIN": "https://app.example.invalid",
        "OIDC_ISSUER": "https://identity.example.invalid/realms/portfolio",
        "OIDC_JWKS_URL": "https://identity.example.invalid/realms/portfolio/protocol/openid-connect/certs",
        "OIDC_TOKEN_URL": "https://identity.example.invalid/realms/portfolio/protocol/openid-connect/token",
        "OIDC_INTERNAL_ORIGIN": "https://identity.example.invalid",
        "OIDC_CLIENT_ID": "portfolio-web",
        "OIDC_CLIENT_SECRET": "a-real-confidential-client-secret",
        "QUANT_CLIENT_SECRET": "a-real-service-client-secret",
        "SESSION_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        "REDIS_URL": "rediss://runtime:redis-secret@redis.example.invalid:6379/0",
        "PORTFOLIO_DATABASE_URL": "postgresql+psycopg://portfolio_runtime:pw@postgres.example.invalid/portfolio_db?sslmode=verify-full",
        "PORTFOLIO_MIGRATION_DATABASE_URL": "postgresql+psycopg://portfolio_migrator:pw@postgres.example.invalid/portfolio_db?sslmode=verify-full",
        "QUANT_DATABASE_URL": "postgresql+psycopg://quant_runtime:pw@postgres.example.invalid/quant_db?sslmode=verify-full",
        "QUANT_MIGRATION_DATABASE_URL": "postgresql+psycopg://quant_migrator:pw@postgres.example.invalid/quant_db?sslmode=verify-full",
        "MARKET_DATABASE_URL": "postgresql+psycopg://market_runtime:pw@postgres.example.invalid/market_db?sslmode=verify-full",
        "MARKET_MIGRATION_DATABASE_URL": "postgresql+psycopg://market_migrator:pw@postgres.example.invalid/market_db?sslmode=verify-full",
        "PORTFOLIO_PUBLISHER_BROKER_URL": "amqps://portfolio_publisher:pw@broker.example.invalid:5671/portfolio",
        "PORTFOLIO_CONSUMER_BROKER_URL": "amqps://portfolio_consumer:pw@broker.example.invalid:5671/portfolio",
        "QUANT_PUBLISHER_BROKER_URL": "amqps://quant_publisher:pw@broker.example.invalid:5671/portfolio",
        "QUANT_CONSUMER_BROKER_URL": "amqps://quant_consumer:pw@broker.example.invalid:5671/portfolio",
        "MARKET_PUBLISHER_BROKER_URL": "amqps://market_publisher:pw@broker.example.invalid:5671/portfolio",
        "MARKET_CONSUMER_BROKER_URL": "amqps://market_consumer:pw@broker.example.invalid:5671/portfolio",
        "BUNDLE_DIRECTORY": "/srv/portfolio/bundles",
        "DATASET_DIRECTORY": "/srv/portfolio/datasets",
        "TLS_CA_DIRECTORY": "/srv/portfolio/ca",
    }


def test_staging_accepts_external_secure_dependencies_with_distinct_runtime_roles():
    load_validator().validate(staging_values())


@pytest.mark.parametrize(
    "key,value",
    [
        ("OIDC_ISSUER", "http://identity.example.invalid/realms/portfolio"),
        ("REDIS_URL", "redis://runtime:secret@redis.example.invalid:6379/0"),
        (
            "MARKET_PUBLISHER_BROKER_URL",
            "amqp://market_publisher:pw@broker.example.invalid/portfolio",
        ),
        (
            "MARKET_DATABASE_URL",
            "postgresql+psycopg://market_runtime:pw@postgres.example.invalid/market_db",
        ),
        ("MARKET_IMAGE", "registry.example.invalid/market:latest"),
        ("MARKET_IMAGE", "registry.example.invalid/market"),
        ("OIDC_CLIENT_SECRET", ""),
        ("OIDC_CLIENT_SECRET", "CHANGE_ME"),
        ("SESSION_ENCRYPTION_KEY", "short"),
    ],
)
def test_staging_rejects_insecure_or_incomplete_configuration_without_exposing_values(
    key, value
):
    values = staging_values()
    values[key] = value
    with pytest.raises(ValueError) as error:
        load_validator().validate(values)
    assert key in str(error.value)
    assert value not in str(error.value) if value else True


def test_staging_rejects_shared_database_or_migrator_runtime_identity():
    values = staging_values()
    values["MARKET_DATABASE_URL"] = values["PORTFOLIO_DATABASE_URL"]
    values["MARKET_MIGRATION_DATABASE_URL"] = values["PORTFOLIO_MIGRATION_DATABASE_URL"]
    with pytest.raises(ValueError, match="database"):
        load_validator().validate(values)
    values = staging_values()
    values["MARKET_DATABASE_URL"] = values["MARKET_MIGRATION_DATABASE_URL"]
    with pytest.raises(ValueError, match="MARKET_DATABASE_URL"):
        load_validator().validate(values)


@pytest.mark.parametrize(
    "key,value",
    [
        ("ALLOW_INSECURE_HTTP", "true"),
        ("ALLOW_DEMO_INPUTS", "true"),
        ("OIDC_CLIENT_ID", "portfolio-test"),
    ],
)
def test_staging_rejects_local_development_bypasses(key, value):
    values = staging_values()
    values[key] = value
    with pytest.raises(ValueError, match=key):
        load_validator().validate(values)


def test_example_cli_validates_without_a_deployed_service_or_optional_dependencies(
    tmp_path,
):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "infra/staging/validate.py"),
            "--env-file",
            str(ROOT / "infra/staging/.env.example"),
            "--allow-example",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "no services were deployed" in result.stdout
    assert "CHANGE_ME" not in result.stdout + result.stderr
