"""Rebuild the matched Step 2 arms on an alternative vintage of the same SJC series."""
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from backtest._black_litterman import black_litterman_posterior_mu
from experiments_core.src.core import prior_posterior, simulate
from experiments_core.src.frozen import BASE_RUN, READY, ROOT
from gen_view.ranking.risk_management import detect_market_regime
from gen_view.view_generators import build_views_matrix, generate_ml_views
from phase2_gold_k5.audit import align_quotes, require
from phase2_gold_k5.portfolio import load_optimizer

EXT = ROOT / "extensions_C_v1"
FROZEN = EXT / "inputs"
ARMS = ("B1_BLnoML", "B2_BLML")


def panels(inputs, archive_csv):
    archive = pd.read_csv(archive_csv, parse_dates=["date"], float_precision="round_trip").set_index("date")
    # Accept the normalized frozen archive as an independent replay control.
    archive = archive.rename(columns={"sjc_buy": "archive_bid", "sjc_sell": "archive_ask"})
    archive = archive[["archive_bid", "archive_ask", "provider_carry_flag", "source_file"]].astype(
        {"archive_bid": float, "archive_ask": float})
    require(archive.index.is_unique and archive.index.is_monotonic_increasing
            and not archive.isna().any().any() and archive.provider_carry_flag.dtype == bool
            and np.isfinite(archive[["archive_bid", "archive_ask"]]).all().all()
            and (archive.archive_ask >= archive.archive_bid).all() and (archive.archive_bid > 0).all(),
            "Invalid daily SJC archive")
    eligible, valuation = [pd.read_csv(FROZEN / f"prices_{kind}.csv", index_col="date", parse_dates=True,
                                       float_precision="round_trip") for kind in ("eligible", "valuation")]
    dates = valuation.index
    require(dates.equals(eligible.index) and dates.is_unique and dates.is_monotonic_increasing,
            "Original information and valuation calendars disagree")
    ledger = pd.read_csv(FROZEN / "availability_ledger.csv", parse_dates=["session_date"], float_precision="round_trip")
    mask = ledger.asset.eq("GOLD")
    gold = ledger.loc[mask].set_index("session_date").copy()
    prior_day = dates - pd.Timedelta(days=1)
    require(dates.isin(archive.index).all() and prior_day.isin(archive.index).all(),
            "Missing dated valuation or eligible observation in SJC snapshot")
    require(gold.index.equals(dates)
            and pd.DatetimeIndex(pd.to_datetime(gold.observed_at, utc=True)).tz_convert("Asia/Ho_Chi_Minh")
            .tz_localize(None).normalize().equals(prior_day), "Frozen D+1 calendar mismatch")
    prior_quotes = archive.loc[prior_day]
    gold["price"] = prior_quotes.archive_ask.to_numpy()
    raw = READY / "gold_archive_raw" if archive_csv.resolve() == (READY / "gold_archive_daily.csv").resolve() else archive_csv.parent / "raw"
    if raw.is_relative_to(ROOT):
        raw = raw.relative_to(ROOT)
    gold["source"] = [str(raw / name) for name in prior_quotes.source_file]
    ledger.loc[mask, ["price", "source"]] = gold[["price", "source"]].to_numpy()
    quotes = align_quotes(archive, dates, gold)
    valuation["GOLD"], eligible["GOLD"] = quotes.archive_ask, quotes.known_ask
    for kind, frame in (("eligible", eligible), ("valuation", valuation)):
        frame.to_csv(inputs / f"prices_{kind}.csv")
    ledger.to_csv(inputs / "availability_ledger.csv", index=False)
    quotes.to_csv(inputs.parent / "gold_quotes.csv")
    # The frozen solver experiment read CSVs with pandas' default parser.
    return [pd.read_csv(inputs / f"prices_{kind}.csv", index_col="date", parse_dates=True)
            for kind in ("eligible", "valuation")]


