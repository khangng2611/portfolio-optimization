"""G2 business boundaries; these tests catch policy spoofing and stale acceptance."""

from datetime import timedelta
from uuid import uuid4

import pytest
from portfolio_contracts import Envelope, OptimizeResult, utcnow
from portfolio_service.models import Job
from portfolio_service.workflow import consume_result
from test_workflow import stack as workflow_stack, headers, portfolio, enqueue  # noqa: F401

stack = workflow_stack


def answers(**changes):
    return {
        "questionnaire_version": "risk-v1",
        "horizon_months": 36,
        "liquidity_need": "low",
        "loss_tolerance": "medium",
        "experience": "experienced",
        **changes,
    }


def onboard(client, **changes):
    return client.post(
        "/api/v1/onboarding/portfolios",
        headers=headers(),
        json={
            "name": "Mục tiêu dài hạn",
            "capital_vnd": "100000000",
            "universe_id": "DEMO",
            "answers": answers(**changes),
        },
    )


def complete(client, sessions, pid, key="test-key"):
    jid = enqueue(client, pid, key).json()["job_id"]
    with sessions() as session:
        job = session.get(Job, jid)
        payload = OptimizeResult(
            job_id=jid,
            input_hash=job.input_hash,
            run_id=uuid4(),
            bundle_hash="a" * 64,
            status="SUCCEEDED",
            result={
                "strategy": "MVO",
                "asset_ids": ["AAA", "BBB", "VFF"],
                "weights": [0.4, 0.3, 0.3],
                "status": "optimal",
                "core_version": "0.1.0",
                "diagnostics": {},
            },
        )
    consume_result(
        sessions,
        Envelope(
            type="quant.optimization.completed",
            producer="quant-serving",
            correlation_id=jid,
            payload=payload.model_dump(mode="json"),
        ),
    )
    return jid


def accept(client, rid, version="1", user="alice"):
    return client.post(
        f"/api/v1/recommendations/{rid}/accept",
        headers=headers(user, **{"If-Match": f'"{version}"'}),
        json={},
    )


@pytest.mark.parametrize(
    "changes,profile,risk",
    [
        ({}, "balanced", 3.0),
        ({"loss_tolerance": "high", "horizon_months": 60}, "growth", 1.5),
        ({"loss_tolerance": "high", "liquidity_need": "high"}, "conservative", 6.0),
        ({"horizon_months": 6}, "conservative", 6.0),
        ({"loss_tolerance": "high", "experience": "beginner"}, "balanced", 3.0),
    ],
)
def test_backend_assigns_policy_from_most_conservative_answer(
    stack, changes, profile, risk
):
    client, _ = stack
    response = onboard(client, **changes)
    assert response.status_code == 201, response.text
    value = response.json()
    assert value["risk_profile"]["profile"] == profile
    assert value["risk_profile"]["answers"] == answers(**changes)
    assert value["constraints"]["risk_aversion"] == risk
    assert value["policy_version_id"] == (
        f"risk-policy-v1:{profile}:{value['risk_profile']['version_id']}"
    )
    assert (
        client.get(
            f"/api/v1/portfolios/{value['id']}", headers=headers("bob")
        ).status_code
        == 404
    )


def test_rejects_unknown_questionnaire_and_policy_injection(stack):
    client, _ = stack
    assert onboard(client, questionnaire_version="risk-v99").status_code == 422
    assert onboard(client, risk_aversion=0.1).status_code == 422
    assert onboard(client, horizon_months=0).status_code == 422


def test_accept_persists_target_retry_and_dashboard_without_executing_holdings(stack):
    client, sessions = stack
    p = onboard(client).json()
    assert "id" in p, p
    rid = complete(client, sessions, p["id"])
    result = client.get(f"/api/v1/recommendations/{rid}", headers=headers()).json()
    assert result["policy_version_id"] == p["policy_version_id"]
    response = accept(client, rid)
    assert response.status_code == 200, response.text
    target = response.json()
    assert target["recommendation_id"] == rid
    assert target["allocation"]["weights"] == ["0.4", "0.3", "0.3"]
    assert target["allocation"]["risk_profile"] == p["risk_profile"]
    assert target["portfolio_version"] == 2
    assert response.headers["etag"] == '"2"'
    assert accept(client, rid).json() == target
    dashboard = client.get(
        f"/api/v1/portfolios/{p['id']}/dashboard", headers=headers()
    ).json()
    assert dashboard["accepted_target"] == target
    assert dashboard["holdings_status"] == "NOT_TRACKED"
    assert dashboard["portfolio"]["version"] == 2
    assert dashboard["proposal_count"] == 1
    assert client.get(
        f"/api/v1/portfolios/{p['id']}/targets", headers=headers()
    ).json() == [target]
    for user in ["bob", "admin"]:
        assert accept(client, rid, user=user).status_code == 404
        for suffix in ["dashboard", "targets"]:
            assert (
                client.get(
                    f"/api/v1/portfolios/{p['id']}/{suffix}", headers=headers(user)
                ).status_code
                == 404
            )


def test_accept_requires_precondition_and_blocks_stale_portfolio(stack):
    client, sessions = stack
    pid = portfolio(client)
    rid = complete(client, sessions, pid)
    assert (
        client.post(
            f"/api/v1/recommendations/{rid}/accept", headers=headers(), json={}
        ).status_code
        == 428
    )
    assert accept(client, rid, "99").status_code == 412
    assert (
        client.patch(
            f"/api/v1/portfolios/{pid}",
            headers=headers(**{"If-Match": '"1"'}),
            json={"capital_vnd": "2000"},
        ).status_code
        == 200
    )
    assert accept(client, rid, "2").status_code == 409


def test_accept_blocks_expired_proposal_and_second_proposal_after_accept(stack):
    client, sessions = stack
    pid = portfolio(client)
    first = complete(client, sessions, pid, "first")
    second = complete(client, sessions, pid, "second")
    assert accept(client, first).status_code == 200
    assert accept(client, second, "2").status_code == 409
    pid2 = portfolio(client)
    expired = complete(client, sessions, pid2, "expired")
    with sessions.begin() as session:
        job = session.get(Job, expired)
        job.input = {
            **job.input,
            "inputs": {
                **job.input["inputs"],
                "valid_until": (utcnow() - timedelta(seconds=1)).isoformat(),
            },
        }
    assert accept(client, expired).status_code == 409


def test_manual_constraint_edit_removes_risk_label_and_freezes_old_policy(stack):
    client, sessions = stack
    response = onboard(client)
    assert response.status_code == 201, response.text
    pid = response.json()["id"]
    jid = enqueue(client, pid).json()["job_id"]
    updated = client.patch(
        f"/api/v1/portfolios/{pid}",
        headers=headers(**{"If-Match": '"1"'}),
        json={"risk_aversion": 2},
    ).json()
    assert updated["risk_profile"] is None
    assert updated["policy_version_id"] == "manual-constraints-v1"
    with sessions() as session:
        assert (
            session.get(Job, jid).input["decision_context"]["policy_version_id"]
            == response.json()["policy_version_id"]
        )
