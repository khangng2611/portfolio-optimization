from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
import xgboost

from portfolio_contracts import OptimizeResult, canonical_hash
from quant_service import asset_ensemble


def captured_views(monkeypatch, values=(0.03, -0.02, 0.0005), ratio=1.5):
    calls = []
    assets = ["ACB", "BID", "CTG", "VFF"]
    manifest = SimpleNamespace(
        schema_version=5,
        xgboost_version=xgboost.__version__,
        status="APPROVED",
        fit_epoch="2026-11-16",
        covered_asset_ids=assets[:3],
    )

    def predict(*args, **kwargs):
        calls.append(kwargs["asset_ids"])
        return np.array([[v] * 5 for v in values])

    monkeypatch.setattr("quant_service.ml.phase1_predictions", predict)
    inputs = (
        "unused",
        manifest,
        {a: [0.0] * 8 for a in assets[:3]},
        {a: 0.02 for a in assets[:3]},
        assets,
        {"regime": "stress", "vol_ratio": ratio},
    )
    return inputs, calls


def test_capture_preserves_views_and_predicts_once(monkeypatch):
    inputs, calls = captured_views(monkeypatch)
    before = asset_ensemble.infer_asset_views(*inputs)
    evidence = {}
    after = asset_ensemble.infer_asset_views(*inputs, evidence=evidence)
    assert before == after
    assert len(calls) == 2  # one call per invocation, including capture
    rows = evidence["views"]
    assert [r["status"] for r in rows] == [
        "APPLIED",
        "APPLIED",
        "BELOW_THRESHOLD",
        "APPLIED",
    ]
    assert rows[0]["raw_mean_return"] == pytest.approx(0.03)
    assert rows[1]["raw_mean_return"] < 0
    assert rows[0]["horizon_sessions"] == 5
    assert rows[0]["applied_q_daily"] == after["views_q"][0]
    assert rows[0]["confidence_applied"] == after["view_confidences"][0]
    assert rows[2]["applied_q_daily"] is None
    assert rows[-1]["source_kind"] == "POLICY"
    assert rows[-1]["raw_mean_return"] is None
    assert rows[-1]["coefficients"]["VFF"] == 1
    assert "GOLD" not in rows[-1]["coefficients"]


def test_collector_failure_does_not_change_numerical_views(monkeypatch):
    inputs, _ = captured_views(monkeypatch)
    expected = asset_ensemble.infer_asset_views(*inputs)

    class Broken(dict):
        def update(self, *args, **kwargs):
            raise ValueError("collector failed")

    assert asset_ensemble.infer_asset_views(*inputs, evidence=Broken()) == expected


def test_result_sidecar_does_not_change_legacy_wire_or_numerical_result():
    payload = dict(
        job_id=str(uuid4()),
        run_id=str(uuid4()),
        input_hash="a" * 64,
        bundle_hash="b" * 64,
        status="SUCCEEDED",
        result={"weights": [0.5, 0.5]},
        error=None,
    )
    assert OptimizeResult.model_validate(payload).model_dump(mode="json") == payload
    digest = canonical_hash(payload["result"])
    with_evidence = OptimizeResult.model_validate(
        payload | {"explanation_evidence": {"bad": "body"}}
    )
    assert canonical_hash(with_evidence.result) == digest


def test_strict_sidecar_rejects_tampering_and_nonfinite():
    from portfolio_contracts.explanation import OptimizationExplanationEvidence

    fields = dict(
        job_id=str(uuid4()),
        run_id=str(uuid4()),
        input_hash="a" * 64,
        bundle_hash="b" * 64,
        snapshot_id="snap",
        asset_ids=["ACB", "VFF"],
        active_asset_ids=["ACB", "VFF"],
        status="PARTIAL",
    )
    body = OptimizationExplanationEvidence(**fields).seal()
    assert OptimizationExplanationEvidence.model_validate(body).checked()
    forged = deepcopy(body)
    forged["active_asset_ids"] = ["VFF"]
    with pytest.raises(ValueError):
        OptimizationExplanationEvidence.model_validate(forged).checked()
    with pytest.raises(ValueError):
        OptimizationExplanationEvidence(
            **(
                fields
                | {
                    "features": {
                        "ACB": [
                            {"name": "rsi_14", "value": float("nan"), "unit": "index"}
                        ]
                    }
                }
            )
        )


@pytest.mark.parametrize(
    "name,unit",
    [
        ("rsi_14", "fraction"),
        ("macd_hist", "fraction"),
        ("price_std_20", "thousand_vnd"),
    ],
)
def test_feature_units_are_not_interchangeable(name, unit):
    from portfolio_contracts.explanation import FeatureEvidence

    with pytest.raises(ValueError):
        FeatureEvidence(name=name, unit=unit, value=1.0)


def test_complete_response_requires_complete_quant_payload():
    from portfolio_contracts.explanation import RecommendationEvidence

    with pytest.raises(ValueError):
        RecommendationEvidence(
            recommendation_id=str(uuid4()),
            run_id=str(uuid4()),
            facts_hash="a" * 64,
            status="COMPLETE",
        )


