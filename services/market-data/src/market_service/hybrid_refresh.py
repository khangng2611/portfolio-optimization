"""Refresh the real selected-assets catalog and hand off immutable buffered snapshot pins."""

import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import time

from portfolio_contracts import utcnow
from portfolio_contracts.assets import ASSET_IDS
from .selected_refresh import (
    POLICY,
    ArtifactStore,
    completed_selected_cutoff,
    refresh_selected,
)
from .selected_snapshots import build_selected_snapshot
from .runtime import sessions_from_env
from .refresh_provider import KbsProvider, normalize
from .phase1_sources import equity_missing_sessions

HANDOFF = Path("/datasets/refresh/hybrid-automation")
SOURCE = Path("/datasets/refresh/full-phase1")


class CheckedKbs(KbsProvider):
    """A replica can return overlapping daily bars. Require a complete clean response."""

    calendar = None

    def fetch_raw(self, symbol, start, end, *, index=False):
        for attempt in range(4):
            raw = super().fetch_raw(symbol, start, end, index=index)
            try:
                rows = normalize(raw, symbol, start, end)
                if index:
                    self.calendar = [d for d, _ in rows]
                elif self.calendar is not None:
                    equity_missing_sessions(
                        symbol, rows, [str(d) for d in self.calendar if d >= start]
                    )
                return raw
            except ValueError:
                if attempt == 3:
                    raise


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
        if path.exists():
            previous = json.loads(path.read_text())
            if previous["slot"] == slot and previous.get("cutoff_date") == str(cutoff):
                assets = previous.get("retry_assets", [])
                if not assets or (
                    not retry_failed and now.timestamp() < previous["retry_after"]
                ):
                    return
        sessions = sessions_from_env()
        data = refresh_selected(
            assets,
            cutoff,
            ArtifactStore(SOURCE),
            sessions=sessions,
            kbs=CheckedKbs(),
            seed=str(SOURCE / "seed.json"),
            now=now,
        )
        if not data["calendar_sessions"]:
            raise ValueError("KBS_CALENDAR_UNAVAILABLE")
        with sessions.begin() as session:
            snapshot = build_selected_snapshot(
                session, calendar=data["calendar_sessions"], availability_policy=POLICY
            )
            receipt = dict(
                slot=slot,
                cutoff_date=str(cutoff),
                snapshot_id=snapshot.id,
                snapshot_hash=snapshot.content_hash,
                refreshed_at=utcnow().isoformat(),
                retry_assets=[
                    a
                    for a in assets
                    if data["asset_receipts"][a]["status"] != "AVAILABLE"
                ],
                retry_after=now.timestamp() + 1800,
            )
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(receipt))
        os.replace(tmp, path)
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
