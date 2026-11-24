"""Build the frozen 32-asset research panel from one cutoff's captured source vintages."""
from datetime import date, datetime, timedelta
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re

import pandas as pd

from market_service.hybrid_forward_capture import DECISION_TIME, FIRST_DAY, LAST_DAY, SETTLE_UNTIL, HISTORY_START, VIETNAM
from market_service.phase1_sources import (
    EQUITY_GAP_ALLOWLIST, GOLD_PROVIDER, VFF_PROVIDER, frozen_gold,
    normalize_fmarket, normalize_gold_archive, verify_vff_identity,
)
from market_service.refresh_provider import BASE, MAX_BYTES, PROVIDER, normalize, normalized_csv
from portfolio_contracts import canonical_hash
from portfolio_contracts.assets import ASSET_IDS, EQUITY_IDS
from quant_service.full import FullDataUnavailable, MixedPanel, START, check_full_availability

PROTOCOL_SHA256 = "2fe5db506685dfd31486562f016bcefb520bef5e837d5acbafb8360626efac54"


def _timestamp(value):
    ts = datetime.fromisoformat(value)
    if ts.utcoffset() is None:
        raise ValueError("Receipt timestamp lacks timezone")
    return ts


class _Batch:
    def __init__(self, root, batch, cutoff, rehearsal, *, gold_shadow=False):
        self.root, self.path = Path(root).resolve(), Path(batch).resolve()
        self.cutoff = cutoff
        if cutoff.utcoffset() is None or not self.path.is_relative_to(self.root):
            raise ValueError("Invalid archive cutoff or directory")
        parts = self.path.relative_to(self.root).parts
        if len(parts) != 3:
            raise ValueError("Expected phase/date/capture archive")
        self.phase, stamp, capture = parts
        self.day = date.fromisoformat(stamp)
        phases = {"rehearsal"} if rehearsal else {"evaluation", "settlement"}
        if gold_shadow and not rehearsal:
            phases.add("gold_shadow")
        if self.phase not in phases:
            raise ValueError("Archive phase mismatch")
        self.manifest, manifest_hash = self.read("manifest")
        summary, summary_hash = self.read("summary")
        self.hashes = summary["receipts"]
        self.started = _timestamp(self.manifest["started_at"])
        self.finished = _timestamp(summary["finished_at"])
        if any(doc["phase"] != self.phase or doc["date"] != stamp for doc in (self.manifest, summary)):
            raise ValueError("Capture identity mismatch")
        if (self.manifest["schema_version"] != 1 or capture != self.started.strftime("%Y%m%dT%H%M%S%f%z")
                or self.started > self.finished or self.started > cutoff):
            raise ValueError("Invalid capture identity or timing")
        if self.phase == "evaluation":
            scheduled = datetime.combine(self.day, DECISION_TIME, VIETNAM)
            if (not FIRST_DAY <= self.day <= LAST_DAY or _timestamp(self.manifest["decision_at"]) != scheduled
                    or self.started.astimezone(VIETNAM).date() != self.day):
                raise ValueError("Capture outside locked evaluation calendar")
        elif self.phase == "settlement" and not LAST_DAY < self.day <= SETTLE_UNTIL:
            raise ValueError("Capture outside settlement period")
        elif self.phase == "gold_shadow" and (self.day <= SETTLE_UNTIL
                or self.started.astimezone(VIETNAM).date() != self.day or self.manifest["decision_at"] is not None):
            raise ValueError("Capture outside GOLD shadow extension")
        if sha256(self.object(self.manifest["protocol"])).hexdigest() != PROTOCOL_SHA256:
            raise ValueError("Locked protocol hash mismatch")
        for ref in self.manifest["implementation"].values():
            self.object(ref)
        self.provenance = dict(phase=self.phase, batch="/".join(parts), protocol_sha256=PROTOCOL_SHA256,
                               manifest_sha256=manifest_hash, summary_sha256=summary_hash,
                               cutoff=cutoff.isoformat(), receipts={}, historical_publication_verified=False)

    def read(self, name):
        path = self.path / (name + ".json")
        if path.resolve() != path or path.stat().st_size > MAX_BYTES:
            raise ValueError("Invalid archive receipt path or size")
        raw = path.read_bytes()
        return json.loads(raw), sha256(raw).hexdigest()

    def object(self, ref):
        digest = ref["sha256"]
        if (not re.fullmatch(r"[a-f0-9]{64}", digest) or ref["path"] != f"objects/{digest}.gz"
                or not 0 < ref["bytes"] <= MAX_BYTES):
            raise ValueError("Invalid archive object reference")
        path = self.root / ref["path"]
        if path.resolve() != path:
            raise ValueError("Archive object path mismatch")
        with gzip.open(path, "rb") as stream:
            raw = stream.read(ref["bytes"] + 1)
        if len(raw) != ref["bytes"] or sha256(raw).hexdigest() != digest:
            raise ValueError("Archive object hash mismatch")
        return raw

    def source(self, name, url, method, parser, **expected_request):
        receipt, digest = self.read(name)
        if self.hashes.get(name) != digest or receipt["source"] != name:
            raise ValueError(f"{name}: receipt hash or identity mismatch")
        if receipt["status"] != "recorded":
            raise ValueError(f"{name}: {receipt['status']}")
        request = receipt["request"]
        requested, received = (_timestamp(request[k]) for k in ("requested_at", "received_at"))
        attempted = _timestamp(receipt["attempted_at"])
        if not self.started <= attempted <= requested <= received <= min(self.finished, self.cutoff):
            raise ValueError(f"{name}: source unavailable by cutoff")
        if (self.phase == "evaluation" and self.cutoff <= _timestamp(self.manifest["decision_at"])
                and not receipt["available_by_decision"]):
            raise ValueError(f"{name}: capture unavailable by decision")
        if ((request["url"], request["method"]) != (url, method)
                or any(request.get(key) != value for key, value in expected_request.items())):
            raise ValueError(f"{name}: provider identity mismatch")
        rows, metadata = parser(self.object(receipt["raw"]))
        if rows is not None and (receipt["normalized_sha256"] != sha256(normalized_csv(rows, name)).hexdigest()
                                 or receipt["row_count"] != len(rows) or receipt["latest_date"] != str(rows[-1][0])):
            raise ValueError(f"{name}: normalized receipt mismatch")
        self.provenance["receipts"][name] = dict(sha256=digest, raw_sha256=receipt["raw"]["sha256"],
                                                 received_at=received.isoformat())
        return rows, metadata

    def stock(self, asset):
        index = asset == "VNINDEX"
        name = "index" if index else "stocks"
        start = HISTORY_START if index else START
        return self.source(asset, f"{BASE}/{name}/{asset}/data_day", "GET",
                           lambda raw: (normalize(raw, asset, start, self.day), {}),
                           **{"from": str(start), "to": str(self.day)})[0]

    def calendar(self):
        return [str(day) for day, _ in self.stock("VNINDEX")]


