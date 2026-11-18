import importlib.util
from pathlib import Path

import pytest


def module():
    path = Path("scripts/verify_user_selection_preservation.py")
    spec = importlib.util.spec_from_file_location("selection_preservation", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_preservation_receipt_detects_hash_change_and_ignores_added_rows_columns():
    m = module()
    rows = [
        {"id": "a", "result": {"weights": [0.4, 0.6]}},
        {"id": "b", "result": {"weights": [0.5, 0.5]}},
    ]
    saved = m.row_receipt(rows)
    m.verify_rows(
        saved,
        [dict(row, new_nullable=None) for row in rows] + [{"id": "new", "result": {}}],
    )
    with pytest.raises(ValueError, match="changed"):
        m.verify_rows(saved, [rows[0], {"id": "b", "result": {"weights": [0.6, 0.4]}}])
    with pytest.raises(ValueError, match="missing"):
        m.verify_rows(saved, rows[:1])
    assert "weights" not in str(saved)
