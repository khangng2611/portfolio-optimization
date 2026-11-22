from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from portfolio_contracts import OptimizeCommand, canonical_hash, utcnow


def legacy():
    return OptimizeCommand(
        job_id=uuid4(),
        owner_user_id=uuid4(),
        portfolio_id=uuid4(),
        portfolio_version=1,
        strategy="EW",
        capital_vnd="100000000",
        inputs={
            "bundle_id": "base",
            "bundle_hash": "a" * 64,
            "snapshot_id": "snapshot",
            "asset_ids": ["FPT", "MWG"],
            "as_of_date": "2026-11-11",
            "valid_until": utcnow() + timedelta(hours=1),
        },
        constraints={},
        deadline=utcnow() + timedelta(minutes=2),
        input_hash="0" * 64,
    )


def test_legacy_command_hash_is_unchanged():
    command = legacy()
    original = command.model_dump(
        mode="json",
        exclude={
            "input_hash": True,
            "decision_context": True,
            "inputs": {"provenance"},
        },
    )
    original.pop("selection_context", None)
    assert command.compute_hash() == canonical_hash(original)
    assert command.selection_context is None
    assert "selection_context" not in command.model_dump(mode="json")


def test_selection_context_rejects_duplicate_ids_and_naive_time():
    from portfolio_contracts.selection import SelectionContext

    now = utcnow()
    values = dict(
        revision_id=str(uuid4()),
        candidate_asset_ids=["FPT", "VFF"],
        candidate_hash="a" * 64,
        regime={
            "regime": "normal",
            "vol_ratio": 1.0,
            "drawdown": 0.0,
            "equity_momentum": 0.0,
        },
        regime_input_hash="b" * 64,
        decision_at=now,
        decision_session=now.date(),
        valid_until=now + timedelta(hours=1),
    )
    context = SelectionContext(**values)
    command = legacy()
    selected = command.model_copy(update={"selection_context": context})
    assert selected.compute_hash() != command.compute_hash()
    with pytest.raises(ValidationError):
        SelectionContext(**(values | {"candidate_asset_ids": ["FPT", "FPT"]}))
    with pytest.raises(ValidationError):
        SelectionContext(**(values | {"valid_until": now.replace(tzinfo=None)}))
