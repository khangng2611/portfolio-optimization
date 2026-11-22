"""Read-only audit must distinguish visible revisions from later knowledge."""

import copy
import importlib.util
from pathlib import Path

import pytest

from portfolio_contracts import canonical_hash


@pytest.fixture
def audit(monkeypatch):
    path = Path(__file__).parents[2] / "scripts/audit_model_point_in_time.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("pit_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence():
    row = dict(
        revision_id="r1",
        asset_id="FPT",
        observation_date="2026-11-06",
        provider="kbs-direct-v1",
        price_type="close",
        price_vnd="100.000000",
        unit="VND/share",
        revision=1,
        content_hash="a" * 64,
        available_at="2026-11-11T01:00:00Z",
        ingested_at="2026-11-11T01:00:00Z",
        published_at=None,
        source_hash="b" * 64,
        data_origin="real",
        price_basis="provider_adjusted",
        availability_basis="ingestion",
    )
    later = row | dict(
        revision_id="r2",
        revision=2,
        price_vnd="110.000000",
        content_hash="c" * 64,
        available_at="2026-11-19T01:00:00Z",
        ingested_at="2026-11-19T01:00:00Z",
    )
    rows = [row]
    manifest = dict(
        observation_count=1,
        revision_ids=["r1"],
        observation_hash=canonical_hash({"observations": rows}),
        availability_policy="user-selection-data-v1",
        historical_publication_verified=False,
    )
    snapshot = manifest | dict(
        id="snapshot",
        content_hash=canonical_hash(manifest),
        created_at="2026-11-12T01:00:00Z",
    )
    jobs = {
        "j1": dict(
            quality_status="PASS",
            quality_checked_at="2026-11-11T01:01:00Z",
            source_hash="b" * 64,
        ),
        "j2": dict(
            quality_status="PASS",
            quality_checked_at="2026-11-19T01:01:00Z",
            source_hash="b" * 64,
        ),
    }
    return (
        snapshot,
        rows,
        [row | {"ingestion_job_id": "j1"}, later | {"ingestion_job_id": "j2"}],
        jobs,
    )


def test_future_revision_cannot_disqualify_frozen_snapshot_or_certify_history(audit):
    snapshot, rows, ledger, jobs = evidence()
    report = audit.audit_snapshot(
        snapshot,
        rows,
        ledger,
        jobs,
        decision_at="2026-11-18T08:00:00Z",
        nominal_at="2026-11-16T11:00:00Z",
    )
    assert report["live_integrity"] == "PASS"
    assert report["counts"]["newer_visible_revision"] == 0
    assert report["first_seen_after_observation_close"] == 1
    assert report["unavailable_by_nominal_epoch"] == 0
    assert report["historical_publication"] == "NOT_EVIDENCED"
    assert report["point_in_time_certified"] is False


def test_revision_available_before_snapshot_cannot_be_silently_ignored(audit):
    snapshot, rows, ledger, jobs = evidence()
    ledger[1].update(
        available_at="2026-11-11T02:00:00Z", ingested_at="2026-11-11T02:00:00Z"
    )
    jobs["j2"]["quality_checked_at"] = "2026-11-11T02:01:00Z"
    report = audit.audit_snapshot(
        snapshot,
        rows,
        ledger,
        jobs,
        decision_at="2026-11-18T08:00:00Z",
        nominal_at="2026-11-16T11:00:00Z",
    )
    assert report["live_integrity"] == "FAIL"
    assert report["counts"]["newer_visible_revision"] == 1


@pytest.mark.parametrize(
    "change",
    [
        "future_known",
        "future_quality",
        "row_mismatch",
        "missing_revision",
        "source_hash",
    ],
)
def test_inconsistent_revision_evidence_fails_closed(audit, change):
    snapshot, rows, ledger, jobs = evidence()
    if change == "future_known":
        ledger[0]["ingested_at"] = "2026-11-20T00:00:00Z"
    elif change == "future_quality":
        jobs["j1"]["quality_checked_at"] = "2026-11-20T00:00:00Z"
    elif change == "row_mismatch":
        ledger[0]["price_vnd"] = "999.000000"
    elif change == "missing_revision":
        ledger = ledger[1:]
    else:
        jobs["j1"]["source_hash"] = "f" * 64
    report = audit.audit_snapshot(
        snapshot,
        rows,
        ledger,
        jobs,
        decision_at="2026-11-18T08:00:00Z",
        nominal_at="2026-11-16T11:00:00Z",
    )
    assert report["live_integrity"] == "FAIL"
    assert report["point_in_time_certified"] is False


