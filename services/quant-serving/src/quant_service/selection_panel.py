"""Immutable numeric shared panel, projected only onto user candidates."""

from bisect import bisect_right
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import io
import json
from math import ceil
from pathlib import Path
import zipfile

import numpy as np

from portfolio_contracts import canonical_hash, utcnow
from portfolio_contracts.selection import LIVE_NAV_POLICY
from portfolio_core.assets import (
    ASSET_IDS,
    EQUITY_IDS,
    CATALOG_VERSION,
    canonical_candidates,
)
from .full import START, TZ, GOLD_PROVIDER, VFF_PROVIDER
from .phase1 import PRICE_CONVENTION
from .snapshot_inputs import timestamp

MAX_BYTES = 32 * 1024 * 1024
ARRAYS = ("prices", "valid", "observation_days", "policy_seconds", "known_seconds")


class SelectionDataError(ValueError):
    def __init__(self, code, asset=None, **details):
        self.code = code
        self.details = dict(asset_id=asset, max_age_days=7, **details)
        super().__init__(f"{code}: {asset or 'selection'}")


class SelectionPanel:
    def __init__(self, snapshot, observations, *, expected_hash, now=None):
        now = now or utcnow()
        manifest = {
            k: v
            for k, v in snapshot.items()
            if k not in {"id", "content_hash", "created_at"}
        }
        if (
            snapshot.get("content_hash") != expected_hash
            or canonical_hash(manifest) != expected_hash
        ):
            raise ValueError("Selection snapshot hash mismatch")
        if (
            snapshot.get("schema_version") != 3
            or snapshot.get("status") != "READY"
            or snapshot.get("quality_status") != "PER_ASSET"
            or snapshot.get("asset_ids") != list(ASSET_IDS)
            or snapshot.get("availability_policy")
            not in {"user-selection-data-v1", LIVE_NAV_POLICY}
            or snapshot.get("catalog_version") != CATALOG_VERSION
            or snapshot.get("currency") != "VND"
            or snapshot.get("data_origin") != "real"
        ):
            raise ValueError("Unsupported selection snapshot identity")
        if (
            len(observations) != snapshot["observation_count"]
            or [r["revision_id"] for r in observations] != snapshot["revision_ids"]
            or len(set(snapshot["revision_ids"])) != len(observations)
            or canonical_hash({"observations": observations})
            != snapshot["observation_hash"]
        ):
            raise ValueError("Selection observation hash mismatch")
        created = timestamp(snapshot["created_at"])
        live_nav = snapshot["availability_policy"] == LIVE_NAV_POLICY
        if created > now or now.tzinfo is None:
            raise ValueError("Selection snapshot not yet available")
        coverage = snapshot.get("asset_coverage")
        if (
            not isinstance(coverage, dict)
            or set(coverage) != set(ASSET_IDS)
            or any(
                not isinstance(item, dict)
                or item.get("status") not in {"AVAILABLE", "MISSING", "QUARANTINED"}
                for item in coverage.values()
            )
        ):
            raise ValueError("Invalid selection asset coverage")
        calendar = [date.fromisoformat(d) for d in snapshot["calendar_sessions"]]
        if (
            not calendar
            or calendar != sorted(set(calendar))
            or len(calendar) > 10000
            or calendar[-1] > now.astimezone(TZ).date()
        ):
            raise ValueError("Invalid selection calendar")
        self.dates = [
            d
            for d in calendar
            if START <= d <= date.fromisoformat(snapshot["end_date"])
        ]
        if not self.dates or self.dates[0] != START:
            raise ValueError("Selection initialization must begin 2020-01-14")
        self.ids = list(ASSET_IDS)
        self.snapshot = snapshot
        self.metadata = snapshot
        self.prices = np.zeros((len(self.dates), 32))
        self.valid = np.zeros_like(self.prices, dtype=bool)
        self.observation_days = np.zeros_like(self.prices, dtype=np.int64)
        self.policy_seconds = np.zeros_like(self.observation_days)
        self.known_seconds = np.zeros_like(self.observation_days)
        gaps = snapshot.get("equity_missing_sessions", {})
        if not isinstance(gaps, dict) or not set(gaps) <= set(EQUITY_IDS):
            raise ValueError("Invalid equity gaps")
        for dates in gaps.values():
            if dates != sorted(set(dates)) or not set(dates) <= set(
                snapshot["calendar_sessions"]
            ):
                raise ValueError("Invalid equity gap dates")
        by_asset = {a: [] for a in self.ids}
        seen = set()
        for row in observations:
            asset = row["asset_id"]
            day = date.fromisoformat(row["observation_date"])
            if (
                asset not in by_asset
                or (asset, day) in seen
                or snapshot["asset_coverage"][asset]["status"] != "AVAILABLE"
                or (
                    live_nav
                    and asset == "VFF"
                    and coverage[asset].get("quality_status") != "PASS"
                )
            ):
                raise ValueError("Unexpected selection observation")
            seen.add((asset, day))
            ingested, known = (
                timestamp(row["ingested_at"]),
                timestamp(row["available_at"]),
            )
            price = float(row["price_vnd"])
            if (
                not ingested <= known <= created
                or known.astimezone(TZ).date() < day
                or row.get("data_origin") != "real"
                or not np.isfinite(price)
                or price <= 0
            ):
                raise ValueError("Invalid selection source availability or price")
            if asset in EQUITY_IDS:
                if (
                    tuple(
                        row[k]
                        for k in ("provider", "price_type", "unit", "price_basis")
                    )
                    != PRICE_CONVENTION
                ):
                    raise ValueError("Invalid equity convention")
                eligible = datetime.combine(day, time(18), TZ)
            elif asset == "GOLD":
                if (
                    row["provider"],
                    row["price_type"],
                    row["unit"],
                    row["price_basis"],
                ) != (GOLD_PROVIDER, "close", "VND/tael", "raw_close"):
                    raise ValueError("Invalid GOLD convention")
                eligible = datetime.combine(day + timedelta(days=1), time(), TZ)
            else:
                if (
                    row["provider"],
                    row["price_type"],
                    row["unit"],
                    row["price_basis"],
                ) != (VFF_PROVIDER, "nav", "VND/unit", "nav") or row.get(
                    "source_metadata", {}
                ).get("product_id") != 21:
                    raise ValueError("Invalid VFF convention")
                if live_nav:
                    # Live statistics align verified NAV by valuation date, not inferred publication.
                    eligible = datetime.combine(day, time(18), TZ)
                else:
                    index = bisect_right(calendar, day) + 4
                    if index >= len(calendar):
                        continue
                    eligible = datetime.combine(calendar[index], time(18), TZ)
                    record = row["source_metadata"].get(
                        "provider_record_created_at"
                    ) or row["source_metadata"].get("raw_fund_record_created_at")
                    if record:
                        eligible = max(eligible, timestamp(record))
            by_asset[asset].append((eligible, day, known, price))
        for j, asset in enumerate(self.ids):
            records = sorted(by_asset[asset])
            cursor, latest = 0, None
            for i, day in enumerate(self.dates):
                cut = datetime.combine(day, time(18), TZ)
                while cursor < len(records) and records[cursor][0] <= cut:
                    row = records[cursor]
                    if latest is None or (row[1], row[0]) > (latest[1], latest[0]):
                        latest = row
                    cursor += 1
                if latest is None:
                    continue
                eligible, observed, known, price = latest
                if (
                    asset in EQUITY_IDS
                    and observed != day
                    and str(day) not in gaps.get(asset, [])
                ):
                    continue
                self.prices[i, j] = price
                self.valid[i, j] = True
                self.observation_days[i, j] = observed.toordinal()
                self.policy_seconds[i, j] = ceil(
                    (
                        max(eligible, known, created)
                        if live_nav and asset == "VFF"
                        else eligible
                    ).timestamp()
                )
                self.known_seconds[i, j] = ceil(known.timestamp())
        self.feature_known_at = max(
            (timestamp(r["available_at"]) for r in observations), default=created
        )
        self.decision_index = self.index_at(now)
        self.panel_hash = canonical_hash(
            {"snapshot_hash": expected_hash, "family": "user-selection-market-v1"}
        )

    def index_at(self, now):
        if now.tzinfo is None:
            raise ValueError("Aware decision time required")
        completed = [
            i
            for i, d in enumerate(self.dates)
            if datetime.combine(d, time(18), TZ) <= now
        ]
        if not completed:
            raise SelectionDataError("HISTORY_INSUFFICIENT")
        return completed[-1]

    def availability(self, asset, index, now):
        j = self.ids.index(asset)
        if not self.valid[index, j]:
            raise SelectionDataError("ASSET_DATA_MISSING", asset)
        observed = date.fromordinal(int(self.observation_days[index, j]))
        return dict(
            observation_date=str(observed),
            age_days=(now.astimezone(TZ).date() - observed).days,
            available_at=datetime.fromtimestamp(
                int(self.known_seconds[index, j]), timezone.utc
            ).isoformat(),
            policy_available_at=datetime.fromtimestamp(
                int(self.policy_seconds[index, j]), timezone.utc
            ).isoformat(),
            max_age_days=7,
        )

    def project(self, candidate_ids, now=None, *, decision_index=None):
        now = now or utcnow()
        if self.snapshot["availability_policy"] == LIVE_NAV_POLICY and now < timestamp(
            self.snapshot["created_at"]
        ):
            raise SelectionDataError("INPUT_INVALID")
        ids = canonical_candidates(candidate_ids)
        t = self.index_at(now) if decision_index is None else decision_index
        if not 120 <= t <= self.index_at(now):
            raise SelectionDataError("HISTORY_INSUFFICIENT")
        availability = {}
        valid_until = datetime.max.replace(tzinfo=timezone.utc)
        indices = [self.ids.index(a) for a in ids]
        for asset, j in zip(ids, indices):
            item = self.availability(asset, t, now)
            availability[asset] = item
            if (
                item["age_days"] < 0
                or max(self.policy_seconds[t, j], self.known_seconds[t, j])
                > now.timestamp()
            ):
                raise SelectionDataError("INPUT_INVALID", asset)
            if item["age_days"] > 7:
                code = (
                    asset + "_STALE" if asset in ("GOLD", "VFF") else "ASSET_DATA_STALE"
                )
                raise SelectionDataError(
                    code,
                    asset,
                    **{k: item[k] for k in ("observation_date", "age_days")},
                )
            if not self.valid[: t + 1, j].all() or np.any(
                self.known_seconds[: t + 1, j] > now.timestamp()
            ):
                raise SelectionDataError("HISTORY_INSUFFICIENT", asset)
            expiry = datetime.combine(
                date.fromisoformat(item["observation_date"]) + timedelta(days=8),
                time(),
                TZ,
            )
            valid_until = min(valid_until, expiry)
        prices = self.prices[: t + 1, indices]
        returns = prices[1:] / prices[:-1] - 1
        return dict(
            asset_ids=ids,
            prices=prices,
            returns=returns,
            availability=availability,
            decision_index=t,
            decision_session=self.dates[t],
            valid_until=valid_until,
        )


