import pytest

from portfolio_service.api import create_app
from portfolio_service.models import Job
from fastapi.testclient import TestClient
from test_workflow import (
    stack as workflow_stack,
    headers,
    portfolio,
    Resolver,
    Verifier,
)  # noqa: F401


@pytest.mark.parametrize(
    "failure,explicit,status,effective",
    [
        ("model", True, 202, "EW"),
        ("model", False, 503, None),
        ("invalid", True, 503, None),
        ("expired", True, 409, None),
    ],
)
def test_fallback_is_explicit_and_only_for_unavailable_ml(
    stack, failure, explicit, status, effective
):
    from portfolio_contracts import ModelUnavailable

    _, sessions = stack
    calls = []

    class Serving(Resolver):
        def ready(self, universe_id, strategy):
            calls.append((universe_id, strategy))
            if strategy == "BL_ML":
                if failure == "model":
                    raise ModelUnavailable("No approved model")
                if failure == "invalid":
                    raise ValueError("Corrupt data")
            value = super().ready(universe_id, strategy)
            if failure == "expired":
                value["valid_until"] = "2020-01-01T00:00:00+00:00"
            return value

    with TestClient(
        create_app(sessions=sessions, verifier=Verifier(), resolver=Serving())
    ) as client:
        pid = portfolio(client)
        body = {"strategy": "BL_ML"}
        if explicit:
            body["fallback_strategy"] = "EW"
        response = client.post(
            f"/api/v1/portfolios/{pid}/recommendations",
            headers=headers(**{"Idempotency-Key": "fallback-key"}),
            json=body,
        )
        assert response.status_code == status, response.text
        assert calls == [("DEMO", "BL_ML")] + ([("DEMO", "EW")] if effective else [])
        if effective:
            with sessions() as session:
                command = session.get(Job, response.json()["job_id"]).input
                assert command["strategy"] == "EW"
                assert command["decision_context"]["requested_strategy"] == "BL_ML"
                assert (
                    command["decision_context"]["fallback_reason"]
                    == "MODEL_UNAVAILABLE"
                )
            assert (
                client.post(
                    f"/api/v1/portfolios/{pid}/recommendations",
                    headers=headers(**{"Idempotency-Key": "fallback-key"}),
                    json=body,
                ).json()
                == response.json()
            )


stack = workflow_stack


def test_legacy_command_hash_is_stable_when_context_is_absent():
    from portfolio_contracts import OptimizeCommand, canonical_hash

    # Independent old wire shape: adding an optional field must not break queued jobs.
    from uuid import uuid4
    from portfolio_contracts import utcnow

    old = {
        "job_id": str(uuid4()),
        "owner_user_id": str(uuid4()),
        "portfolio_id": str(uuid4()),
        "portfolio_version": 1,
        "strategy": "MVO",
        "core_version": "0.1.0",
        "capital_vnd": "100",
        "inputs": Resolver().ready("DEMO", "MVO"),
        "constraints": {
            "risk_aversion": 1.5,
            "max_position_weight": 0.5,
            "defensive_asset_ids": [],
            "min_defensive_weight": 0,
            "max_non_defensive_weight": 1,
        },
        "deadline": utcnow().isoformat(),
    }
    # Normalize timestamps and numerical types exactly like the original command contract.
    normalized = OptimizeCommand.model_validate(
        old | {"input_hash": "0" * 64}
    ).model_dump(mode="json", exclude={"input_hash", "decision_context"})
    normalized["inputs"].pop("provenance", None)  # Absent in the legacy wire contract.
    hashed = canonical_hash(normalized)
    assert (
        OptimizeCommand.model_validate(
            normalized | {"input_hash": hashed}
        ).compute_hash()
        == hashed
    )


def test_pre_upgrade_recommendation_request_keeps_its_idempotency_key(stack):
    from portfolio_contracts import canonical_hash
    from test_workflow import enqueue

    client, sessions = stack
    pid = portfolio(client)
    first = enqueue(client, pid)
    assert first.status_code == 202
    with sessions.begin() as session:
        session.get(Job, first.json()["job_id"]).body_hash = canonical_hash(
            {"strategy": "MVO"}
        )
    response = enqueue(client, pid)
    assert response.status_code == 202, response.text
    assert response.json() == first.json()
