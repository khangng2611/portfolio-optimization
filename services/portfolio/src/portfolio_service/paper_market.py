"""Read the trusted, read-only market close export written by paper_market_export."""

from datetime import date, datetime
import json
from math import isfinite
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from portfolio_contracts import canonical_hash
from portfolio_contracts.assets import ASSET_IDS

VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _positive(value):
    if type(value) not in (int, float) or not isfinite(value) or value <= 0:
        raise ValueError("Invalid paper market price")
    return value


def read_market(start, now):
    folder = Path(os.environ.get("PAPER_MARKET_DIRECTORY", "/paper-market"))
    calendar = json.loads((folder / "calendar.json").read_bytes())
    sessions = calendar["sessions"]
    today = now.astimezone(VN).date()
    if not isinstance(sessions, list) or sorted(set(sessions)) != sessions:
        raise ValueError("Invalid paper session calendar")
    days = [date.fromisoformat(day) for day in sessions]
    if any(day.weekday() >= 5 for day in days):
        raise ValueError("Invalid market session")
    available = [day for day in days if day <= today]
    if start is None:
        wanted = available[-1:]
    else:
        wanted = [day for day in available if day >= start]
    frames = []
    for day in wanted:
        try:
            envelope = json.loads((folder / f"{day}.json").read_bytes())
        except FileNotFoundError:
            break
        frame = envelope["frame"]
        if (
            set(frame)
            - {
                "date",
                "as_of",
                "source",
                "prices",
                "eligible",
                "gold_bid",
                "gold_ask",
                "gold_tradable",
                "vff_nav",
                "vff_nav_date",
                "eligible_vff_date",
                "share_factors",
                "eligible_gold_bid",
                "eligible_gold_ask",
                "eligible_gold_date",
                "receipts",
                "vff_navs",
            }
            or envelope["sha256"] != canonical_hash(frame)
            or frame["date"] != str(day)
            or not isinstance(frame["source"], str)
            or not frame["source"]
        ):
            raise ValueError("Invalid paper market frame identity")
        as_of = datetime.fromisoformat(frame["as_of"])
        if as_of.utcoffset() is None or as_of.astimezone(VN).date() < day:
            raise ValueError("Invalid paper frame publication time")
        if as_of > now:
            break
        for name in ("prices", "eligible", "share_factors", "vff_navs", "receipts"):
            if not isinstance(frame.get(name, {}), dict):
                raise ValueError("Invalid paper market observation map")
        if not {"prices", "eligible"} <= frame.keys() or not isinstance(
            frame.get("gold_tradable", True), bool
        ):
            raise ValueError("Invalid paper market observations")
        for name in ("prices", "eligible", "share_factors"):
            for asset, price in frame.get(name, {}).items():
                if asset not in ASSET_IDS:
                    raise ValueError("Unknown paper quote asset")
                _positive(price)
        for key in (
            "gold_bid",
            "gold_ask",
            "vff_nav",
            "eligible_gold_bid",
            "eligible_gold_ask",
        ):
            if frame.get(key) is not None:
                _positive(frame[key])
        if (
            "eligible_gold_date" in frame
            and not 1
            <= (day - date.fromisoformat(frame["eligible_gold_date"])).days
            <= 7
        ):
            raise ValueError("Ineligible SJC observation date")
        for when, price in frame.get("vff_navs", {}).items():
            if not 0 <= (day - date.fromisoformat(when)).days <= 7:
                raise ValueError("VFF NAV outside its publication window")
            _positive(price)
        for key in ("vff_nav_date", "eligible_vff_date"):
            if (
                frame.get(key)
                and not 0 <= (day - date.fromisoformat(frame[key])).days <= 7
            ):
                raise ValueError("Invalid VFF NAV date")
        for prefix in ("gold_", "eligible_gold_"):
            bid, ask = frame.get(prefix + "bid"), frame.get(prefix + "ask")
            if (bid is None) != (ask is None) or (bid is not None and bid > ask):
                raise ValueError("Invalid SJC quote")
        frames.append(frame)
    return frames, str(available[-1]) if available else None
