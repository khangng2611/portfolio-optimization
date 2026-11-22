"""Safe reproductions from the user-selection boundary review."""

from datetime import timedelta
import hashlib
import io
import json
import zipfile

import numpy as np
import pytest

from portfolio_contracts import canonical_hash
from quant_service.phase1 import START
from quant_service.selection_panel import ARRAYS, load_panel


def test_npz_array_headers_are_bounded_before_materialization(tmp_path, monkeypatch):
    malformed = io.BytesIO()
    np.lib.format.write_array_header_1_0(
        malformed,
        {
            "descr": "<f8",
            "fortran_order": False,
            "shape": (1_000_000_000, 32),
        },
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for key in ARRAYS:
            if key == "prices":
                content = malformed.getvalue()
            else:
                item = io.BytesIO()
                np.save(
                    item,
                    np.zeros((121, 32), dtype=bool if key == "valid" else np.int64),
                    allow_pickle=False,
                )
                content = item.getvalue()
            archive.writestr(key + ".npy", content)
    blob = payload.getvalue()
    digest = hashlib.sha256(blob).hexdigest()
    (tmp_path / f"selection-panel-{digest}.npz").write_bytes(blob)
    snapshot = {"content_hash": "a" * 64}
    meta = {
        "npz_hash": digest,
        "snapshot": snapshot,
        "dates": [str(START + timedelta(days=i)) for i in range(121)],
        "panel_hash": canonical_hash(
            {
                "snapshot_hash": snapshot["content_hash"],
                "family": "user-selection-market-v1",
            }
        ),
    }
    content = json.dumps(meta).encode()
    (tmp_path / "panel.json").write_bytes(content)

    def no_materialization(*args, **kwargs):
        raise AssertionError(
            "NumPy array materialization reached before rejecting the oversized NPY header"
        )

    monkeypatch.setattr(np.lib.format, "read_array", no_materialization)
    with pytest.raises(ValueError):
        load_panel(tmp_path, "panel.json", hashlib.sha256(content).hexdigest())


def test_fractional_first_seen_is_never_rounded_into_the_past():
    from datetime import datetime, time
    from quant_service.full import TZ
    from quant_service.selection_panel import SelectionPanel
    from test_selection_panel import fixture
    from test_phase1_full_panel import repin

    snapshot, rows, _ = fixture(170)
    known = datetime.combine(
        datetime.fromisoformat(snapshot["end_date"]).date(), time(19, 0, 0, 800000), TZ
    )
    for row in rows:
        row["ingested_at"] = row["available_at"] = known.isoformat()
    snapshot["created_at"] = known.isoformat()
    repin(snapshot, rows)
    panel = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=known
    )
    assert panel.feature_known_at == known
    with pytest.raises(ValueError, match="INPUT_INVALID"):
        panel.project(["FPT"], known.replace(microsecond=0))
    result = panel.project(["FPT"], known.replace(microsecond=0) + timedelta(seconds=1))
    assert result["availability"]["FPT"]["age_days"] == 0


def test_snapshot_coverage_and_calendar_are_validated_at_panel_boundary():
    from copy import deepcopy
    from quant_service.selection_panel import SelectionPanel
    from test_selection_panel import fixture
    from test_phase1_full_panel import repin

    snapshot, rows, now = fixture(170)
    bad = deepcopy(snapshot)
    bad["asset_coverage"].pop("VFF")
    repin(bad, rows)
    with pytest.raises(ValueError, match="coverage"):
        SelectionPanel(bad, rows, expected_hash=bad["content_hash"], now=now)
    bad = deepcopy(snapshot)
    bad["calendar_sessions"].append(str(now.date() + timedelta(days=2)))
    repin(bad, rows)
    with pytest.raises(ValueError, match="calendar"):
        SelectionPanel(bad, rows, expected_hash=bad["content_hash"], now=now)


def test_identical_numeric_panels_allow_distinct_immutable_snapshot_metadata(tmp_path):
    from copy import deepcopy
    from uuid import uuid4
    from quant_service.selection_panel import SelectionPanel, save_panel, load_panel
    from test_selection_panel import fixture

    snapshot, rows, now = fixture(170)
    first = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )
    first_ref, first_hash = save_panel(tmp_path, first)
    original_npz = next(tmp_path.glob("*.npz"))
    original_mtime = original_npz.stat().st_mtime_ns
    second = deepcopy(first)
    second.snapshot["id"] = str(uuid4())
    second.snapshot["asset_coverage"]["VFF"]["note"] = (
        "Independent source metadata revision"
    )
    second.snapshot["content_hash"] = canonical_hash(
        {
            k: v
            for k, v in second.snapshot.items()
            if k not in {"id", "content_hash", "created_at"}
        }
    )
    second.panel_hash = canonical_hash(
        {
            "snapshot_hash": second.snapshot["content_hash"],
            "family": "user-selection-market-v1",
        }
    )
    second_ref, second_hash = save_panel(tmp_path, second)
    assert second_ref != first_ref
    assert second_hash != first_hash
    assert len(list(tmp_path.glob("*.npz"))) == 1
    assert original_npz.stat().st_mtime_ns == original_mtime
    assert (
        load_panel(tmp_path, first_ref, first_hash).snapshot["id"]
        == first.snapshot["id"]
    )
    assert (
        load_panel(tmp_path, second_ref, second_hash).snapshot["id"]
        == second.snapshot["id"]
    )
