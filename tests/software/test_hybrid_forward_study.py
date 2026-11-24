from datetime import date, datetime
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import hybrid_forward_study as study


def test_ledger_is_append_only_and_calendar_cannot_reindex_old_decisions(tmp_path):
    row = {"session": "2026-11-24", "session_offset": 0, "status": "HOLD", "reason": "NO_CAPTURE"}
    study.commit_row(tmp_path, row)
    study.commit_row(tmp_path, row)
    with pytest.raises((OSError, ValueError)):
        study.commit_row(tmp_path, row | {"reason": "late update"})
    assert study.read_rows(tmp_path, ["2026-11-24"]) == [row]
    with pytest.raises(ValueError):
        study.read_rows(tmp_path, ["2026-11-23", "2026-11-24"])


def test_no_retroactive_decision_or_early_scoring():
    day = date(2026, 11, 24)
    assert study.still_open(day, datetime(2026, 11, 24, 19, 40, tzinfo=study.VIETNAM))
    assert not study.still_open(day, datetime(2026, 11, 24, 20, tzinfo=study.VIETNAM))
    with pytest.raises(ValueError, match="settlement"):
        study.finalize(Path("/unused"), Path("/unused"), datetime(2027, 11, 30, 23, 59, tzinfo=study.VIETNAM))
