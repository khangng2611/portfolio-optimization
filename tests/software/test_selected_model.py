from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from portfolio_contracts import utcnow, ModelUnavailable
from portfolio_core.phase1_full import ASSET_IDS, EQUITY_IDS
from quant_service import phase1
from quant_service.ml import parse_manifest, read_artifact, validate_native_files
from quant_service.asset_ensemble import infer_asset_views, validate_coverage
from ml_platform.selected_train import train_asset_candidate


def equity_panel(count=30):
    dates = []
    day = phase1.START
    while len(dates) < 161:
        if day.weekday() < 5:
            dates.append(day)
        day += timedelta(days=1)
    prices = 20000 * np.cumprod(
        1 + np.random.default_rng(732).normal(0.0005, 0.012, (161, 32)), axis=0
    )
    valid = np.ones(prices.shape, dtype=bool)
    valid[:, count:30] = False
    return SimpleNamespace(
        ids=list(ASSET_IDS),
        dates=dates,
        prices=prices,
        valid=valid,
        decision_index=160,
        snapshot={
            "id": "91800a23-379d-42c1-810e-b231e9d870e7",
            "content_hash": "c" * 64,
        },
        feature_known_at=utcnow() - timedelta(seconds=1),
    )


@pytest.fixture(scope="module")
def complete(tmp_path_factory):
    panel = equity_panel()
    base = tmp_path_factory.mktemp("asset-ensemble")
    ref = train_asset_candidate(base, panel, panel.dates[155])
    manifest = parse_manifest(read_artifact(base, ref))
    return base / Path(ref["file"]).parent, panel, ref, manifest


def test_complete_equity_coverage_exports_150_native_members(complete):
    directory, panel, ref, manifest = complete
    assert manifest.schema_version == 5
    assert manifest.asset_ids == manifest.covered_asset_ids == list(EQUITY_IDS)
    assert manifest.omitted_assets == {}
    assert len(list(directory.glob("*.ubj"))) == 150
    assert manifest.training_cutoff == panel.dates[149]
    assert manifest.fit_epoch == panel.dates[155]
    assert "selection_id" not in manifest.model_dump()
    validate_native_files(directory, manifest, load=True)
    for asset in manifest.asset_ids:
        assert [b.seed for b in manifest.assets[asset].boosters] == list(phase1.SEEDS)
        assert manifest.validation.by_asset[asset].purged_rows == 5
        assert manifest.assets[asset].training_cutoff == manifest.training_cutoff


def test_partial_coverage_is_explicit_and_unrelated_missing_assets_do_not_block(
    tmp_path,
):
    panel = equity_panel(2)
    panel.prices[:, 30:] = np.nan
    panel.valid[:, 30:] = False
    ref = train_asset_candidate(tmp_path, panel, panel.dates[155])
    manifest = parse_manifest(read_artifact(tmp_path, ref))
    assert manifest.asset_ids == list(EQUITY_IDS[:2])
    assert set(manifest.omitted_assets) == set(EQUITY_IDS[2:])
    assert set(manifest.omitted_assets.values()) == {"ASSET_DATA_MISSING"}
    assert len(list(tmp_path.rglob("*.ubj"))) == 10
    validate_coverage(manifest, ["ACB"], panel.dates[155], require_approved=False)
    with pytest.raises(ValueError, match="coverage"):
        validate_coverage(manifest, ["FPT"], panel.dates[155], require_approved=False)
    with pytest.raises(ValueError, match="epoch"):
        validate_coverage(manifest, ["ACB"], panel.dates[145], require_approved=False)


def test_no_complete_asset_and_wrong_fit_epoch_fail_before_publish(tmp_path):
    panel = equity_panel(0)
    with pytest.raises(ValueError):
        train_asset_candidate(tmp_path, panel, panel.dates[155])
    assert not list(tmp_path.rglob("manifest.json"))
    with pytest.raises(ValueError, match="epoch"):
        train_asset_candidate(tmp_path, panel, panel.dates[154])


