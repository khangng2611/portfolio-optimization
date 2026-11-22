from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from portfolio_contracts import canonical_hash, utcnow
from portfolio_core.phase1_full import ASSET_IDS, EQUITY_IDS, schedule, select_equities
from quant_service import phase1
from quant_service.ml import (
    parse_manifest,
    phase1_predictions,
    read_artifact,
    validate_native_files,
)
from quant_service.model_worker import approve_candidate
from ml_platform.full_train import train_full_candidate, training_arrays
from ml_platform.worker import validated_candidate


def panel_fixture(n=161, end_date=None):
    dates = []
    day = phase1.START
    if end_date is not None:
        recent = []
        while len(recent) < n:
            if end_date.weekday() < 5:
                recent.append(end_date)
            end_date -= timedelta(days=1)
        day = recent[-1]
    while len(dates) < n:
        if day.weekday() < 5:
            dates.append(day)
        day += timedelta(days=1)
    prices = 20000 * np.cumprod(
        1 + np.random.default_rng(732).normal(0.0005, 0.012, (n, 32)), axis=0
    )
    timing = schedule(n)

    def selection(t):
        return [EQUITY_IDS[i] for i in select_equities(prices[:t, :30])]

    selected = selection(timing["selection_index"])
    modelled = selection(timing["fit_selection_index"])
    f = timing["fit_index"]
    state = timing | dict(
        selection_id="a" * 64,
        selection_epoch=str(dates[timing["selection_index"]]),
        model_selection_id="b" * 64,
        model_selection_epoch=str(dates[timing["fit_selection_index"]]),
        fit_epoch=str(dates[f]),
        selected_equity_ids=selected,
        model_equity_ids=modelled,
        active_asset_ids=selected + ["GOLD", "VFF"],
        training_cutoff=str(dates[f - 6]),
        training_equity_hash=canonical_hash(
            {
                "dates": list(map(str, dates[: f - 5])),
                "equity_ids": list(EQUITY_IDS),
                "prices_vnd": prices[: f - 5, :30].tolist(),
            }
        ),
    )
    return SimpleNamespace(
        ids=list(ASSET_IDS),
        dates=dates,
        prices=prices,
        snapshot={
            "id": "91800a23-379d-42c1-810e-b231e9d870e7",
            "content_hash": "c" * 64,
        },
        feature_known_at=utcnow() - timedelta(seconds=1),
        selection_state=lambda: state,
    )


@pytest.fixture(scope="module")
def fitted(tmp_path_factory):
    panel = panel_fixture(end_date=utcnow().date() - timedelta(days=1))
    directory = tmp_path_factory.mktemp("full-model")
    ref = train_full_candidate(
        directory, panel, date.fromisoformat(panel.selection_state()["training_cutoff"])
    )
    manifest = parse_manifest(read_artifact(directory, ref))
    native_root = directory / ref["file"].rsplit("/", 1)[0]
    return native_root, panel, ref | {"file": "manifest.json"}, manifest


def test_full_training_uses_independent_fit_selection_and_exclusive_price_endpoint(
    fitted,
):
    directory, panel, ref, manifest = fitted
    state = panel.selection_state()
    assert manifest.schema_version == 4
    assert manifest.asset_ids == state["model_equity_ids"]
    assert manifest.full_asset_ids == list(ASSET_IDS)
    assert manifest.model_selection_id == state["model_selection_id"]
    assert manifest.model_selection_epoch.isoformat() == state["model_selection_epoch"]
    assert manifest.training_cutoff.isoformat() == state["training_cutoff"]
    assert len(list(directory.glob("*.ubj"))) == 25
    for asset, split in manifest.validation.by_asset.items():
        assert split.train_label_end < split.validation_start
        assert split.validation_label_end == manifest.training_cutoff
        assert split.purged_rows == 5
        assert (
            split.train_rows + split.validation_rows + split.purged_rows
            == state["fit_index"] - 5 - 29 - 5
        )
        assert [b.seed for b in manifest.assets[asset].boosters] == [42, 43, 44, 45, 46]
    validate_native_files(directory, manifest, load=True)
    assert validated_candidate(directory, ref) == manifest
    rows = [
        phase1.feature_row(
            panel.prices[: state["decision_index"], ASSET_IDS.index(asset)] / 1000
        )
        for asset in manifest.asset_ids
    ]
    predictions = phase1_predictions(directory, manifest, np.array(rows))
    assert np.array(predictions).shape == (5, 5)
    assert np.isfinite(predictions).all()


