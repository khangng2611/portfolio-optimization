"""Publish paper market sessions from verified, contemporaneous HYBRID capture receipts."""

import argparse
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import json
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

from market_service.hybrid_forward_capture import DECISION_TIME, FIRST_DAY, VIETNAM
from market_service.phase1_sources import normalize_gold_archive
from portfolio_contracts import canonical_hash
from portfolio_contracts.assets import ASSET_IDS, EQUITY_IDS
from quant_service.gold_shadow_quotes import parse_month
from scripts.gold_shadow_marks import CaptureUnavailable, Captures
from scripts.hybrid_forward_panel import _Batch


class PaperCaptures(Captures):
    @lru_cache(maxsize=24)
    def _batch(self, path, day):
        # A paper user can act after the study's 20:00 cutoff, once a late capture actually finishes.
        cutoff = min(
            self.as_of, datetime.combine(date.fromisoformat(day), time.max, VIETNAM)
        )
        batch = _Batch(self.root, path, cutoff, False, gold_shadow=True)
        if (
            batch.finished > cutoff
            or batch.started.astimezone(VIETNAM).date().isoformat() != day
            or batch.started.astimezone(VIETNAM).hour < 15
        ):
            raise ValueError("Capture is not a completed same-day close")
        return batch


def publish(path, payload):
    with NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(payload, stream, sort_keys=True, allow_nan=False)
            stream.flush()
            temporary.chmod(0o644)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def archived_gold(captures, day, observed):
    year, month = observed.year, observed.month

    def get(batch):
        def parse(raw):
            prices, _ = normalize_gold_archive(raw, year, month)
            pair = parse_month(raw, year, month)[str(observed)]
            if pair["ask"] != dict(prices)[observed]:
                raise ValueError("SJC bid/ask identity mismatch")
            return [(d, p) for d, p in prices if d <= batch.day], pair

        return batch.source(
            f"GOLD-{observed:%Y-%m}",
            f"https://giavang.tv/lich-su/{year}/{month}",
            "GET",
            parse,
        )[1]

    return captures._read(day, "GOLD", get)


def market_frame(captures, day, previous, equity_basis):
    stamp = date.fromisoformat(day)
    # Cutoffs are immutable once the scheduled capture window has closed.
    cutoff = datetime.combine(stamp, DECISION_TIME, VIETNAM)
    frame = dict(
        date=day,
        as_of=cutoff.isoformat(),
        prices={},
        eligible={},
        share_factors={},
        receipts={},
        gold_bid=None,
        gold_ask=None,
        gold_tradable=False,
        vff_nav=None,
        vff_nav_date=None,
        vff_navs={},
        eligible_vff_date=None,
        eligible_gold_bid=None,
        eligible_gold_ask=None,
        source="KBS · VNINDEX và giá đóng cửa cổ phiếu / SJC HCM · giá hai chiều / Fmarket · NAV VFF",
    )
    captures.provenance.clear()
    try:
        if captures._read(day, "VNINDEX", lambda b: b.calendar())[-1] != day:
            return frame
    except CaptureUnavailable:
        return frame
    for asset in EQUITY_IDS:
        prior = equity_basis.get(asset)
        try:
            price, basis = captures._stock(day, asset, prior[0] if prior else None)
        except CaptureUnavailable:
            continue
        frame["prices"][asset] = frame["eligible"][asset] = price
        if prior and prior[1] != basis:
            frame["share_factors"][asset] = prior[1] / basis
    try:
        gold = captures._quote(day)
    except CaptureUnavailable:
        pass
    else:
        frame.update(
            gold_bid=gold["bid"],
            gold_ask=gold["ask"],
            gold_tradable=not gold["provider_carry_flag"],
        )
        frame["prices"]["GOLD"] = (gold["bid"] + gold["ask"]) / 2
    prior_day = stamp - timedelta(days=1)
    try:
        prior_gold = archived_gold(captures, day, prior_day)
    except CaptureUnavailable:
        if (
            previous
            and previous.get("gold_bid")
            and (stamp - date.fromisoformat(previous["date"])).days <= 7
        ):
            prior_day = date.fromisoformat(previous["date"])
            prior_gold = {"bid": previous["gold_bid"], "ask": previous["gold_ask"]}
        else:
            prior_gold = None
    if prior_gold:
        frame.update(
            eligible_gold_bid=prior_gold["bid"],
            eligible_gold_ask=prior_gold["ask"],
            eligible_gold_date=str(prior_day),
        )
        frame["eligible"]["GOLD"] = (prior_gold["bid"] + prior_gold["ask"]) / 2
    try:
        nav, nav_day = captures._nav(day, day)
    except CaptureUnavailable:
        pass
    else:
        frame["prices"]["VFF"] = frame["eligible"]["VFF"] = nav
        frame.update(vff_nav=nav, vff_nav_date=nav_day, eligible_vff_date=nav_day)
        for lag in range(8):
            dealing_day = stamp - timedelta(days=lag)
            if dealing_day.weekday() not in (1, 3):
                continue
            try:
                price, observed = captures._nav(str(dealing_day), day)
            except CaptureUnavailable:
                continue
            if observed == str(dealing_day):
                frame["vff_navs"][observed] = price
    frame["receipts"] = {
        batch: info["summary_sha256"] for batch, info in captures.provenance.items()
    }
    finished = [
        captures._batch(captures.root / batch, day).finished
        for batch in frame["receipts"]
    ]
    frame["as_of"] = max([cutoff, *finished]).isoformat()
    return frame


def export(archive, output, now):
    output.mkdir(parents=True, exist_ok=True)
    captures = PaperCaptures(archive, now)
    days = [
        s
        for s in captures.sessions
        if str(FIRST_DAY) <= s
        and datetime.combine(date.fromisoformat(s), DECISION_TIME, VIETNAM) <= now
    ]
    if not days:
        raise ValueError("No completed VNINDEX capture sessions")
    calendar = output / "calendar.json"
    if calendar.exists():
        prior = json.loads(calendar.read_bytes())["sessions"]
        if days[: len(prior)] != prior:
            raise ValueError(
                "VNINDEX session calendar changed; reconciliation required"
            )
    previous, equity_basis = None, {}
    changed = 0
    for day in days:
        path = output / f"{day}.json"
        if path.exists():
            envelope = json.loads(path.read_bytes())
            previous = envelope["frame"]
            if (
                canonical_hash(previous) != envelope["sha256"]
                or previous["date"] != day
            ):
                raise ValueError("Corrupt previously published market frame")
        else:
            frame = market_frame(captures, day, previous, equity_basis)
            if day == str(now.astimezone(VIETNAM).date()) and (
                not frame["receipts"]
                or not set(ASSET_IDS)
                <= frame["prices"].keys() & frame["eligible"].keys()
            ):
                # Today's capture may retry. Seal remaining partial data after the local date closes.
                break
            publish(path, {"frame": frame, "sha256": canonical_hash(frame)})
            previous = frame
            changed += 1
        equity_basis.update(
            {a: (day, p) for a, p in previous["prices"].items() if a in EQUITY_IDS}
        )
    publish(calendar, {"sessions": days})
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    while True:
        try:
            export(args.archive, args.output, datetime.now(timezone.utc))
        except (ValueError, OSError, KeyError, TypeError):
            if not args.scheduled:
                raise
            logging.exception("Paper market export unavailable")
        if not args.scheduled:
            return
        sleep(60)


if __name__ == "__main__":
    main()
