"""Live NAV uses verified inputs today; historical replay keeps its five-session lag."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from quant_service.full import TZ
from quant_service.selection_panel import SelectionPanel, load_panel, save_panel
from test_phase1_full_panel import repin
from test_selection_panel import fixture

LIVE = "user-selection-live-nav-v2"


def live_fixture():
    snapshot, rows, _ = fixture(211)
    known = datetime(2020, 10, 23, 12, tzinfo=TZ)
    verified = known + timedelta(hours=1)
    for row in rows:
        row["ingested_at"] = row["available_at"] = known.isoformat()
    snapshot.update(availability_policy=LIVE, created_at=verified.isoformat())
    for item in snapshot["asset_coverage"].values():
        item["quality_status"] = "PASS"
    repin(snapshot, rows)
    return snapshot, rows, verified


def test_verified_nav_is_usable_without_five_session_wait_and_survives_reload(tmp_path):
    snapshot, rows, now = live_fixture()
    live = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    result = live.project(["VFF"], now)
    assert result["availability"]["VFF"] == {
        "observation_date": "2020-10-22",
        "age_days": 1,
        "available_at": "2020-10-23T05:00:00+00:00",
        "policy_available_at": "2020-10-23T06:00:00+00:00",
        "max_age_days": 7,
    }
    nav = next(
        r
        for r in rows
        if r["asset_id"] == "VFF" and r["observation_date"] == "2020-10-22"
    )
    assert result["prices"][-1, 0] == float(nav["price_vnd"])
    name, digest = save_panel(tmp_path, live)
    loaded = load_panel(tmp_path, name, digest)
    assert loaded.project(["VFF"], now)["availability"] == result["availability"]
    assert np.array_equal(loaded.prices, live.prices)
    # A newly downloaded history cannot be replayed as previously verified input.
    with pytest.raises(ValueError, match="INPUT_INVALID"):
        loaded.project(["VFF"], now - timedelta(seconds=1))

    snapshot["availability_policy"] = "user-selection-data-v1"
    repin(snapshot, rows)
    legacy = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    other_columns = [j for j, asset in enumerate(live.ids) if asset != "VFF"]
    assert np.array_equal(live.prices[:, other_columns], legacy.prices[:, other_columns])
    assert (
        legacy.availability("VFF", legacy.index_at(now), now)["observation_date"]
        == "2020-10-15"
    )
    with pytest.raises(ValueError, match="VFF_STALE"):
        legacy.project(["VFF"], now)


def test_live_nav_age_still_uses_valuation_date_not_download_date():
    snapshot, rows, now = live_fixture()
    panel = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    seven = datetime(2020, 10, 29, 23, 59, tzinfo=TZ)
    assert panel.project(["VFF"], seven)["availability"]["VFF"]["age_days"] == 7
    with pytest.raises(ValueError, match="VFF_STALE"):
        panel.project(["VFF"], seven + timedelta(minutes=1))


def test_live_nav_respects_latest_completed_session():
    snapshot, rows, _ = live_fixture()
    now = datetime(2020, 10, 22, 17, 59, tzinfo=TZ)
    snapshot["created_at"] = now.isoformat()
    for row in rows:
        row["ingested_at"] = row["available_at"] = now.isoformat()
    repin(snapshot, rows)
    panel = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    assert (
        panel.project(["VFF"], now)["availability"]["VFF"]["observation_date"]
        == "2020-10-20"
    )
    assert (
        panel.project(["VFF"], now + timedelta(minutes=1))["availability"]["VFF"][
            "observation_date"
        ]
        == "2020-10-22"
    )


def test_live_publication_pins_policy_and_keeps_legacy_resource_readable(tmp_path):
    import json
    from quant_service.selection_catalog import (
        SelectionCatalog,
        publish_selection_resource,
    )

    snapshot, rows, now = live_fixture()
    live_ref = publish_selection_resource(
        tmp_path,
        snapshot,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id="VN_USER_SELECTION",
        now=now,
    )
    value = json.loads((tmp_path / live_ref["file"]).read_bytes())
    assert value["provenance"]["data_policy_id"] == LIVE
    catalog = SelectionCatalog(tmp_path)
    live_pin = catalog.latest()
    _, panel = catalog.load_resource(live_pin)
    assert (
        panel.project(["VFF"], now)["availability"]["VFF"]["observation_date"]
        == "2020-10-22"
    )
    snapshot["availability_policy"] = "user-selection-data-v1"
    repin(snapshot, rows)
    legacy_ref = publish_selection_resource(
        tmp_path,
        snapshot,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id="VN_USER_SELECTION",
        now=now,
    )
    assert legacy_ref["sha256"] != live_ref["sha256"]
    assert catalog.load_resource(live_pin)[1].snapshot["availability_policy"] == LIVE
    assert (
        catalog.load_resource(catalog.latest())[1].snapshot["availability_policy"]
        == "user-selection-data-v1"
    )


@pytest.mark.parametrize("change", ["future_known", "bad_quality", "wrong_product"])
def test_live_nav_rejects_unverified_inputs(change):
    snapshot, rows, now = live_fixture()
    row = next(r for r in rows if r["asset_id"] == "VFF")
    if change == "future_known":
        row["available_at"] = (now + timedelta(seconds=1)).isoformat()
    elif change == "bad_quality":
        snapshot["asset_coverage"]["VFF"]["quality_status"] = "QUARANTINED"
    else:
        row["source_metadata"]["product_id"] = 22
    repin(snapshot, rows)
    with pytest.raises(ValueError):
        SelectionPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)
