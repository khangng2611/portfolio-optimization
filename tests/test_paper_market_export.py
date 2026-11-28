"""Keep the last actually observed equity basis across gaps and exporter restarts."""

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import paper_market_export as feed


def test_resumed_feed_recovers_share_multiplier_after_missing_session(
    monkeypatch, tmp_path
):
    days = ["2026-11-25", "2026-11-26", "2026-11-27"]

    class Captures:
        def __init__(self, root, now):
            self.root = Path(root)
            self.sessions = [day for day in days if day <= str(now.date())]
            self.provenance = {}

        def _read(self, day, source, get):
            if source != "VNINDEX":
                raise feed.CaptureUnavailable("test source missing")
            self.provenance["test"] = {"summary_sha256": "a" * 64}
            return [day]

        def _batch(self, path, day):
            return SimpleNamespace(
                finished=datetime.fromisoformat(day + "T12:00:00+00:00")
            )

        def _stock(self, day, asset, basis_day):
            assert asset == "FPT"
            if day == days[0]:
                return 80000.0, 80000.0
            if day == days[1]:
                raise feed.CaptureUnavailable("suspended")
            assert basis_day == days[0]
            return 40000.0, 40000.0

        def _quote(self, day):
            raise feed.CaptureUnavailable("no gold")

        def _nav(self, day, publication):
            raise feed.CaptureUnavailable("no fund")

    monkeypatch.setattr(feed, "PaperCaptures", Captures)
    monkeypatch.setattr(feed, "EQUITY_IDS", ["FPT"])
    before = datetime(2026, 11, 26, 18, tzinfo=timezone.utc)
    after = datetime(2026, 11, 27, 18, tzinfo=timezone.utc)
    assert feed.export(tmp_path, tmp_path, before) == 2
    assert feed.export(tmp_path, tmp_path, after) == 1
    assert feed.export(tmp_path, tmp_path, after) == 0
    received = [
        json.loads((tmp_path / f"{day}.json").read_bytes())["frame"] for day in days
    ]
    assert received[1]["prices"] == {}
    assert received[2]["share_factors"] == {"FPT": 2.0}
    assert (
        received[2]["share_factors"]["FPT"] * received[2]["prices"]["FPT"]
        == received[0]["prices"]["FPT"]
    )


def test_same_day_incomplete_capture_can_publish_complete_retry(monkeypatch, tmp_path):
    day = "2026-11-27"
    captures = SimpleNamespace(sessions=[day])
    monkeypatch.setattr(feed, "PaperCaptures", lambda *_: captures)
    monkeypatch.setattr(feed, "ASSET_IDS", ("FPT", "GOLD"))
    prices = {"FPT": 80000.0}

    def current(captures, stamp, previous, basis):
        return dict(
            date=stamp, prices=prices, eligible=prices, receipts={"batch": "a" * 64}
        )

    monkeypatch.setattr(feed, "market_frame", current)
    after_close = datetime(2026, 11, 27, 14, tzinfo=timezone.utc)
    assert feed.export(tmp_path, tmp_path, after_close) == 0
    assert json.loads((tmp_path / "calendar.json").read_bytes())["sessions"] == [day]
    assert not (tmp_path / f"{day}.json").exists()
    prices["GOLD"] = 130_000_000.0
    assert feed.export(tmp_path, tmp_path, after_close) == 1
    assert (
        json.loads((tmp_path / f"{day}.json").read_bytes())["frame"]["prices"] == prices
    )
