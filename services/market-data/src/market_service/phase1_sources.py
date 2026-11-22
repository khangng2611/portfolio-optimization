"""Pinned Phase 1 source identities; metadata is not a verified publication time."""

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from html.parser import HTMLParser
import io
import json
import time

import requests

from portfolio_contracts import utcnow
from .refresh_provider import MAX_BYTES

GOLD_SEED_HASH = "122a1100daac668883854040dc139c5c6a01131b8fa4a9bab93447a9f3e1dc73"
GOLD_PROVIDER = "giavang-sjc-hcm-archive-v1"
VFF_PROVIDER = "fmarket-vff-21-v1"


def positive(value):
    price = Decimal(str(value))
    if not price.is_finite() or price <= 0 or price.as_tuple().exponent < -6:
        raise ValueError("Invalid source price or precision")
    return price


class GoldTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cells = []
        elif tag == "td" and self.cells is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.cells is not None:
            self.rows.append(self.cells)
            self.cells = None


def normalize_gold_archive(raw, year, month):
    if len(raw) > MAX_BYTES:
        raise ValueError("Source exceeds bounded size")
    text = raw.decode("utf-8")
    if "Vàng SJC 1L, 10L, 1KG" not in text or "Hồ Chí Minh" not in text:
        raise ValueError("GOLD source identity changed")
    table = GoldTable()
    table.feed(text)
    rows, metadata = [], {}
    for cells in table.rows:
        if len(cells) != 3:
            continue
        # Day cells include a provider carry annotation after the date.
        stamp = cells[0].split()[0]
        try:
            day = datetime.strptime(stamp, "%d/%m/%Y").date()
        except ValueError:
            continue
        if (day.year, day.month) != (year, month) or str(day) in metadata:
            raise ValueError("Invalid GOLD archive dates")
        sell = cells[2].split()[0].replace(".", "").replace(",", ".")
        rows.append((day, positive(Decimal(sell) * 1_000_000)))
        metadata[str(day)] = {
            "provider_carry_flag": "không đổi" in " ".join(cells),
            "historical_publication_verified": False,
            "source_identity": "SJC 1L,10L,1KG sell HCM",
        }
    if not rows:
        raise ValueError("Missing GOLD archive rows")
    return sorted(rows), metadata


