from datetime import datetime, time, timedelta
from uuid import uuid4

from portfolio_contracts import Constraints, canonical_hash
from portfolio_core.assets import candidate_hash
from quant_service.selection_ready import prepare_selection
from quant_service.selection_panel import SelectionPanel
from quant_service.full import TZ
from test_selection_panel import fixture


def test_preflight_does_not_run_k5(monkeypatch):
    from portfolio_core import selection

    monkeypatch.setattr(
        selection,
        "select_candidate_equities",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("preflight ran K5")
        ),
    )
    snapshot, rows, _ = fixture(211)
    now = datetime.combine(
        datetime.fromisoformat(snapshot["end_date"]).date(), time(19), TZ
    )
    # Fixture arrival at construction is isolated from source availability in this unit test.
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
                valid_until=now + timedelta(hours=1),
            )

        def load_resource(self, pin):
            return {}, panel

        def model(self, value, **kwargs):
            from quant_service.selection_panel import SelectionDataError

            raise SelectionDataError("MODEL_UNAVAILABLE")

    ids = ["FPT", "MWG", "VCB", "VFF"]
    result = prepare_selection(
        Catalog(),
        dict(
            candidate_asset_ids=ids,
            candidate_hash=candidate_hash(ids),
            revision_id=str(uuid4()),
            portfolio_version=1,
            constraints=Constraints().model_dump(),
        ),
        now=now,
    )
    assert result.reason_code == "MODEL_UNAVAILABLE"
    assert result.regime is not None
    assert not hasattr(result, "selected_equity_ids")
    result = prepare_selection(
        Catalog(),
        dict(candidate_asset_ids=["FPT"], constraints=Constraints().model_dump()),
        now=now,
    )
    assert result.reason_code == "INSUFFICIENT_ASSETS"
