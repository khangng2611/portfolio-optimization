"""Issue one independent paper target for each enrolled, committed HYBRID proposal."""

import argparse
from datetime import datetime, time, timedelta, timezone
import json
import logging
import os
from pathlib import Path
from time import sleep

import numpy as np
from sqlalchemy import select

from portfolio_contracts import OptimizeCommand, aware, canonical_hash, utcnow
from portfolio_contracts.assets import EQUITY_IDS
from portfolio_contracts.hybrid import constraint_violations, validate_hybrid_weights
from portfolio_core.hybrid import allocate_hybrid
from portfolio_service.models import (
    GoldShadowDecision,
    GoldShadowEnrollment,
    GoldShadowWitness,
    Job,
    Recommendation,
)
from .full import TZ
from .gold_shadow_quotes import load_capture
from .gold_shadow_receipt import confirmed_receipt
from .runtime import catalog_from_env, sessions_from_env
from .selection import resolve_selection

STUDY = "gold-k5-derived-hybrid-shadow-v1"
PROTOCOL_HASH = "8227f058373339b5f8a133598404bcc82e1c8c327528bea66129d57be0f747d3"
REGISTERED = datetime.fromisoformat("2026-11-24T09:34:00+00:00")
VIEW = "gold-k5-derived-v1"


def issuance_limit(day):
    # On exchange holidays the weekday bound abstains conservatively.
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(9), TZ)


def witnessed_decisions():
    return select(
        GoldShadowDecision.receipt,
        GoldShadowWitness.witnessed_at,
        GoldShadowWitness.receipt_sha256,
    ).join(GoldShadowWitness, GoldShadowWitness.job_id == GoldShadowDecision.job_id)


def prior_forecasts(session, record):
    origins = {}
    for committed in session.execute(
        witnessed_decisions().where(
            GoldShadowDecision.series_id == record["series_id"],
            GoldShadowWitness.witnessed_at
            <= datetime.fromisoformat(record["decision_at"]),
        )
    ):
        old = confirmed_receipt(*committed)
        forecast = old.get("forecast") or {}
        if (
            forecast.get("prediction_5d") is None
            or old["protocol_sha256"] != PROTOCOL_HASH
            or any(
                old.get(key) != record[key]
                for key in (
                    "candidate_hash",
                    "data_policy_id",
                    "selection_policy_id",
                    "applied_selection",
                    "risk_profile",
                    "policy_version",
                    "constraints_hash",
                )
            )
            or old["decision_session"] >= record["decision_session"]
            or old.get("reason") not in (None, "calibration_warmup")
        ):
            continue
        entry = {
            k: old[k] for k in ("decision_session", "selected_equity_ids", "issued_at")
        }
        entry["prediction_5d"] = forecast["prediction_5d"]
        previous = origins.get(entry["decision_session"])
        if previous is None or entry["issued_at"] < previous["issued_at"]:
            origins[entry["decision_session"]] = entry
    return [origins[key] for key in sorted(origins)]


def compute(record, command, proposal, catalog, history):
    from .gold_shadow_forecast import forecast

    context = command.selection_context
    source, panel = catalog.load_resource(command.inputs)
    numerical, proof, inference = resolve_selection(
        catalog, command, now=context.decision_at
    )
    if (
        proof.model_dump(mode="json") != proposal["selection_proof"]
        or inference != proposal["diagnostics"]["inference"]
        or numerical["asset_ids"] != record["asset_ids"]
    ):
        raise ValueError(
            "Pinned production inputs do not reproduce the served selection"
        )
    constraints, policy = (
        command.constraints.model_dump(),
        command.hybrid_policy.model_dump(),
    )
    baseline = allocate_hybrid(numerical, constraints, policy)
    if not np.allclose(
        baseline["weights"], record["production_weights"], rtol=0, atol=1e-8
    ):
        raise ValueError("Pinned production inputs do not reproduce the served target")
    capture = load_capture(
        panel,
        context.decision_session,
        context.decision_at,
        Path(os.environ.get("GOLD_SHADOW_DATASETS", "/datasets")),
        Path(os.environ.get("GOLD_SHADOW_ARCHIVE", "/gold-shadow/archive.csv")),
    )
    capture["prior_forecasts"] = history
    record.update(
        observed_quote=capture["observed_quote"],
        warmup_sha256=capture["warmup_sha256"],
        immutable_panel_sha256=source["panel"]["sha256"],
        numerical_sha256=canonical_hash(numerical),
    )
    selected = record["selected_equity_ids"]
    prediction = forecast(panel, context.decision_session, selected, capture=capture)
    record["forecast"] = prediction
    if prediction["status"] != "active":
        return prediction["status"]
    row = [
        1.0 if asset == "GOLD" else -0.2 if asset in selected else 0.0
        for asset in record["asset_ids"]
    ]
    shadow = numerical | dict(
        views_p=[*numerical["views_p"], row],
        views_q=[*numerical["views_q"], prediction["q_daily"]],
        view_confidences=[*numerical["view_confidences"], prediction["confidence"]],
    )
    candidate = allocate_hybrid(shadow, constraints, policy)
    comparison = candidate["diagnostics"]["hybrid"]
    comparison["ew_constraint_violations"] = constraint_violations(
        record["asset_ids"], comparison["ew_weights"], constraints
    )
    validate_hybrid_weights(
        record["asset_ids"], proof.active_asset_ids, constraints, policy, candidate
    )
    if not np.allclose(
        proposal["diagnostics"]["hybrid"]["mvo_weights"],
        comparison["mvo_weights"],
        rtol=0,
        atol=1e-8,
    ):
        raise ValueError("Serving MVO leg differs from the comparison")
    record.update(view_coefficients=row, shadow_weights=candidate["weights"])
    return None


