"""Refresh must not invalidate an already accepted, unexpired input identity."""

import importlib.util
from pathlib import Path

from quant_service.artifacts import ArtifactCatalog


def test_demo_refresh_preserves_queued_jobs_pinned_bundle(tmp_path):
    path = Path(__file__).resolve().parents[2] / "infra/local/bootstrap.py"
    spec = importlib.util.spec_from_file_location("local_bootstrap", path)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    bootstrap.GENERATED = tmp_path
    bootstrap.create_bundle(refresh=False)
    catalog = ArtifactCatalog(tmp_path / "bundles", allow_demo=True)
    old = catalog.ready("DEMO", "MVO")
    bootstrap.create_bundle(refresh=True)
    current = catalog.ready("DEMO", "MVO")
    assert current.bundle_id != old.bundle_id
    assert catalog.load(old, "MVO")["asset_ids"] == old.asset_ids
