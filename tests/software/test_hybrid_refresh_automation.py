from datetime import timedelta
from types import SimpleNamespace

import pytest

from market_service import hybrid_refresh as market
from portfolio_contracts import utcnow
from quant_service import hybrid_renewal as quant


def test_failed_calendar_retries_without_advancing_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(market, "calendar_ends", lambda *_: (None, None))
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
                "availability_policy": market.LIVE_NAV_POLICY,
            }
        )
    )
    monkeypatch.setattr(
        market, "calendar_ends", lambda *_: ("2026-11-23", "2026-11-23")
    )
    monkeypatch.setattr(market, "sessions_from_env", lambda: None)
    monkeypatch.setattr(
        market, "refresh_selected", lambda *a, **kw: pytest.fail("duplicate refresh")
    )
    market.tick(now)

    # A completed legacy handoff still needs its first live NAV snapshot.
    path = tmp_path / "snapshot.json"
    receipt = json.loads(path.read_text())
    del receipt["availability_policy"]
    path.write_text(json.dumps(receipt))
    calls = []

    def refresh(assets, *args, **kwargs):
        calls.append(assets)
        raise market.CalendarUnavailable("KBS_CALENDAR_UNAVAILABLE")

    monkeypatch.setattr(market, "SOURCE", tmp_path)
    monkeypatch.setattr(market, "refresh_selected", refresh)
    with pytest.raises(market.CalendarUnavailable):
        market.tick(now)
    assert calls == [list(market.ASSET_IDS)]


def test_stale_handoff_and_buffered_snapshot_cannot_enter_live_queue(
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
                    "availability_policy": "user-selection-data-v1",
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


def test_revised_training_history_identifies_model_epoch_and_asset(
    tmp_path, monkeypatch, caplog
):
    from uuid import uuid4

    import numpy as np

    model_id = str(uuid4())
    artifact = tmp_path / "ml-models" / "job" / "model" / f"{model_id}.approved.json"
    artifact.parent.mkdir(parents=True)
    artifact.touch()
    monkeypatch.setattr(
        quant, "CredentialModelResolver", lambda: SimpleNamespace(resolve=lambda _: {})
    )
    monkeypatch.setattr(quant, "read_artifact", lambda *_: b"")
    model = SimpleNamespace(
        schema_version=5,
        status="APPROVED",
        demo=False,
        fit_epoch=145,
        covered_asset_ids=["FPT"],
        assets={"FPT": SimpleNamespace(training_data_hash="old")},
    )
    monkeypatch.setattr(quant, "parse_manifest", lambda _: model)
    panel = SimpleNamespace(
        dates=list(range(151)),
        decision_index=150,
        ids=["FPT"],
        prices=np.ones((151, 1)),
    )
    with pytest.raises(
        ValueError, match="MODEL_REVIEW_OR_COMPATIBILITY_REQUIRED fit_epoch=145"
    ):
        quant.approved_model(tmp_path, panel, ["FPT"])
    assert (
        f"{model_id} at fit epoch 145 failed compatibility: INPUT_INVALID: FPT"
        in caplog.text
    )


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
    monkeypatch.setattr(
        market, "calendar_ends", lambda *_: ("2026-11-23", "2026-11-23")
    )
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
        "availability_policy": market.LIVE_NAV_POLICY,
        "retry_after": now.timestamp() + 1800,
    }
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(pin))
    monkeypatch.setattr(market, "HANDOFF", tmp_path)
    monkeypatch.setattr(market, "SOURCE", tmp_path)
    monkeypatch.setattr(
        market, "calendar_ends", lambda *_: ("2026-11-23", "2026-11-23")
    )
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
        assert availability_policy == "user-selection-live-nav-v2"
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