def test_full_model_requires_registry_approval_and_hash_checks(fitted):
    directory, panel, ref, manifest = fitted
    with pytest.raises(ValueError, match="registry review"):
        approve_candidate(directory, ref, reviewer="reviewer")
    approved = approve_candidate(
        directory, ref, reviewer="reviewer", registry_review=True
    )
    parsed = parse_manifest(read_artifact(directory, approved))
    assert parsed.status == "APPROVED"
    assert parsed.model_dump(
        exclude={"status", "approved_by", "approved_at"}
    ) == manifest.model_dump(exclude={"status", "approved_by", "approved_at"})
    native = directory / manifest.assets[manifest.asset_ids[0]].boosters[0].file
    old = native.read_bytes()
    try:
        native.write_bytes(old + b"tampered")
        with pytest.raises(ValueError, match="checksum"):
            validate_native_files(directory, manifest, load=True)
    finally:
        native.write_bytes(old)


def test_training_feature_rows_and_labels_are_causal_and_exclude_decision_close():
    panel = panel_fixture(146)
    state = panel.selection_state()
    asset = state["model_equity_ids"][0]
    x, y, indices = training_arrays(panel, asset)
    assert indices[0] == 29
    assert indices[-1] + 5 == state["fit_index"] - 6
    split = int(len(indices) * 0.8)
    assert int(np.sum(indices[:split] + 5 < indices[split])) == 79
    expected = [
        phase1.feature_row(panel.prices[: i + 1, ASSET_IDS.index(asset)] / 1000)
        for i in indices
    ]
    np.testing.assert_allclose(x, expected, atol=1e-11, rtol=1e-10)
    column = panel.prices[:, ASSET_IDS.index(asset)] / 1000
    np.testing.assert_allclose(
        y, (column[indices + 5] - column[indices]) / column[indices], atol=0, rtol=0
    )
    panel.prices[state["fit_index"] - 5 :] *= 100
    xx, yy, _ = training_arrays(panel, asset)
    np.testing.assert_array_equal(x, xx)
    np.testing.assert_array_equal(y, yy)


def test_wrong_cutoff_is_rejected_before_artifact_creation(tmp_path):
    panel = panel_fixture(146)
    with pytest.raises(ValueError, match="cutoff"):
        train_full_candidate(tmp_path, panel, date(2020, 2, 1))
    assert not list(tmp_path.iterdir())


def native_member_predictions(directory, ensemble, row):
    from xgboost import Booster

    scaled = np.array([(row - ensemble.scaler_mean) / ensemble.scaler_scale])
    predictions = []
    for member in ensemble.boosters:
        booster = Booster(params={"nthread": 1}, model_file=directory / member.file)
        assert booster.best_iteration == member.best_iteration
        predictions.append(
            booster.inplace_predict(
                scaled, iteration_range=(0, booster.best_iteration + 1)
            )[0]
        )
    return predictions


def test_native_full_ensemble_matches_actual_frozen_wrapper_fixture(fitted):
    import json
    import platform
    from pathlib import Path

    directory, panel, _, manifest = fitted
    reference = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/phase1_full_model_reference.json"
        ).read_text()
    )
    assert manifest.asset_ids == reference["modelled"]
    rows = np.array(
        [
            phase1.feature_row(panel.prices[:160, ASSET_IDS.index(asset)] / 1000)
            for asset in manifest.asset_ids
        ]
    )
    predictions = phase1_predictions(directory, manifest, rows)
    for i, asset in enumerate(manifest.asset_ids):
        oracle = reference["by_asset"][asset]
        np.testing.assert_allclose(
            rows[i], oracle["feature_values"], atol=1e-11, rtol=1e-10
        )
        np.testing.assert_allclose(
            manifest.assets[asset].scaler_mean,
            oracle["scaler_mean"],
            atol=1e-11,
            rtol=1e-10,
        )
        np.testing.assert_allclose(
            manifest.assets[asset].scaler_scale,
            oracle["scaler_scale"],
            atol=1e-11,
            rtol=1e-10,
        )
        np.testing.assert_array_equal(
            predictions[i],
            native_member_predictions(directory, manifest.assets[asset], rows[i]),
        )
        # The frozen refit used macOS arm64; histogram training differs across builds.
        if (platform.system(), platform.machine()) == ("Darwin", "arm64"):
            assert [
                b.best_iteration for b in manifest.assets[asset].boosters
            ] == oracle["best_iteration"]
            np.testing.assert_array_equal(predictions[i], oracle["member_predictions"])
            np.testing.assert_array_equal(
                phase1.ensemble_forecast(predictions[i]), oracle["forecast"]
            )