def frozen_gold(raw):
    if hashlib.sha256(raw).hexdigest() != GOLD_SEED_HASH:
        raise ValueError("Frozen GOLD checksum mismatch")
    rows, metadata = [], {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        day = date.fromisoformat(row["date"])
        rows.append((day, positive(Decimal(row["sjc_sell"]) * 1000)))
        metadata[str(day)] = {
            "provider_carry_flag": row["provider_carry_flag"].lower() == "true",
            "historical_publication_verified": False,
            "source_identity": "SJC 1L,10L,1KG sell HCM",
            "source_file": row["source_file"],
            "source_precision": row["published_precision"],
        }
    return rows, metadata


def normalize_fmarket(raw, start, end):
    if len(raw) > MAX_BYTES:
        raise ValueError("Source exceeds bounded size")
    payload = json.loads(raw, parse_float=Decimal)
    records = payload.get("data")
    if (
        payload.get("status") != 200
        or not isinstance(records, list)
        or not 1 <= len(records) <= 5000
    ):
        raise ValueError("Missing bounded VFF NAV history")
    prices, metadata = {}, {}
    for row in records:
        if row.get("productId") != 21:
            raise ValueError("VFF product identity mismatch")
        day = date.fromisoformat(row["navDate"])
        price = positive(row["nav"])
        if day in prices and prices[day] != price:
            raise ValueError("VFF duplicate conflicting NAV")
        if not start <= day <= end:
            continue
        stamp = row.get("createdAt")
        created = (
            datetime(1970, 1, 1, tzinfo=timezone.utc)
            + timedelta(milliseconds=int(stamp))
            if stamp is not None
            else None
        )
        prices[day] = price
        # Preserve all duplicate provider record metadata, never reinterpret it as publication.
        entry = metadata.setdefault(
            str(day),
            {
                "product_id": 21,
                "nav_date": str(day),
                "raw_fund_record_created_at": None,
                "historical_publication_verified": False,
                "provider_records": [],
            },
        )
        entry["provider_records"].append(
            {
                "id": row.get("id"),
                "created_at": created.isoformat() if created else None,
            }
        )
        if created and (
            entry["raw_fund_record_created_at"] is None
            or created.isoformat() > entry["raw_fund_record_created_at"]
        ):
            entry["raw_fund_record_created_at"] = created.isoformat()
        entry["provider_record_created_at"] = entry["raw_fund_record_created_at"]
    if not prices:
        raise ValueError("Missing VFF requested history")
    return sorted(prices.items()), metadata


def verify_vff_identity(raw):
    payload = json.loads(raw)
    rows = payload.get("data", {}).get("rows", [])
    matches = [r for r in rows if r.get("id") == 21]
    if payload.get("status") != 200 or len(matches) != 1:
        raise ValueError("VFF product identity missing")
    row = matches[0]
    if (
        row.get("code") != "VFF"
        or row.get("dataFundAssetType", {}).get("code") != "BOND"
        or row.get("owner", {}).get("shortName") != "VINACAPITAL"
    ):
        raise ValueError("VFF product identity changed")


class MixedSource:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/html",
                "Origin": "https://fmarket.vn",
            }
        )
        self.last_request = 0.0

    def fetch(self, url, *, payload=None):
        time.sleep(max(0, 1 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        requested = utcnow().isoformat()
        with self.session.request(
            "POST" if payload is not None else "GET",
            url,
            json=payload,
            timeout=(5, 15),
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise OSError("Phase 1 source unavailable")
            chunks, size, started = [], 0, time.monotonic()
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES or time.monotonic() - started > 20:
                    raise OSError("Source response exceeded bounds")
                chunks.append(chunk)
            return b"".join(chunks), {
                "url": url,
                "method": "POST" if payload is not None else "GET",
                "payload": payload,
                "requested_at": requested,
                "received_at": utcnow().isoformat(),
                "status": 200,
            }


# Only these missing sessions are evidenced by the frozen baseline source.
EQUITY_GAP_ALLOWLIST = {
    "ACB": ["2020-12-02", "2020-12-03", "2020-12-04", "2020-12-07", "2020-12-08"],
    "DGC": [
        "2020-07-20",
        "2020-07-21",
        "2020-07-22",
        "2020-07-23",
        "2020-07-24",
        "2020-07-27",
    ],
    "GVR": [
        "2020-03-09",
        "2020-03-10",
        "2020-03-11",
        "2020-03-12",
        "2020-03-13",
        "2020-03-16",
    ],
    "LPB": [
        "2020-10-26",
        "2020-10-27",
        "2020-10-28",
        "2020-10-29",
        "2020-10-30",
        "2020-11-02",
        "2020-11-03",
        "2020-11-04",
        "2020-11-05",
        "2020-11-06",
    ],
    "SHB": ["2021-10-06", "2021-10-07", "2021-10-08"],
    "VIB": [
        "2020-10-30",
        "2020-11-02",
        "2020-11-03",
        "2020-11-04",
        "2020-11-05",
        "2020-11-06",
        "2020-11-09",
    ],
}

EQUITY_GAP_EVIDENCE = {
    "baseline": "availability-observed-contract-20261012T233110",
    "calendar_sha256": "cc9d57fa3a725ac7d5058a45b4464f59c21b08b6dc51cfc35bd7532b4c59f7cd",
    "loader_sha256": "869040738b643030f913ff12fd1522113ca93112b8f7326ad8373648a880a3de",
    "loader_rule": "series.reindex(series.index.union(calendar)).sort_index().ffill().reindex(calendar)",
    "raw_source_sha256": {
        "ACB": "1a49d52a8b6ab4c8f17fd8d12d8c28afcf0ad4dfd288542243cd950091659cac",
        "DGC": "6a2cc0ad30c3567e9b0e5a67d7661f98f5ce2ac0b362ab070cc91201aa22fbc6",
        "GVR": "fb47ee4a438a204f9eefe872a7c5608f2dff7931fae6d047516485f020c2d48a",
        "LPB": "40b04f66a77aeeaf99c367c0c31b5719f1c7324f6c95c8681198ea5cd8c678f8",
        "SHB": "98275cb6f979ecc4c9b2a5a89b782c15ae23400a546c1c7df791b54f6a59eeaf",
        "VIB": "8cbe050485b643032136a3fbe76d22c1b8cb31cd50a483a669a566f2da03423f",
    },
}


def equity_missing_sessions(symbol, rows, calendar):
    from .quality import QualityFailure, finding

    observed = {str(day) for day, _ in rows}
    expected = set(calendar)
    missing = expected - observed
    if observed - expected or not missing <= set(EQUITY_GAP_ALLOWLIST.get(symbol, [])):
        raise QualityFailure([finding("MISSING_SESSIONS")], len(rows))
    return sorted(missing)