def rebuild_arms(inputs, eligible, valuation):
    cfg = json.loads((BASE_RUN / "run_config.json").read_text())
    solver = load_optimizer()
    native = pd.read_csv(BASE_RUN / "artifacts/ml_prediction_audit.csv", parse_dates=["feature_date", "label_start"],
                         float_precision="round_trip")
    require(not native.duplicated(["feature_date", "asset"]).any()
            and native.feature_date.equals(native.label_start) and native.prediction_horizon.eq(5).all()
            and not native.asset.isin(["VFF", "GOLD"]).any(), "Unexpected B2 native model provenance")
    groups = dict(tuple(native.groupby("feature_date", sort=False)))
    outputs = {arm: {"audits": [], "targets": {}} for arm in ARMS}
    saved_b2 = pd.read_csv(FROZEN / "B2_BLML_posterior_audit.csv", parse_dates=["decision_date"]).set_index("decision_date")
    events = {pd.Timestamp(r["date"]): r for r in json.loads((BASE_RUN / "views_history.json").read_text())}
    calendar = pd.read_csv(inputs.parent / "selected_k5_events.csv", parse_dates=["decision_date", "history_end"])
    returns = eligible.pct_change(fill_method=None).iloc[1:]
    diagnostics = []
    for event in calendar.itertuples():
        date, t = event.decision_date, event.decision_index
        names = [getattr(event, f"ticker_{i}") for i in range(1, 6)] + ["GOLD", "VFF"]
        active = eligible.columns.get_indexer(names)
        origin = eligible.index[t-1]
        hist = returns.iloc[t-cfg["WINDOW"]:t]
        require(hist.index[-1] == date and origin == pd.Timestamp(events[date]["prediction_origin_date"])
                and event.history_end < date and (active >= 0).all() and names == json.loads(saved_b2.at[date, "assets"]),
                f"Decision information mismatch at {date}")
        sigma = hist.cov().to_numpy()[np.ix_(active, active)]
        pi = prior_posterior(sigma, 2.5, .05)

        # Native means and base confidences were produced from each equity's own history.
        group = groups.get(origin)
        predictions = {} if group is None else {r.asset: (r.prediction_mean, r.confidence) for r in group.itertuples()}
        require(set(predictions) <= set(names[:-2]), f"Native prediction outside K5 at {date}")
        views = generate_ml_views(predictions, prediction_horizon=cfg["DEFAULT_PREDICTION_HORIZON"],
                                  min_return_threshold=cfg["ML_MIN_ALLOWED_PREDICTION_RETURN"], returns=hist)
        p, q, confidence, _ = build_views_matrix(views, names)
        regime = detect_market_regime(returns, t)
        ratio = regime["vol_ratio"]
        damp = cfg["VOL_DAMPENER_THRESHOLD"] / ratio if ratio > cfg["VOL_DAMPENER_THRESHOLD"] else 1.
        p, q, confidence = ([], [], []) if p is None else (p.tolist(), q.tolist(), (confidence*damp).tolist())
        require(p == json.loads(saved_b2.at[date, "P"]) and q == json.loads(saved_b2.at[date, "Q"]),
                f"Unexpected change in equity-only P/Q at {date}")
        original = np.asarray(json.loads(saved_b2.at[date, "confidence"]))
        diagnostics.append(dict(decision_date=date, prediction_origin=origin, ml_views=len(p),
                                frozen_regime=events[date]["regime"], **regime, confidence_dampener=damp,
                                max_abs_confidence_change=float(np.max(np.abs(original-confidence), initial=0))))
        for arm, pick, view, conf in ((ARMS[0], [], [], []), (ARMS[1], p, q, confidence)):
            mu = prior_posterior(sigma, 2.5, .05, pick, view, conf)
            posterior_error = 0.
            if pick:
                other = black_litterman_posterior_mu(sigma, np.full(len(names), 1/len(names)), pick, view, conf)
                posterior_error = float(np.max(np.abs(other-mu)))
                require(posterior_error < 1e-10, f"Independent BL posterior mismatch on {date}")
            w = solver.optimize_weight_ranking(mu, sigma, names, risk_aversion=1.5)
            residual = max(abs(w.sum()-1), 0., -w.min(), w.max()-.5, .15-w[-1], w.sum()-w[-1]-.7)
            require(np.isfinite(w).all() and residual <= 1e-8, f"Infeasible {arm} at {date}")
            target = np.zeros(len(eligible.columns))
            target[active] = w
            outputs[arm]["targets"][date] = target
            outputs[arm]["audits"].append(dict(decision_date=date, assets=json.dumps(names), optimizer="BL",
                ml_views=arm==ARMS[1], n_ml_views=len(pick), constraint_max_residual=residual,
                posterior_max_error=posterior_error, risk_aversion=1.5, information_end=hist.index[-1],
                selection_information_end=event.history_end, mu=json.dumps(mu.tolist()), pi=json.dumps(pi.tolist()),
                covariance=json.dumps(sigma.tolist()), P=json.dumps(pick), Q=json.dumps(view), confidence=json.dumps(conf)))
    for arm, result in outputs.items():
        pd.DataFrame(result["audits"]).to_csv(inputs / f"{arm}_posterior_audit.csv", index=False)
        sim = simulate(valuation, result["targets"], start_index=cfg["WINDOW"])
        sim["weights"].to_csv(inputs / f"{arm}_weights.csv", index=False)
    pd.DataFrame(diagnostics).to_csv(inputs.parent / "b2_regime_confidence.csv", index=False)


def prepare(out: Path, archive_csv: Path):
    inputs = out / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    for name in ("selected_k5_events.csv", "rebalance_calendar.csv"):
        shutil.copyfile(EXT / name, out / name)
    shutil.copyfile(FROZEN / "selection_history.csv", inputs / "selection_history.csv")
    eligible, valuation = panels(inputs, archive_csv)
    rebuild_arms(inputs, eligible, valuation)
