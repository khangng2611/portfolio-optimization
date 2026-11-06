"""Bounded KBS daily adapter, verified against installed vnstock 4.0.4 Quote.history.

Fixed endpoints/keys from vnstock/explorer/kbs/{quote,const}.py. KBS `c` is
VND; keep exact decimals without vnstock's optional two-decimal rounding.
https://vnstocks.com/docs/vnstock/tham-khao/data-sources describes KBS/VCI
corporate-action adjusted OHLCV. This is provider-adjusted price, not certified
total return or historical adjustment vintages. Calendar is provider-observed
VNINDEX dates, not an independently verified exchange holiday calendar.
"""

import csv
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import tempfile
from zoneinfo import ZoneInfo

import requests

PROVIDER = "kbs-direct-v1"
SOURCE_DOC = "https://vnstocks.com/docs/vnstock/tham-khao/data-sources"
BASE = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"
MAX_BYTES = 4 * 1024 * 1024
MAX_HISTORY_DAYS = 3650


def completed_cutoff(now):
    return now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date() - timedelta(days=1)


def history_window_expired(initial_start_date, now):
    return (
        completed_cutoff(now) - date.fromisoformat(initial_start_date)
    ).days > MAX_HISTORY_DAYS


class HistoryWindowExpired(ValueError):
    pass


class KbsProvider:
    def __init__(self):
        self.last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        )

    def fetch_raw(self, symbol, start, end, *, index=False):
        if not re.fullmatch(r"[A-Z0-9]{1,12}", symbol) or (
            index and symbol != "VNINDEX"
        ):
            raise ValueError("Invalid source symbol")
        if not start <= end or (end - start).days > MAX_HISTORY_DAYS:
            raise ValueError("Invalid bounded source window")
        # One worker process, at most one source call per second. Retries belong
        # to durable jobs; requests performs no implicit source substitution.
        time.sleep(max(0, 1.0 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        url = f"{BASE}/{'index' if index else 'stocks'}/{symbol}/data_day"
        with self.session.get(
            url,
            params={
                "sdate": start.strftime("%d-%m-%Y"),
                "edate": end.strftime("%d-%m-%Y"),
            },
            timeout=(5, 15),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise OSError("Source unavailable")
            chunks, size = [], 0
            started = time.monotonic()
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES or time.monotonic() - started > 20:
                    raise OSError("Source response exceeded bounds")
                chunks.append(chunk)
            return b"".join(chunks)


def normalize(raw, symbol, start, end):
    if len(raw) > MAX_BYTES:
        raise ValueError("Source response exceeds bounded size")
    payload = json.loads(raw, parse_float=Decimal)
    rows = payload.get("data_day") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise ValueError("Missing bounded source daily bars")
    normalized, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("t"), str):
            raise ValueError("Invalid daily source row")
        day = date.fromisoformat(row["t"][:10])
        if not start <= day <= end or day in seen:
            raise ValueError("Source bars outside requested dates or duplicated")
        price = Decimal(str(row.get("c")))
        if not price.is_finite() or price <= 0:
            raise ValueError("Invalid source close")
        seen.add(day)
        normalized.append((day, price))
    return sorted(normalized)


def normalized_csv(rows, symbol):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["date", "price", "symbol"])
    for day, price in rows:
        writer.writerow([day.isoformat(), str(price), symbol])
    return output.getvalue().encode()


class ArtifactStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def path(self, artifact):
        name = artifact["file"]
        if not re.fullmatch(r"[a-f0-9]{64}\.(json|csv)", name):
            raise ValueError("Invalid artifact name")
        target = (self.directory / name).resolve()
        if not target.is_relative_to(self.directory):
            raise ValueError("Artifact escapes trusted directory")
        return target

    def put(self, raw, suffix):
        digest = hashlib.sha256(raw).hexdigest()
        artifact = {"file": f"{digest}.{suffix}", "sha256": digest, "bytes": len(raw)}
        target = self.path(artifact)
        descriptor, temporary = tempfile.mkstemp(prefix=".refresh-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o444)
            try:
                # Publish only complete bytes and never replace an existing pin.
                os.link(temporary, target)
            except FileExistsError:
                self.read(artifact)
        finally:
            os.unlink(temporary)
        return artifact

    def read(self, artifact):
        target = self.path(artifact)
        if target.stat().st_size > MAX_BYTES:
            raise ValueError("Artifact exceeds bounded size")
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
            raise ValueError("Artifact checksum mismatch")
        return raw
