"""Mixed availability and immutable stale publication gates."""

import copy
import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import numpy as np
import pytest

from portfolio_contracts import canonical_hash, utcnow
from portfolio_core.phase1_full import ASSET_IDS, EQUITY_IDS, schedule
from quant_service.full import MixedPanel, FullDataUnavailable, check_full_availability
from quant_service.snapshot_publisher import publish_snapshot
from quant_service.artifacts import ArtifactCatalog


def mixed_fixture(n=210):
    now = utcnow()
    days = []
    day = date(2020, 1, 2)
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    prices = 20000 * np.cumprod(
        1 + np.random.default_rng(42).normal(0.0005, 0.01, (n, 32)), axis=0
    )
    rows = []
    for j, asset in enumerate(ASSET_IDS):
        for i, day in enumerate(days):
            if asset == "VFF" and day.weekday() not in (1, 3):
                continue
            rows.append(
                dict(
                    revision_id=str(uuid4()),
                    asset_id=asset,
                    observation_date=str(day),
                    price_vnd=str(prices[i, j]),
                    unit="VND/unit"
                    if asset == "VFF"
                    else "VND/tael"
                    if asset == "GOLD"
                    else "VND/share",
                    provider="fmarket-vff-21-v1"
                    if asset == "VFF"
                    else "giavang-sjc-hcm-archive-v1"
                    if asset == "GOLD"
                    else "kbs-direct-v1",
                    price_type="nav" if asset == "VFF" else "close",
                    price_basis="nav"
                    if asset == "VFF"
                    else "raw_close"
                    if asset == "GOLD"
                    else "provider_adjusted",
                    data_origin="real",
                    availability_basis="ingestion",
                    ingested_at=now.isoformat(),
                    available_at=now.isoformat(),
                    published_at=None,
                    source_metadata={"product_id": 21} if asset == "VFF" else {},
                    raw_source_hash="a" * 64,
                )
            )
    value = dict(
        schema_version=2,
        status="READY",
        quality_status="PASS",
        asset_ids=list(ASSET_IDS),
        candidate_equity_ids=list(EQUITY_IDS),
        calendar_sessions=list(map(str, days)),
        availability_policy="phase1-full-v1",
        currency="VND",
        data_origin="real",
        availability_basis="ingestion",
        calendar="observed-sessions-only",
        start_date=str(days[0]),
        end_date=str(days[-1]),
        as_of_date=str(now.date()),
        observation_count=len(rows),
        revision_ids=[r["revision_id"] for r in rows],
        observation_hash=canonical_hash({"observations": rows}),
    )
    return (
        value
        | dict(
            id=str(uuid4()),
            content_hash=canonical_hash(value),
            created_at=now.isoformat(),
        ),
        rows,
        now,
    )


def repin(snapshot, rows):
    snapshot["observation_hash"] = canonical_hash({"observations": rows})
    snapshot["content_hash"] = canonical_hash(
        {
            k: v
            for k, v in snapshot.items()
            if k not in {"id", "content_hash", "created_at"}
        }
    )


def test_mixed_panel_preserves_initialization_lag_and_schedule():
    snapshot, rows, now = mixed_fixture()
    panel = MixedPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)
    assert panel.dates[0] == date(2020, 1, 14)
    assert panel.prices.shape[1] == 32
    state = panel.selection_state()
    timing = schedule(len(panel.dates))
    assert state["fit_epoch"] == str(panel.dates[timing["fit_index"]])
    assert state["selection_epoch"] == str(panel.dates[timing["selection_index"]])
    assert len(state["selected_equity_ids"]) == len(state["model_equity_ids"]) == 5
    assert panel.ledger["VFF"][0]["observation_date"] == "2020-01-07"
    assert panel.ledger["VFF"][0]["policy_available_at"] == "2020-01-14T18:00:00+07:00"
    assert panel.ledger["GOLD"][0]["observation_date"] == "2020-01-13"
    assert panel.feature_known_at == now
    numerical, features, provenance = panel.inputs()
    assert numerical["active_asset_ids"] == state["selected_equity_ids"] + [
        "GOLD",
        "VFF",
    ]
    assert features["feature_date"] == str(panel.dates[timing["decision_index"] - 1])
    assert provenance["historical_publication_verified"] is False
    with pytest.raises(FullDataUnavailable, match="VFF_STALE"):
        panel.check_freshness()


def test_late_older_nav_does_not_replace_newer_eligible_nav():
    snapshot, rows, now = mixed_fixture()
    first = next(r for r in rows if r["asset_id"] == "VFF")
    first["source_metadata"]["provider_record_created_at"] = "2020-05-01T10:00:00+00:00"
    repin(snapshot, rows)
    panel = MixedPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)
    index = next(i for i, d in enumerate(panel.dates) if d >= date(2020, 5, 4))
    assert panel.ledger["VFF"][index]["observation_date"] > first["observation_date"]


