"""Best-effort evidence capture; never alters numerical inputs or results."""

from portfolio_contracts.explanation import OptimizationExplanationEvidence


def capture(evidence, factory):
    if evidence is not None:
        try:
            evidence.update(factory())
        except Exception:
            # Observability must not turn successful inference into a failed allocation.
            try:
                evidence["_failed"] = True
            except Exception:
                pass


def capture_asset_views(predictions, equities, active, p, q, confidence):
    import numpy as np
    from .phase1 import ensemble_forecast

    rows, index = [], 0
    for asset, members in zip(equities, predictions):
        mean, base = ensemble_forecast(members)
        applied = abs(mean) >= 0.001
        rows.append(
            dict(
                source_kind="ML",
                status="APPLIED" if applied else "BELOW_THRESHOLD",
                coefficients={asset: 1.0},
                raw_mean_return=mean,
                member_std=float(np.asarray(members, dtype=np.float32).std()),
                horizon_sessions=5,
                raw_return_unit="simple_fraction",
                confidence_base=base,
                confidence_applied=confidence[index] if applied else None,
                applied_q_daily=q[index] if applied else None,
                transform_version="phase1-option-b-v1",
            )
        )
        index += int(applied)
    if len(q) > index:
        rows.append(
            dict(
                source_kind="POLICY",
                status="APPLIED",
                coefficients={a: w for a, w in zip(active, p[index]) if w},
                raw_mean_return=None,
                confidence_applied=confidence[index],
                applied_q_daily=q[index],
                transform_version="vff-relative-policy-v1",
            )
        )
    return rows


def capture_selection(command, panel, proof, features, manifest, t):
    from .phase1 import FEATURES

    result = dict(
        features={
            a: [
                dict(
                    name=name,
                    value=float(v),
                    unit="index"
                    if name == "rsi_14"
                    else "thousand_vnd"
                    if name == "macd_hist"
                    else "fraction",
                )
                for name, v in zip(FEATURES, row)
            ]
            for a, row in features.items()
        },
        history_end_date=str(panel.dates[t - 1]),
        selection_hash=proof.selection_hash,
        regime_end_date=str(panel.dates[t]),
        covariance_end_date=str(panel.dates[t]),
        snapshot_hash=proof.snapshot_hash,
        regime=command.selection_context.regime.model_dump()
        | dict(
            asset_ids=command.selection_context.candidate_asset_ids, observed_sessions=t
        ),
    )
    if manifest:
        result.update(
            model_id=str(manifest.model_id),
            fit_epoch=str(manifest.fit_epoch),
            trained_at=getattr(manifest, "trained_at", None),
            training_cutoff=getattr(manifest, "training_cutoff", None),
        )
    return result


def build_quant_evidence(command, run_id, numerical, captured):
    if captured.get("_failed"):
        raise ValueError("Evidence capture failed")
    context = command.selection_context
    return OptimizationExplanationEvidence(
        status="COMPLETE"
        if captured.get("features") and captured.get("views")
        else "PARTIAL",
        job_id=str(command.job_id),
        run_id=str(run_id),
        input_hash=command.input_hash,
        bundle_hash=command.inputs.bundle_hash,
        snapshot_id=command.inputs.snapshot_id,
        model_bundle_id=command.inputs.model_bundle_id,
        asset_ids=numerical["asset_ids"],
        active_asset_ids=numerical.get("active_asset_ids", numerical["asset_ids"]),
        decision_at=context.decision_at if context else None,
        history_end_date=captured.get("history_end_date"),
        regime_end_date=captured.get("regime_end_date"),
        covariance_end_date=captured.get("covariance_end_date"),
        snapshot_hash=captured.get("snapshot_hash"),
        model_id=captured.get("model_id"),
        fit_epoch=captured.get("fit_epoch"),
        trained_at=captured.get("trained_at"),
        training_cutoff=captured.get("training_cutoff"),
        selection_hash=captured.get("selection_hash"),
        feature_schema="phase1-asset-features-v1" if captured.get("features") else None,
        features=captured.get("features", {}),
        views=captured.get("views", []),
        regime=captured.get("regime"),
        limitations=["ATTRIBUTION_NOT_AVAILABLE", "PIT_NOT_CERTIFIED"]
        + ([] if captured.get("features") else ["NOT_RETAINED"]),
    )
