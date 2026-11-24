from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd
import pytest

from market_service.hybrid_forward_capture import archive
from market_service.refresh_provider import normalized_csv
from scripts import hybrid_forward_panel as panel


def calendar_capture(tmp_path):
    day = date(2026, 11, 24)
    started = datetime(2026, 11, 24, 19, tzinfo=panel.VIETNAM)
    cutoff = started + timedelta(hours=1)
    batch = tmp_path / "evaluation" / str(day) / started.strftime("%Y%m%dT%H%M%S%f%z")
    batch.mkdir(parents=True)
    protocol = Path('docs/superpowers/plans/2026-11-23-hybrid-mvo60-walk-forward.md').read_bytes()
    manifest = dict(date=str(day), phase="evaluation", started_at=started.isoformat(), schema_version=1,
                    decision_at=cutoff.isoformat(), protocol=archive(tmp_path, protocol), implementation={})
    rows = [(day, 1600)]
    receipt = {"source": "VNINDEX", "status": "recorded", "available_by_decision": True,
               "attempted_at": started.isoformat(), "request": {"url": panel.BASE + "/index/VNINDEX/data_day",
               "method": "GET", "from": "2020-01-01", "to": str(day),
               "requested_at": started.isoformat(), "received_at": (started + timedelta(seconds=2)).isoformat()},
               "raw": archive(tmp_path, json.dumps({"data_day": [{"t": str(day), "c": 1600}]}).encode()),
               "normalized_sha256": sha256(normalized_csv(rows, "VNINDEX")).hexdigest(),
               "row_count": 1, "latest_date": str(day)}
    (batch / 'VNINDEX.json').write_text(json.dumps(receipt))
    (batch / 'manifest.json').write_text(json.dumps(manifest))
    summary = dict(phase="evaluation", date=str(day), finished_at=(started + timedelta(seconds=3)).isoformat(),
                   receipts={"VNINDEX": sha256((batch / 'VNINDEX.json').read_bytes()).hexdigest()})
    (batch / 'summary.json').write_text(json.dumps(summary))
    return batch, cutoff


def test_calendar_requires_timely_archive_hash_and_locked_phase(tmp_path):
    batch, cutoff = calendar_capture(tmp_path)
    assert panel.load_calendar(tmp_path, batch, cutoff) == ["2026-11-24"]
    with pytest.raises(ValueError, match="source unavailable"):
        panel.load_calendar(tmp_path, batch, cutoff - timedelta(hours=1))
    with pytest.raises(ValueError, match="phase mismatch"):
        panel.load_calendar(tmp_path, batch, cutoff, rehearsal=True)
    with pytest.raises(ValueError, match="locked evaluation cutoff"):
        panel.load_panel(tmp_path, batch, cutoff + timedelta(minutes=1))
    receipt = batch / 'VNINDEX.json'
    receipt.write_bytes(receipt.read_bytes() + b' ')
    with pytest.raises(ValueError, match="receipt hash"):
        panel.load_calendar(tmp_path, batch, cutoff)


def test_object_substitution_and_protocol_change_fail(tmp_path):
    batch, cutoff = calendar_capture(tmp_path)
    path = batch / "manifest.json"
    manifest = json.loads(path.read_text())
    protocol = manifest["protocol"]
    manifest["protocol"] = protocol | {"path": "../objects/" + protocol["sha256"] + ".gz"}
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="object reference"):
        panel.load_calendar(tmp_path, batch, cutoff)
    manifest["protocol"] = archive(tmp_path, b"changed")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="protocol hash"):
        panel.load_calendar(tmp_path, batch, cutoff)


def test_valuation_unresolved_stock_gold_and_stale_fund_stay_missing():
    days = ["2020-12-01", "2020-12-02", "2020-12-03", "2020-12-09"]
    rows = {a: [(date(2020, 12, 1), 12.0, a)] for a in panel.ASSET_IDS}
    frame = panel._valuation(days, rows)
    assert frame.loc["2020-12-02", "ACB"] == 12  # documented prior suspension
    assert pd.isna(frame.loc["2020-12-02", "FPT"])
    assert pd.isna(frame.loc["2020-12-02", "GOLD"])
    assert frame.loc["2020-12-03", "VFF"] == 12
    assert pd.isna(frame.loc["2020-12-09", "VFF"])


def test_asof_and_economic_nav_remain_distinct_and_enforce_seven_days(tmp_path, monkeypatch):
    batch, cutoff = calendar_capture(tmp_path)
    dates = sorted(set(pd.bdate_range("2020-01-02", periods=160).date)
                   | set(pd.bdate_range("2026-10-01", "2026-11-24").date))
    sessions = list(map(str, dates))
    rows = {a: [(d, i+100, a) for i, d in enumerate(dates) if a in ("VFF", "GOLD") or d >= panel.START] for a in panel.ASSET_IDS}
    def read(data):
        data.provenance["receipts"] = {a: {"raw_sha256": "a"*64, "received_at": cutoff.isoformat()} for a in rows}
        return sessions, rows, {str(d): {"product_id": 21} for d in dates}
    monkeypatch.setattr(panel, "_read_sources", read)
    result = panel.load_panel(tmp_path, batch, cutoff)
    assert list(result["information"].columns) == list(panel.ASSET_IDS)
    assert result["information"].iloc[-1]["VFF"] == 100 + len(dates) - 6
    assert result["valuation"].iloc[-1]["VFF"] == 100 + len(dates) - 1
    assert result["provenance"]["availability"]["VFF"]["observation_date"] == str(dates[-6])
    assert result["information"].iloc[-1]["GOLD"] == 100 + len(dates) - 2
    rows["VFF"] = rows["VFF"][:-6]
    with pytest.raises(ValueError, match="VFF_STALE"):
        panel.load_panel(tmp_path, batch, cutoff)
    prepared = panel.load_panel(tmp_path, batch, cutoff, prepare_only=True)
    assert prepared["decision_block"]["reason"].startswith("VFF_STALE")
    assert prepared["decision_block"]["details"]["age_days"] > 7
    assert prepared["information"].shape == result["information"].shape
