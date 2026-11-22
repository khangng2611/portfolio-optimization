import json

import pytest

from quant_service.artifacts import ArtifactCatalog
from quant_service.snapshot_publisher import publish_snapshot
from test_selection_panel import fixture


def test_custom_publication_is_per_asset_and_hash_pinned(tmp_path):
    snapshot, rows, now = fixture()
    reference = publish_snapshot(
        tmp_path,
        snapshot,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id="VN_USER_SELECTION",
        now=now,
        publication_intent="selection-fixture",
        intent_hash="a" * 64,
    )
    value = json.loads((tmp_path / reference["file"]).read_text())
    assert value["schema_version"] == 2
    assert "numerical" not in value  # shared resource has no user selection
    catalog = ArtifactCatalog(tmp_path)
    assert catalog.selection_catalog.latest().bundle_hash == reference["sha256"]
    assert catalog.universes() == []
    assert (
        catalog.selection_catalog.load_resource(catalog.selection_catalog.latest())[
            1
        ].snapshot["id"]
        == snapshot["id"]
    )
    assert (
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="VN_USER_SELECTION",
            now=now,
            publication_intent="selection-fixture",
            intent_hash="a" * 64,
        )
        == reference
    )
    with pytest.raises(ValueError, match="7 days"):
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="VN_USER_SELECTION",
            max_age_days=8,
            now=now,
        )
    with pytest.raises(ValueError):
        publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="OTHER",
            now=now,
        )
    panel_path = tmp_path / value["panel"]["file"]
    panel_path.write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        catalog.selection_catalog.load_resource(catalog.selection_catalog.latest())
