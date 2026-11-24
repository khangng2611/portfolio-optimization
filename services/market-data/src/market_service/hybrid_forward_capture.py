"""Archive real provider vintages for the locked HYBRID walk-forward study."""

import argparse
from datetime import date, datetime, time, timedelta
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from zoneinfo import ZoneInfo

from portfolio_contracts import utcnow
from portfolio_contracts.assets import EQUITY_IDS
import requests

from .phase1_full import START
from .phase1_sources import (
    MixedSource,
    frozen_gold,
    normalize_fmarket,
    normalize_gold_archive,
    verify_vff_identity,
)
from .refresh_provider import BASE, MAX_BYTES, KbsProvider, normalize, normalized_csv

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
FIRST_DAY = date(2026, 11, 24)
LAST_DAY = date(2027, 11, 23)
SETTLE_UNTIL = LAST_DAY + timedelta(days=7)
DECISION_TIME = time(20)
COLLECTION_HOUR = 19
MAX_ATTEMPTS = 3
HISTORY_START = date(2020, 1, 1)


def window(now, rehearsal=False, *, gold_shadow=False):
    local = now.astimezone(VIETNAM)
    day = local.date()
    if rehearsal:
        completed = day if local.hour >= 18 else day - timedelta(days=1)
        return completed, "rehearsal", None
    if FIRST_DAY <= day <= SETTLE_UNTIL and 18 <= local.hour < DECISION_TIME.hour:
        if day <= LAST_DAY:
            return day, "evaluation", datetime.combine(day, DECISION_TIME, VIETNAM)
        return day, "settlement", None
    if gold_shadow and day > SETTLE_UNTIL and 18 <= local.hour < DECISION_TIME.hour:
        return day, "gold_shadow", None
    return None


def due(root, now, *, gold_shadow=False):
    active = window(now, gold_shadow=gold_shadow)
    if not active or now.astimezone(VIETNAM).hour < COLLECTION_HOUR:
        return False
    day, phase, _ = active
    attempts = sorted((root / phase / str(day)).glob("*/summary.json"))
    if not attempts:
        return True
    last = json.loads(attempts[-1].read_bytes())
    if (last["status"] == "recorded" and not last.get("recent_stock_gaps")) or len(attempts) >= MAX_ATTEMPTS:
        return False
    return now >= datetime.fromisoformat(last["finished_at"]) + timedelta(minutes=10)


def write_once(path, content):
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(0o400)
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise OSError(f"Archive content mismatch at {path.name}") from None
        finally:
            temporary.unlink()


