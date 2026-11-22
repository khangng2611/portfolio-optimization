"""Owner-scoped frozen evidence, separate from recommendation JSON/hash."""

from datetime import datetime

from portfolio_contracts import canonical_hash
from portfolio_contracts.explanation import (
    OptimizationExplanationEvidence,
    RecommendationEvidence,
)


def validate_evidence(body, command, run_id, result):
    evidence = OptimizationExplanationEvidence.model_validate(body).checked()
    if any(
        (
            evidence.job_id != command["job_id"],
            evidence.run_id != str(run_id),
            evidence.input_hash != command["input_hash"],
            evidence.bundle_hash != command["inputs"]["bundle_hash"],
            evidence.snapshot_id != command["inputs"]["snapshot_id"],
            evidence.model_bundle_id != command["inputs"].get("model_bundle_id"),
            evidence.asset_ids != result["asset_ids"],
        )
    ):
        raise ValueError("Evidence pins mismatch")
    context = command.get("selection_context")
    if command.get("strategy") in ("EW", "MVO") and (
        evidence.views or evidence.features
    ):
        raise ValueError("Non-BL allocation did not apply ML features/views")
    if context:
        proof = result["diagnostics"]["selection"]
        if (
            evidence.selection_hash != proof["selection_hash"]
            or evidence.active_asset_ids != proof["active_asset_ids"]
            or str(evidence.history_end_date) != proof["selection_price_end_date"]
            or evidence.decision_at != datetime.fromisoformat(context["decision_at"])
        ):
            raise ValueError("Evidence selection mismatch")
        for key, expected in {
            "snapshot_hash": proof["snapshot_hash"],
            "regime_end_date": context["decision_session"],
            "covariance_end_date": context["decision_session"],
        }.items():
            observed = getattr(evidence, key)
            if observed is not None and str(observed) != expected:
                raise ValueError("Evidence historical pin mismatch")
        inference = result["diagnostics"].get("inference") or {}
        for key in ("model_id", "fit_epoch"):
            observed = getattr(evidence, key)
            if (
                observed is not None
                and key in inference
                and str(observed) != str(inference[key])
            ):
                raise ValueError("Evidence model pin mismatch")
        if evidence.trained_at and evidence.trained_at > datetime.fromisoformat(
            context["decision_at"]
        ):
            raise ValueError("Future model evidence")
        if evidence.regime and any(
            getattr(evidence.regime, k) != v for k, v in context["regime"].items()
        ):
            raise ValueError("Evidence regime mismatch")
    return evidence


def store_evidence(body, command, run_id, result):
    if body is None:
        return None
    try:
        return validate_evidence(body, command, run_id, result).model_dump(mode="json")
    except (ValueError, TypeError, KeyError, AttributeError):
        return {"status": "UNAVAILABLE"}


def recommendation_evidence(value, job, facts):
    quant = None
    status, limitations = "PARTIAL", ["NOT_RETAINED"]
    if value.explanation_evidence is not None:
        try:
            quant = validate_evidence(
                value.explanation_evidence, job.input, value.run_id, value.result
            )
            status, limitations = quant.status, quant.limitations
        except (ValueError, TypeError, KeyError, AttributeError):
            status, limitations = "UNAVAILABLE", ["INVALID_EVIDENCE"]
    return RecommendationEvidence(
        recommendation_id=value.id,
        run_id=value.run_id,
        facts_hash=canonical_hash(facts),
        status=status,
        quant=quant,
        limitations=limitations,
    ).seal()
