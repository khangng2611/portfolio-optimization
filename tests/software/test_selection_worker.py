from datetime import datetime, time, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from portfolio_contracts import Constraints, canonical_hash
from portfolio_contracts.selection import SelectionContext
from portfolio_core.assets import candidate_hash
from quant_service.selection import recompute_selection
from quant_service.selection_panel import SelectionPanel
from quant_service.selection_ready import prepare_selection
from quant_service.full import TZ
from test_selection_panel import fixture


def selected_command(ids=None, strategy="BL_ML"):
    snapshot, rows, _ = fixture(211)
    now = datetime.combine(
        datetime.fromisoformat(snapshot["end_date"]).date(), time(19), TZ
    )
    for row in rows:
        row["available_at"] = row["ingested_at"] = now.isoformat()
    snapshot["created_at"] = now.isoformat()
    snapshot["observation_hash"] = canonical_hash({"observations": rows})
    snapshot["content_hash"] = canonical_hash(
        {
            k: v
            for k, v in snapshot.items()
            if k not in ("id", "content_hash", "created_at")
        }
    )
    panel = SelectionPanel(
        snapshot, rows, expected_hash=snapshot["content_hash"], now=now
    )

    class Catalog:
        def latest(self):
            from portfolio_contracts import ReadyInput

            return ReadyInput(
                bundle_id="test",
                bundle_hash="a" * 64,
                snapshot_id=snapshot["id"],
                asset_ids=panel.ids,
                as_of_date=str(panel.dates[-1]),
                valid_until=now + timedelta(hours=12),
            )

        def load_resource(self, pin):
            return {}, panel

        def model(self, value, **kwargs):
            from quant_service.selection_panel import SelectionDataError

            raise SelectionDataError("MODEL_UNAVAILABLE")

    ids = ids or panel.ids[:8] + ["GOLD", "VFF"]
    catalog = Catalog()
    ready = prepare_selection(
        catalog,
        dict(
            candidate_asset_ids=ids,
            candidate_hash=candidate_hash(ids),
            revision_id=str(uuid4()),
            portfolio_version=1,
            constraints=Constraints().model_dump(),
        ),
        now=now,
    )
    context = SelectionContext(
        revision_id=ready.revision_id,
        candidate_asset_ids=ids,
        candidate_hash=ready.candidate_hash,
        regime=ready.regime,
        regime_input_hash=ready.regime_input_hash,
        decision_at=now,
        decision_session=ready.decision_session,
        valid_until=ready.selection_valid_until,
    )
    command = SimpleNamespace(
        selection_context=context,
        inputs=ready.inputs,
        input_hash="b" * 64,
        constraints=ready.effective_constraints,
        decision_context=None,
        strategy=strategy,
        deadline=now + timedelta(minutes=10),
    )
    return catalog, command, now


def test_worker_selects_five_equities_inside_job():
    catalog, command, now = selected_command()
    proof = recompute_selection(catalog, command, now=now)[3]
    assert len(proof.active_asset_ids) == 7
    assert len(proof.rejected_equity_ids) == 3
    assert proof.selection_price_end_date < command.selection_context.decision_session
    command.input_hash = "c" * 64
    repeated = recompute_selection(catalog, command, now=now)[3]
    assert repeated.selection_hash == proof.selection_hash
    assert repeated.input_hash != proof.input_hash
    command.selection_context.regime_input_hash = "d" * 64
    with pytest.raises(ValueError, match="regime"):
        recompute_selection(catalog, command, now=now)


def test_queued_selection_expires_at_day_eight():
    catalog, command, now = selected_command(["FPT", "MWG", "VCB", "VFF"])
    assert len(recompute_selection(catalog, command, now=now)[3].active_asset_ids) == 4
    with pytest.raises(ValueError, match="VFF_STALE"):
        recompute_selection(catalog, command, now=now + timedelta(days=1))


def test_worker_rejects_policy_different_from_pinned_panel():
    catalog, command, now = selected_command(["FPT", "MWG", "VCB", "VFF"])
    command.selection_context.data_policy_id = "user-selection-live-nav-v2"
    with pytest.raises(ValueError, match="policy"):
        recompute_selection(catalog, command, now=now)