def save_panel(directory, panel):
    directory = Path(directory)
    payload = io.BytesIO()
    np.savez_compressed(payload, **{key: getattr(panel, key) for key in ARRAYS})
    content = payload.getvalue()
    digest = sha256(content).hexdigest()
    name = f"selection-panel-{digest}.npz"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    if target.exists():
        if target.read_bytes() != content:
            raise ValueError("Immutable panel collision")
    else:
        target.write_bytes(content)
    meta = {
        "snapshot": panel.snapshot,
        "dates": list(map(str, panel.dates)),
        "panel_hash": panel.panel_hash,
        "npz_hash": digest,
    }
    meta_bytes = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode()
    meta_digest = sha256(meta_bytes).hexdigest()
    meta_name = f"selection-panel-{meta_digest}.json"
    meta_path = directory / meta_name
    if meta_path.exists():
        if meta_path.read_bytes() != meta_bytes:
            raise ValueError("Immutable panel metadata collision")
    else:
        meta_path.write_bytes(meta_bytes)
    return meta_name, meta_digest


def load_panel(directory, name, expected_hash):
    if Path(name).name != name:
        raise ValueError("Invalid panel path")
    directory = Path(directory).resolve()
    path = directory / name
    if path.is_symlink():
        raise ValueError("Invalid panel path")
    content = path.read_bytes()
    if len(content) > MAX_BYTES or sha256(content).hexdigest() != expected_hash:
        raise ValueError("Panel metadata hash mismatch")
    meta = json.loads(content)
    npz = directory / f"selection-panel-{meta['npz_hash']}.npz"
    if npz.is_symlink():
        raise ValueError("Invalid panel array path")
    blob = npz.read_bytes()
    if len(blob) > MAX_BYTES or sha256(blob).hexdigest() != meta["npz_hash"]:
        raise ValueError("Panel array hash mismatch")
    dates = [date.fromisoformat(d) for d in meta["dates"]]
    if (
        not 121 <= len(dates) <= 10000
        or dates != sorted(set(dates))
        or dates[0] != START
    ):
        raise ValueError("Invalid panel dates")
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        entries = archive.infolist()
        if (
            len(entries) != len(ARRAYS)
            or {item.filename for item in entries} != {key + ".npy" for key in ARRAYS}
            or sum(item.file_size for item in entries) > MAX_BYTES
        ):
            raise ValueError("Panel archive exceeds bounds")
        for key in ARRAYS:
            item = archive.getinfo(key + ".npy")
            with archive.open(item) as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError("Unsupported panel array format")
                expected_dtype = np.dtype(
                    "bool"
                    if key == "valid"
                    else "float64"
                    if key == "prices"
                    else "int64"
                )
                if (
                    shape != (len(dates), 32)
                    or fortran
                    or dtype != expected_dtype
                    or stream.tell() + len(dates) * 32 * dtype.itemsize
                    != item.file_size
                ):
                    raise ValueError("Invalid panel array header or payload size")
    with np.load(io.BytesIO(blob), allow_pickle=False) as data:
        arrays = {key: data[key] for key in ARRAYS}
    for key, array in arrays.items():
        expected_kind = "b" if key == "valid" else "f" if key == "prices" else "i"
        if (
            array.shape != (len(dates), 32)
            or array.dtype.kind != expected_kind
            or not np.isfinite(array).all()
        ):
            raise ValueError("Invalid panel array")
    if np.any(arrays["prices"][arrays["valid"]] <= 0):
        raise ValueError("Invalid positive panel price")
    panel = SelectionPanel.__new__(SelectionPanel)
    panel.__dict__.update(
        arrays,
        dates=dates,
        ids=list(ASSET_IDS),
        snapshot=meta["snapshot"],
        metadata=meta["snapshot"],
        panel_hash=meta["panel_hash"],
    )
    panel.feature_known_at = datetime.fromtimestamp(
        int(panel.known_seconds.max()), timezone.utc
    )
    panel.decision_index = panel.index_at(utcnow())
    if panel.panel_hash != canonical_hash(
        {
            "snapshot_hash": panel.snapshot["content_hash"],
            "family": "user-selection-market-v1",
        }
    ):
        raise ValueError("Panel identity hash mismatch")
    return panel
