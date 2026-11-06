from fastapi.testclient import TestClient

from portfolio_service.api import create_app
from quant_service.main import create_app as quant_app
from test_workflow import stack as stack_fixture, Verifier, Resolver, headers
from service_auth import Principal

stack = stack_fixture


def test_ready_universes_are_server_owned_authenticated_choices(stack):
    _, sessions = stack
    expected = [
        {
            "universe_id": "REAL",
            "asset_ids": ["FPT", "VCB"],
            "as_of_date": "2026-10-23",
            "demo": False,
        }
    ]

    class Catalog(Resolver):
        def universes(self):
            return expected

    with TestClient(
        create_app(sessions=sessions, verifier=Verifier(), resolver=Catalog())
    ) as client:
        assert client.get("/api/v1/universes").status_code == 401
        assert client.get("/api/v1/universes", headers=headers()).json() == expected

    class ServiceVerifier:
        def verify(self, token):
            return Principal("iss", token, frozenset(), frozenset({"quant:resolve"}))

    with TestClient(
        quant_app(sessions=None, verifier=ServiceVerifier(), catalog=Catalog())
    ) as client:
        assert client.get("/internal/v1/inputs/universes").status_code == 401
        assert (
            client.get("/internal/v1/inputs/universes", headers=headers()).json()
            == expected
        )
