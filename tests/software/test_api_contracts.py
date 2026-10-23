import ssl

from portfolio_service.api import create_app as portfolio_app
from quant_service.main import create_app as quant_app


def test_portfolio_swagger_bearer_security():
    schema = portfolio_app(sessions=None, verifier=None, resolver=None).openapi()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/api/v1/portfolios"]["post"]["security"] == [
        {"HTTPBearer": []}
    ]
    assert not schema["paths"]["/health/live"]["get"].get("security")


def test_quant_swagger_service_bearer_security():
    schema = quant_app(sessions=None, verifier=None, catalog=None).openapi()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/internal/v1/inputs/ready"]["get"]["security"] == [
        {"HTTPBearer": []}
    ]


def test_staging_broker_verifies_certificate_and_hostname(monkeypatch):
    from portfolio_contracts.broker import connection_from_url

    monkeypatch.setenv("BROKER_CA_FILE", "/ca/ca.pem")
    connection = connection_from_url(
        "amqps://publisher:password@broker.example:5671/portfolio"
    )
    assert connection.ssl == {
        "cert_reqs": ssl.CERT_REQUIRED,
        "ca_certs": "/ca/ca.pem",
        "server_hostname": "broker.example",
    }
    assert connection.transport_options["confirm_publish"] is True


def test_development_broker_remains_plaintext():
    from portfolio_contracts.broker import connection_from_url

    connection = connection_from_url(
        "amqp://publisher:password@localhost:5673/portfolio"
    )
    assert not connection.ssl