def save_json(path, value):
    write_once(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def archive(root, raw):
    digest = sha256(raw).hexdigest()
    relative = Path("objects") / f"{digest}.gz"
    (root / relative.parent).mkdir(mode=0o700, exist_ok=True)
    target = root / relative
    # Different zlib versions can encode the same provider response differently.
    if not target.is_file():
        write_once(target, gzip.compress(raw, mtime=0))
    if gzip.decompress(target.read_bytes()) != raw:
        raise OSError(f"Archive content mismatch at {target.name}")
    return {"path": str(relative), "sha256": digest, "bytes": len(raw)}


def capture_source(root, batch, name, decision_at, fetch, parse):
    record = {"source": name, "attempted_at": utcnow().isoformat()}
    try:
        raw, request = fetch()
    except (requests.RequestException, OSError, ValueError) as exc:
        record.update(
            status="fetch_failed", error=str(exc), available_by_decision=False
        )
    else:
        record.update(
            request=request, raw=archive(root, raw), available_by_decision=False
        )
        try:
            rows = parse(raw)
            if rows is not None and not rows:
                raise ValueError("No rows on or before the source cutoff")
        except (ValueError, KeyError, IndexError, TypeError, ArithmeticError) as exc:
            record.update(status="invalid", error=str(exc))
        else:
            received_at = datetime.fromisoformat(request["received_at"])
            record.update(
                status="recorded",
                available_by_decision=decision_at is not None
                and received_at <= decision_at,
            )
            if rows is not None:
                record.update(
                    row_count=len(rows),
                    latest_date=str(rows[-1][0]),
                    recent_dates=[str(day) for day, _ in rows[-15:]],
                    normalized_sha256=sha256(normalized_csv(rows, name)).hexdigest(),
                )
    save_json(batch / f"{name}.json", record)
    return record


def collect(root, gold_seed, protocol, now, *, rehearsal=False, gold_shadow=False):
    capture_window = window(now, rehearsal, gold_shadow=gold_shadow)
    if capture_window is None:
        return {"status": "outside_capture_window", "checked_at": now.isoformat()}
    day, phase, decision_at = capture_window
    if gold_seed.stat().st_size > MAX_BYTES:
        raise ValueError("GOLD seed exceeds bounded size")
    seed = gold_seed.read_bytes()
    frozen_gold(seed)
    batch = root / phase / str(day) / now.strftime("%Y%m%dT%H%M%S%f%z")
    batch.mkdir(mode=0o700, parents=True)
    source_dir = Path(__file__).parent
    manifest = {
        "schema_version": 1,
        "phase": phase,
        "date": str(day),
        "started_at": now.isoformat(),
        "decision_at": decision_at.isoformat() if decision_at else None,
        "protocol": archive(root, protocol.read_bytes()),
        "gold_warmup": archive(root, seed),
        "implementation": {
            module: archive(root, (source_dir / module).read_bytes())
            for module in (
                "hybrid_forward_capture.py",
                "refresh_provider.py",
                "phase1_sources.py",
            )
        },
        "historical_publication_verified": False,
    }
    save_json(batch / "manifest.json", manifest)
    kbs, mixed = KbsProvider(), MixedSource()
    sources = {}

    def record(name, fetch, parse):
        sources[name] = capture_source(root, batch, name, decision_at, fetch, parse)

    def stock(asset, start, index):
        requested = utcnow()
        raw = kbs.fetch_raw(asset, start, day, index=index)
        return raw, {
            "url": f"{BASE}/{'index' if index else 'stocks'}/{asset}/data_day",
            "method": "GET",
            "from": str(start),
            "to": str(day),
            "requested_at": requested.isoformat(),
            "received_at": utcnow().isoformat(),
        }

    for asset in ("VNINDEX", *EQUITY_IDS):
        start = HISTORY_START if asset == "VNINDEX" else START
        record(
            asset,
            lambda: stock(asset, start, asset == "VNINDEX"),
            lambda raw: normalize(raw, asset, start, day),
        )

    # Preserve each archive version. The trusted warm-up covers through April 2026.
    month = date(2026, 5, 1)
    while month <= day:
        record(
            f"GOLD-{month:%Y-%m}",
            lambda: mixed.fetch(
                f"https://giavang.tv/lich-su/{month.year}/{month.month}"
            ),
            lambda raw: [
                (d, p)
                for d, p in normalize_gold_archive(raw, month.year, month.month)[0]
                if d <= day
            ],
        )
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

    record(
        "VFF-identity",
        lambda: mixed.fetch(
            "https://api.fmarket.vn/res/products/filter",
            payload={
                "searchField": "VFF",
                "types": ["NEW_FUND", "TRADING_FUND"],
                "pageSize": 100,
            },
        ),
        verify_vff_identity,
    )

    def fund(raw):
        if sources["VFF-identity"]["status"] != "recorded":
            raise ValueError("Fund identity is unverified in this capture")
        return normalize_fmarket(raw, HISTORY_START, day)[0]

    record(
        "VFF",
        lambda: mixed.fetch(
            "https://api.fmarket.vn/res/product/get-nav-history",
            payload={
                "isAllData": 1,
                "productId": 21,
                "fromDate": None,
                "toDate": day.strftime("%Y%m%d"),
            },
        ),
        fund,
    )

    issues = {
        name: value["status"]
        for name, value in sources.items()
        if value["status"] != "recorded"
    }
    recent_sessions = sources["VNINDEX"].get("recent_dates", [])[-7:]
    missing_stock_sessions = {
        asset: sorted(
            set(recent_sessions) - set(sources[asset].get("recent_dates", []))
        )
        for asset in EQUITY_IDS
    }
    summary = {
        "status": "partial" if issues else "recorded",
        "phase": phase,
        "date": str(day),
        "source_count": len(sources),
        "issues": issues,
        "finished_at": utcnow().isoformat(),
        "receipt_directory": str(batch),
        "latest_observed_session": sources["VNINDEX"].get("latest_date"),
        "recent_stock_gaps": {
            asset: dates for asset, dates in missing_stock_sessions.items() if dates
        },
        "latest_gold_date": sources[f"GOLD-{day:%Y-%m}"].get("latest_date"),
        "latest_nav_date": sources["VFF"].get("latest_date"),
        "receipts": {
            name: sha256((batch / f"{name}.json").read_bytes()).hexdigest()
            for name in sources
        },
    }
    save_json(batch / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--gold-seed", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--gold-shadow-extension", action="store_true",
                        default=os.environ.get("GOLD_SHADOW_CAPTURE_EXTENSION") == "1",
                        help="Continue market observations for GOLD shadow after the HYBRID study settles")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--rehearsal", action="store_true")
    mode.add_argument("--scheduled", action="store_true")
    args = parser.parse_args()
    if args.scheduled:
        print(
            json.dumps(
                {
                    "status": "scheduled",
                    "timezone": str(VIETNAM),
                    "collection_hour": COLLECTION_HOUR,
                    "decision_at": DECISION_TIME.isoformat(),
                    "first_day": str(FIRST_DAY),
                    "last_day": str(LAST_DAY),
                    "settle_until": str(SETTLE_UNTIL),
                }
            ),
            flush=True,
        )
        while True:
            now = utcnow()
            if due(args.directory, now, gold_shadow=args.gold_shadow_extension):
                print(
                    json.dumps(
                        collect(args.directory, args.gold_seed, args.protocol, now, gold_shadow=args.gold_shadow_extension)
                    ),
                    flush=True,
                )
            sleep(60)
    result = collect(
        args.directory,
        args.gold_seed,
        args.protocol,
        utcnow(),
        rehearsal=args.rehearsal,
    )
    print(json.dumps(result))
    return 1 if result["status"] == "partial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
