"""Refresh the real selected-assets catalog and hand off live NAV snapshot pins."""

import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import time

from sqlalchemy import case, func, select
from portfolio_contracts import utcnow
from portfolio_contracts.assets import ASSET_IDS
from portfolio_contracts.selection import LIVE_NAV_POLICY
from .models import Snapshot
from .selected_refresh import (
    ArtifactStore,
    CalendarUnavailable,
    completed_selected_cutoff,
    refresh_selected,
)
from .selected_snapshots import build_selected_snapshot
from .runtime import sessions_from_env
from .refresh_provider import KbsProvider, normalize_completed_closes
from .phase1_sources import equity_missing_sessions

HANDOFF = Path("/datasets/refresh/hybrid-automation")
SOURCE = Path("/datasets/refresh/full-phase1")


class CheckedKbs(KbsProvider):
    """A replica can return overlapping daily bars. Require a complete clean response."""

    calendar = None
    cutoff = None
    minimum_calendar_end = ""

    def fetch_raw(self, symbol, start, end, *, index=False):
        cutoff = self.cutoff or end
        for attempt in range(4):
            raw = super().fetch_raw(symbol, start, end, index=index)
            try:
                rows = normalize_completed_closes(raw, symbol, start, cutoff, end)
                if index:
                    if str(rows[-1][0]) < self.minimum_calendar_end:
                        raise CalendarUnavailable(
                            f"KBS_CALENDAR_REGRESSION: received {rows[-1][0]}, expected at least {self.minimum_calendar_end}"
                        )
                    self.calendar = [d for d, _ in rows]
                elif self.calendar is not None:
                    equity_missing_sessions(
                        symbol, rows, [str(d) for d in self.calendar if d >= start]
                    )
                return raw
            except ValueError:
                if attempt == 3:
                    raise


def calendar_ends(sessions, previous, cutoff):
    # Historical Market snapshots also cover bundles published before this worker existed.
    m = Snapshot.manifest
    end = m["end_date"].as_string()
    pinned = (Snapshot.id == previous.get("snapshot_id")) & (
        Snapshot.content_hash == previous.get("snapshot_hash")
    )
    with sessions() as session:
        return session.execute(
            select(func.max(end), func.max(case((pinned, end)))).where(
                m["universe_id"].as_string() == "VN_USER_SELECTION",
                m["calendar"].as_string() == "kbs-observed-vnindex-sessions",
                m["calendar_status"].as_string() == "AVAILABLE",
                m["data_origin"].as_string() == "real",
                end <= str(cutoff),
            )
        ).one()


def write_handoff(path, receipt):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt))
    os.replace(tmp, path)


def tick(now, *, retry_failed=False):
    HANDOFF.mkdir(exist_ok=True)
    with (HANDOFF / "refresh.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        path = HANDOFF / "snapshot.json"
        slot = int(now.timestamp()) // (4 * 3600)
        cutoff = completed_selected_cutoff(now)
        assets = list(ASSET_IDS)
        previous = json.loads(path.read_text()) if path.exists() else {}
        sessions = sessions_from_env()
        floor, pinned_end = calendar_ends(sessions, previous, cutoff)
        if previous.get("slot") == slot and previous.get("cutoff_date") == str(cutoff):
            if (
                pinned_end is not None
                and pinned_end == floor
                and previous.get("availability_policy") == LIVE_NAV_POLICY
            ):
                assets = previous.get("retry_assets", [])
                if not assets or (
                    not retry_failed and now.timestamp() < previous["retry_after"]
                ):
                    return
        kbs = CheckedKbs()
        kbs.cutoff = cutoff
        kbs.minimum_calendar_end = floor or ""
        try:
            data = refresh_selected(
                assets,
                cutoff,
                ArtifactStore(SOURCE),
                sessions=sessions,
                kbs=kbs,
                seed=str(SOURCE / "seed.json"),
                now=now,
                minimum_calendar_end=kbs.minimum_calendar_end,
            )
            if not data["calendar_sessions"]:
                raise CalendarUnavailable("KBS_CALENDAR_UNAVAILABLE")
        except CalendarUnavailable:
            if previous:
                write_handoff(
                    path,
                    previous
                    | dict(
                        retry_assets=list(ASSET_IDS), retry_after=now.timestamp() + 600
                    ),
                )
            raise
        with sessions.begin() as session:
            snapshot = build_selected_snapshot(
                session,
                calendar=data["calendar_sessions"],
                availability_policy=LIVE_NAV_POLICY,
            )
            receipt = dict(
                slot=slot,
                cutoff_date=str(cutoff),
                snapshot_id=snapshot.id,
                snapshot_hash=snapshot.content_hash,
                availability_policy=LIVE_NAV_POLICY,
                refreshed_at=utcnow().isoformat(),
                retry_assets=[
                    a
                    for a, result in data["asset_receipts"].items()
                    if result["status"] != "AVAILABLE"
                ],
                retry_after=now.timestamp() + 1800,
            )
        write_handoff(path, receipt)
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry unresolved assets now and exit",
    )
    if parser.parse_args().retry_failed:
        tick(utcnow(), retry_failed=True)
        raise SystemExit(0)
    while True:
        try:
            tick(utcnow())
        except Exception as error:
            logging.error(
                "Selected refresh failed (%s); retry in 10 minutes",
                error if isinstance(error, ValueError) else type(error).__name__,
            )
        time.sleep(600)
