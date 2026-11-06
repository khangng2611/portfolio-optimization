"""Offline checks for evidence validation, never an integration substitute."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def smoke():
    path = Path(__file__).resolve().parents[2] / "scripts/smoke_chat.py"
    assert path.exists(), "The live Chat smoke harness is not implemented"
    spec = importlib.util.spec_from_file_location("smoke_chat", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ready(**changes):
    return {
        "universe_id": "REAL",
        "status": "READY",
        "reason_code": "READY",
        "data_origin": "real",
        "demo": False,
        "asset_ids": ["AAA", "BBB"],
        "bundle_hash": "a" * 64,
        "snapshot_id": "snapshot",
        "valid_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "strategies": [{"strategy": "MVO", "available": True, "reason_code": "READY"}],
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"data_origin": "synthetic"},
        {"demo": True},
        {"status": "EXPIRED"},
        {"valid_until": "2000-01-01T00:00:00+00:00"},
        {"asset_ids": ["AAA"]},
        {"strategies": [{"strategy": "EW", "available": True, "reason_code": "READY"}]},
    ],
)
def test_no_demo_stale_or_incompatible_substitution(smoke, changes):
    with pytest.raises(
        smoke.SmokeFailure, match="No current READY real-price MVO universe"
    ):
        smoke.select_real_universe([ready(**changes)])


def test_real_universe_selected_after_unusable_entry(smoke):
    assert (
        smoke.select_real_universe([ready(demo=True), ready()])["universe_id"] == "REAL"
    )


def test_grounding_checks_complete_facts_including_provenance(smoke):
    facts = {"weights": ["0.5", "0.5"], "provenance": {"provider": "original"}}
    card = {"facts": facts, "facts_hash": smoke.canonical_hash(facts)}
    smoke.assert_grounded(card, facts)
    changed = facts | {"provenance": {"provider": "changed"}}
    with pytest.raises(smoke.SmokeFailure, match="canonical facts"):
        smoke.assert_grounded(card, changed)


@pytest.mark.parametrize(
    "weights", [["nan", "1"], ["0.6", "0.4"], ["0.4", "0.4"], [True, 0], ["0.5"]]
)
def test_nonfinite_infeasible_and_wrong_length_weights_rejected(smoke, weights):
    with pytest.raises(smoke.SmokeFailure, match="weights"):
        smoke.assert_weights(
            {
                "asset_ids": ["AAA", "BBB"],
                "weights": weights,
                "constraints": {"max_position_weight": 0.5},
            }
        )


def test_sse_comments_multiline_and_persisted_replay(smoke):
    raw = ': heartbeat\r\n\r\nid: 1\r\nevent: accepted\r\ndata: {"job_id":\r\ndata: "job"}\r\n\r\nid: 2\nevent: completed\ndata: {}\n\n'
    events = smoke.parse_sse(raw)
    assert events == [
        {"id": 1, "event": "accepted", "data": {"job_id": "job"}},
        {"id": 2, "event": "completed", "data": {}},
    ]
    smoke.assert_replay(events, events[1:], 1)
    with pytest.raises(smoke.SmokeFailure, match="replay"):
        smoke.assert_replay(events, events, 1)
    with pytest.raises(smoke.SmokeFailure, match="sequence"):
        smoke.assert_replay(events + [events[-1]], events[1:], 1)


def test_token_and_grant_fields_refuse_receipt_serialization(smoke, tmp_path):
    for forbidden in ("access_token", "password", "grant_id", "authorization"):
        with pytest.raises(smoke.SmokeFailure, match="credential"):
            smoke.write_receipt(
                tmp_path / "receipt.json", {"nested": {forbidden: "secret"}}
            )
    assert not (tmp_path / "receipt.json").exists()


def test_receipt_writes_valid_json_with_private_file_mode(smoke, tmp_path):
    import json
    path = tmp_path / 'receipt.json'
    receipt = {'job_id': 'job', 'facts_hash': 'a' * 64}
    smoke.write_receipt(path, receipt)
    assert json.loads(path.read_text()) == receipt
    assert path.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('*.tmp'))