def test_missing_quality_evidence_is_not_reported_as_pass(audit):
    snapshot, rows, ledger, jobs = evidence()
    del jobs["j1"]
    report = audit.audit_snapshot(
        snapshot,
        rows,
        ledger,
        jobs,
        decision_at="2026-11-18T08:00:00Z",
        nominal_at="2026-11-16T11:00:00Z",
    )
    assert report["live_integrity"] == "NOT_EVIDENCED"


def test_hash_mismatch_and_naive_clock_are_rejected(audit):
    snapshot, rows, ledger, jobs = evidence()
    with pytest.raises(ValueError, match="Timezone"):
        audit.audit_snapshot(
            snapshot,
            rows,
            ledger,
            jobs,
            decision_at="2026-11-18T08:00:00",
            nominal_at="2026-11-16T11:00:00Z",
        )
    bad = copy.deepcopy(snapshot)
    bad["content_hash"] = "0" * 64
    with pytest.raises(ValueError, match="hash"):
        audit.audit_snapshot(
            bad,
            rows,
            ledger,
            jobs,
            decision_at="2026-11-18T08:00:00Z",
            nominal_at="2026-11-16T11:00:00Z",
        )


def test_model_trained_later_is_live_valid_but_not_available_at_nominal_epoch(audit):
    model = dict(
        fit_epoch="2026-11-16",
        training_knowledge_cutoff="2026-11-18T07:00:00Z",
        trained_at="2026-11-18T08:00:00Z",
        approved_at="2026-11-18T08:10:00Z",
    )
    report = audit.audit_timeline(
        model,
        training_created_at="2026-11-18T07:10:00Z",
        serving_created_at="2026-11-18T07:20:00Z",
        published_at="2026-11-18T08:20:00Z",
        decision_at="2026-11-18T08:30:00Z",
    )
    assert report["live_integrity"] == "PASS"
    assert report["model_available_at_nominal_epoch"] is False
    assert report["point_in_time_certified"] is False
    model["approved_at"] = "2026-11-18T09:00:00Z"
    assert (
        audit.audit_timeline(
            model,
            training_created_at="2026-11-18T07:10:00Z",
            serving_created_at="2026-11-18T07:20:00Z",
            published_at="2026-11-18T08:20:00Z",
            decision_at="2026-11-18T08:30:00Z",
        )["live_integrity"]
        == "FAIL"
    )


def test_source_bytes_cannot_be_replaced_without_audit_failure(audit, tmp_path):
    import hashlib

    raw = b"date,price\n2026-11-06,100\n"
    path = tmp_path / "source.csv"
    path.write_bytes(raw)
    jobs = {
        "j1": {
            "normalized_ref": {
                "path": "source.csv",
                "sha256": hashlib.sha256(raw).hexdigest(),
            },
            "source_metadata_ref": None,
            "source_provenance": [],
        }
    }
    result = audit.audit_artifacts(jobs, tmp_path)
    assert result["byte_integrity"] == "PASS"
    assert result["jobs_without_fetch_metadata"] == 1
    path.write_bytes(b"date,price\n2026-11-06,999\n")
    assert audit.audit_artifacts(jobs, tmp_path)["byte_integrity"] == "FAIL"


def test_legacy_raw_reference_resolves_beside_its_pinned_normalized_csv(
    audit, tmp_path
):
    import hashlib

    parent = tmp_path / "legacy"
    parent.mkdir()
    csv, raw = b"date,price\n2026-11-06,100\n", b'{"price":100}'
    (parent / "source.csv").write_bytes(csv)
    (parent / "raw.json").write_bytes(raw)
    jobs = {
        "j1": {
            "normalized_ref": {
                "path": "legacy/source.csv",
                "sha256": hashlib.sha256(csv).hexdigest(),
            },
            "source_metadata_ref": None,
            "source_provenance": [
                {"raw": {"file": "raw.json", "sha256": hashlib.sha256(raw).hexdigest()}}
            ],
        }
    }
    assert audit.audit_artifacts(jobs, tmp_path)["byte_integrity"] == "PASS"
    (parent / "raw.json").write_bytes(b'{"price":999}')
    assert audit.audit_artifacts(jobs, tmp_path)["byte_integrity"] == "FAIL"
