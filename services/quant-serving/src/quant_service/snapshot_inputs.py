"""Causal, explicitly versioned features/estimates from a hash-pinned Market snapshot.

Only aligned observed sessions are used. This does not certify an exchange calendar
or point-in-time corporate-action adjustment history.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import re

import numpy as np

from portfolio_contracts import canonical_hash, utcnow

FEATURE_SCHEMA = "market-close-features-v1"
FEATURE_NAMES = ["return_1", "momentum_5", "momentum_20", "volatility_20"]
FEATURE_DEFINITION = {
    "schema": FEATURE_SCHEMA,
    "names": FEATURE_NAMES,
    "momentum": "close[t]/close[t-window]-1",
    "volatility": "sample std of 20 daily simple returns; ddof=1",
    "horizon": "next observed session",
    "fill": "none",
}


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware availability required")
    return parsed.astimezone(timezone.utc)


class SnapshotPanel:
    def __init__(
        self,
        snapshot,
        observations,
        *,
        expected_hash,
        now=None,
        max_age_days=7,
        min_returns=60,
        lookback=252,
        max_gap_days=14,
    ):
        self.now = now or utcnow()
        if (
            self.now.tzinfo is None
            or not 1 <= max_age_days <= 30
            or not 20 <= min_returns <= lookback <= 2520
        ):
            raise ValueError("Invalid timing/estimator policy")
        manifest = {
            k: v
            for k, v in snapshot.items()
            if k not in {"id", "content_hash", "created_at"}
        }
        if (
            expected_hash != snapshot.get("content_hash")
            or canonical_hash(manifest) != expected_hash
        ):
            raise ValueError("Market snapshot manifest hash mismatch")
        if (
            snapshot.get("status") != "READY"
            or snapshot.get("schema_version") != 1
            or snapshot.get("currency") != "VND"
            or snapshot.get("data_origin") != "real"
            or snapshot.get("availability_basis") != "ingestion"
            or snapshot.get("calendar") != "observed-sessions-only"
        ):
            raise ValueError("Unverified or unsupported Market snapshot")
        ids = snapshot["asset_ids"]
        if (
            not 2 <= len(ids) <= 100
            or len(set(ids)) != len(ids)
            or any(not re.fullmatch(r"[A-Z0-9_-]{1,64}", a) for a in ids)
        ):
            raise ValueError("Invalid asset universe")
        if (
            len(observations) != snapshot["observation_count"]
            or [r["revision_id"] for r in observations] != snapshot["revision_ids"]
            or len(set(snapshot["revision_ids"])) != len(observations)
            or canonical_hash({"observations": observations})
            != snapshot["observation_hash"]
        ):
            raise ValueError("Market observations hash/revision mismatch")
        created = timestamp(snapshot["created_at"])
        if (
            created > self.now
            or not date.fromisoformat(snapshot["end_date"])
            <= date.fromisoformat(snapshot["as_of_date"])
            <= self.now.date()
        ):
            raise ValueError("Snapshot not yet available")
        by_asset = {a: {} for a in ids}
        conventions = {a: set() for a in ids}
        for row in observations:
            if row["asset_id"] not in by_asset or row.get("data_origin") != "real":
                raise ValueError("Unexpected asset/origin")
            basis = row.get("price_basis")
            unit = row["unit"]
            if (
                basis not in {"provider_adjusted", "raw_close", "nav"}
                or unit not in {"VND/share", "VND/unit", "VND/tael"}
                or (
                    basis == "nav"
                    and (unit != "VND/unit" or row["price_type"] != "nav")
                )
                or (unit == "VND/share" and row["price_type"] != "close")
            ):
                raise ValueError("Unsupported price convention/unit")
            day = date.fromisoformat(row["observation_date"])
            if (
                not date.fromisoformat(snapshot["start_date"])
                <= day
                <= date.fromisoformat(snapshot["end_date"])
            ):
                raise ValueError("Observation outside snapshot window")
            available, ingested = (
                timestamp(row["available_at"]),
                timestamp(row["ingested_at"]),
            )
            published = (
                timestamp(row["published_at"]) if row.get("published_at") else None
            )
            if (
                row.get("availability_basis") != "ingestion"
                or available > created
                or ingested > created
                or available < ingested
                or available.date() < day
                or (
                    published is not None
                    and (published > available or published.date() < day)
                )
            ):
                raise ValueError("Observation timing inconsistent")
            try:
                price = Decimal(str(row["price_vnd"]))
                if not price.is_finite() or price <= 0:
                    raise ValueError("Invalid price")
            except InvalidOperation as exc:
                raise ValueError("Invalid price") from exc
            if day in by_asset[row["asset_id"]]:
                raise ValueError("Duplicate asset/session")
            by_asset[row["asset_id"]][day] = (
                float(price),
                available,
                row["revision_id"],
            )
            conventions[row["asset_id"]].add(
                (row["provider"], row["price_type"], unit, basis)
            )
        dates = sorted(by_asset[ids[0]])
        if len(dates) <= min_returns or any(
            sorted(by_asset[a]) != dates or len(conventions[a]) != 1 for a in ids
        ):
            raise ValueError(
                "Insufficient history or unaligned asset sessions/conventions"
            )
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        if (
            max(gaps) > max_gap_days
            or (self.now.date() - dates[-1]).days > max_age_days
        ):
            raise ValueError("Stale or missing session history")
        self.snapshot, self.ids, self.dates = snapshot, ids, dates
        self.prices = np.array([[by_asset[a][d][0] for a in ids] for d in dates])
        self.known = [[by_asset[a][d][1] for a in ids] for d in dates]
        self.returns = self.prices[1:] / self.prices[:-1] - 1
        if not np.isfinite(self.returns).all():
            raise ValueError("Nonfinite simple returns")
        self.lookback, self.max_age_days = lookback, max_age_days
        self.conventions, self.max_gap = conventions, max(gaps)

    def feature_rows(self, index):
        prices, returns = self.prices, self.returns
        return np.column_stack(
            (
                returns[index - 1],
                prices[index] / prices[index - 5] - 1,
                prices[index] / prices[index - 20] - 1,
                np.std(returns[index - 20 : index], axis=0, ddof=1),
            )
        ).tolist()

    def inputs(self):
        returns = self.returns[-self.lookback :]
        covariance = np.cov(returns, rowvar=False, ddof=1)
        numerical = {
            "asset_ids": self.ids,
            "mean_returns": returns.mean(axis=0).tolist(),
            "covariance": covariance.tolist(),
            "market_weights": [1 / len(self.ids)] * len(self.ids),
        }
        features = {
            "feature_schema_version": FEATURE_SCHEMA,
            "feature_names": FEATURE_NAMES,
            "asset_ids": self.ids,
            "feature_date": self.dates[-1].isoformat(),
            "feature_known_at": max(t for row in self.known for t in row).isoformat(),
            "rows": self.feature_rows(len(self.dates) - 1),
        }
        provenance = {
            "snapshot_id": self.snapshot["id"],
            "snapshot_hash": self.snapshot["content_hash"],
            "observation_hash": self.snapshot["observation_hash"],
            "data_origin": "real",
            "revision_ids": self.snapshot["revision_ids"],
            "calendar": "observed-sessions-only",
            "availability_basis": "ingestion",
            "data_as_of": self.dates[-1].isoformat(),
            "feature_schema_hash": canonical_hash(FEATURE_DEFINITION),
            "estimator": "arithmetic-mean-sample-covariance-v1",
            "return_unit": "daily_simple_fraction",
            "return_observations": len(returns),
            "covariance_ddof": 1,
            "prior_policy": "equal-weight-v1",
            "covariance_rank": int(np.linalg.matrix_rank(covariance)),
            "covariance_condition": float(np.linalg.cond(covariance))
            if np.isfinite(np.linalg.cond(covariance))
            else None,
            "max_calendar_gap_days": self.max_gap,
            "max_data_age_days": self.max_age_days,
            "price_conventions": {
                a: [list(v) for v in self.conventions[a]] for a in self.ids
            },
        }
        return numerical, features, provenance

    def training_data(self, cutoff):
        if not isinstance(cutoff, date) or cutoff >= self.dates[-1]:
            raise ValueError(
                "Training economic cutoff must precede serving feature date"
            )
        features, targets, dates, labels, feature_known, label_known = (
            [],
            [],
            [],
            [],
            [],
            [],
        )
        for i in range(20, len(self.dates) - 1):
            if self.dates[i + 1] > cutoff:
                continue
            batch = self.feature_rows(i)
            for j in range(len(self.ids)):
                features.append(batch[j])
                targets.append(float(self.returns[i, j]))
                dates.append(self.dates[i].isoformat())
                labels.append(self.dates[i + 1].isoformat())
                feature_known.append(
                    max(self.known[k][j] for k in range(i + 1)).isoformat()
                )
                label_known.append(
                    max(self.known[k][j] for k in range(i + 2)).isoformat()
                )
        return {
            "schema_version": 2,
            "horizon_sessions": 1,
            "return_unit": "daily_simple_fraction",
            "asset_ids": self.ids,
            "feature_names": FEATURE_NAMES,
            "feature_schema_version": FEATURE_SCHEMA,
            "snapshot_id": self.snapshot["id"],
            "snapshot_hash": self.snapshot["content_hash"],
            "demo": False,
            "training_cutoff": cutoff.isoformat(),
            "knowledge_cutoff": self.now.isoformat(),
            "features": features,
            "targets": targets,
            "feature_dates": dates,
            "label_dates": labels,
            "feature_known_at": feature_known,
            "label_known_at": label_known,
        }