def test_older_calendar_reopens_completed_legacy_slot_and_recovers(
    tmp_path, monkeypatch
):
    from datetime import datetime, timezone
    import json

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from market_service.models import Base, IngestionJob, Snapshot

    now = datetime(2026, 11, 24, 14, tzinfo=timezone.utc)
    sessions = sessionmaker(create_engine("sqlite://"))
    Base.metadata.create_all(sessions.kw["bind"])
    manifest = dict(
        universe_id="VN_USER_SELECTION",
        calendar="kbs-observed-vnindex-sessions",
        data_origin="real",
        calendar_status="AVAILABLE",
    )
    with sessions.begin() as session:
        for day in ("20", "23", "24"):
            session.add(
                Snapshot(
                    id=day,
                    content_hash=day,
                    observations=[],
                    manifest=manifest
                    | dict(
                        end_date=f"2026-11-{day}",
                        calendar_status="MISSING" if day == "24" else "AVAILABLE",
                    ),
                )
            )
    pin = dict(
        slot=int(now.timestamp()) // 14400,
        cutoff_date="2026-11-24",
        snapshot_id="20",
        snapshot_hash="20",
        retry_assets=[],
    )
    handoff = tmp_path / "snapshot.json"
    handoff.write_text(json.dumps(pin))
    monkeypatch.setattr(market, "HANDOFF", tmp_path)
    monkeypatch.setattr(market, "SOURCE", tmp_path)
    monkeypatch.setenv("DATASET_DIRECTORY", str(tmp_path))
    monkeypatch.setattr(market, "sessions_from_env", lambda: sessions)
    days = iter(["2026-11-20"] * 4)

    def fetch(self, symbol, start, end, *, index=False):
        assert index and symbol == "VNINDEX"
        return json.dumps({"data_day": [{"t": next(days), "c": "100"}]}).encode()

    monkeypatch.setattr(market.KbsProvider, "fetch_raw", fetch)
    with pytest.raises(market.CalendarUnavailable, match="KBS_CALENDAR_REGRESSION"):
        market.tick(now)
    retry = json.loads(handoff.read_text())
    assert retry["snapshot_id"] == "20" and retry["retry_assets"] == list(
        market.ASSET_IDS
    )
    with sessions() as session:
        assert session.query(IngestionJob).count() == 0
        assert session.query(Snapshot).count() == 3

    def recovered(assets, cutoff, store, *, minimum_calendar_end, **kwargs):
        assert assets == list(market.ASSET_IDS) and minimum_calendar_end == "2026-11-23"
        return dict(
            calendar_sessions=["2026-11-24"],
            asset_receipts={a: {"status": "AVAILABLE"} for a in assets},
        )

    monkeypatch.setattr(market, "refresh_selected", recovered)
    monkeypatch.setattr(
        market,
        "build_selected_snapshot",
        lambda *a, **kw: SimpleNamespace(id="new", content_hash="new"),
    )
    market.tick(now + timedelta(minutes=10))
    result = json.loads(handoff.read_text())
    assert result["snapshot_id"] == "new" and result["retry_assets"] == []


def test_expired_publication_still_sets_calendar_floor(tmp_path, monkeypatch):
    from datetime import date

    now = utcnow()
    pin = dict(refreshed_at=now.isoformat(), snapshot_id="new", snapshot_hash="hash")
    current = SimpleNamespace(dates=[date(2026, 11, 23)], decision_index=0)
    older = SimpleNamespace(dates=[date(2026, 11, 20)], decision_index=0)
    monkeypatch.setattr(
        quant,
        "CredentialMarketReader",
        lambda: SimpleNamespace(
            load=lambda *_: (
                dict(availability_policy=quant.LIVE_NAV_POLICY, max_age_days=7),
                [],
            )
        ),
    )
    monkeypatch.setattr(quant, "SelectionPanel", lambda *a, **kw: older)
    monkeypatch.setattr(quant, "eligible_assets", lambda *a: (["FPT"], {}))
    monkeypatch.setattr(
        quant,
        "SelectionCatalog",
        lambda _: SimpleNamespace(
            latest=lambda: SimpleNamespace(valid_until=now - timedelta(seconds=1)),
            load_resource=lambda _: (None, current),
        ),
    )
    with pytest.raises(ValueError, match="OLDER_SNAPSHOT"):
        quant.enqueue(pin, tmp_path, now)
