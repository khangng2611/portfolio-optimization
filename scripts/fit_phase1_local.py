"""Fit the frozen Phase 1 ensemble once, export native files, and check serving parity."""

import argparse
import csv
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import platform
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pandas as pd
import sklearn
import xgboost as xgb


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "outputs/step1/readiness_20261012"
RUN_ID = "availability-observed-contract-20261012T233110"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def inputs(kbs_dir, output, phase1):
    from market_service.refresh_provider import normalize

    run = BASELINE / "runs" / RUN_ID
    manifest = json.loads((run / "manifest.json").read_bytes())
    attachments = json.loads((run / "post_run_input_attachments.json").read_bytes())
    note = BASELINE / "Baseline_For_Step2.md"
    if RUN_ID not in note.read_text() or manifest["status"] != "succeeded":
        raise ValueError("Unexpected frozen baseline")
    for name, expected in attachments.items():
        if digest(run / name) != expected:
            raise ValueError(f"Frozen input checksum mismatch: {name}")
    snapshot = run / "source_snapshot"
    sources = {
        r["path"]: r["sha256"]
        for r in manifest["source"]["files"]
        if r["path"].endswith(".py")
    }
    for name, expected in sources.items():
        if digest(snapshot / name) != expected:
            raise ValueError(f"Frozen source checksum mismatch: {name}")
    sys.path.insert(0, str(snapshot))

    with (run / "candidate_information_prices.csv").open() as stream:
        rows = [
            row
            for row in csv.DictReader(stream)
            if row["date"] <= phase1.CUTOFF.isoformat()
        ]
    days = [date.fromisoformat(row["date"]) for row in rows]
    if days != sorted(set(days)) or (days[0], days[-1]) != (
        phase1.START,
        phase1.CUTOFF,
    ):
        raise ValueError("Incomplete frozen training history")
    stocks_vnd = [
        [Decimal(row[asset]) * 1000 for asset in phase1.ASSETS] for row in rows
    ]
    with (run / "availability_ledger.csv").open() as stream:
        ledger = {
            (row["asset"], row["session_date"]): row
            for row in csv.DictReader(stream)
            if row["asset"] in phase1.ASSETS
            and row["session_date"] <= phase1.CUTOFF.isoformat()
        }
    for row in rows:
        for asset in phase1.ASSETS:
            day = row["date"]
            entry = ledger[asset, day]
            if (
                entry["observed_at"][:10] != day
                or datetime.fromisoformat(entry["available_at"])
                > datetime.fromisoformat(entry["decision_at"])
                or Decimal(entry["price"]) != Decimal(row[asset])
            ):
                raise ValueError("Frozen stock is missing same-session eligible prices")

    (output / "kbs").mkdir()
    current = {}
    probe = {}
    for symbol in ["VNINDEX", *phase1.ASSETS]:
        path = kbs_dir / f"{symbol}.json"
        raw = path.read_bytes()
        rows_kbs = normalize(raw, symbol, date(2020, 1, 1), date.today())
        current[symbol] = dict(rows_kbs)
        (output / "kbs" / path.name).write_bytes(raw)
        probe[symbol] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "observations": len(rows_kbs),
            "first": rows_kbs[0][0].isoformat(),
            "last": rows_kbs[-1][0].isoformat(),
        }
    calendar = list(current["VNINDEX"])
    if (
        any(list(current[asset]) != calendar for asset in phase1.ASSETS)
        or [d for d in calendar if phase1.START <= d <= phase1.CUTOFF] != days
        or not 0 <= (date.today() - calendar[-1]).days <= 7
        or calendar[-2] <= phase1.CUTOFF
        or any(
            current[asset][day] != stocks_vnd[i][j]
            for i, day in enumerate(days)
            for j, asset in enumerate(phase1.ASSETS)
        )
    ):
        raise ValueError(
            "KBS coverage, freshness or adjusted price convention differs from Phase 1"
        )
    write_json(
        output / "input-evidence.json",
        {
            "baseline_note_sha256": digest(note),
            "frozen_input_hashes": attachments,
            "kbs": probe,
            "identical_overlap_sessions_per_asset": len(days),
            "price_conversion": "candidate thousand VND/share × 1000 = KBS VND/share",
            "calendar_verified": False,
        },
    )
    fit = pd.DataFrame(
        np.array(stocks_vnd, dtype=float) / 1000,
        index=pd.to_datetime(days),
        columns=phase1.ASSETS,
    )
    calendar = [day for day in calendar if day >= phase1.START]
    live_vnd = np.array(
        [[current[asset][day] for asset in phase1.ASSETS] for day in calendar],
        dtype=float,
    )
    return run, manifest, attachments, sources, fit, stocks_vnd, calendar, live_vnd


