from uuid import uuid4
from fastapi.testclient import TestClient
from portfolio_contracts import utcnow
from market_service.api import create_app
from service_auth import Principal
from test_market import market  # noqa: F401, F811


class ChatVerifier:
    def verify(self, token):
        return Principal(
            "issuer", str(uuid4()), frozenset(), frozenset({"market:chat:read"}), token
        )


def test_market_tool_auth_and_canonical_freshness(market):  # noqa: F811
    _, sessions, provider, _ = market
    c = TestClient(
        create_app(sessions=sessions, verifier=ChatVerifier(), provider=provider)
    )
    path = "/internal/v1/chat/market-facts"
    assert c.get(path).status_code == 401
    assert c.get(path, headers={"Authorization": "Bearer attacker"}).status_code == 403
    r = c.get(path, headers={"Authorization": "Bearer chat-service"})
    assert r.status_code == 200, r.text
    assert r.json()["observations"] == []
    assert r.json()["status"] == "NO_OBSERVATIONS"
    assert r.json()["checked_at"].startswith(str(utcnow().date()))