def test_trainer_runtime_errors_are_not_disguised_as_missing_coverage(
    tmp_path, monkeypatch
):
    import ml_platform.full_train as trainer

    panel = equity_panel(1)

    def broken(*args, **kwargs):
        raise RuntimeError("native trainer broken")

    monkeypatch.setattr(trainer.xgb, "train", broken)
    with pytest.raises(RuntimeError, match="native trainer broken"):
        train_asset_candidate(tmp_path, panel, panel.dates[155])
    assert not list(tmp_path.rglob("manifest.json"))


def test_asset_model_matches_native_predictions_at_best_iteration(complete):
    import json
    from quant_service.ml import phase1_predictions
    from test_phase1_full_training import native_member_predictions

    directory, panel, _, manifest = complete
    frozen = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/phase1_full_model_reference.json"
        ).read_text()
    )
    ids = frozen["modelled"]
    rows = np.array(
        [phase1.feature_row(panel.prices[:160, ASSET_IDS.index(a)] / 1000) for a in ids]
    )
    predictions = phase1_predictions(directory, manifest, rows, asset_ids=ids)
    for i, asset in enumerate(ids):
        np.testing.assert_array_equal(
            predictions[i],
            native_member_predictions(directory, manifest.assets[asset], rows[i]),
        )


def test_inference_uses_only_active_equities_and_requires_ml_view_before_defensive(
    complete,
):
    directory, panel, _, manifest = complete
    active = ["ACB", "BID", "GOLD", "VFF"]
    features = {
        a: phase1.feature_row(panel.prices[:160, ASSET_IDS.index(a)] / 1000)
        for a in active
        if a in EQUITY_IDS
    }
    volatility = {a: 0.01 for a in features}
    views = infer_asset_views(
        directory,
        manifest,
        features,
        volatility,
        active,
        {"regime": "stress", "vol_ratio": 1.4},
        require_approved=False,
    )
    assert np.array(views["views_p"]).shape[1] == 4
    assert views["views_p"][-1] == [-1 / 3, -1 / 3, -1 / 3, 1.0]
    with pytest.raises(ModelUnavailable, match="ML view"):
        infer_asset_views(
            directory,
            manifest,
            {},
            {},
            ["GOLD", "VFF"],
            {"regime": "crisis", "vol_ratio": 2.0},
            require_approved=False,
        )


def test_manifest_rejects_missing_member_coverage_overlap_and_asset_epoch_mix(complete):
    from copy import deepcopy
    from quant_service.ml import AssetEnsembleManifest

    manifest = complete[3]
    for change in ("member", "coverage", "epoch"):
        raw = deepcopy(manifest.model_dump(mode="json"))
        first = raw["asset_ids"][0]
        if change == "member":
            raw["assets"][first]["boosters"].pop()
        elif change == "coverage":
            raw["omitted_assets"][first] = "ASSET_DATA_MISSING"
        else:
            raw["assets"][first]["training_cutoff"] = str(
                manifest.training_cutoff - timedelta(days=1)
            )
        with pytest.raises(ValueError):
            AssetEnsembleManifest.model_validate(raw)


def test_below_threshold_ml_predictions_cannot_be_rescued_by_defensive_views(
    complete, monkeypatch
):
    from portfolio_contracts import ModelUnavailable

    directory, panel, _, manifest = complete
    monkeypatch.setattr(phase1, "ensemble_forecast", lambda members: (0.0, 0.7))
    features = {"ACB": phase1.feature_row(panel.prices[:160, 0] / 1000)}
    with pytest.raises(ModelUnavailable, match="ML view"):
        infer_asset_views(
            directory,
            manifest,
            features,
            {"ACB": 0.01},
            ["ACB", "VFF"],
            {"regime": "crisis", "vol_ratio": 2.0},
            require_approved=False,
        )
