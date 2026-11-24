from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from portfolio_contracts import Constraints, OptimizeCommand, canonical_hash
from portfolio_contracts.assets import candidate_hash
from portfolio_contracts.hybrid import hybrid_policy
from portfolio_contracts.selection import SelectionProof
from portfolio_core.hybrid import allocate_hybrid
from portfolio_service.models import (
    Base,
    GoldShadowDecision,
    GoldShadowEnrollment,
    Job,
    Recommendation,
)
from quant_service import gold_shadow_worker as worker
from quant_service import gold_shadow_forecast


@pytest.fixture
def example(monkeypatch):
    now = datetime.fromisoformat("2026-11-27T11:10:00+00:00")  # Friday after close.
    ids = ["ACB", "BID", "CTG", "DGC", "FPT", "GAS", "GOLD", "VFF"]
    active = [asset for asset in ids if asset != "GAS"]
    selected = active[:5]
    numerical = dict(
        asset_ids=ids,
        active_asset_ids=active,
        active_policy_version="user-selection-active-v1",
        mean_returns=[0.001] * len(ids),
        covariance=(np.eye(len(ids)) * 0.001).tolist(),
        market_weights=[1 / len(active) if a in active else 0 for a in ids],
        views_p=[[1, 0, 0, 0, 0, 0, 0, 0]],
        views_q=[0.0001],
        view_confidences=[0.5],
    )
    command = OptimizeCommand(
        job_id=uuid4(),
        owner_user_id=uuid4(),
        portfolio_id=uuid4(),
        portfolio_version=1,
        capital_vnd="1000000",
        strategy="HYBRID",
        input_hash="0" * 64,
        deadline=now + timedelta(minutes=1),
        decision_context=dict(
            risk_profile=dict(profile="growth", version_id="1"),
            policy_version_id="1",
            requested_strategy="HYBRID",
        ),
        constraints=Constraints(defensive_asset_ids=["VFF"], min_defensive_weight=0.15),
        hybrid_policy=hybrid_policy("normal", "growth"),
        inputs=dict(
            bundle_id="fixture",
            bundle_hash="1" * 64,
            snapshot_id="fixture",
            model_bundle_id="2" * 64,
            asset_ids=ids,
            as_of_date=str(now.date()),
            valid_until=now + timedelta(days=5),
        ),
        selection_context=dict(
            revision_id=uuid4(),
            candidate_asset_ids=ids,
            candidate_hash=candidate_hash(ids),
            regime=dict(regime="normal", vol_ratio=1, drawdown=0, equity_momentum=0),
            regime_input_hash="3" * 64,
            decision_at=now,
            decision_session=now.date(),
            valid_until=now + timedelta(days=5),
        ),
    )
    command.input_hash = command.compute_hash()
    constraints = command.constraints.model_dump()
    proof = SelectionProof(
        input_hash=command.input_hash,
        candidate_hash=candidate_hash(ids),
        snapshot_hash="3" * 64,
        panel_hash="4" * 64,
        selection_hash="5" * 64,
        selection_policy_id="user-k5-v1",
        applied_selection="equity-k5-v1",
        decision_session=now.date(),
        selection_price_end_date=now.date() - timedelta(days=1),
        selected_equity_ids=selected,
        active_asset_ids=active,
        rejected_equity_ids=["GAS"],
        effective_constraints_hash=canonical_hash(constraints),
    )
    inference = dict(manifest_hash="2" * 64)
    proposal = allocate_hybrid(
        numerical, constraints, command.hybrid_policy.model_dump()
    )
    proposal.update(
        selection_proof=proof.model_dump(mode="json"),
        constraints=constraints,
        input_hash=command.input_hash,
    )
    proposal["weights"] = list(map(str, proposal["weights"]))
    proposal["diagnostics"]["inference"] = inference
    sessions = sessionmaker(create_engine("sqlite://"), expire_on_commit=False)
    Base.metadata.create_all(sessions.kw["bind"])
    jid, pid, uid = map(
        str, [command.job_id, command.portfolio_id, command.owner_user_id]
    )
    with sessions.begin() as session:
        session.add(
            GoldShadowEnrollment(
                study_id=worker.STUDY, started_at=now - timedelta(hours=1)
            )
        )
        session.add(
            Job(
                id=jid,
                portfolio_id=pid,
                owner_user_id=uid,
                input=command.model_dump(mode="json"),
                status="SUCCEEDED",
                input_hash=command.input_hash,
                body_hash="0" * 64,
                idempotency_key="one",
                deadline=command.deadline,
            )
        )
        session.add(
            Recommendation(
                id=jid,
                job_id=jid,
                portfolio_id=pid,
                owner_user_id=uid,
                run_id=str(uuid4()),
                created_at=now,
                result=proposal,
            )
        )
    catalog = SimpleNamespace(
        load_resource=lambda pin: (dict(panel={"sha256": "9" * 64}), object())
    )
    monkeypatch.setattr(
        worker, "resolve_selection", lambda *a, **kw: (numerical, proof, inference)
    )
    monkeypatch.setattr(
        worker,
        "load_capture",
        lambda *a: dict(
            observed_quote={"bid": 990, "ask": 1000}, warmup_sha256="8" * 64
        ),
    )
    monkeypatch.setattr(
        gold_shadow_forecast,
        "forecast",
        lambda *a, **kw: dict(
            status="active", prediction_5d=0.05, q_daily=0.01, confidence=0.6
        ),
    )
    return sessions, catalog, now, proposal, jid


