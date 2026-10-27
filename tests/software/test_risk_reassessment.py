"""Immutable risk revisions, authorization, replay and frozen decision pins."""

import copy
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from sqlalchemy import func, select

from portfolio_contracts import canonical_hash
from portfolio_service.models import AcceptedTarget, Job, Portfolio
from test_onboarding import accept, answers, complete, onboard
from test_workflow import headers, portfolio, stack as workflow_stack

stack = workflow_stack


def url(pid):
    return f"/api/v1/portfolios/{pid}/risk-assessments"


def confirm(client, pid, version=1, key="assessment-1", changes=None, user="alice"):
    return client.post(
        url(pid),
        headers=headers(user, **{"If-Match": f'"{version}"', "Idempotency-Key": key}),
        json={"answers": answers(**(changes or {}))},
    )


def test_preview_is_pure_and_server_maps_answers(stack):
    client, sessions = stack
    pid = portfolio(client)
    before = client.get(f"/api/v1/portfolios/{pid}", headers=headers()).json()
    response = client.post(
        url(pid) + "/preview", headers=headers(), json={"answers": answers()}
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["portfolio_id"] == pid
    assert preview["portfolio_version"] == 1
    assert preview["before"] == {
        k: before[k] for k in ("constraints", "risk_profile", "policy_version_id")
    }
    assert preview["after"]["risk_profile"]["profile"] == "balanced"
    assert preview["after"]["constraints"]["risk_aversion"] == 3
    assert response.headers["etag"] == '"1"'
    assert client.get(f"/api/v1/portfolios/{pid}", headers=headers()).json() == before
    assert client.get(url(pid), headers=headers()).json() == []
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_confirm_has_stable_immutable_replay_and_history(stack):
    client, _ = stack
    p = onboard(client).json()
    pid = p["id"]
    initial = client.get(url(pid), headers=headers()).json()
    assert len(initial) == 1
    assert initial[0]["reason"] == "onboarding"
    assert initial[0]["is_active"] is True
    assert initial[0]["id"] == p["risk_profile"]["version_id"]
    first = confirm(client, pid)
    assert first.status_code == 201, first.text
    revision = first.json()
    UUID(revision["id"])
    assert revision["reason"] == "reassessment"
    assert revision["answers"] == answers()
    assert revision["portfolio_version"] == 2
    assert revision["risk_profile"]["version_id"] == revision["id"]
    assert revision["policy_version_id"] == f"risk-policy-v1:balanced:{revision['id']}"
    assert first.headers["etag"] == '"2"'
    # A later change cannot replace the original receipt or its ETag.
    assert (
        confirm(client, pid, 2, "assessment-2", {"horizon_months": 6}).status_code
        == 201
    )
    replay = confirm(client, pid)
    assert replay.status_code == 201
    assert replay.json() == revision
    assert replay.headers["etag"] == first.headers["etag"]
    history = client.get(url(pid), headers=headers(), params={"limit": 2, "offset": 1})
    assert history.status_code == 200
    assert history.headers["x-total-count"] == "3"
    assert history.headers["x-limit"] == "2"
    assert history.headers["x-offset"] == "1"
    assert [r["id"] for r in history.json()] == [revision["id"], initial[0]["id"]]
    assert not any(r["is_active"] for r in history.json())
    current = client.get(url(pid), headers=headers()).json()
    assert current[0]["is_active"] is True
    assert (
        confirm(client, pid, 3, "assessment-1", {"horizon_months": 6}).status_code
        == 409
    )


def test_validation_ownership_and_preconditions(stack):
    client, _ = stack
    pid = portfolio(client)
    for user in ("bob", "admin"):
        for suffix, method in (("", "get"), ("", "post"), ("/preview", "post")):
            kwargs = {
                "headers": headers(
                    user, **{"If-Match": '"1"', "Idempotency-Key": "secret"}
                )
            }
            if method == "post":
                kwargs["json"] = {"answers": answers()}
            assert (
                getattr(client, method)(url(pid) + suffix, **kwargs).status_code == 404
            )
    assert (
        client.post(
            url(pid),
            headers=headers(**{"Idempotency-Key": "key"}),
            json={"answers": answers()},
        ).status_code
        == 428
    )
    assert (
        client.post(
            url(pid),
            headers=headers(**{"If-Match": '"1"'}),
            json={"answers": answers()},
        ).status_code
        == 400
    )
    assert confirm(client, pid, 99).status_code == 412
    assert (
        client.post(
            url(pid) + "/preview",
            headers=headers(),
            json={"answers": answers(risk_aversion=1)},
        ).status_code
        == 422
    )
    assert (
        client.post(
            url(pid),
            headers=headers(**{"If-Match": '"1"', "Idempotency-Key": "key"}),
            json={"answers": answers(), "constraints": {}},
        ).status_code
        == 422
    )
    for params in ({"limit": 101}, {"offset": -1}):
        assert client.get(url(pid), headers=headers(), params=params).status_code == 422


def test_manual_override_deactivates_profile_without_rewriting_history(stack):
    client, _ = stack
    p = onboard(client).json()
    pid = p["id"]
    history = client.get(url(pid), headers=headers()).json()
    assert len(history) == 1
    updated = client.patch(
        f"/api/v1/portfolios/{pid}",
        headers=headers(**{"If-Match": '"1"'}),
        json={"risk_aversion": 2},
    ).json()
    assert updated["risk_profile"] is None
    after = client.get(url(pid), headers=headers()).json()
    assert after == [history[0] | {"is_active": False}]


def test_reassessment_blocks_old_proposals_and_preserves_accepted_target_bytes(stack):
    client, sessions = stack
    p = onboard(client).json()
    pid = p["id"]
    accepted_rid = complete(client, sessions, pid, "accepted")
    target = accept(client, accepted_rid).json()
    old_pending = complete(client, sessions, pid, "old-pending")
    with sessions() as session:
        old_job = copy.deepcopy(session.get(Job, old_pending).input)
        old_hash = session.get(Job, old_pending).input_hash
        target_allocation = canonical_hash(
            session.scalar(select(AcceptedTarget)).allocation
        )
    revision = confirm(client, pid, 2).json()
    assert revision["portfolio_version"] == 3
    assert accept(client, old_pending, "3").status_code == 409
    assert client.get(
        f"/api/v1/portfolios/{pid}/targets", headers=headers()
    ).json() == [target]
    with sessions() as session:
        assert session.get(Job, old_pending).input == old_job
        assert session.get(Job, old_pending).input_hash == old_hash
        assert (
            canonical_hash(session.scalar(select(AcceptedTarget)).allocation)
            == target_allocation
        )
    fresh = complete(client, sessions, pid, "fresh")
    result = client.get(f"/api/v1/recommendations/{fresh}", headers=headers()).json()
    assert result["risk_profile"]["version_id"] == revision["id"]
    assert result["policy_version_id"] == revision["policy_version_id"]
    assert accept(client, fresh, "3").status_code == 200


def test_legacy_current_state_is_not_fabricated_and_input_hash_stays_legacy(stack):
    client, sessions = stack
    pid = portfolio(client)
    legacy = {
        "profile": "balanced",
        "answers": answers(),
        "mapping_version": "risk-policy-v1",
    }
    with sessions.begin() as session:
        session.get(Portfolio, pid).risk_profile = legacy
    assert client.get(url(pid), headers=headers()).json() == []
    rid = complete(client, sessions, pid)
    with sessions() as session:
        before = copy.deepcopy(session.get(Job, rid).input)
    assert before["decision_context"]["policy_version_id"] == "risk-policy-v1:balanced"
    assert before["decision_context"]["risk_profile"] == legacy
    assert confirm(client, pid).status_code == 201
    with sessions() as session:
        assert session.get(Job, rid).input == before


def test_concurrent_confirm_with_same_version_has_single_winner(stack):
    client, _ = stack
    pid = portfolio(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda n: confirm(client, pid, key=f"race-{n}"), range(2))
        )
    assert sorted(response.status_code for response in responses) == [201, 412]
    assert len(client.get(url(pid), headers=headers()).json()) == 1
