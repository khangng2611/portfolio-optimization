import json
from datetime import datetime
from datetime import timedelta

import pytest

from portfolio_contracts import utcnow
from quant_service.model_worker import train_candidate, approve_candidate
from quant_service.ml import infer
from test_snapshot_inputs import snapshot_fixture


def training_case():
    from quant_service.snapshot_inputs import SnapshotPanel

    snapshot, rows, now = snapshot_fixture()
    panel = SnapshotPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    return panel, panel.training_data(now.date() - timedelta(days=10))


def test_model_manifest_pins_actual_knowledge_and_real_snapshot_then_infers(tmp_path):
    panel, raw = training_case()
    ref = train_candidate(tmp_path, raw)
    ref = approve_candidate(tmp_path, ref, reviewer="integration-reviewer")
    manifest = json.loads((tmp_path / ref["file"]).read_text())
    assert manifest["schema_version"] == 2
    assert manifest["training_snapshot_hash"] == raw["snapshot_hash"]
    assert datetime.fromisoformat(
        manifest["training_knowledge_cutoff"]
    ) == datetime.fromisoformat(raw["knowledge_cutoff"])
    assert manifest["validation"]["point_in_time_certified"] is False
    numerical, batch, _ = panel.inputs()
    value = {
        "ml_inference": batch | {"manifest": ref},
        "model_bundle_id": ref["sha256"],
        "numerical": numerical,
        "as_of_date": panel.dates[-1].isoformat(),
        "demo": False,
        "decision_at": utcnow().isoformat(),
    }
    predicted, provenance = infer(tmp_path, value)
    assert len(predicted["views_q"]) == 3
    assert provenance["training_snapshot_hash"] == raw["snapshot_hash"]
    value["decision_at"] = (panel.now - timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        infer(tmp_path, value)


@pytest.mark.parametrize(
    "failure",
    [
        "label_future",
        "feature_future",
        "missing_hash",
        "unknown_origin",
        "cutoff_future",
    ],
)
def test_v2_training_rejects_unavailable_or_incomplete_provenance(tmp_path, failure):
    _, raw = training_case()
    if failure == "label_future":
        raw["label_known_at"][0] = (utcnow() + timedelta(days=1)).isoformat()
    if failure == "feature_future":
        raw["feature_known_at"][0] = (utcnow() + timedelta(days=1)).isoformat()
    if failure == "missing_hash":
        raw.pop("snapshot_hash")
    if failure == "unknown_origin":
        raw["demo"] = True
    if failure == "cutoff_future":
        raw["knowledge_cutoff"] = (utcnow() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):
        train_candidate(tmp_path, raw)


def test_approval_must_be_known_before_the_bundle_decision(tmp_path):
    from quant_service.snapshot_publisher import publish_snapshot
    from quant_service.snapshot_inputs import SnapshotPanel

    snapshot, rows, now = snapshot_fixture()
    panel = SnapshotPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    candidate = train_candidate(
        tmp_path, panel.training_data(now.date() - timedelta(days=10))
    )
    decision = utcnow()
    approved = approve_candidate(tmp_path, candidate, reviewer="reviewer")
    with pytest.raises(ValueError, match="unavailable at decision"):
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="REAL",
            model=approved,
            now=decision,
        )