def test_full_candidate_reuses_queue_receipt_review_and_resolution(tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from ml_platform.main import create_app
    from ml_platform.models import Base
    from ml_platform.worker import TrainingQueue, process_one, materialize_approvals
    from quant_service.full import MixedPanel
    from test_phase1_full_panel import mixed_fixture
    from test_model_operations import Identities, headers, PATH

    snapshot, observations, now = mixed_fixture(170)
    panel = MixedPanel(
        snapshot, observations, expected_hash=snapshot["content_hash"], now=now
    )
    state = panel.selection_state()
    pins = dict(
        snapshot_id=snapshot["id"],
        snapshot_hash=snapshot["content_hash"],
        training_cutoff=state["training_cutoff"],
    )
    engine = create_engine(
        f"sqlite:///{tmp_path}/ml.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    directory = tmp_path / "models"
    client = TestClient(
        create_app(sessions=sessions, verifier=Identities(), directory=directory)
    )

    class Reader:
        def load(self, identity, digest):
            assert (identity, digest) == (snapshot["id"], snapshot["content_hash"])
            return snapshot, observations

    response = client.post(
        PATH + "/training-jobs", json=pins, headers=headers(key="full-train")
    )
    assert response.status_code == 202, response.text
    job = response.json()
    queue = TrainingQueue(sessions)
    assert process_one(queue, directory, Reader())
    completed = client.get(job["status_url"], headers=headers()).json()
    assert completed["status"] == "SUCCEEDED", completed
    model = client.get(
        PATH + "/models/" + completed["result"]["model_id"], headers=headers()
    ).json()
    assert model["metadata"]["schema_version"] == 4
    assert model["metadata"]["modelled_asset_ids"] == model["metadata"]["asset_ids"]
    review = client.post(
        PATH + "/models/" + model["model_id"] + "/reviews",
        json={"decision": "APPROVED", "reason": "Verified full ensemble pins"},
        headers=headers("reviewer", key="full-review", version=model["version"]),
    )
    assert review.status_code == 200, review.text
    assert materialize_approvals(sessions, directory) == 1
    resolve = client.get(
        "/internal/v1/ml/models/" + model["model_id"] + "/manifest",
        headers=headers("reader"),
    )
    assert resolve.status_code == 200, resolve.text
    assert resolve.json()["model_id"] == model["model_id"]
    assert (directory / job["job_id"] / "candidate-receipt.json").exists()
    assert not process_one(queue, directory, Reader())


def inference_bundle(fitted):
    from quant_service.ml import infer
    from quant_service.full import TZ
    from datetime import datetime, time

    directory, panel, ref, manifest = fitted
    approved_ref = approve_candidate(
        directory, ref, reviewer="full-reviewer", registry_review=True
    )
    state = dict(panel.selection_state())
    t = state["decision_index"]
    as_of = panel.dates[t]
    state |= dict(
        decision_date=str(as_of),
        freshness_max_age_days=7,
        regime={
            "regime": "stress",
            "vol_ratio": 1.4,
            "drawdown": -0.11,
            "equity_momentum": -0.001,
        },
        availability={
            asset: {
                "observation_date": str(as_of),
                "policy_available_at": datetime.combine(
                    as_of, time(18), tzinfo=TZ
                ).isoformat(),
                "available_at": panel.feature_known_at.isoformat(),
                "age_days": (utcnow().date() - as_of).days,
                "max_age_days": 7,
            }
            for asset in ASSET_IDS
        },
    )
    returns = panel.prices[1:] / panel.prices[:-1] - 1
    features = dict(
        manifest=approved_ref,
        feature_schema_version="phase1-full-features-v1",
        feature_names=phase1.FEATURES,
        asset_ids=manifest.asset_ids,
        feature_date=str(panel.dates[t - 1]),
        feature_known_at=panel.feature_known_at.isoformat(),
        rows=[
            phase1.feature_row(panel.prices[:t, ASSET_IDS.index(asset)] / 1000)
            for asset in manifest.asset_ids
        ],
        daily_volatility={
            asset: float(returns[t - 20 : t, ASSET_IDS.index(asset)].std(ddof=1))
            for asset in manifest.asset_ids
        },
        state=state,
    )
    active = state["active_asset_ids"]
    value = dict(
        ml_inference=features,
        numerical=dict(
            asset_ids=list(ASSET_IDS),
            active_asset_ids=active,
            mean_returns=returns[t - 20 : t].mean(axis=0).tolist(),
            covariance=np.cov(returns[t - 20 : t], rowvar=False).tolist(),
            market_weights=[1 / 7 if asset in active else 0 for asset in ASSET_IDS],
        ),
        model_bundle_id=approved_ref["sha256"],
        universe_id="VN_PHASE1_FULL",
        demo=False,
        as_of_date=str(as_of),
        decision_at=utcnow().isoformat(),
        valid_until=(utcnow() + timedelta(minutes=30)).isoformat(),
        provenance=dict(phase1_full=state, data_origin="real", max_data_age_days=7),
    )
    return directory, value, infer


def test_full_inference_positive_maps_intersection_views_to_full_order(fitted):
    from quant_service import phase1
    from portfolio_core.phase1_full import adjust_views

    directory, value, infer = inference_bundle(fitted)
    numerical, provenance = infer(directory, value)
    state = value["ml_inference"]["state"]
    active = state["active_asset_ids"]
    assert len(numerical["views_p"]) >= 1
    assert len(numerical["views_p"][0]) == 32
    assert numerical["views_p"][-1][-1] == 1
    assert numerical["views_p"][-1][-2] == -1 / 6
    assert provenance["model_id"] == fitted[3].model_id
    native = phase1_predictions(
        directory, fitted[3], np.array(value["ml_inference"]["rows"])
    )
    p, q, c = [], [], []
    for asset, members in zip(fitted[3].asset_ids, native):
        if asset not in state["selected_equity_ids"]:
            continue
        mean, confidence = phase1.ensemble_forecast(members)
        if abs(mean) < 0.001:
            continue
        annual = 0.5 * np.tanh(
            mean / (value["ml_inference"]["daily_volatility"][asset] * np.sqrt(5))
        )
        p.append([float(asset == a) for a in active])
        q.append(float(annual / 252))
        c.append(confidence)
    expected = adjust_views(
        {"views_p": p, "views_q": q, "view_confidences": c} if p else None,
        state["regime"],
        active,
    )
    np.testing.assert_allclose(
        numerical["views_q"], expected["views_q"], atol=1e-15, rtol=0
    )
    np.testing.assert_array_equal(
        numerical["view_confidences"], expected["view_confidences"]
    )
    for row in numerical["views_p"]:
        assert all(
            row[i] == 0 for i, asset in enumerate(ASSET_IDS) if asset not in active
        )


@pytest.mark.parametrize(
    "change", ["fit", "selection", "order", "candidate", "manifest_hash", "native_hash"]
)
def test_full_inference_rejects_incompatible_manifest_selection_and_native_bytes(
    fitted, change
):
    from copy import deepcopy
    from portfolio_contracts import ModelUnavailable

    directory, value, infer = inference_bundle(fitted)
    value = deepcopy(value)
    state = value["ml_inference"]["state"]
    native = None
    old = None
    if change == "fit":
        state["fit_epoch"] = str(
            date.fromisoformat(state["fit_epoch"]) - timedelta(days=1)
        )
    elif change == "selection":
        state["model_selection_id"] = "f" * 64
    elif change == "order":
        value["numerical"]["asset_ids"] = list(reversed(ASSET_IDS))
    elif change == "candidate":
        value["ml_inference"]["manifest"] = fitted[2]
        value["model_bundle_id"] = fitted[2]["sha256"]
    elif change == "manifest_hash":
        value["ml_inference"]["manifest"]["sha256"] = "f" * 64
    elif change == "native_hash":
        native = directory / fitted[3].assets[fitted[3].asset_ids[0]].boosters[0].file
        old = native.read_bytes()
        native.write_bytes(old + b"tampered")
    try:
        with pytest.raises((ValueError, ModelUnavailable)):
            infer(directory, value)
    finally:
        if native:
            native.write_bytes(old)


def test_first_fit_retains_small_purged_training_set_and_skips_incomplete_attempt(
    tmp_path,
):
    panel = panel_fixture(146)
    orphan = tmp_path / "phase1-interrupted-attempt"
    orphan.mkdir()
    incomplete = orphan / "ACB-42.ubj"
    incomplete.write_bytes(b"incomplete native write")
    reference = train_full_candidate(
        tmp_path, panel, date.fromisoformat(panel.selection_state()["training_cutoff"])
    )
    manifest = parse_manifest(read_artifact(tmp_path, reference))
    assert all(
        split.train_rows == 79 for split in manifest.validation.by_asset.values()
    )
    assert all(
        split.validation_rows == 22 for split in manifest.validation.by_asset.values()
    )
    assert incomplete.read_bytes() == b"incomplete native write"
    assert reference["file"].split("/")[0] != orphan.name
    validate_native_files(
        tmp_path / reference["file"].rsplit("/", 1)[0], manifest, load=True
    )