def test_selection_records_distinct_history_endpoints():
    from test_selection_worker import selected_command
    from quant_service.selection import resolve_selection

    catalog, command, now = selected_command(["ACB", "BID", "VFF"], strategy="MVO")
    captured = {}
    _, proof, _ = resolve_selection(catalog, command, now=now, evidence=captured)
    assert captured["history_end_date"] == str(proof.selection_price_end_date)
    assert captured["regime_end_date"] == str(
        command.selection_context.decision_session
    )
    assert captured["covariance_end_date"] == captured["regime_end_date"]
    assert captured["history_end_date"] < captured["regime_end_date"]


def test_optional_metadata_does_not_rehash_existing_sidecars():
    from portfolio_contracts.explanation import OptimizationExplanationEvidence

    body = OptimizationExplanationEvidence(
        status="PARTIAL",
        job_id=str(uuid4()),
        run_id=str(uuid4()),
        input_hash="a" * 64,
        bundle_hash="b" * 64,
        snapshot_id="snap",
        asset_ids=["ACB", "VFF"],
        active_asset_ids=["ACB", "VFF"],
    ).seal()
    for key in (
        "regime_end_date",
        "covariance_end_date",
        "snapshot_hash",
        "model_id",
        "fit_epoch",
        "trained_at",
        "training_cutoff",
    ):
        body.pop(key, None)
    body["evidence_hash"] = canonical_hash(
        {k: v for k, v in body.items() if k != "evidence_hash"}
    )
    value = OptimizationExplanationEvidence.model_validate(body).checked()
    assert value.model_dump(mode="json") == body


def test_capture_construction_failure_isolated_from_native_views(monkeypatch):
    from quant_service import explanation

    inputs, _ = captured_views(monkeypatch)
    expected = asset_ensemble.infer_asset_views(*inputs)
    calls = []

    def broken(*args):
        calls.append(1)
        raise ValueError("capture construction failed")

    monkeypatch.setattr(explanation, "capture_asset_views", broken, raising=False)
    assert asset_ensemble.infer_asset_views(*inputs, evidence={}) == expected
    assert calls == [1]
    assert asset_ensemble.infer_asset_views(*inputs) == expected
    assert calls == [1]


def test_selection_capture_construction_failure_keeps_numerical_inputs(monkeypatch):
    from quant_service import explanation
    from quant_service.selection import resolve_selection
    from test_selection_worker import selected_command

    catalog, command, now = selected_command(["ACB", "BID", "VFF"], strategy="MVO")
    expected = resolve_selection(catalog, command, now=now)
    calls = []

    def broken(*args):
        calls.append(1)
        raise ValueError("capture construction failed")

    monkeypatch.setattr(explanation, "capture_selection", broken, raising=False)
    assert resolve_selection(catalog, command, now=now, evidence={}) == expected
    assert calls == [1]


def test_future_tail_preserves_selection_features_views_and_evidence(monkeypatch):
    from datetime import timedelta

    from quant_service import selection
    from test_selection_worker import selected_command

    catalog, command, now = selected_command()
    _, panel = catalog.load_resource(command.inputs)
    manifest = SimpleNamespace(
        schema_version=5,
        xgboost_version=xgboost.__version__,
        status="APPROVED",
        model_id=str(uuid4()),
        fit_epoch="2026-11-16",
        covered_asset_ids=panel.ids[:-2],
        point_in_time_certified=False,
    )
    monkeypatch.setattr(
        catalog, "load_resource", lambda pin: ({"model_bundle_id": "a" * 64}, panel)
    )
    monkeypatch.setattr(catalog, "model", lambda value: ("unit-directory", manifest))
    monkeypatch.setattr(selection, "check_model", lambda *args: manifest)

    def predictions(directory, model, rows, *, asset_ids):
        # Offline provider injection; retain the actual view transformation/capture.
        return np.repeat((0.02 + 0.001 * np.tanh(rows[:, :1])), 5, axis=1)

    monkeypatch.setattr("quant_service.ml.phase1_predictions", predictions)
    before_evidence = {}
    before = selection.resolve_selection(
        catalog, command, now=now, evidence=before_evidence
    )
    panel.dates += [panel.dates[-1] + timedelta(days=i) for i in (1, 2)]
    for name in (
        "prices",
        "valid",
        "observation_days",
        "policy_seconds",
        "known_seconds",
    ):
        array = getattr(panel, name)
        tail = np.repeat(array[-1:], 2, axis=0)
        if name == "prices":
            tail *= np.random.default_rng(41).uniform(1e3, 1e6, tail.shape)
        setattr(panel, name, np.concatenate([array, tail]))
    after_evidence = {}
    after = selection.resolve_selection(
        catalog, command, now=now, evidence=after_evidence
    )
    assert before == after
    assert before_evidence == after_evidence
    assert canonical_hash(before_evidence) == canonical_hash(after_evidence)
    assert before_evidence["features"] and before_evidence["views"]
    assert before_evidence["history_end_date"] < before_evidence["regime_end_date"]
    assert manifest.point_in_time_certified is False
