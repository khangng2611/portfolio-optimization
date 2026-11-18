from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from quant_service.selection_panel import SelectionPanel, save_panel, load_panel
from test_phase1_full_panel import mixed_fixture, repin


def fixture(n=210):
    snapshot, rows, now = mixed_fixture(n)
    snapshot.update(
        schema_version=3,
        quality_status="PER_ASSET",
        availability_policy="user-selection-data-v1",
        catalog_version="supported-assets-v1",
    )
    snapshot["asset_coverage"] = {
        a: {"status": "AVAILABLE"} for a in snapshot["asset_ids"]
    }
    repin(snapshot, rows)
    return snapshot, rows, now


def test_selected_projection_checks_only_required_assets(tmp_path):
    snapshot, rows, now = fixture()
    rows = [r for r in rows if r["asset_id"] != "VFF"]
    snapshot["asset_coverage"]["VFF"]["status"] = "MISSING"
    snapshot.update(
        observation_count=len(rows), revision_ids=[r["revision_id"] for r in rows]
    )
    repin(snapshot, rows)
    panel = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    # Historical fixture: isolate freshness from projection equivalence.
    at = datetime.combine(
        panel.dates[-1], datetime.min.time(), timezone.utc
    ) + timedelta(hours=12)
    panel.known_seconds[:] = 0
    result = panel.project(["FPT", "MWG"], at)
    assert result["prices"].shape[1] == 2
    with pytest.raises(ValueError, match="ASSET_DATA_MISSING"):
        panel.project(["FPT", "VFF"], at)
    path, digest = save_panel(tmp_path, panel)
    loaded = load_panel(tmp_path, path, digest)
    assert np.array_equal(loaded.valid, panel.valid)
    assert np.array_equal(loaded.prices, panel.prices)
    with pytest.raises(ValueError, match="hash"):
        load_panel(tmp_path, path, "a" * 64)


def test_age_seven_passes_eight_fails():
    snapshot, rows, now = fixture()
    panel = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    at = datetime.combine(
        panel.dates[-1], datetime.min.time(), timezone.utc
    ) + timedelta(days=7, hours=12)
    panel.known_seconds[:] = 0
    assert panel.project(["FPT"], at)["availability"]["FPT"]["age_days"] == 7
    with pytest.raises(ValueError, match="ASSET_DATA_STALE"):
        panel.project(["FPT"], at + timedelta(days=1))


def test_latest_completed_session_and_feature_parity():
    from quant_service.full import MixedPanel

    snapshot, rows, now = mixed_fixture(210)
    legacy = MixedPanel(snapshot, rows, expected_hash=snapshot["content_hash"], now=now)
    snapshot.update(
        schema_version=3,
        quality_status="PER_ASSET",
        availability_policy="user-selection-data-v1",
        catalog_version="supported-assets-v1",
    )
    snapshot["asset_coverage"] = {
        a: {"status": "AVAILABLE"} for a in snapshot["asset_ids"]
    }
    repin(snapshot, rows)
    custom = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    assert custom.decision_index == len(custom.dates) - 1
    assert custom.dates == legacy.dates
    assert np.array_equal(custom.prices, legacy.prices)
    before = datetime.combine(
        custom.dates[-1], datetime.min.time(), timezone.utc
    ) + timedelta(hours=10)
    assert custom.index_at(before) == len(custom.dates) - 2
