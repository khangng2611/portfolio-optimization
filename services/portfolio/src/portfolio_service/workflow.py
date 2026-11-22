import json
import math
from datetime import datetime

from sqlalchemy import select

from portfolio_contracts import Envelope, OptimizeResult, aware, utcnow
from portfolio_contracts.selection import SelectionProof
from service_observability import link_job, log_event, span
from .models import Inbox, Job, Portfolio, Recommendation
from .explanation import store_evidence


def validate_result(result, command, *, resolver=None, deadline=None):
    # Reject non-JSON/nonfinite diagnostics before PostgreSQL JSON persistence.
    json.dumps(result, allow_nan=False)
    context = command.get("selection_context")
    ids = context["candidate_asset_ids"] if context else command["inputs"]["asset_ids"]
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
    phase = (command["inputs"].get("provenance") or {}).get("phase1_full")
    if phase and command["strategy"] == "BL_ML":
        active = phase["active_asset_ids"]
        if any(abs(w) > 1e-7 for asset, w in zip(ids, weights) if asset not in active):
            raise ValueError("Inactive asset has nonzero weight")
        inference = result["diagnostics"].get("inference") or {}
        if (
            not isinstance(inference, dict)
            or any(
                inference.get(key) != phase[key]
                for key in (
                    "selection_id",
                    "selection_epoch",
                    "fit_epoch",
                    "active_asset_ids",
                )
            )
            or (
                inference.get("model_manifest_hash")
                != command["inputs"]["model_bundle_id"]
            )
        ):
            raise ValueError(
                "Full-universe inference pins do not match the accepted command"
            )
    if context:
        proof = SelectionProof.model_validate(result["diagnostics"].get("selection"))
        provenance = command["inputs"].get("provenance") or {}
        if (
            proof.input_hash != command["input_hash"]
            or proof.candidate_hash != context["candidate_hash"]
            or proof.snapshot_hash != provenance.get("snapshot_hash")
            or proof.panel_hash != provenance.get("panel_hash")
            or proof.decision_session.isoformat() != context["decision_session"]
            or proof.active_asset_ids != [a for a in ids if a in proof.active_asset_ids]
            or len(set(proof.active_asset_ids)) != len(proof.active_asset_ids)
            or (command["strategy"] != "HYBRID" and any(
                w != 0 for a, w in zip(ids, weights) if a not in proof.active_asset_ids
            ))
        ):
            raise ValueError("Selection proof does not match accepted command")
        if command["strategy"] in {"BL_ML", "HYBRID"}:
            inference = result["diagnostics"].get("inference") or {}
            if (
                inference.get("manifest_hash") != command["inputs"]["model_bundle_id"]
                or inference.get("snapshot_id") != command["inputs"]["snapshot_id"]
                or inference.get("snapshot_hash") != proof.snapshot_hash
            ):
                raise ValueError("Selected model/snapshot pin mismatch")
        if command["strategy"] == "HYBRID":
            from portfolio_contracts.hybrid import hybrid_policy, validate_hybrid_weights

            pin = hybrid_policy(context["regime"]["regime"], command["decision_context"]["risk_profile"].get("profile"))
            if pin != command["hybrid_policy"]:
                raise ValueError("HYBRID policy pin mismatch")
            validate_hybrid_weights(ids, proof.active_asset_ids, c, pin, result)
        if resolver is None or deadline is None:
            raise RuntimeError("Selection verification resolver required")
        if not resolver.verify_selection(
            command["inputs"],
            context,
            proof.model_dump(mode="json"),
            deadline,
            constraints=c,
            strategy=command["strategy"],
        ):
            raise ValueError("Selection proof source recomputation failed")
    defensive = sum(
        w for asset, w in zip(ids, weights) if asset in c["defensive_asset_ids"]
    )
    if (
        defensive + 1e-7 < c["min_defensive_weight"]
        or 1 - defensive > c["max_non_defensive_weight"] + 1e-7
    ):
        raise ValueError("Defensive constraints violated")