@pytest.mark.parametrize(
    "change", ["hash", "order", "unit", "identity", "future", "policy"]
)
def test_mixed_panel_rejects_invalid_trust_boundary(change):
    snapshot, rows, now = mixed_fixture()
    if change == "hash":
        rows[0]["price_vnd"] = "1"
    elif change == "order":
        snapshot["asset_ids"][0:2] = reversed(snapshot["asset_ids"][0:2])
        repin(snapshot, rows)
    elif change == "unit":
        rows[0]["unit"] = "thousand_VND/share"
        repin(snapshot, rows)
    elif change == "identity":
        next(r for r in rows if r["asset_id"] == "VFF")["source_metadata"][
            "product_id"
        ] = 22
        repin(snapshot, rows)
    elif change == "future":
        rows[0]["available_at"] = (now + timedelta(days=1)).isoformat()
        repin(snapshot, rows)
    else:
        snapshot["availability_policy"] = "other"
        repin(snapshot, rows)
    with pytest.raises(ValueError):
        MixedPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)


def test_stale_publication_is_visible_but_all_strategies_fail_closed(tmp_path):
    snapshot, rows, now = mixed_fixture()
    ref = publish_snapshot(
        tmp_path,
        snapshot,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id="VN_PHASE1_FULL",
        now=now,
    )
    value = json.loads((tmp_path / ref["file"]).read_text())
    assert value["blocking_reason"]["code"] == "VFF_STALE"
    catalog = ArtifactCatalog(tmp_path)
    readiness = catalog.readiness("VN_PHASE1_FULL")
    assert readiness["reason_code"] == "VFF_STALE"
    assert readiness["next_action"] == "REFRESH_DATA"
    assert readiness["provenance"]["phase1_full"]["freshness_max_age_days"] == 7
    assert all(
        not s["available"] and s["reason_code"] == "VFF_STALE"
        for s in readiness["strategies"]
    )
    assert catalog.universes() == []
    for strategy in ("EW", "MVO", "BL_ML"):
        with pytest.raises(FullDataUnavailable, match="VFF_STALE"):
            catalog.ready("VN_PHASE1_FULL", strategy)
    with pytest.raises(ValueError, match="7 days"):
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="VN_PHASE1_FULL",
            max_age_days=8,
        )


def test_seven_calendar_day_boundary_and_actual_time_recheck():
    # Unit fixture dates only; this never alters the local stack clock.
    cutoff = datetime(2026, 11, 11, 16, tzinfo=timezone.utc)
    item = {
        "observation_date": "2026-11-04",
        "policy_available_at": "2026-11-11T11:00:00+00:00",
        "available_at": "2026-11-11T12:00:00+00:00",
    }
    state = {
        "availability": {a: copy.copy(item) for a in ASSET_IDS},
        "freshness_max_age_days": 7,
    }
    check_full_availability(state, cutoff)
    with pytest.raises(FullDataUnavailable, match="8 days"):
        check_full_availability(state, cutoff + timedelta(days=1))


def test_equity_carry_requires_explicit_snapshot_gap_and_keeps_original_revision():
    snapshot, rows, now = mixed_fixture()
    missing = next(
        r
        for r in rows
        if r["asset_id"] == "ACB" and r["observation_date"] == "2020-02-03"
    )
    rows.remove(missing)
    snapshot["revision_ids"] = [r["revision_id"] for r in rows]
    snapshot["observation_count"] = len(rows)
    repin(snapshot, rows)
    with pytest.raises(ValueError, match="Missing eligible history"):
        MixedPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)
    snapshot["equity_missing_sessions"] = {"ACB": ["2020-02-03"]}
    repin(snapshot, rows)
    panel = MixedPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)
    i = panel.dates.index(date(2020, 2, 3))
    assert panel.prices[i, 0] == panel.prices[i - 1, 0]
    assert (
        panel.ledger["ACB"][i]["revision_id"]
        == panel.ledger["ACB"][i - 1]["revision_id"]
    )
    assert panel.ledger["ACB"][i]["carry_basis"] == "frozen-forward-fill-declared-gap"


def test_reserved_full_universe_rejects_legacy_snapshot(tmp_path):
    from test_snapshot_inputs import snapshot_fixture

    snapshot, rows, now = snapshot_fixture()
    with pytest.raises(ValueError, match="VN_PHASE1_FULL"):
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="VN_PHASE1_FULL",
            now=now,
        )


def test_market_and_serving_source_identities_match():
    from market_service import phase1_sources
    from quant_service import full

    assert full.GOLD_PROVIDER == phase1_sources.GOLD_PROVIDER
    assert full.VFF_PROVIDER == phase1_sources.VFF_PROVIDER