def issue(session, recommendation, job, catalog, enrolled_at, clock):
    command = OptimizeCommand.model_validate(job.input)
    context = command.selection_context
    proposal = recommendation.result
    proof = proposal["selection_proof"]
    assets, selected = proposal["asset_ids"], proof["selected_equity_ids"]
    limit = min(
        issuance_limit(context.decision_session),
        context.valid_until,
        command.inputs.valid_until,
    )
    record = dict(
        study_id=STUDY,
        protocol_sha256=PROTOCOL_HASH,
        enrolled_at=enrolled_at.isoformat(),
        job_id=job.id,
        input_hash=job.input_hash,
        run_id=recommendation.run_id,
        series_id=recommendation.portfolio_id,
        registered_at=aware(recommendation.created_at).isoformat(),
        decision_session=str(context.decision_session),
        decision_at=context.decision_at.isoformat(),
        valid_until=context.valid_until.isoformat(),
        issue_before=limit.isoformat(),
        asset_ids=assets,
        selected_equity_ids=selected,
        active_asset_ids=proof["active_asset_ids"],
        production_weights=[float(w) for w in proposal["weights"]],
        shadow_weights=None,
        policy_version=command.hybrid_policy.version,
        mvo_share=command.hybrid_policy.mvo_share,
        risk_profile=command.decision_context.risk_profile["profile"],
        constraints_hash=canonical_hash(proposal["constraints"]),
        candidate_hash=context.candidate_hash,
        selection_hash=proof["selection_hash"],
        selection_policy_id=context.selection_policy_id,
        applied_selection=proof["applied_selection"],
        data_policy_id=context.data_policy_id,
        view_protocol=VIEW,
        horizon_sessions=5,
        execution_lag_sessions=1,
        snapshot_id=command.inputs.snapshot_id,
        snapshot_hash=proof["snapshot_hash"],
        panel_hash=proof["panel_hash"],
        bundle_hash=command.inputs.bundle_hash,
        model_bundle_id=command.inputs.model_bundle_id,
    )
    if (
        command.compute_hash() != job.input_hash
        or command.input_hash != proposal["input_hash"]
        or str(command.job_id) != recommendation.job_id
        or str(command.portfolio_id) != recommendation.portfolio_id
    ):
        reason = "PROPOSAL_IDENTITY_MISMATCH"
    elif context.decision_at < enrolled_at:
        reason = "DECISION_BEFORE_ENROLLMENT"
    elif (
        "GOLD" not in proof["active_asset_ids"]
        or len(selected) != 5
        or [a for a in proof["active_asset_ids"] if a in EQUITY_IDS] != selected
    ):
        reason = "REQUIRES_GOLD_AND_FIVE_SELECTED_EQUITIES"
    elif clock() >= limit:
        reason = "ISSUANCE_WINDOW_CLOSED"
    else:
        try:
            reason = compute(
                record, command, proposal, catalog, prior_forecasts(session, record)
            )
        except Exception as exc:
            logging.exception("Gold shadow computation failed for job %s", job.id)
            reason = "SHADOW_INPUT_OR_CALCULATION_UNAVAILABLE"
            record["detail"] = (
                str(exc)[:240] if isinstance(exc, ValueError) else type(exc).__name__
            )
    issued = clock()
    if issued < max(context.decision_at, aware(recommendation.created_at), enrolled_at):
        reason = "OBSERVER_CLOCK_BEFORE_PROPOSAL"
    if issued >= limit and reason in (None, "fit_warmup", "calibration_warmup"):
        reason = "ISSUANCE_WINDOW_CLOSED"
    if reason:
        record["shadow_weights"] = None
    record.update(
        status="ABSTAIN" if reason else "TARGET",
        reason=reason,
        issued_at=issued.isoformat(),
    )
    record["receipt_sha256"] = canonical_hash(record)
    return record