def consume_result(sessions, event: Envelope, *, resolver=None):
    if (
        event.type != "quant.optimization.completed"
        or event.producer != "quant-serving"
    ):
        raise ValueError("Unexpected producer/type")
    numerical_envelope = dict(event.payload)
    raw_evidence = numerical_envelope.pop("explanation_evidence", None)
    payload = OptimizeResult.model_validate(numerical_envelope)
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
            log_event(
                "portfolio.result",
                job_id=job.id,
                event_id=str(event.event_id),
                outcome="duplicate_delivery",
            )
            return
        session.add(Inbox(event_id=event.event_id))
        if job.status != "QUEUED":
            log_event(
                "portfolio.result",
                job_id=job.id,
                event_id=str(event.event_id),
                outcome="terminal_job",
            )
            return

        def fail(error, code):
            with span(
                "portfolio.result.persist",
                attributes=attributes | {"status": "FAILED", "error.code": code},
            ):
                job.status, job.error = "FAILED", error
                session.flush()
                log_event(
                    "portfolio.result.persist",
                    job_id=job.id,
                    event_id=str(event.event_id),
                    status="FAILED",
                    error_code=code,
                )

        portfolio = session.scalar(
            select(Portfolio).where(Portfolio.id == job.portfolio_id).with_for_update()
        )
        if aware(job.deadline) <= utcnow():
            fail(
                {"code": "DEADLINE_EXCEEDED", "message": "Quá thời hạn tính toán."},
                "DEADLINE_EXCEEDED",
            )
            return
        if payload.status == "FAILED":
            fail(payload.error or {"code": "QUANT_FAILED"}, "QUANT_FAILED")
            return
        try:
            with span("portfolio.result.validate", attributes=attributes):
                validate_result(
                    payload.result or {},
                    job.input,
                    resolver=resolver,
                    deadline=aware(job.deadline),
                )
                if (
                    not job.input.get("selection_context")
                    and portfolio.version != job.input["portfolio_version"]
                ):
                    raise ValueError("Portfolio changed")
                if (
                    aware(
                        datetime.fromisoformat(
                            (job.input.get("selection_context") or job.input["inputs"])[
                                "valid_until"
                            ]
                        )
                    )
                    <= utcnow()
                ):
                    raise ValueError("Input expired")
        except (ValueError, TypeError) as exc:
            fail(
                {"code": "INVALID_QUANT_RESULT", "message": str(exc)},
                "INVALID_QUANT_RESULT",
            )
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
            "policy_version_id": (job.input.get("decision_context") or {}).get(
                "policy_version_id", "manual-constraints-v1"
            ),
            "risk_profile": (job.input.get("decision_context") or {}).get(
                "risk_profile"
            ),
            "requested_strategy": (job.input.get("decision_context") or {}).get(
                "requested_strategy", job.input["strategy"]
            ),
            "fallback_reason": (job.input.get("decision_context") or {}).get(
                "fallback_reason"
            ),
        }
        if job.input.get("selection_context"):
            result["selection_context"] = job.input["selection_context"]
            result["selection_proof"] = payload.result["diagnostics"]["selection"]
            result["valid_until"] = job.input["selection_context"]["valid_until"]
        requested = (job.input.get("decision_context") or {}).get(
            "requested_constraints"
        )
        if requested is not None:
            result["requested_constraints"] = requested
        if job.input["inputs"].get("provenance") is not None:
            result["inputs_provenance"] = job.input["inputs"]["provenance"]
        with span(
            "portfolio.result.persist", attributes=attributes | {"status": "SUCCEEDED"}
        ):
            session.add(
                Recommendation(
                    id=job.id,
                    job_id=job.id,
                    owner_user_id=job.owner_user_id,
                    portfolio_id=job.portfolio_id,
                    run_id=str(payload.run_id),
                    result=result,
                    explanation_evidence=store_evidence(raw_evidence, job.input, payload.run_id, result),
                )
            )
            job.status, job.recommendation_id = "SUCCEEDED", job.id
            session.flush()
            log_event(
                "portfolio.result.persist",
                job_id=job.id,
                event_id=str(event.event_id),
                status="SUCCEEDED",
            )
