from copy import deepcopy

import pytest

from portfolio_core import allocate
from portfolio_service.workflow import validate_result
from quant_service.selection import resolve_selection
from test_selection_worker import selected_command


def test_consumer_recomputes_selection_proof():
    catalog, command, now = selected_command(
        ["FPT", "MWG", "VCB", "VFF"], strategy="MVO"
    )
    numerical, proof, _ = resolve_selection(catalog, command, now=now)
    result = allocate(
        numerical | dict(strategy="MVO", constraints=command.constraints.model_dump())
    )
    result["diagnostics"]["selection"] = proof.model_dump(mode="json")
    command.inputs.provenance = {
        "snapshot_hash": proof.snapshot_hash,
        "panel_hash": proof.panel_hash,
    }
    raw = dict(
        inputs=command.inputs.model_dump(mode="json"),
        constraints=command.constraints.model_dump(),
        selection_context=command.selection_context.model_dump(mode="json"),
        core_version="0.1.0",
        strategy="MVO",
        input_hash=command.input_hash,
    )

    class ValidResolver:
        def verify_selection(self, *args, **kwargs):
            return True

    validate_result(result, raw, resolver=ValidResolver(), deadline=command.deadline)
    forged = deepcopy(result)
    forged["diagnostics"]["selection"]["active_asset_ids"] = ["FPT", "VFF"]
    forged["diagnostics"]["selection"]["selection_hash"] = "e" * 64

    # A consumer must not accept a self-reported hash without source recomputation.
    class Resolver:
        def verify_selection(self, *args, **kwargs):
            return False

    with pytest.raises(ValueError):
        validate_result(forged, raw, resolver=Resolver(), deadline=command.deadline)
    forged = deepcopy(result)
    forged["diagnostics"]["selection"]["input_hash"] = "f" * 64
    with pytest.raises(ValueError):
        validate_result(forged, raw)


def test_verification_outage_retries_without_losing_result(tmp_path, monkeypatch):
    from uuid import uuid4
    import httpx
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import sessionmaker
    from portfolio_contracts import OptimizeResult, Envelope
    from portfolio_service import workflow
    from portfolio_service.models import (
        Base,
        User,
        Portfolio,
        Job,
        Inbox,
        Recommendation,
    )

    catalog, command, now = selected_command(
        ["FPT", "MWG", "VCB", "VFF"], strategy="MVO"
    )
    numerical, proof, _ = resolve_selection(catalog, command, now=now)
    result = allocate(
        numerical | dict(strategy="MVO", constraints=command.constraints.model_dump())
    )
    result["diagnostics"]["selection"] = proof.model_dump(mode="json")
    command.inputs.provenance = {
        "snapshot_hash": proof.snapshot_hash,
        "panel_hash": proof.panel_hash,
    }
    raw = dict(
        inputs=command.inputs.model_dump(mode="json"),
        constraints=command.constraints.model_dump(),
        selection_context=command.selection_context.model_dump(mode="json"),
        core_version="0.1.0",
        strategy="MVO",
        input_hash=command.input_hash,
        portfolio_version=1,
        capital_vnd="100000000",
    )
    engine = create_engine(f"sqlite:///{tmp_path}/selected.db")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    uid, pid, jid = map(str, (uuid4(), uuid4(), uuid4()))
    with sessions.begin() as session:
        session.add(User(id=uid, issuer="fixture", subject="alice"))
        session.add(
            Portfolio(
                id=pid,
                owner_user_id=uid,
                name="selected",
                capital_vnd=100000000,
                universe_id="USER_SELECTED",
                constraints=raw["constraints"],
                version=2,
            )
        )
        session.add(
            Job(
                id=jid,
                owner_user_id=uid,
                portfolio_id=pid,
                idempotency_key="selected",
                body_hash="c" * 64,
                input_hash=command.input_hash,
                input=raw,
                deadline=command.deadline,
                status="QUEUED",
            )
        )
    payload = OptimizeResult(
        job_id=jid,
        input_hash=command.input_hash,
        run_id=str(uuid4()),
        bundle_hash=command.inputs.bundle_hash,
        status="SUCCEEDED",
        result=result,
        error=None,
    )
    event = Envelope(
        type="quant.optimization.completed",
        producer="quant-serving",
        correlation_id=jid,
        payload=payload.model_dump(mode="json"),
    )
    monkeypatch.setattr(workflow, "utcnow", lambda: now)

    class Resolver:
        available = False

        def verify_selection(self, *args, **kwargs):
            if not self.available:
                raise httpx.ConnectError("temporary verification outage")
            return True

    resolver = Resolver()
    with pytest.raises(httpx.ConnectError):
        workflow.consume_result(sessions, event, resolver=resolver)
    with sessions() as session:
        assert session.get(Job, jid).status == "QUEUED"
        assert session.scalar(select(func.count()).select_from(Inbox)) == 0
    resolver.available = True
    workflow.consume_result(sessions, event, resolver=resolver)
    workflow.consume_result(sessions, event, resolver=resolver)
    with sessions() as session:
        proposal = session.get(Recommendation, jid)
        assert proposal.result["selection_context"] == raw["selection_context"]
        assert proposal.result["portfolio_version"] == 1
        assert proposal.result["valid_until"] == raw["selection_context"]["valid_until"]
        assert session.scalar(select(func.count()).select_from(Recommendation)) == 1
