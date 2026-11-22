from datetime import timedelta
import hashlib

import numpy as np
import pytest
import xgboost as xgb

from portfolio_contracts import ModelUnavailable, utcnow
from quant_service.ml import infer, parse_manifest
from quant_service.model_worker import approve_candidate, publish_json
from ml_platform.import_phase1 import import_candidate
from ml_platform.models import Base, Model
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ASSETS = ["FPT", "MWG", "VCB"]
FEATURES = [
    "momentum_5",
    "momentum_10",
    "momentum_20",
    "rsi_14",
    "ma_ratio_10_30",
    "volatility_20",
    "macd_hist",
    "price_std_20",
]
DIGEST = "a" * 64
IDENTITY = "70cf811f-dc16-4184-8a5b-ec5441799157"


@pytest.fixture
def candidate(tmp_path):
    root = tmp_path / f"phase1-{IDENTITY}"
    root.mkdir()
    x = xgb.DMatrix(np.zeros((2, 8)), label=[0.02, 0.02], feature_names=FEATURES)
    model = xgb.train({"nthread": 1, "base_score": 0.02}, x, num_boost_round=2)
    model.set_attr(best_iteration="0")
    native = bytes(model.save_raw(raw_format="ubj"))
    assets = {}
    for asset in ASSETS:
        members = []
        for seed in range(42, 47):
            name = f"{asset}-{seed}.ubj"
            (root / name).write_bytes(native)
            members.append(
                dict(
                    file=name,
                    sha256=hashlib.sha256(native).hexdigest(),
                    seed=seed,
                    best_iteration=0,
                    validation_rmse=0.01,
                )
            )
        assets[asset] = dict(
            scaler_mean=[0] * 8, scaler_scale=[1] * 8, boosters=members
        )
    cutoff = "2026-04-29"
    validation = dict(
        train_rows=1200,
        validation_rows=300,
        purged_rows=5,
        train_label_end="2025-02-01",
        validation_start="2025-02-02",
        validation_end="2026-04-22",
        validation_label_end=cutoff,
        mae=0.01,
        rmse=0.01,
        r2=-0.1,
    )
    ref = publish_json(
        root,
        "manifest.json",
        dict(
            schema_version=3,
            model_id=IDENTITY,
            status="CANDIDATE",
            core_version="0.1.0",
            xgboost_version=xgb.__version__,
            feature_schema_version="phase1-equity-features-v1",
            feature_names=FEATURES,
            asset_ids=ASSETS,
            training_cutoff=cutoff,
            training_data_hash=DIGEST,
            training_history_hash=DIGEST,
            baseline_run_id="availability-observed-contract-20261012T233110",
            baseline_manifest_sha256=DIGEST,
            source_hashes={"config.py": DIGEST},
            training_knowledge_cutoff=(utcnow() - timedelta(days=1)).isoformat(),
            trained_at=utcnow().isoformat(),
            demo=False,
            horizon_sessions=5,
            return_unit="five_session_simple_fraction",
            assets=assets,
            validation=dict(
                method="phase1-chronological-80-20-label-purge-v1",
                point_in_time_certified=False,
                mae=0.01,
                rmse=0.01,
                train_rows=3600,
                validation_rows=900,
                train_label_end="2025-02-01",
                validation_start="2025-02-02",
                by_asset={asset: validation for asset in ASSETS},
            ),
        ),
    )
    return root, ref


def bundle(ref):
    now = utcnow()
    day = now.date() - timedelta(days=1)
    return dict(
        universe_id="VN_EQUITY_PHASE1",
        as_of_date=day.isoformat(),
        demo=False,
        valid_until=(now + timedelta(hours=12)).isoformat(),
        decision_at=now.isoformat(),
        model_bundle_id=ref["sha256"],
        numerical={"asset_ids": ASSETS},
        provenance=dict(max_data_age_days=7),
        ml_inference=dict(
            manifest=ref,
            feature_schema_version="phase1-equity-features-v1",
            feature_names=FEATURES,
            asset_ids=ASSETS,
            rows=[[0] * 8 for _ in ASSETS],
            feature_date=(day - timedelta(days=3)).isoformat(),
            feature_known_at=now.isoformat(),
            history_start="2020-01-14",
            training_history_hash=DIGEST,
            daily_volatility=[0.01] * 3,
        ),
    )


