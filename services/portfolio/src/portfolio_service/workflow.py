import json
import math
from datetime import datetime

from sqlalchemy import select

from portfolio_contracts import Envelope, OptimizeResult, aware, utcnow
from service_observability import link_job, log_event, span
from .models import Inbox, Job, Portfolio, Recommendation


def validate_result(result, command):
    # Reject non-JSON/nonfinite diagnostics before PostgreSQL JSON persistence.
    json.dumps(result, allow_nan=False)
    ids = command["inputs"]["asset_ids"]
    weights = result.get("weights", [])
    c = command["constraints"]
    if (
        result.get("asset_ids") != ids
        or not isinstance(weights, list)
        or len(weights) != len(ids)
        or result.get("core_version") != command["core_version"]
        or result.get("strategy") != command["strategy"]
        or result.get("status") != "optimal"
        or not isinstance(result.get("diagnostics"), dict)
    ):
        raise ValueError("Result metadata does not match the accepted command")
    if any(
        isinstance(w, bool)
        or not isinstance(w, (int, float))
        or not math.isfinite(w)
        or w < -1e-7
        or w > c["max_position_weight"] + 1e-7
        for w in weights
    ):
        raise ValueError("Invalid or infeasible final weights")
    if abs(sum(weights) - 1) > 1e-7:
        raise ValueError("Invalid weight sum")
    defensive = sum(
        w for asset, w in zip(ids, weights) if asset in c["defensive_asset_ids"]
    )
    if (
        defensive + 1e-7 < c["min_defensive_weight"]
        or 1 - defensive > c["max_non_defensive_weight"] + 1e-7
    ):
        raise ValueError("Defensive constraints violated")


def consume_result(sessions, event: Envelope):
    if (
        event.type != "quant.optimization.completed"
        or event.producer != "quant-serving"
    ):
        raise ValueError("Unexpected producer/type")
    payload = OptimizeResult.model_validate(event.payload)
    if event.correlation_id != payload.job_id:
        raise ValueError("Correlation mismatch")
    link_job(None, payload.job_id)
    attributes = {"job.id": str(payload.job_id), "event.id": str(event.event_id)}
    with sessions.begin() as session:
        job = session.scalar(
            select(Job).where(Job.id == str(payload.job_id)).with_for_update()
        )
        if (
            not job
            or payload.input_hash != job.input_hash
            or payload.bundle_hash != job.input["inputs"]["bundle_hash"]
        ):
            raise ValueError("Unmatched result")
        if session.get(Inbox, event.event_id):
            log_event("portfolio.result", job_id=job.id, event_id=str(event.event_id), outcome="duplicate_delivery")
            return
        session.add(Inbox(event_id=event.event_id))
        if job.status != "QUEUED":
            log_event("portfolio.result", job_id=job.id, event_id=str(event.event_id), outcome="terminal_job")
            return
        def fail(error, code):
            with span("portfolio.result.persist", attributes=attributes | {"status": "FAILED", "error.code": code}):
                job.status, job.error = "FAILED", error
                session.flush()
                log_event("portfolio.result.persist", job_id=job.id, event_id=str(event.event_id), status="FAILED", error_code=code)

        portfolio = session.scalar(
            select(Portfolio).where(Portfolio.id == job.portfolio_id).with_for_update()
        )
        if aware(job.deadline) <= utcnow():
            fail({"code": "DEADLINE_EXCEEDED", "message": "Quá thời hạn tính toán."}, "DEADLINE_EXCEEDED")
            return
        if payload.status == "FAILED":
            fail(payload.error or {"code": "QUANT_FAILED"}, "QUANT_FAILED")
            return
        try:
            with span("portfolio.result.validate", attributes=attributes):
                validate_result(payload.result or {}, job.input)
                if portfolio.version != job.input["portfolio_version"]:
                    raise ValueError("Portfolio changed")
                if (
                    aware(datetime.fromisoformat(job.input["inputs"]["valid_until"]))
                    <= utcnow()
                ):
                    raise ValueError("Input expired")
        except (ValueError, TypeError) as exc:
            fail({"code": "INVALID_QUANT_RESULT", "message": str(exc)}, "INVALID_QUANT_RESULT")
            return
        result = payload.result | {
            "weights": [str(w) for w in payload.result["weights"]],
            "data_snapshot_id": job.input["inputs"]["snapshot_id"],
            "model_bundle_id": job.input["inputs"]["model_bundle_id"],
            "input_hash": job.input_hash,
            "bundle_hash": payload.bundle_hash,
            "portfolio_version": job.input["portfolio_version"],
            "constraints": job.input["constraints"],
            "capital_vnd": job.input["capital_vnd"],
            "as_of_date": job.input["inputs"]["as_of_date"],
            "valid_until": job.input["inputs"]["valid_until"],
            "demo": job.input["inputs"]["demo"],
        }
        with span("portfolio.result.persist", attributes=attributes | {"status": "SUCCEEDED"}):
            session.add(
                Recommendation(
                    id=job.id, job_id=job.id, owner_user_id=job.owner_user_id,
                    portfolio_id=job.portfolio_id, run_id=str(payload.run_id), result=result,
                )
            )
            job.status, job.recommendation_id = "SUCCEEDED", job.id
            session.flush()
            log_event("portfolio.result.persist", job_id=job.id, event_id=str(event.event_id), status="SUCCEEDED")