def register_once(sessions, catalog, clock):
    with sessions.begin() as session:
        # Only observer replicas lock this row. Proposal and job rows remain readable and writable.
        enrollment = session.scalar(
            select(GoldShadowEnrollment)
            .where(GoldShadowEnrollment.study_id == STUDY)
            .with_for_update(skip_locked=True)
        )
        if enrollment is None:
            return None
        started = max(REGISTERED, aware(enrollment.started_at))
        pair = session.execute(
            select(Recommendation, Job)
            .join(Job, Job.id == Recommendation.job_id)
            .where(
                Recommendation.created_at >= started,
                Job.status == "SUCCEEDED",
                Job.input["strategy"].as_string() == "HYBRID",
                Job.input["inputs"]["demo"].as_boolean().is_(False),
                ~select(GoldShadowDecision.job_id)
                .where(GoldShadowDecision.job_id == Job.id)
                .exists(),
            )
            .order_by(Recommendation.created_at, Job.id)
            .limit(1)
        ).first()
        if not pair:
            return None
        recommendation, job = pair
        try:
            receipt = issue(session, recommendation, job, catalog, started, clock)
        except (KeyError, TypeError, ValueError) as exc:
            logging.exception("Invalid retained proposal for job %s", job.id)
            receipt = dict(
                study_id=STUDY,
                protocol_sha256=PROTOCOL_HASH,
                job_id=job.id,
                run_id=recommendation.run_id,
                series_id=recommendation.portfolio_id,
                input_hash=job.input_hash,
                status="ABSTAIN",
                reason="INVALID_RETAINED_PROPOSAL",
                detail=type(exc).__name__,
                issued_at=clock().isoformat(),
            )
            receipt["receipt_sha256"] = canonical_hash(receipt)
        session.add(
            GoldShadowDecision(
                job_id=job.id, series_id=recommendation.portfolio_id, receipt=receipt
            )
        )
    return receipt


def witness_once(sessions, clock):
    with sessions.begin() as session:
        # Read from a new transaction. A stalled issuance commit cannot be backdated.
        row = session.scalar(
            select(GoldShadowDecision)
            .where(
                ~select(GoldShadowWitness.job_id)
                .where(GoldShadowWitness.job_id == GoldShadowDecision.job_id)
                .exists()
            )
            .order_by(GoldShadowDecision.job_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        witnessed_at = clock().astimezone(timezone.utc)
        digest = row.receipt["receipt_sha256"]
        result = confirmed_receipt(row.receipt, witnessed_at, digest)
        session.add(
            GoldShadowWitness(
                job_id=row.job_id, witnessed_at=witnessed_at, receipt_sha256=digest
            )
        )
    return result


def observe_once(sessions, catalog, *, clock=utcnow):
    recovered = witness_once(sessions, clock)
    if recovered is not None:
        return recovered
    if register_once(sessions, catalog, clock) is not None:
        return witness_once(sessions, clock)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "once", "export"])
    action = parser.parse_args().action
    sessions = sessions_from_env()
    if action == "export":
        with sessions() as session:
            for row in session.execute(
                witnessed_decisions().order_by(GoldShadowDecision.job_id)
            ):
                print(json.dumps(confirmed_receipt(*row), allow_nan=False))
        return
    catalog = catalog_from_env().selection_catalog
    if action == "once":
        print(json.dumps(observe_once(sessions, catalog), allow_nan=False))
        return
    while True:
        try:
            if observe_once(sessions, catalog) is not None:
                continue
        except Exception:
            logging.exception(
                "Gold shadow observer unavailable; pending proposals remain registered"
            )
        sleep(5)


if __name__ == "__main__":
    main()
