from test_p1_compose import service


def test_selection_consumer_has_scoped_quant_resolver_config():
    consumer = service("portfolio-consume")
    for line in (
        "OIDC_TOKEN_URL: http://auth-api:8000/internal/v1/token",
        "QUANT_API_URL: http://quant-api:8000",
        "QUANT_CLIENT_SECRET: ${QUANT_CLIENT_SECRET:?Run bootstrap.py}",
    ):
        assert line in consumer, (
            "Proof consumer requires existing scoped resolver config: "
            + line.split(":", 1)[0]
        )
