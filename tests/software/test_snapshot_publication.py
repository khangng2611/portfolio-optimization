import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from portfolio_contracts import ModelUnavailable
from quant_service.artifacts import ArtifactCatalog
from quant_service.model_worker import train_candidate, approve_candidate
from test_snapshot_inputs import snapshot_fixture


def test_publish_real_bundle_replays_and_preserves_queued_pins(tmp_path):
    from quant_service.snapshot_publisher import publish_snapshot

    snapshot, rows, now = snapshot_fixture()

    def publish():
        return publish_snapshot(
            tmp_path,
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="REAL_STOCKS",
            now=now,
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        published = list(pool.map(lambda _: publish(), range(3)))
    assert published[0] == published[1] == published[2]
    catalog = ArtifactCatalog(tmp_path)
    pin = catalog.ready("REAL_STOCKS", "MVO")
    assert pin.demo is False
    assert pin.provenance["snapshot_hash"] == snapshot["content_hash"]
    with pytest.raises(ModelUnavailable):
        catalog.ready("REAL_STOCKS", "BL_ML")
    from quant_service.snapshot_inputs import SnapshotPanel

    panel = SnapshotPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    model = train_candidate(
        tmp_path, panel.training_data(now.date() - timedelta(days=10))
    )
    approved = approve_candidate(tmp_path, model, reviewer="test")
    publish_snapshot(
        tmp_path,
        snapshot,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id="REAL_STOCKS",
        model=approved,
    )
    assert catalog.ready("REAL_STOCKS", "BL_ML").model_bundle_id == approved["sha256"]
    assert catalog.load(pin, "MVO")["asset_ids"] == ["FPT", "VCB", "HPG"]
    assert len(json.loads((tmp_path / "catalog.json").read_text())["bundles"]) == 2


def test_different_universe_demo_never_poison_real_catalog(tmp_path):
    from quant_service.snapshot_publisher import publish_snapshot
    from test_bootstrap import load_bootstrap

    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    bootstrap.create_bundle(False)
    root = tmp_path / "bundles"
    snapshot, rows, now = snapshot_fixture()
    publish_snapshot(
        root,
        snapshot,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id="REAL",
        now=now,
    )
    catalog = ArtifactCatalog(root)
    assert catalog.ready("REAL", "MVO").demo is False
    assert [u["universe_id"] for u in catalog.universes()] == ["REAL"]
    # Corruption of an indexed unrelated demo file must not stop pinned real reads.
    demo = next(
        e
        for e in json.loads((root / "catalog.json").read_text())["bundles"]
        if e["universe_id"] == "DEMO"
    )
    (root / demo["file"]).chmod(0o600)
    (root / demo["file"]).write_text("broken")
    assert (
        catalog.load(catalog.ready("REAL", "MVO"), "MVO")["asset_ids"]
        == snapshot["asset_ids"]
    )
    publish_snapshot(
        root,
        snapshot,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id="REAL_SECOND",
        now=now,
    )


def test_bootstrap_refresh_and_real_publication_share_catalog_lock(
    tmp_path, monkeypatch
):
    from pathlib import Path
    from threading import Event
    from quant_service.snapshot_publisher import publish_snapshot
    from test_bootstrap import load_bootstrap

    bootstrap = load_bootstrap()
    bootstrap.GENERATED = tmp_path
    bootstrap.create_bundle(False)
    snapshot, rows, now = snapshot_fixture()
    paused, release = Event(), Event()
    original = Path.replace

    def replace(path, target):
        if path.name.startswith(".catalog-"):
            paused.set()
            assert release.wait(5)
        return original(path, target)

    monkeypatch.setattr(Path, "replace", replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        refresh = pool.submit(bootstrap.create_bundle, True)
        assert paused.wait(5)
        publication = pool.submit(
            publish_snapshot,
            tmp_path / "bundles",
            snapshot,
            rows,
            expected_hash=snapshot["content_hash"],
            universe_id="REAL",
            now=now,
        )
        # A writer respecting the lock cannot complete until refresh releases it.
        import time

        time.sleep(0.1)
        blocked = not publication.done()
        release.set()
        refresh.result()
        publication.result()
    assert blocked, "DEMO refresh did not hold the shared publication lock"
    catalog = ArtifactCatalog(tmp_path / "bundles", allow_demo=True)
    assert catalog.ready("REAL", "MVO").demo is False
