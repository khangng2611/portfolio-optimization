from datetime import date, datetime, timezone
import gzip
from hashlib import sha256
import json

import pytest

from market_service import hybrid_forward_capture as capture


@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        ("2026-11-23T12:00:00", None),
        ("2026-11-24T10:59:59", None),
        ("2026-11-24T12:00:00", "evaluation"),
        ("2026-11-24T13:00:00", None),
        ("2027-11-23T12:00:00", "evaluation"),
        ("2027-11-24T12:00:00", "settlement"),
        ("2027-12-01T12:00:00", None),
    ],
)
def test_capture_time_uses_vietnam_calendar(utc, expected):
    result = capture.window(datetime.fromisoformat(utc).replace(tzinfo=timezone.utc))
    assert (result[1] if result else None) == expected


def test_scheduler_waits_until_19_and_skips_a_finished_capture(tmp_path):
    now = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    assert not capture.due(tmp_path, now - capture.timedelta(minutes=1))
    assert capture.due(tmp_path, now)
    attempt = tmp_path / "evaluation" / "2026-11-24" / "attempt"
    attempt.mkdir(parents=True)
    assert capture.due(tmp_path, now)
    (attempt / "summary.json").write_text('{"status":"recorded"}')
    assert not capture.due(tmp_path, now)
    assert not capture.due(tmp_path, now + capture.timedelta(hours=1))


def test_source_receipt_retains_invalid_bytes_and_excludes_late_response(tmp_path):
    cutoff = date(2026, 11, 24)
    deadline = datetime(2026, 11, 24, 13, tzinfo=timezone.utc)
    late = deadline.replace(minute=1)
    early = deadline.replace(hour=12)
    raw = b'{"data_day":[{"t":"2026-11-24","c":12300}]}'
    malformed = b'{"unexpected":true}'
    attempt = tmp_path / "attempt"
    attempt.mkdir()

    def save(asset, body, received_at):
        return capture.capture_source(
            tmp_path,
            attempt,
            asset,
            deadline,
            lambda: (body, {"received_at": received_at.isoformat()}),
            lambda value: capture.normalize_completed_closes(value, asset, cutoff, cutoff, cutoff),
        )

    available = save("ACB", raw, early)
    unavailable = save("BID", raw, late)
    rejected = save("CTG", malformed, early)
    assert available["available_by_decision"] is True
    assert unavailable["available_by_decision"] is False
    assert rejected["status"] == "invalid"
    assert rejected["available_by_decision"] is False
    assert available["raw"] == unavailable["raw"]
    assert available["raw"]["sha256"] == sha256(raw).hexdigest()
    assert (
        gzip.decompress((tmp_path / rejected["raw"]["path"]).read_bytes()) == malformed
    )
    assert json.loads((attempt / "BID.json").read_text()) == unavailable


def test_partial_capture_retries_bounded_in_same_window(tmp_path):
    now = datetime(2026, 11, 24, 12, 5, tzinfo=timezone.utc)
    for i in range(3):
        folder = tmp_path / "evaluation/2026-11-24" / str(i)
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(json.dumps({"status": "partial", "finished_at": now.isoformat()}))
        assert not capture.due(tmp_path, now)
        now += capture.timedelta(minutes=10)
        assert capture.due(tmp_path, now) == (i < 2)


def test_extension_has_a_separate_phase_after_locked_settlement(tmp_path):
    now = datetime(2027, 12, 1, 12, tzinfo=timezone.utc)
    assert capture.window(now) is None
    assert capture.window(now, gold_shadow=True) == (now.date(), "gold_shadow", None)
    assert capture.due(tmp_path, now, gold_shadow=True)
