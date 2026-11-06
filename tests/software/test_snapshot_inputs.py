import copy
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import numpy as np
import pytest

from portfolio_contracts import canonical_hash, utcnow


def snapshot_fixture():
    now = utcnow()
    dates = [(now.date() - timedelta(days=90 - i)).isoformat() for i in range(90)]
    rows = []
    for j, asset in enumerate(["FPT", "VCB", "HPG"]):
        for i, day in enumerate(dates):
            rows.append(
                {
                    "revision_id": str(uuid4()),
                    "asset_id": asset,
                    "observation_date": day,
                    "price_vnd": str(
                        Decimal(50000 + j * 10000 + i * 100 + (i % 5) * j * 20)
                    ),
                    "unit": "VND/share",
                    "provider": "real-import",
                    "price_type": "close",
                    "revision": 1,
                    "content_hash": "a" * 64,
                    "source_hash": "b" * 64,
                    "published_at": None,
                    "available_at": (now - timedelta(minutes=3)).isoformat(),
                    "ingested_at": (now - timedelta(minutes=3)).isoformat(),
                    "availability_basis": "ingestion",
                    "data_origin": "real",
                    "price_basis": "provider_adjusted",
                }
            )
    manifest = {
        "schema_version": 1,
        "status": "READY",
        "asset_ids": ["FPT", "VCB", "HPG"],
        "start_date": dates[0],
        "end_date": dates[-1],
        "as_of_date": now.date().isoformat(),
        "max_age_days": 14,
        "calendar": "observed-sessions-only",
        "observation_count": len(rows),
        "revision_ids": [r["revision_id"] for r in rows],
        "observation_hash": canonical_hash({"observations": rows}),
        "availability_basis": "ingestion",
        "currency": "VND",
        "data_origin": "real",
    }
    snapshot = manifest | {
        "id": str(uuid4()),
        "content_hash": canonical_hash(manifest),
        "created_at": (now - timedelta(minutes=1)).isoformat(),
    }
    return snapshot, rows, now


def repin(snapshot, rows):
    snapshot["observation_hash"] = canonical_hash({"observations": rows})
    snapshot["observation_count"] = len(rows)
    snapshot["revision_ids"] = [r["revision_id"] for r in rows]
    snapshot["content_hash"] = canonical_hash(
        {
            k: v
            for k, v in snapshot.items()
            if k not in {"id", "content_hash", "created_at"}
        }
    )


def test_real_snapshot_builds_independently_checked_daily_statistics_and_causal_features():
    from quant_service.snapshot_inputs import SnapshotPanel

    snapshot, rows, now = snapshot_fixture()
    panel = SnapshotPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    numerical, features, provenance = panel.inputs()
    prices = np.array(
        [
            [float(r["price_vnd"]) for r in rows if r["asset_id"] == a]
            for a in snapshot["asset_ids"]
        ]
    ).T
    returns = prices[1:] / prices[:-1] - 1
    assert numerical["mean_returns"] == pytest.approx(returns.mean(axis=0))
    assert np.asarray(numerical["covariance"]) == pytest.approx(
        np.cov(returns, rowvar=False, ddof=1)
    )
    assert features["feature_names"] == [
        "return_1",
        "momentum_5",
        "momentum_20",
        "volatility_20",
    ]
    assert features["rows"][0] == pytest.approx(
        [
            returns[-1, 0],
            prices[-1, 0] / prices[-6, 0] - 1,
            prices[-1, 0] / prices[-21, 0] - 1,
            np.std(returns[-20:, 0], ddof=1),
        ]
    )
    assert provenance["snapshot_hash"] == snapshot["content_hash"]
    assert provenance["data_origin"] == "real"
    assert provenance["prior_policy"] == "equal-weight-v1"


@pytest.mark.parametrize(
    "failure",
    [
        "hash",
        "rows_hash",
        "unknown",
        "synthetic",
        "future_available",
        "stale",
        "zero",
        "nonfinite",
        "grid",
        "units",
        "basis",
        "duplicate",
        "gap",
    ],
)
def test_builder_fails_closed_for_invalid_real_inputs(failure):
    from quant_service.snapshot_inputs import SnapshotPanel

    snapshot, rows, now = snapshot_fixture()
    if failure == "hash":
        snapshot["content_hash"] = "c" * 64
    elif failure == "rows_hash":
        rows[0]["price_vnd"] = "42"
    else:
        if failure in {"unknown", "synthetic"}:
            rows[0]["data_origin"] = (
                "unverified" if failure == "unknown" else "synthetic"
            )
        if failure == "future_available":
            rows[0]["available_at"] = (now + timedelta(days=1)).isoformat()
        if failure == "stale":
            now += timedelta(days=10)
        if failure == "zero":
            rows[0]["price_vnd"] = "0"
        if failure == "nonfinite":
            rows[0]["price_vnd"] = "NaN"
        if failure == "grid":
            rows.pop(4)
        if failure == "units":
            rows[0]["unit"] = "thousand_VND/share"
        if failure == "basis":
            rows[0]["price_basis"] = "unverified"
        if failure == "duplicate":
            rows.append(dict(rows[0]))
        if failure == "gap":
            start = now.date() - timedelta(days=70)
            end = now.date() - timedelta(days=50)
            rows[:] = [
                r
                for r in rows
                if not start.isoformat() <= r["observation_date"] <= end.isoformat()
            ]
        repin(snapshot, rows)
    with pytest.raises(ValueError):
        SnapshotPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)


def test_training_uses_next_session_labels_and_distinct_ingestion_knowledge_time():
    from quant_service.snapshot_inputs import SnapshotPanel

    snapshot, rows, now = snapshot_fixture()
    panel = SnapshotPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    cutoff = now.date() - timedelta(days=10)
    training = panel.training_data(cutoff)
    assert training["schema_version"] == 2
    assert max(training["label_dates"]) <= cutoff.isoformat()
    assert max(training["label_known_at"]) > cutoff.isoformat()
    assert training["snapshot_hash"] == snapshot["content_hash"]
    # Changing only prices after training cutoff must not change historical X/y.
    future = copy.deepcopy(rows)
    for r in future:
        if r["observation_date"] > cutoff.isoformat():
            r["price_vnd"] = str(float(r["price_vnd"]) * 1.2)
    repin(snapshot, future)
    second = SnapshotPanel(
        snapshot, future, expected_hash=snapshot["content_hash"], now=now
    ).training_data(cutoff)
    assert second["features"] == training["features"]
    assert second["targets"] == training["targets"]