def load_calendar(root, batch, cutoff, *, rehearsal=False):
    return _Batch(root, batch, cutoff, rehearsal).calendar()


def _read_sources(data):
    sessions = data.calendar()
    by_asset = {asset: [(day, price, asset) for day, price in data.stock(asset)] for asset in EQUITY_IDS}
    seed = data.manifest["gold_warmup"]
    gold, _ = frozen_gold(data.object(seed))
    data.provenance["receipts"]["GOLD-seed"] = dict(raw_sha256=seed["sha256"], received_at=data.started.isoformat())
    by_asset["GOLD"] = [(day, price, "GOLD-seed") for day, price in gold]
    month = date(2026, 5, 1)
    while month <= data.day:
        name = f"GOLD-{month:%Y-%m}"
        def parse(raw):
            rows, meta = normalize_gold_archive(raw, month.year, month.month)
            return [(day, price) for day, price in rows if day <= data.day], meta
        rows, _ = data.source(name, f"https://giavang.tv/lich-su/{month.year}/{month.month}", "GET", parse)
        by_asset["GOLD"].extend((day, price, name) for day, price in rows)
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    data.source("VFF-identity", "https://api.fmarket.vn/res/products/filter", "POST", lambda raw: (verify_vff_identity(raw), {}),
                payload={"searchField": "VFF", "types": ["NEW_FUND", "TRADING_FUND"], "pageSize": 100})
    rows, meta = data.source("VFF", "https://api.fmarket.vn/res/product/get-nav-history", "POST",
                             lambda raw: normalize_fmarket(raw, HISTORY_START, data.day),
                             payload={"isAllData": 1, "productId": 21, "fromDate": None, "toDate": data.day.strftime("%Y%m%d")})
    by_asset["VFF"] = [(day, price, "VFF") for day, price in rows]
    return sessions, by_asset, meta