def export(output, phase1, run, baseline, attachments, sources, fit, vnd):
    from gen_view.xgboost.xgboost_core import XGBoostEnsembleModel
    from portfolio_contracts import utcnow
    from quant_service.ml import Phase1Manifest

    model = XGBoostEnsembleModel()
    model.train(fit, verbose=False)
    trained_at = utcnow()
    if (
        model.feature_cols != phase1.FEATURES
        or list(model.ensemble_models) != phase1.ASSETS
    ):
        raise ValueError("Frozen trainer produced an unexpected ensemble/schema")
    model_id = str(uuid4())
    root = output / f"phase1-{model_id}"
    root.mkdir()
    assets, splits, errors = {}, {}, []
    for audit in model.training_audit:
        asset = audit["asset"]
        training_end = audit["last_fitting_label_end"].date()
        validation_start = audit["validation_start"].date()
        validation_label_end = audit["validation_last_label_end"].date()
        if (
            audit["status"] != "trained"
            or not training_end < validation_start
            or not validation_label_end
            == audit["last_label_end"].date()
            == phase1.CUTOFF
        ):
            raise ValueError(f"Invalid frozen label boundaries for {asset}")
        validation_dates = fit.loc[
            audit["validation_start"] : audit["validation_end"]
        ].index
        if len(validation_dates) != audit["n_validation"]:
            raise ValueError("Unexpected validation dates in frozen trainer")
        features = model._compute_features(fit[asset]).loc[validation_dates]
        labels = model._compute_labels(fit[asset]).loc[validation_dates].to_numpy()
        scaled = pd.DataFrame(
            model.scalers[asset].transform(features),
            index=features.index,
            columns=features.columns,
        )
        members = []
        predictions = []
        for estimator, details in zip(
            model.ensemble_models[asset], audit["members"], strict=True
        ):
            path = root / f"{asset}-{details['seed']}.ubj"
            estimator.get_booster().save_model(path)
            members.append(
                {
                    "file": path.name,
                    "sha256": digest(path),
                    "seed": details["seed"],
                    "best_iteration": details["best_iteration"],
                    "validation_rmse": details["best_score"],
                }
            )
            predictions.append(estimator.predict(scaled))
        error = np.mean(predictions, axis=0) - labels
        errors.extend(error.tolist())
        splits[asset] = {
            "train_rows": audit["n_train"],
            "validation_rows": audit["n_validation"],
            "purged_rows": audit["purged_rows"],
            "train_label_end": training_end,
            "validation_start": validation_start,
            "validation_end": audit["validation_end"].date(),
            "validation_label_end": validation_label_end,
            "mae": np.abs(error).mean(),
            "rmse": np.sqrt(np.mean(error**2)),
            "r2": 1 - np.sum(error**2) / np.sum((labels - labels.mean()) ** 2),
        }
        assets[asset] = {
            "scaler_mean": audit["scaler_mean"],
            "scaler_scale": audit["scaler_scale"],
            "boosters": members,
        }

    manifest = Phase1Manifest(
        schema_version=3,
        model_id=model_id,
        status="CANDIDATE",
        core_version="0.1.0",
        xgboost_version=xgb.__version__,
        feature_schema_version=phase1.FEATURE_SCHEMA,
        feature_names=model.feature_cols,
        asset_ids=phase1.ASSETS,
        training_cutoff=phase1.CUTOFF,
        training_data_hash=attachments["candidate_information_prices.csv"],
        training_history_hash=phase1.history_hash([d.date() for d in fit.index], vnd),
        baseline_run_id=RUN_ID,
        baseline_manifest_sha256=digest(run / "manifest.json"),
        source_hashes={f"source_snapshot/{name}": sha for name, sha in sources.items()}
        | {"scripts/fit_phase1_local.py": digest(Path(__file__))},
        training_knowledge_cutoff=baseline["finished_at"],
        trained_at=trained_at,
        demo=False,
        horizon_sessions=phase1.HORIZON,
        return_unit="five_session_simple_fraction",
        assets=assets,
        validation={
            "method": "phase1-chronological-80-20-label-purge-v1",
            "point_in_time_certified": False,
            "by_asset": splits,
            "mae": np.abs(errors).mean(),
            "rmse": np.sqrt(np.mean(np.square(errors))),
            "train_rows": sum(s["train_rows"] for s in splits.values()),
            "validation_rows": sum(s["validation_rows"] for s in splits.values()),
            "train_label_end": max(s["train_label_end"] for s in splits.values()),
            "validation_start": min(s["validation_start"] for s in splits.values()),
        },
    )
    write_json(root / "manifest.json", manifest.model_dump(mode="json"))
    return model, manifest, root


