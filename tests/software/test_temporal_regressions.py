"""Offline causal perturbations; native training is intercepted, never registered."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_asof_snapshot_ignores_later_revision_even_with_old_publication_date():
    from market_service.models import Base, Asset, PriceRevision
    from market_service.snapshots import build_snapshot
    from portfolio_contracts.market import SnapshotRequest

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    def revision(number, price, known):
        at = datetime(2026, 11, known, 8, tzinfo=timezone.utc)
        return PriceRevision(
            id=f"revision-{number}",
            asset_id="AAA",
            observation_date=date(2026, 11, 6),
            price_vnd=Decimal(price),
            unit="VND/share",
            source_unit="VND/share",
            provider="fixture",
            price_type="close",
            revision=number,
            content_hash=str(number) * 64,
            source_hash="a" * 64,
            published_at=datetime(2026, 11, 6, 8, tzinfo=timezone.utc),
            available_at=at,
            ingested_at=at,
            data_origin="real",
            price_basis="provider_adjusted",
        )

    def request(day):
        return SnapshotRequest(
            asset_ids=["AAA"],
            start_date=date(2026, 11, 6),
            end_date=date(2026, 11, 6),
            as_of_date=date(2026, 11, day),
            max_age_days=7,
        )

    with Session(engine) as db:
        db.add(Asset(id="AAA", kind="stock", unit="VND/share"))
        db.add(revision(1, "100", 7))
        db.flush()
        first = build_snapshot(db, request(8))
        first_hash = first.content_hash
        db.add(revision(2, "110", 9))
        db.flush()
        again = build_snapshot(db, request(8))
        assert again.id == first.id and again.content_hash == first_hash
        assert again.observations[0]["revision_id"] == "revision-1"
        assert (
            build_snapshot(db, request(10)).observations[0]["revision_id"]
            == "revision-2"
        )


def test_v5_future_tail_cannot_change_training_features_labels_or_hash(
    tmp_path, monkeypatch
):
    from ml_platform.selected_train import fit_state, train_asset_candidate
    from ml_platform import full_train
    from test_selected_model import equity_panel

    panel = equity_panel(1)
    original = panel.prices.copy()
    state = fit_state(panel)
    assert state["fit_index"] == 155 and state["training_cutoff"] == panel.dates[149]
    calls = []

    class Captured(Exception):
        pass

    def capture(root, asset, features, labels, indices, dates):
        assert asset == "ACB"
        assert len(features) == 116
        np.testing.assert_array_equal(indices, np.arange(29, 145))
        quoted = (
            original[:, 0] / 1000
        )  # Frozen feature/label pipeline uses thousand VND.
        expected = (quoted[34:150] - quoted[29:145]) / quoted[29:145]
        np.testing.assert_array_equal(labels, expected)
        calls.append((features.copy(), labels.copy()))
        raise Captured()

    monkeypatch.setattr(full_train, "fit_asset", capture)
    with pytest.raises(Captured):
        train_asset_candidate(tmp_path / "before", panel, panel.dates[155])
    panel.prices[150:] *= 1e6
    panel.valid[150:, 0] = False
    assert fit_state(panel) == state
    with pytest.raises(Captured):
        train_asset_candidate(tmp_path / "after", panel, panel.dates[155])
    np.testing.assert_array_equal(calls[0][0], calls[1][0])
    np.testing.assert_array_equal(calls[0][1], calls[1][1])


def test_validation_and_purged_rows_cannot_change_training_scaler(
    tmp_path, monkeypatch
):
    from ml_platform import full_train
    from test_selected_model import equity_panel

    features = np.arange(800, dtype=float).reshape(100, 8)
    labels = np.linspace(-0.1, 0.1, 100)
    indices = np.arange(29, 129)
    calls = []

    class UnitBooster:
        best_iteration, best_score = 0, 1.0

        def save_raw(self, raw_format):
            return b"unit-placeholder-not-a-model"

        def predict(self, data, iteration_range):
            return np.zeros(data.num_row())

    def fit(params, train, **kwargs):
        assert train.num_row() == 75 and kwargs["evals"][0][0].num_row() == 20
        calls.append(train.get_data().toarray())
        return UnitBooster()

    monkeypatch.setattr(full_train.xgb, "train", fit)
    dates = equity_panel(1).dates

    def run(name, rows):
        root = tmp_path / name
        root.mkdir()
        return full_train.fit_asset(root, "ACB", rows, labels, indices, dates)

    before = run("before", features)
    changed = features.copy()
    changed[75:] += 1e9
    after = run("after", changed)
    np.testing.assert_allclose(before[0]["scaler_mean"], features[:75].mean(axis=0))
    assert before[0]["scaler_mean"] == after[0]["scaler_mean"]
    assert before[0]["scaler_scale"] == after[0]["scaler_scale"]
    assert before[1]["purged_rows"] == 5
    assert before[1]["train_label_end"] < before[1]["validation_start"]
    for matrix in calls[1:]:
        np.testing.assert_array_equal(calls[0], matrix)


def test_future_panel_tail_cannot_change_k5_features_or_covariance(monkeypatch):
    from portfolio_core.assets import EQUITY_IDS
    from quant_service import selection, asset_ensemble
    from test_selection_worker import selected_command

    catalog, command, now = selected_command()
    _, panel = catalog.load_resource(command.inputs)
    t = panel.dates.index(command.selection_context.decision_session)
    original = panel.prices.copy()
    model = SimpleNamespace(
        model_id="offline-unit-model",
        fit_epoch=panel.dates[155],
        covered_asset_ids=list(EQUITY_IDS),
    )
    monkeypatch.setattr(
        catalog, "load_resource", lambda pin: ({"model_bundle_id": "a" * 64}, panel)
    )
    monkeypatch.setattr(catalog, "model", lambda value: ("unit-directory", model))
    monkeypatch.setattr(selection, "check_model", lambda *args: model)
    real_select = selection.select_candidate_equities
    equities = [
        a for a in command.selection_context.candidate_asset_ids if a in EQUITY_IDS
    ]

    def select(prices, ids):
        np.testing.assert_array_equal(
            prices, original[:t, [panel.ids.index(a) for a in equities]]
        )
        return real_select(prices, ids)

    monkeypatch.setattr(selection, "select_candidate_equities", select)

    def infer(directory, manifest, features, volatility, active, regime):
        for a, row in features.items():
            np.testing.assert_array_equal(
                row, selection.feature_row(original[:t, panel.ids.index(a)] / 1000)
            )
        return dict(
            views_p=[[1.0] + [0.0] * (len(active) - 1)],
            views_q=[0.001],
            view_confidences=[0.9],
        )

    monkeypatch.setattr(asset_ensemble, "infer_asset_views", infer)
    before = selection.resolve_selection(catalog, command, now=now)
    panel.dates += [
        panel.dates[-1] + timedelta(days=1),
        panel.dates[-1] + timedelta(days=2),
    ]
    for name in (
        "prices",
        "valid",
        "observation_days",
        "policy_seconds",
        "known_seconds",
    ):
        array = getattr(panel, name)
        tail = np.repeat(array[-1:], 2, axis=0)
        if name == "prices":
            tail *= np.random.default_rng(41).uniform(1e3, 1e6, tail.shape)
        setattr(panel, name, np.concatenate([array, tail]))
    after = selection.resolve_selection(catalog, command, now=now)
    assert before == after
