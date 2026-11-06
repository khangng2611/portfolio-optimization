from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from service_auth import Principal
from portfolio_contracts import utcnow
from portfolio_service.api import create_app
from portfolio_service.models import Base, DelegationGrant
from test_workflow import Resolver, headers, portfolio


class Verifier:
    def verify(self, token):
        return Principal(
            "https://identity",
            token,
            frozenset({"investor"}),
            frozenset({"portfolio:read", "portfolio:write", "chat:delegate"}),
            "chat-service" if token == "chat" else "portfolio-web",
        )


@pytest.fixture
def grants(tmp_path):
    sessions = sessionmaker(
        create_engine(
            f"sqlite:///{tmp_path}/p.db", connect_args={"check_same_thread": False}
        ),
        expire_on_commit=False,
    )
    Base.metadata.create_all(sessions.kw["bind"])
    state = {"active": True}
    with TestClient(
        create_app(
            sessions=sessions,
            verifier=Verifier(),
            resolver=Resolver(),
            account_active=lambda issuer, subject: state["active"],
        )
    ) as client:
        yield client, sessions, state


def issue(client, pid, **changes):
    body = {
        "conversation_id": str(uuid4()),
        "job_id": str(uuid4()),
        "portfolio_id": pid,
        "tools": [
            "get_profile",
            "get_portfolio_summary",
            "request_allocation",
            "get_recommendation",
            "get_allocation_job",
        ],
    }
    return client.post(
        "/internal/v1/delegation-grants",
        headers=headers(**{"X-Service-Authorization": "Bearer chat"}),
        json=body | changes,
    )


def tool(client, grant, name="get_portfolio_summary", **args):
    return client.post(
        f"/internal/v1/chat-tools/{name}",
        headers=headers(
            "chat",
            **{
                "X-Delegation-Grant": grant["grant_id"],
                "X-Chat-Job": grant["job_id"],
                "X-Chat-Conversation": grant["conversation_id"],
            },
        ),
        json=args,
    )


def test_grant_requires_actor_and_current_owner(grants):
    c, _, _ = grants
    pid = portfolio(c)
    assert c.post(
        "/internal/v1/delegation-grants", headers=headers(), json={}
    ).status_code in (401, 422)
    assert issue(c, pid, tools=["accept_target"]).status_code == 422
    b = issue(c, pid).json()
    assert tool(c, b, portfolio_id=pid).status_code == 200
    assert tool(c, b, portfolio_id=str(uuid4())).status_code == 403
    assert tool(c, b, "accept_target").status_code == 404
    assert (
        c.post(
            "/internal/v1/chat-tools/get_profile",
            headers=headers(
                **{
                    "X-Delegation-Grant": b["grant_id"],
                    "X-Chat-Job": b["job_id"],
                    "X-Chat-Conversation": b["conversation_id"],
                }
            ),
            json={},
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/internal/v1/delegation-grants",
            headers=headers("bob", **{"X-Service-Authorization": "Bearer chat"}),
            json={
                "conversation_id": str(uuid4()),
                "job_id": str(uuid4()),
                "portfolio_id": pid,
                "tools": ["get_profile"],
            },
        ).status_code
        == 404
    )


def test_grant_expiry_revoke_disabled_and_binding(grants):
    c, sessions, state = grants
    pid = portfolio(c)
    g = issue(c, pid).json()
    assert tool(c, g | {"job_id": str(uuid4())}, "get_profile").status_code == 403
    state["active"] = False
    assert tool(c, g, "get_profile").status_code == 403
    state["active"] = True
    with sessions.begin() as s:
        s.get(DelegationGrant, g["grant_id"]).expires_at = utcnow() - timedelta(
            seconds=1
        )
    assert tool(c, g, "get_profile").status_code == 403
    g = issue(c, pid).json()
    assert (
        c.post(
            "/api/v1/chat/delegations/revoke", headers=headers(), json={}
        ).status_code
        == 200
    )
    assert tool(c, g, "get_profile").status_code == 403


def test_confirmed_versions_required_and_owner_idempotency(grants):
    c, _, _ = grants
    pid = portfolio(c)
    g = issue(c, pid).json()
    args = {
        "portfolio_id": pid,
        "strategy": "MVO",
        "expected_version": 1,
        "expected_policy_version": "manual-constraints-v1",
    }
    first = tool(c, g, "request_allocation", **args)
    assert first.status_code == 200, first.text
    assert tool(c, g, "request_allocation", **args).json() == first.json()
    assert (
        tool(c, g, "request_allocation", **(args | {"strategy": "EW"})).status_code
        == 409
    )
    g2 = issue(c, pid).json()
    assert (
        tool(
            c, g2, "request_allocation", **(args | {"expected_version": 2})
        ).status_code
        == 409
    )


def test_identity_status_fails_closed_and_checks_role(monkeypatch):
    import httpx
    from portfolio_service.runtime import IdentityStatus

    monkeypatch.setenv("OIDC_ISSUER", "https://identity")
    monkeypatch.setenv(
        "OIDC_TOKEN_URL",
        "https://identity/realms/portfolio/protocol/openid-connect/token",
    )
    monkeypatch.setenv("OIDC_ACCOUNT_READER_SECRET", "private")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **kw: httpx.Response(
            200,
            json={"access_token": "service-private", "expires_in": 60},
            request=httpx.Request("POST", a[0]),
        ),
    )
    state = {"enabled": True, "roles": ["investor"]}

    def get(url, **kw):
        value = (
            [{"name": r} for r in state["roles"]]
            if url.endswith("/composite")
            else {"enabled": state["enabled"]}
        )
        return httpx.Response(200, json=value, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    check = IdentityStatus()
    uid = str(uuid4())
    assert check("https://identity", uid)
    state["enabled"] = False
    assert not check("https://identity", uid)
    state["enabled"] = True
    state["roles"] = []
    assert not check("https://identity", uid)
    assert not check("https://other", uid)

    def outage(*args, **kw):
        raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(httpx, "get", outage)
    assert not check("https://identity", uid)


def test_reconcile_prior_submission_after_portfolio_version_changes(grants):
    c, _, _ = grants
    pid = portfolio(c)
    g = issue(c, pid).json()
    args = {
        "portfolio_id": pid,
        "strategy": "MVO",
        "expected_version": 1,
        "expected_policy_version": "manual-constraints-v1",
    }
    first = tool(c, g, "request_allocation", **args)
    assert first.status_code == 200
    changed = c.patch(
        f"/api/v1/portfolios/{pid}",
        headers=headers(**{"If-Match": '"1"'}),
        json={"capital_vnd": "200000000"},
    )
    assert changed.status_code == 200
    replay = tool(c, g, "request_allocation", **args)
    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert (
        tool(c, issue(c, pid).json(), "request_allocation", **args).status_code == 409
    )