def parity(output, phase1, model, manifest, root, calendar, live_vnd):
    from gen_view.view_generators import generate_ml_views, build_views_matrix
    from portfolio_contracts import ModelUnavailable, utcnow
    from quant_service.ml import phase1_predictions

    live = pd.DataFrame(
        live_vnd / 1000, index=pd.to_datetime(calendar), columns=phase1.ASSETS
    )
    reports = []
    for count in [31, 501, len(calendar)]:
        frame = live.iloc[:count]
        reference = model.predict(frame.iloc[:-1])
        actual_returns = frame.pct_change().iloc[1:]
        panel = SimpleNamespace(
            ids=phase1.ASSETS,
            dates=calendar[:count],
            prices=live_vnd[:count],
            known=[[utcnow()]],
            returns=actual_returns.to_numpy(),
            conventions={a: {phase1.PRICE_CONVENTION} for a in phase1.ASSETS},
        )
        if count == len(calendar):
            batch = phase1.feature_batch(panel)
            if (
                batch["training_history_hash"] != manifest.training_history_hash
                or batch["feature_date"] != calendar[-2].isoformat()
            ):
                raise ValueError(
                    "Serving history hash or observed-session lag mismatch"
                )
        else:
            batch = {
                "rows": [
                    phase1.feature_row(column)
                    for column in frame.iloc[:-1].to_numpy().T
                ],
                "daily_volatility": actual_returns.tail(20).std().tolist(),
            }
        audited = model.prediction_audit[-len(phase1.ASSETS) :]
        rows = np.asarray(batch["rows"])
        frozen_rows = [r["feature_values"] for r in audited]
        np.testing.assert_allclose(rows, frozen_rows, rtol=1e-10, atol=1e-11)
        native = phase1_predictions(root, manifest, rows)
        frozen_predictions = [r["member_predictions"] for r in audited]
        np.testing.assert_array_equal(native, frozen_predictions)
        forecast = [phase1.ensemble_forecast(preds) for preds in native]
        np.testing.assert_array_equal(
            forecast, [reference[asset] for asset in phase1.ASSETS]
        )
        p, q, confidence, names = build_views_matrix(
            generate_ml_views(reference, prediction_horizon=5, returns=actual_returns),
            phase1.ASSETS,
        )
        if names:
            views = phase1.option_b(forecast, batch["daily_volatility"])
            np.testing.assert_array_equal(views["views_p"], p)
            np.testing.assert_allclose(views["views_q"], q, rtol=1e-12)
            np.testing.assert_array_equal(views["view_confidences"], confidence)
        else:
            try:
                phase1.option_b(forecast, batch["daily_volatility"])
            except ModelUnavailable:
                views = None
            else:
                raise AssertionError("Serving accepted an empty view set")
        reports.append(
            {
                "decision_session": calendar[count - 1].isoformat(),
                "feature_session": calendar[count - 2].isoformat(),
                "max_feature_absolute_difference": float(
                    np.max(np.abs(rows - frozen_rows))
                ),
                "native_member_predictions": np.asarray(native).tolist(),
                "forecasts": forecast,
                "views": views,
            }
        )
    write_json(output / "parity.json", reports)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kbs-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for component in (
        "services/quant-serving",
        "services/market-data",
        "packages/contracts",
    ):
        sys.path.insert(0, str(ROOT / component / "src"))

    from portfolio_contracts import utcnow
    from quant_service import phase1

    args.output.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": 1,
        "status": "running",
        "started_at": utcnow().isoformat(),
        "cwd": str(Path.cwd()),
        "command": [sys.executable, *sys.argv],
        "baseline_run": RUN_ID,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "xgboost": xgb.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "sklearn": sklearn.__version__,
        },
    }
    record_path = args.output / "run.json"
    write_json(record_path, record)
    try:
        run, baseline, attachments, sources, fit, vnd, calendar, live_vnd = inputs(
            args.kbs_dir, args.output, phase1
        )
        model, manifest, root = export(
            args.output, phase1, run, baseline, attachments, sources, fit, vnd
        )
        record.update(
            model_id=manifest.model_id, manifest_sha256=digest(root / "manifest.json")
        )
        parity(args.output, phase1, model, manifest, root, calendar, live_vnd)
        record.update(status="succeeded", native_boosters=15, parity_cases=3)
        print(root)
        print(json.dumps(manifest.validation.model_dump(mode="json")))
    except Exception as exc:
        record.update(status="failed", error=str(exc))
        raise
    finally:
        record["finished_at"] = utcnow().isoformat()
        write_json(record_path, record)


if __name__ == "__main__":
    main()