def _valuation(sessions, by_asset):
    dates = pd.DatetimeIndex(sessions, name="date")
    columns = {}
    for asset in ASSET_IDS:
        marks = pd.Series({pd.Timestamp(d): float(p) for d, p, _ in by_asset[asset]}).sort_index()
        values = marks.reindex(dates)
        if asset == "VFF":
            # Weekly NAV marks carry by valuation date, with no interpolation or backward fill.
            position = marks.index.get_indexer(dates, method="pad", tolerance=pd.Timedelta(days=7))
            values = marks.iloc[position].set_axis(dates).where(position >= 0)
        elif asset in EQUITY_IDS:
            allowed = dates.isin(pd.to_datetime(EQUITY_GAP_ALLOWLIST.get(asset, [])))
            values = values.where(~(values.isna() & allowed), values.ffill())
        columns[asset] = values
    return pd.DataFrame(columns).loc[str(START):]


def load_valuation(root, batch, cutoff, *, rehearsal=False):
    """Economic marks from a captured vintage. Missing closes stay missing for reconciliation."""
    data = _Batch(root, batch, cutoff, rehearsal)
    sessions, rows, _ = _read_sources(data)
    return dict(sessions=sessions, assets=list(ASSET_IDS), valuation=_valuation(sessions, rows),
                provenance=data.provenance | {"snapshot_hash": canonical_hash(data.provenance)})


def load_panel(root, batch, cutoff, *, rehearsal=False, prepare_only=False):
    data = _Batch(root, batch, cutoff, rehearsal)
    if not rehearsal and (data.phase != "evaluation" or cutoff != _timestamp(data.manifest["decision_at"])):
        raise ValueError("Decision requires the locked evaluation cutoff")
    sessions, rows, nav_meta = _read_sources(data)
    dates = {day for day in sessions if day >= str(START)}
    observations, gaps = [], {}
    for asset in ASSET_IDS:
        received_days = {str(day) for day, _, _ in rows[asset]}
        if asset in EQUITY_IDS:
            missing = dates - received_days
            unknown = missing - set(EQUITY_GAP_ALLOWLIST.get(asset, []))
            if unknown or received_days - dates:
                raise ValueError(f"MISSING_SESSIONS {asset}: {sorted(unknown or received_days - dates)}")
            gaps[asset] = sorted(missing)
        for day, price, source in rows[asset]:
            item = data.provenance["receipts"][source]
            provider, unit, basis = ((VFF_PROVIDER, "VND/unit", "nav") if asset == "VFF"
                                     else (GOLD_PROVIDER, "VND/tael", "raw_close") if asset == "GOLD"
                                     else (PROVIDER, "VND/share", "provider_adjusted"))
            observations.append(dict(asset_id=asset, observation_date=str(day), price_vnd=str(price), provider=provider,
                                     unit=unit, price_type="nav" if asset == "VFF" else "close", price_basis=basis,
                                     data_origin="real", ingested_at=item["received_at"], available_at=item["received_at"],
                                     revision_id=f"{asset}/{day}/{item['raw_sha256']}", raw_source_hash=item["raw_sha256"],
                                     source_metadata=nav_meta[str(day)] if asset == "VFF" else {}))
    manifest = dict(schema_version=2, status="READY", quality_status="PASS", currency="VND",
                    data_origin="real", availability_policy="phase1-full-v1", candidate_equity_ids=list(EQUITY_IDS),
                    asset_ids=list(ASSET_IDS), calendar_sessions=sessions, end_date=sessions[-1],
                    equity_missing_sessions=gaps, observation_count=len(observations),
                    revision_ids=[r["revision_id"] for r in observations],
                    observation_hash=canonical_hash({"observations": observations}))
    digest = canonical_hash(manifest)
    snapshot = manifest | dict(id=digest, created_at=max(_timestamp(x["received_at"]) for x in data.provenance["receipts"].values()).isoformat(),
                               content_hash=digest)
    panel = MixedPanel(snapshot, observations, expected_hash=digest, now=cutoff)
    availability = {asset: panel.ledger[asset][-1] for asset in ASSET_IDS}
    decision_block = None
    try:
        check_full_availability({"availability": availability, "freshness_max_age_days": 7}, now=cutoff)
    except FullDataUnavailable as exc:
        if not prepare_only:
            raise
        decision_block = {"reason": str(exc), "details": exc.details}
    return dict(sessions=sessions, assets=list(ASSET_IDS), decision_block=decision_block,
                information=pd.DataFrame(panel.prices, index=pd.DatetimeIndex(panel.dates, name="date"), columns=ASSET_IDS),
                valuation=_valuation(sessions, rows),
                provenance=data.provenance | dict(snapshot_hash=digest, observation_hash=manifest["observation_hash"],
                              price_unit="VND", availability=availability, equity_missing_sessions=gaps))
