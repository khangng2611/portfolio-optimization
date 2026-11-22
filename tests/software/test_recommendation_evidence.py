from copy import deepcopy
from uuid import uuid4

import pytest

from portfolio_contracts import Envelope, OptimizeResult, canonical_hash
from portfolio_service.models import Job, Recommendation
from portfolio_service.workflow import consume_result
from test_chat_delegation import grants as grants_fixture, issue, tool
from test_workflow import enqueue, headers, portfolio, stack as stack_fixture

grants = grants_fixture
stack = stack_fixture


def finish(client, sessions, pid, sidecar=None):
    rid = enqueue(client, pid).json()["job_id"]
    with sessions() as s:
        job = s.get(Job, rid)
        payload = OptimizeResult(
            job_id=rid,
            run_id=uuid4(),
            input_hash=job.input_hash,
            bundle_hash="a" * 64,
            status="SUCCEEDED",
            result=dict(
                strategy="MVO",
                asset_ids=["AAA", "BBB", "VFF"],
                weights=[0.4, 0.3, 0.3],
                status="optimal",
                core_version="0.1.0",
                diagnostics={},
            ),
        )
        if sidecar == "valid":
            from portfolio_contracts.explanation import OptimizationExplanationEvidence

            payload.explanation_evidence = OptimizationExplanationEvidence(
                status="PARTIAL",
                job_id=rid,
                run_id=str(payload.run_id),
                input_hash=job.input_hash,
                bundle_hash=payload.bundle_hash,
                snapshot_id="snapshot-v1",
                asset_ids=payload.result["asset_ids"],
                active_asset_ids=payload.result["asset_ids"],
                limitations=["NOT_RETAINED"],
            ).seal()
    wire = payload.model_dump(mode="json")
    if sidecar is not None and sidecar != "valid":
        wire["explanation_evidence"] = sidecar
    event = Envelope(
        type="quant.optimization.completed",
        producer="quant-serving",
        correlation_id=rid,
        payload=wire,
    )
    consume_result(sessions, event)
    consume_result(sessions, event)
    return rid


@pytest.mark.parametrize(
    "sidecar,status",
    [(None, "PARTIAL"), ({"malformed": True}, "UNAVAILABLE"), ("valid", "PARTIAL")],
)
def test_sidecar_independent_of_canonical_result_and_current_profile(
    stack, sidecar, status
):
    c, sessions = stack
    pid = portfolio(c)
    rid = finish(c, sessions, pid, sidecar)
    url = f"/api/v1/recommendations/{rid}"
    facts = c.get(url, headers=headers()).json()
    r = c.get(url + "/evidence", headers=headers())
    assert r.status_code == 200, r.text
    evidence = r.json()
    assert evidence["status"] == status
    assert evidence["facts_hash"] == canonical_hash(facts)
    assert evidence["recommendation_id"] == rid
    assert facts["weights"] == ["0.4", "0.3", "0.3"]
    assert "explanation_evidence" not in facts
    c.patch(
        f"/api/v1/portfolios/{pid}",
        headers=headers(**{"If-Match": '"1"'}),
        json={"capital_vnd": "200000000"},
    )
    assert c.get(url + "/evidence", headers=headers()).json() == evidence
    assert c.get(url, headers=headers()).json() == facts
    for user in ("bob", "admin"):
        assert c.get(url + "/evidence", headers=headers(user)).status_code == 404
    assert c.get(url + "/evidence").status_code == 401


def test_tampered_pins_do_not_publish_evidence(stack):
    c, sessions = stack
    rid = finish(c, sessions, portfolio(c), "valid")
    with sessions.begin() as s:
        r = s.get(Recommendation, rid)
        changed = deepcopy(r.explanation_evidence)
        changed["snapshot_id"] = "other"
        body = {k: v for k, v in changed.items() if k != "evidence_hash"}
        changed["evidence_hash"] = canonical_hash(body)
        r.explanation_evidence = changed
    response = c.get(
        f"/api/v1/recommendations/{rid}/evidence", headers=headers()
    ).json()
    assert response["status"] == "UNAVAILABLE"
    assert response["quant"] is None


@pytest.mark.parametrize("body", ["malformed", ["malformed"], 42])
def test_non_object_sidecar_does_not_drop_valid_allocation(stack, body):
    c, sessions = stack
    rid = finish(c, sessions, portfolio(c), body)
    facts = c.get(f"/api/v1/recommendations/{rid}", headers=headers())
    assert facts.status_code == 200
    assert facts.json()["weights"] == ["0.4", "0.3", "0.3"]
    evidence = c.get(
        f"/api/v1/recommendations/{rid}/evidence", headers=headers()
    ).json()
    assert evidence["status"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "field", ["snapshot_hash", "regime_end_date", "covariance_end_date"]
)
def test_retained_pins_cannot_be_resealed_to_wrong_source(field):
    from test_selection_worker import selected_command
    from quant_service.selection import resolve_selection
    from quant_service.explanation import build_quant_evidence
    from portfolio_service.explanation import store_evidence

    catalog, command, now = selected_command(["ACB", "BID", "VFF"], strategy="MVO")
    command.job_id = uuid4()
    captured = {}
    numerical, proof, _ = resolve_selection(
        catalog, command, now=now, evidence=captured
    )
    run_id = str(uuid4())
    body = build_quant_evidence(command, run_id, numerical, captured).seal()
    result = {
        "asset_ids": numerical["asset_ids"],
        "diagnostics": {"selection": proof.model_dump(mode="json")},
    }
    cmd = {
        "job_id": str(command.job_id),
        "input_hash": command.input_hash,
        "inputs": command.inputs.model_dump(mode="json"),
        "strategy": "MVO",
        "selection_context": command.selection_context.model_dump(mode="json"),
    }
    assert store_evidence(body, cmd, run_id, result)["status"] == "PARTIAL"
    body[field] = "f" * 64 if field == "snapshot_hash" else "2099-01-01"
    body["evidence_hash"] = canonical_hash(
        {k: v for k, v in body.items() if k != "evidence_hash"}
    )
    assert store_evidence(body, cmd, run_id, result) == {"status": "UNAVAILABLE"}


def test_evidence_tool_obeys_grant_bindings(grants):
    c, sessions, _ = grants
    pid = portfolio(c)
    rid = finish(c, sessions, pid)
    grant = issue(c, pid, tools=["get_recommendation_evidence"]).json()
    assert (
        tool(c, grant, "get_recommendation_evidence", resource_id=rid).status_code
        == 200
    )
    assert tool(c, grant, "get_recommendation", resource_id=rid).status_code == 403
    wrong = grant | {"conversation_id": str(uuid4())}
    assert (
        tool(c, wrong, "get_recommendation_evidence", resource_id=rid).status_code
        == 403
    )
    assert (
        tool(
            c, grant, "get_recommendation_evidence", resource_id=str(uuid4())
        ).status_code
        == 404
    )
    c.post("/api/v1/chat/delegations/revoke", headers=headers(), json={})
    assert (
        tool(c, grant, "get_recommendation_evidence", resource_id=rid).status_code
        == 403
    )
