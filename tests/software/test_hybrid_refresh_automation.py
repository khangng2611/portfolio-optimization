from datetime import timedelta
from types import SimpleNamespace

import pytest

from market_service import hybrid_refresh as market
from portfolio_contracts import utcnow
from quant_service import hybrid_renewal as quant


def test_failed_calendar_retries_without_advancing_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "HANDOFF", tmp_path)
    monkeypatch.setattr(market, "SOURCE", tmp_path)
    monkeypatch.setattr(market, "sessions_from_env", lambda: None)
    monkeypatch.setattr(
        market, "refresh_selected", lambda *a, **kw: {"calendar_sessions": []}
    )
    with pytest.raises(ValueError, match="KBS_CALENDAR_UNAVAILABLE"):
        market.tick(utcnow())
    assert not (tmp_path / "snapshot.json").exists()


def test_finished_refresh_slot_is_not_fetched_again(tmp_path, monkeypatch):
    import json

    now = utcnow()
    monkeypatch.setattr(market, "HANDOFF", tmp_path)
    (tmp_path / "snapshot.json").write_text(
        json.dumps(
            {
                "slot": int(now.timestamp()) // 14400,
                "cutoff_date": str(market.completed_selected_cutoff(now)),
            }
        )
    )
    monkeypatch.setattr(
        market, "sessions_from_env", lambda: pytest.fail("duplicate refresh")
    )
    market.tick(now)


def test_stale_handoff_and_unbuffered_snapshot_cannot_enter_queue(
    tmp_path, monkeypatch
):
    now = utcnow()
    pin = dict(
        snapshot_id="unused",
        snapshot_hash="unused",
        refreshed_at=(now - timedelta(hours=5)).isoformat(),
    )
    with pytest.raises(ValueError, match="REFRESH_OVERDUE"):
        quant.enqueue(pin, tmp_path, now)
    pin["refreshed_at"] = now.isoformat()
    monkeypatch.setattr(
        quant,
        "CredentialMarketReader",
        lambda: SimpleNamespace(
            load=lambda *_: (
                {
                    "availability_policy": "user-selection-live-nav-v2",
                    "max_age_days": 7,
                },
                [],
            )
        ),
    )
    with pytest.raises(ValueError, match="WRONG_AVAILABILITY_POLICY"):
        quant.enqueue(pin, tmp_path, now)


def test_no_manually_approved_candidate_blocks_publication(tmp_path):
    panel = SimpleNamespace(dates=list(range(200)), decision_index=150)
    with pytest.raises(ValueError, match="MODEL_REVIEW_OR_COMPATIBILITY_REQUIRED"):
        quant.approved_model(tmp_path, panel, ["FPT"])


def test_retry_kbs_rejects_conflicting_close_until_clean_response(monkeypatch):
    import json
    from datetime import date

    day = date(2026, 11, 23)
    row = {"t": str(day), "c": "42"}
    clean = json.dumps({"data_day": [row]}).encode()
    conflict = json.dumps({"data_day": [row, row | {"c": "99"}]}).encode()
    responses = iter([conflict, clean])
    monkeypatch.setattr(
        market.KbsProvider, "fetch_raw", lambda *a, **kw: next(responses)
    )
    assert market.CheckedKbs().fetch_raw("FPT", day, day) == clean
    monkeypatch.setattr(market.KbsProvider, "fetch_raw", lambda *a, **kw: conflict)
    with pytest.raises(ValueError, match="duplicated"):
        market.CheckedKbs().fetch_raw("FPT", day, day)


def test_new_completed_session_refreshes_before_next_four_hour_slot(
    tmp_path, monkeypatch
):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import json

    now = datetime(2026, 11, 24, 18, 1, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    monkeypatch.setattr(market, "HANDOFF", tmp_path)
    monkeypatch.setattr(market, "SOURCE", tmp_path)
    (tmp_path / "snapshot.json").write_text(
        json.dumps(
            {
                "slot": int(now.timestamp()) // 14400,
                "cutoff_date": "2026-11-23",
                "retry_assets": [],
            }
        )
    )
    monkeypatch.setattr(market, "sessions_from_env", lambda: None)
    calls = []

    def refresh(assets, cutoff, *args, **kwargs):
        calls.append((assets, cutoff))
        return {"calendar_sessions": []}

    monkeypatch.setattr(market, "refresh_selected", refresh)
    with pytest.raises(ValueError, match="KBS_CALENDAR_UNAVAILABLE"):
        market.tick(now)
    assert calls == [(list(market.ASSET_IDS), now.date())]


def test_retry_only_failed_assets_preserves_snapshot_handoff(tmp_path, monkeypatch):
    from contextlib import nullcontext
    import json

    now = utcnow()
    pin = {
        "slot": int(now.timestamp()) // 14400,
        "cutoff_date": str(market.completed_selected_cutoff(now)),
        "retry_assets": ["FPT"],
        "retry_after": now.timestamp() + 1800,
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(pin))
    monkeypatch.setattr(market, "HANDOFF", tmp_path)
    monkeypatch.setattr(market, "SOURCE", tmp_path)
    monkeypatch.setattr(
        market, "sessions_from_env", lambda: SimpleNamespace(begin=nullcontext)
    )
    calls = []

    def refresh(assets, cutoff, *args, **kwargs):
        calls.append(assets)
        return {
            "calendar_sessions": [str(cutoff)],
            "asset_receipts": {"FPT": {"status": "AVAILABLE"}},
        }

    monkeypatch.setattr(market, "refresh_selected", refresh)

    def snapshot(_session, *, calendar, availability_policy):
        assert availability_policy == "user-selection-data-v1"
        return SimpleNamespace(id="next", content_hash="digest")

    monkeypatch.setattr(market, "build_selected_snapshot", snapshot)
    market.tick(now)
    assert json.loads(path.read_text()) == pin
    market.tick(now, retry_failed=True)
    result = json.loads(path.read_text())
    assert (
        calls == [["FPT"]]
        and result["retry_assets"] == []
        and result["snapshot_id"] == "next"
    )