def test_committed_pair_has_same_inputs_and_preserves_recommendation(example):
    sessions, catalog, now, proposal, jid = example
    original = deepcopy(proposal)
    row = worker.observe_once(
        sessions, catalog, clock=lambda: now + timedelta(seconds=18)
    )
    assert row["status"] == "TARGET"
    assert row["issued_at"] == (now + timedelta(seconds=18)).isoformat()
    assert row["issue_before"] == "2026-11-30T09:00:00+07:00"
    assert row["production_weights"] == list(map(float, original["weights"]))
    assert row["view_coefficients"] == [-0.2] * 5 + [0, 1, 0]
    assert not np.allclose(row["shadow_weights"], row["production_weights"])
    assert row["receipt_sha256"] == canonical_hash(
        {k: v for k, v in row.items() if k != "receipt_sha256"}
    )
    assert worker.observe_once(sessions, catalog, clock=lambda: now) is None
    with sessions() as session:
        stored = session.get(GoldShadowDecision, jid).receipt
        assert stored["receipt_sha256"] == row["issued_receipt_sha256"]
        assert (
            worker.confirmed_receipt(
                *session.execute(worker.witnessed_decisions()).one()
            )
            == row
        )
        assert session.get(Recommendation, jid).result == original
        assert session.get(Job, jid).status == "SUCCEEDED"


def test_late_fit_abstains_and_compute_failure_preserves_production(
    example, monkeypatch
):
    sessions, catalog, now, original, jid = example
    limit = worker.issuance_limit(now.date())
    times = iter([now, limit, limit])
    row = worker.observe_once(sessions, catalog, clock=lambda: next(times))
    assert row["reason"] == "ISSUANCE_WINDOW_CLOSED" and row["shadow_weights"] is None
    with sessions.begin() as session:
        session.delete(session.get(worker.GoldShadowWitness, jid))
        session.flush()
        session.delete(session.get(GoldShadowDecision, jid))

    def unavailable(*args, **kwargs):
        raise ValueError("Missing pinned bid")

    monkeypatch.setattr(worker, "load_capture", unavailable)
    row = worker.observe_once(sessions, catalog, clock=lambda: now)
    assert row["status"] == "ABSTAIN" and row["detail"] == "Missing pinned bid"
    with sessions() as session:
        assert session.get(Recommendation, jid).result == original


def test_ineligible_old_or_uncommitted_proposals_are_ignored(example):
    sessions, catalog, now, _, jid = example
    with sessions.begin() as session:
        session.get(GoldShadowEnrollment, worker.STUDY).started_at = now + timedelta(
            minutes=1
        )
    assert worker.observe_once(sessions, catalog, clock=lambda: now) is None
    with sessions.begin() as session:
        session.get(GoldShadowEnrollment, worker.STUDY).started_at = now - timedelta(
            minutes=1
        )
        session.get(Job, jid).status = "FAILED"
    assert worker.observe_once(sessions, catalog, clock=lambda: now) is None
    with sessions() as session:
        assert session.scalar(select(GoldShadowDecision.job_id)) is None


@pytest.mark.parametrize("late", [False, True])
def test_commit_witness_is_recovered_after_crash_and_checks_deadline(example, late):
    sessions, catalog, now, _, jid = example
    original = worker.register_once(sessions, catalog, lambda: now)
    assert original["status"] == "TARGET"
    with sessions() as session:
        assert session.get(GoldShadowDecision, jid) is not None
        assert session.execute(worker.witnessed_decisions()).first() is None
    measured = worker.issuance_limit(now.date()) if late else now + timedelta(seconds=2)
    actual = worker.observe_once(sessions, catalog, clock=lambda: measured)
    assert actual["issued_receipt_sha256"] == original["receipt_sha256"]
    assert datetime.fromisoformat(actual["witnessed_at"]) == measured
    if late:
        assert actual["reason"] == "DURABILITY_WITNESSED_AFTER_WINDOW"
        assert actual["status"] == "ABSTAIN" and actual["shadow_weights"] is None
        assert "forecast" not in actual
    else:
        assert (
            actual["status"] == "TARGET"
            and actual["shadow_weights"] == original["shadow_weights"]
        )
    with pytest.raises(ValueError, match="witness does not match"):
        worker.confirmed_receipt(
            original | {"run_id": "tampered"}, measured, original["receipt_sha256"]
        )
    assert worker.observe_once(sessions, catalog, clock=lambda: now) is None


def test_calibration_only_uses_previously_witnessed_forecast_in_same_context(example):
    sessions, catalog, now, _, jid = example
    original = worker.register_once(sessions, catalog, lambda: now)
    seen = now + timedelta(hours=1)
    later = original | {
        "decision_session": "2026-12-04",
        "decision_at": seen.isoformat(),
    }
    with sessions() as session:
        assert worker.prior_forecasts(session, later) == []
    worker.witness_once(sessions, lambda: seen)
    with sessions() as session:
        assert (
            worker.prior_forecasts(session, later | {"decision_at": now.isoformat()})
            == []
        )
        assert (
            worker.prior_forecasts(session, later | {"data_policy_id": "other"}) == []
        )
        assert len(worker.prior_forecasts(session, later)) == 1
    # A prior malformed proposal can be logged with only its job/series identity.
    with sessions.begin() as session:
        invalid = {
            "reason": "INVALID_RETAINED_PROPOSAL",
            "issued_at": now.isoformat(),
            "status": "ABSTAIN",
        }
        invalid["receipt_sha256"] = canonical_hash(invalid)
        session.add(
            GoldShadowDecision(
                job_id="invalid", series_id=later["series_id"], receipt=invalid
            )
        )
    worker.witness_once(sessions, lambda: seen)
    with sessions() as session:
        assert worker.prior_forecasts(session, later)[0]["prediction_5d"] == 0.05
