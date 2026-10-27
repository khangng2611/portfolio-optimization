"""Deployment topology keeps source/model artifact writers within their owner."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def service(name):
    source = (ROOT / "infra/local/compose.yaml").read_text()
    match = re.search(
        r"^  " + re.escape(name) + r":\n(.*?)(?=^  [a-z][a-z-]*:|\Z)",
        source,
        re.M | re.S,
    )
    assert match, f"Missing service {name}"
    return match.group(1)


def test_refresh_worker_owns_only_child_dataset_write_mount():
    worker = service("market-refresh")
    assert '["python", "-m", "market_service.refresh_worker"]' in worker
    assert (
        'user: "${LOCAL_BUNDLE_UID:?Run bootstrap.py}:${LOCAL_BUNDLE_GID:?Run bootstrap.py}"'
        in worker
    )
    assert "REFRESH_ARTIFACT_DIRECTORY: /datasets/refresh" in worker
    assert "./.generated/datasets:/datasets:ro" in worker
    assert "./.generated/datasets/refresh:/datasets/refresh:rw" in worker
    for reader in ["market-api", "market-consume"]:
        assert "./.generated/datasets/refresh:/datasets/refresh:ro" in service(reader)
    assert "market-migrate: {condition: service_completed_successfully}" in worker
    assert "refresh_job" in worker and "os.W_OK" in worker


def test_ml_owner_has_separate_database_and_single_artifact_writer():
    source = (ROOT / "infra/local/compose.yaml").read_text()
    assert "image: portfolio-software-ml:local" in service("ml-migrate")
    assert "ml_migrator:" in service("ml-migrate")
    assert "ml_runtime:" in source
    assert "ML_ARTIFACT_DIRECTORY: /ml-models" in source
    assert "./.generated/ml-models:/ml-models:ro" in service("ml-api")
    assert "./.generated/ml-models:/ml-models:rw" in service("ml-worker")
    assert "ML_MARKET_READER_CLIENT_SECRET" in service("ml-worker")
    assert "127.0.0.1:8004:8000" in service("ml-api")
    assert "ml-migrate: {condition: service_completed_successfully}" in service(
        "ml-worker"
    )
    for name in ["quant-api", "quant-dispatch", "quant-consume", "quant-publication"]:
        assert "./.generated/ml-models:/bundles/ml-models:ro" in service(name)
    assert "ML_API_URL: http://ml-api:8000" in source
    assert "ML_READER_CLIENT_SECRET" in source
    assert "ML_API_URL: http://ml-api:8000" in service("web")
    assert "ml:read ml:train ml:review" in service("web")


def test_quant_model_resolver_has_client_credentials_token_endpoint():
    source = (ROOT / "infra/local/compose.yaml").read_text()
    quant_environment = source.split("x-quant-environment:", 1)[1].split(
        "x-market-environment:", 1
    )[0]
    assert (
        "OIDC_TOKEN_URL: http://keycloak:8080/realms/portfolio/protocol/openid-connect/token"
        in quant_environment
    )