def test_candidate_import_idempotent_and_approval_required(tmp_path, candidate):
    root, ref = candidate
    ref = ref | {"file": f"{root.name}/{ref['file']}"}
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)
    assert import_candidate(sessions, tmp_path, ref) == IDENTITY
    assert import_candidate(sessions, tmp_path, ref) == IDENTITY
    with sessions() as session:
        row = session.get(Model, IDENTITY)
        assert row.status == "CANDIDATE"
        assert row.approved_ref is None
        assert row.training_job_id is None
        assert row.provenance["source"] == "phase1-offline-fit"
    with pytest.raises(ModelUnavailable, match="not approved"):
        infer(tmp_path, bundle(ref))
    with pytest.raises(ValueError, match="registry review"):
        approve_candidate(
            root, {"file": "manifest.json", "sha256": ref["sha256"]}, reviewer="test"
        )
    (root / "FPT-42.ubj").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        import_candidate(sessions, tmp_path, ref)


def test_import_checks_native_paths(tmp_path, candidate):
    root, ref = candidate
    raw = parse_manifest((root / ref["file"]).read_bytes()).model_dump(mode="json")
    raw["assets"]["FPT"]["boosters"][0]["file"] = "../FPT-42.ubj"
    with pytest.raises(ValueError, match="booster filename"):
        import json

        parse_manifest(json.dumps(raw).encode())


@pytest.mark.parametrize(
    ("invalid", "reason"),
    [
        ("hash", "checksum"),
        ("order", "identity"),
        ("expired", "snapshot expired"),
        ("stale_snapshot", "snapshot expired"),
        ("history", "history"),
        ("availability", "unavailable at decision time"),
        ("lag", "observation lag"),
    ],
)
def test_serving_rejects_incompatible_phase1_bundle(
    tmp_path, candidate, invalid, reason
):
    root, ref = candidate
    approved = approve_candidate(root, ref, reviewer="test", registry_review=True)
    value = bundle(approved)
    assert len(infer(root, value)[0]["views_q"]) == 3
    if invalid == "hash":
        (root / "VCB-46.ubj").write_bytes(b"changed")
    elif invalid == "order":
        value["numerical"]["asset_ids"] = ASSETS[::-1]
    elif invalid == "expired":
        value["valid_until"] = value["decision_at"]
    elif invalid == "stale_snapshot":
        value["as_of_date"] = (utcnow().date() - timedelta(days=8)).isoformat()
    elif invalid == "history":
        value["ml_inference"]["training_history_hash"] = "0" * 64
    elif invalid == "availability":
        value["ml_inference"]["feature_known_at"] = (
            utcnow() + timedelta(days=1)
        ).isoformat()
    else:
        value["ml_inference"]["feature_date"] = value["as_of_date"]
    with pytest.raises(ValueError, match=reason):
        infer(root, value)


def test_phase1_requires_views_and_preserves_signed_daily_units():
    from quant_service.phase1 import option_b

    with pytest.raises(ModelUnavailable, match="No valid Phase 1 views"):
        option_b([(0.0009, 0.7), (-0.0009, 0.7), (0, 0.7)], [0.01] * 3)
    views = option_b([(0.01, 0.6), (0, 0.7), (-0.01, 0.5)], [0.02] * 3)
    assert views["views_p"] == [[1, 0, 0], [0, 0, 1]]
    q = 0.5 * np.tanh(0.01 / (0.02 * np.sqrt(5))) / 252
    assert views["views_q"] == pytest.approx([q, -q])
    assert views["view_confidences"] == [0.6, 0.5]
