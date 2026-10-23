"""Read-only independent replay/audit of the primary Step 1 run.

Does not fit models, rerun strategies, or overwrite primary exported evidence.
Writes audit evidence only in this new April review directory.
"""
from pathlib import Path
import hashlib
import itertools
import json
import pickle
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/step1/readiness_20261012/candidate_workspace"
OUT = ROOT / "outputs/step1/readiness_20261012"
RUN = OUT / "runs/availability-observed-contract-20261012T233110"
ART = RUN / "artifacts"
AUDIT = OUT / "independent_review"
AUDIT.mkdir(exist_ok=True)
sys.path.insert(0, str(BASE))
started = time.monotonic()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def independent_features(s):
    """Original eight definitions; EWM starts at first historical observation."""
    out = {f"momentum_{p}": s / s.shift(p) - 1 for p in (5, 10, 20)}
    d = s.diff()
    gains = d.clip(lower=0).fillna(0).rolling(14, min_periods=1).mean()
    losses = (-d.clip(upper=0)).fillna(0).rolling(14, min_periods=1).mean()
    out["rsi_14"] = (100 - 100 / (1 + gains / losses.replace(0, np.nan))).fillna(50)
    out["ma_ratio_10_30"] = s.ewm(span=10, adjust=False).mean() / s.ewm(span=30, adjust=False).mean() - 1
    out["volatility_20"] = s.pct_change(fill_method=None).rolling(20).std()
    macd = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    out["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    out["price_std_20"] = s.rolling(20).std() / s.rolling(20).mean()
    return pd.DataFrame(out).iloc[29:]


bundle = pickle.load((RUN / "result.pkl").open("rb"))
result = bundle["result"]
# Pickle is a locally produced, trusted run artifact; its values are checked
# against portable CSV/JSON exports rather than accepted as independent proof.
prices = bundle["prices"]
csv_prices = pd.read_csv(RUN / "aligned_prices.csv", index_col="date", parse_dates=True)
information = pd.read_csv(OUT / "candidate_information_prices.csv", index_col=0, parse_dates=True).loc[prices.index, prices.columns]
manifest = json.loads((RUN / "manifest.json").read_text())
training = json.loads((RUN / "ml_training_audit.json").read_text())
predictions = json.loads((RUN / "ml_prediction_audit.json").read_text())
nav_csv = pd.read_csv(ART / "trusted_baseline_nav.csv", parse_dates=["date"])
return_csv = pd.read_csv(ART / "trusted_baseline_daily_returns.csv", parse_dates=["date"])
weights_csv = pd.read_csv(ART / "trusted_baseline_weights.csv", parse_dates=["date", "decision_date"])
turnover_csv = pd.read_csv(ART / "trusted_baseline_turnover.csv", parse_dates=["date", "decision_date"])
metric_csv = pd.read_csv(ART / "trusted_baseline_metrics.csv", parse_dates=["start_date", "end_date"])
ledger = pd.read_csv(ART / "execution_ledger.csv", parse_dates=["decision_date", "execution_date", "first_return_date", "latest_feature_date", "latest_correlation_date", "latest_covariance_date"])
window_csv = pd.read_csv(ART / "training_window_audit.csv")
report = {"evidence_kind": "actual_run_independent_review", "run_id": manifest["run_id"],
          "method": "Independent fixed-share cash/holdings replay, independent feature/statistic recomputation, all actual audit rows checked. No strategy rerun or fitting.",
          "counts": {"price_rows": len(prices), "assets": prices.shape[1], "training_events": len(training),
                     "predictions": len(predictions), "executions": len(ledger), "selection_events": len(bundle["selections"]),
                     "bl_posteriors": len(bundle["bl_samples"])},
          "checks": {}, "limitations": [], "failures": []}


def check(name, passed, details=None):
    report["checks"][name] = {"pass": bool(passed), "details": details}
    if not passed:
        report["failures"].append(name)


def loc(date):
    return int(prices.index.get_loc(pd.Timestamp(date)))


def maxerr(a, b):
    return float(np.max(np.abs(np.asarray(a) - np.asarray(b))))


check("portable_price_export", csv_prices.index.equals(prices.index) and list(csv_prices.columns) == list(prices.columns)
      and np.allclose(csv_prices, prices, atol=1e-12, rtol=1e-15), maxerr(csv_prices, prices))
price_hash = hashlib.sha256(pd.util.hash_pandas_object(prices, index=True).values.tobytes()).hexdigest()
check("aligned_price_hash", price_hash == manifest["aligned_inputs"]["price_matrix_sha256"], price_hash)
source_changes = [x["path"] for x in manifest["source"]["files"] if digest(BASE / x["path"]) != x["sha256"]]
input_changes = [x["path"] for x in manifest["inputs"] if digest(x["path"]) != x["sha256"]]
artifact_changes = [x["path"] for x in manifest["results"]["artifacts"] if digest(x["path"]) != x["sha256"]]
check("manifest_input_hashes", not input_changes, input_changes)
check("manifest_artifact_hashes", not artifact_changes, artifact_changes)
scientific_source_changes = [p for p in source_changes if p != "STATUS.json" and not p.startswith("tests/")]
check("manifest_current_scientific_source_hashes", not scientific_source_changes, scientific_source_changes)
report["observed_postrun_metadata_changes"] = [p for p in source_changes if p == "STATUS.json"]
report["runner_sha256"] = digest(RUN / "runner_source.py")
check("captured_runner_digest", report["runner_sha256"] == manifest["source"]["runner_sha256"])
snapshot_changes = [x["path"] for x in manifest["source"]["files"] if digest(RUN / "source_snapshot" / x["path"]) != x["sha256"]]
check("captured_source_snapshot_hashes", not snapshot_changes, snapshot_changes)
# Verify every actual fitting schedule from the raw price cutoff, rather than
# merely accepting the runner's PASS assertion.
features = {a: independent_features(prices[a]) for a in prices.columns[:30]}
training_by_id = {x["training_event_id"]: x for x in training}
training_errors, scaler_mean_error, scaler_var_error, scaler_scale_error = [], 0.0, 0.0, 0.0
for x in training:
    e, h, fw = loc(x["input_price_end"]), x["prediction_horizon"], x["feature_window"]
    t, n = e + h + 1, x["n_price_rows"]
    valid = n - (fw - 1) - h
    split = int(valid * 0.8)
    fitting = split - h
    assertions = [x["status"] == "trained", n == e + 1, valid == x["n_valid_before_split"],
                  split == x["n_train_before_purge"], fitting == x["n_train"], x["purged_rows"] == h,
                  valid - split == x["n_validation"], loc(x["train_feature_start"]) == fw - 1,
                  loc(x["train_feature_end"]) == fw - 2 + fitting,
                  loc(x["last_fitting_label_end"]) == loc(x["train_feature_end"]) + h,
                  loc(x["validation_start"]) == fw - 1 + split,
                  loc(x["validation_end"]) == n - h - 1,
                  loc(x["validation_last_label_end"]) == e,
                  loc(x["last_label_start"]) == n - h - 1, loc(x["last_label_end"]) == e,
                  loc(x["last_fitting_label_end"]) < loc(x["validation_start"]), e < t - 1,
                  x["scaler_n_samples_seen"] == fitting, len(x["feature_cols"]) == 8,
                  [m["seed"] for m in x["members"]] == list(range(42, 47))]
    for i, m in enumerate(x["members"]):
        p = m["parameters"]
        assertions.extend([p["random_state"] == 42 + i, p["n_estimators"] == 200,
                           p["max_depth"] == 4, p["learning_rate"] == .05, p["subsample"] == .8,
                           abs(p["colsample_bytree"] - (.7 + .05 * i)) < 1e-15,
                           0 <= m["best_iteration"] < m["boosted_rounds"] <= 200])
    c = window_csv.loc[window_csv.training_event_id == x["training_event_id"]].iloc[0]
    assertions.extend([c.evidence_kind == "actual_fit", bool(c.fit_performed), c.pass_fail == "PASS",
                       loc(c.retrain_date) == t, loc(c.prediction_date) == t, loc(c.execution_date) == t + 1])
    if not all(assertions):
        training_errors.append(x["training_event_id"])
    fit = features[x["asset"]].loc[pd.Timestamp(x["train_feature_start"]):pd.Timestamp(x["train_feature_end"]), x["feature_cols"]]
    mean, variance = fit.to_numpy().mean(axis=0), fit.to_numpy().var(axis=0)
    scale = np.sqrt(variance)
    scale[scale == 0] = 1
    scaler_mean_error = max(scaler_mean_error, maxerr(mean, x["scaler_mean"]))
    scaler_var_error = max(scaler_var_error, maxerr(variance, x["scaler_variance"]))
    scaler_scale_error = max(scaler_scale_error, maxerr(scale, x["scaler_scale"]))
check("all_actual_training_schedules_and_seeds", not training_errors, training_errors)
check("all_actual_scalers_fitted_on_purged_rows", max(scaler_mean_error, scaler_var_error, scaler_scale_error) < 1e-10,
      {"max_mean_error": scaler_mean_error, "max_variance_error": scaler_var_error, "max_scale_error": scaler_scale_error})

prediction_errors, feature_error, mean_error, std_error, confidence_error = [], 0.0, 0.0, 0.0, 0.0
for j, x in enumerate(predictions):
    train = training_by_id[x["training_event_id"]]
    i = loc(x["feature_date"])
    member = np.asarray(x["member_predictions"], dtype=np.float32)
    expected = features[x["asset"]].loc[pd.Timestamp(x["feature_date"]), x["feature_cols"]]
    feature_error = max(feature_error, maxerr(expected, x["feature_values"]))
    mean_error = max(mean_error, abs(float(member.mean()) - x["prediction_mean"]))
    std_error = max(std_error, abs(float(member.std()) - x["prediction_std"]))
    confidence_error = max(confidence_error, abs(float(np.clip(.7 - member.std()/.005, .25, .7)) - x["confidence"]))
    if not (train["asset"] == x["asset"] and loc(x["label_start"]) == i and loc(train["input_price_end"]) <= i
            and prices.index[i+1] in set(ledger.decision_date) and x["prediction_horizon"] == 5
            and [m["seed"] for m in x["members"]] == list(range(42, 47))
            and np.isfinite(member).all() and np.isfinite(x["feature_values"]).all()):
        prediction_errors.append(j)
check("all_actual_prediction_cutoffs_and_links", not prediction_errors, prediction_errors)
check("all_actual_prediction_features_full_history", feature_error < 1e-10, feature_error)
check("ensemble_mean_std_confidence_arithmetic", max(mean_error, std_error, confidence_error) < 1e-12,
      {"max_mean_error": mean_error, "max_std_error": std_error, "max_confidence_error": confidence_error,
       "precision": "Original XGBoost member predictions are float32; aggregation preserves that dtype."})

timing_errors = []
for i, x in ledger.iterrows():
    d, e = loc(x.decision_date), loc(x.execution_date)
    r = loc(x.first_return_date) if pd.notna(x.first_return_date) else d+2
    if not (e == d+1 and r == d+2 and loc(x.latest_feature_date) == d-1
            and loc(x.latest_covariance_date) == d and loc(x.latest_correlation_date) <= d-1):
        timing_errors.append(i)
check("all_execution_index_relations", not timing_errors, timing_errors)

# Completely independent portfolio replay uses wealth = cash + shares * price;
# targets only change shares at their exported execution date. No target is
# allowed to earn a price movement ending on its execution date.
strategies = ["EW", "MVO", "BL", "HYBRID"]
assets = list(prices.columns)
first = 20
oos = int((prices.index >= pd.Timestamp("2023-10-01")).argmax())
reset = oos - 1
share_replay = {}
nav_error, return_error, daily_weight_error, turnover_error, target_export_error = 0., 0., 0., 0., 0.
for s in strategies:
    target = weights_csv.loc[weights_csv.strategy == s].pivot(index="date", columns="asset", values="target_weight").reindex(columns=assets)
    observed_turnover = turnover_csv.loc[turnover_csv.strategy == s].set_index(["date", "asset"])
    shares, cash, wealth = np.zeros(len(assets)), 1., 1.
    wealth_path, pre_return_weights = {prices.index[first]: 1.}, {}
    for i in range(first+1, len(prices)):
        date = prices.index[i]
        pre_return_weights[date] = shares * prices.iloc[i-1].to_numpy() / wealth
        values = shares * prices.iloc[i].to_numpy()
        wealth = float(cash + values.sum())
        wealth_path[date] = wealth
        if date in target.index:
            pre, pre_cash = values / wealth, cash / wealth
            w = target.loc[date].to_numpy()
            rows = observed_turnover.loc[date].reindex(assets)
            expected_turnover = float(np.abs(w-pre).sum()/2)
            turnover_error = max(turnover_error, maxerr(pre, rows.pre_trade_weight),
                                 maxerr(w-pre, rows.weight_change), maxerr(w, rows.target_weight),
                                 maxerr(expected_turnover, rows.portfolio_turnover),
                                 maxerr(expected_turnover+.5*pre_cash, rows.cash_inclusive_turnover),
                                 maxerr(pre_cash, rows.pre_trade_cash_weight))
            if not (rows.initial_allocation == (pre_cash > .999999)).all():
                report["failures"].append("initial_allocation_flag_"+s+"_"+str(date))
            shares, cash = w * wealth / prices.iloc[i].to_numpy(), 0.
    path = pd.Series(wealth_path)
    share_replay[s] = path
    daily_actual = result[s.lower()+"_weights_hist"]
    daily_expected = np.array([pre_return_weights[d] for d in prices.index[oos:]])
    daily_weight_error = max(daily_weight_error, maxerr(daily_actual, daily_expected))
    for phase in ("IS", "OOS"):
        observed = nav_csv.loc[(nav_csv.strategy == s) & (nav_csv.phase == phase)].set_index("date").nav
        expected = path.iloc[:reset-first+1] if phase == "IS" else path.loc[prices.index[reset]:]/path.loc[prices.index[reset]]
        check("nav_dates_"+phase+"_"+s, observed.index.equals(expected.index), {"rows": len(observed)})
        nav_error = max(nav_error, maxerr(observed, expected))
        returns_expected = expected.pct_change(fill_method=None).iloc[1:]
        returns_observed = return_csv.loc[(return_csv.strategy == s) & (return_csv.phase == phase)].set_index("date")["return"]
        check("return_dates_"+phase+"_"+s, returns_observed.index.equals(returns_expected.index))
        return_error = max(return_error, maxerr(returns_expected, returns_observed))
    for r in result["rebalance_weights_history"]:
        target_export_error = max(target_export_error, maxerr(target.loc[r["date"]], r[s]))
check("all_nav_fixed_share_replay", nav_error < 1e-10, {"max_absolute_error": nav_error, "IS_returns": reset-first, "OOS_returns": len(prices)-1-reset})
check("all_daily_returns_fixed_share_replay", return_error < 1e-12, return_error)
check("all_OOS_daily_pre_return_weights_replay", daily_weight_error < 1e-10, daily_weight_error)
check("all_turnover_pretrade_and_targets_replay", turnover_error < 1e-10, turnover_error)
check("all_target_weights_csv_pickle_agreement", target_export_error < 1e-14, target_export_error)

metric_errors = {}
rf = 1.06**(1/252)-1
summary_turnover = turnover_csv.drop_duplicates(["date", "strategy"])
for _, row in metric_csv.iterrows():
    nav = share_replay[row.strategy].loc[row.start_date:row.end_date]
    nav = nav/nav.iloc[0]
    r = nav.pct_change(fill_method=None).iloc[1:]
    excess = r-rf
    mdd = float((nav/nav.cummax()-1).min())
    ann_return = float((nav.iloc[-1]/nav.iloc[0])**(252/len(r))-1)
    turnover = summary_turnover.loc[(summary_turnover.strategy == row.strategy) & (summary_turnover.date > row.start_date)
                                   & (summary_turnover.date <= row.end_date) & (~summary_turnover.initial_allocation), "portfolio_turnover"].sum()
    values = {"final_nav": nav.iloc[-1], "ann_return": ann_return, "ann_volatility": r.std(ddof=1)*np.sqrt(252),
              "sharpe": excess.mean()/excess.std(ddof=1)*np.sqrt(252), "max_drawdown": mdd,
              "sortino": excess.mean()/np.sqrt((excess[excess<0]**2).mean())*np.sqrt(252),
              "calmar": ann_return/abs(mdd), "total_turnover": turnover, "annualized_turnover": turnover*252/len(r)}
    metric_errors[row.phase+"_"+row.strategy] = {k: abs(float(row[k])-float(v)) for k,v in values.items()}
check("all_exported_metrics_independent_recalculation", max(v for row in metric_errors.values() for v in row.values()) < 1e-9,
      {"max_absolute_error": max(v for row in metric_errors.values() for v in row.values()), "errors": metric_errors})

constraint_error, cap_error, bl_inactive_error = 0., 0., 0.
for rec in result["rebalance_weights_history"]:
    select = max((x for x in bundle["selections"] if x["selection_date"] <= rec["decision_date"]), key=lambda x:x["selection_date"])
    active = set(select["selected_assets"]+["GOLD", "VFF"])
    for s in strategies:
        w = rec[s]
        constraint_error = max(constraint_error, abs(w.sum()-1), max(0., -w.min()))
        cap_error = max(cap_error, max(0., w.max()-.5))
        if s == "BL":
            vff = w[assets.index("VFF")]
            constraint_error = max(constraint_error, max(0., (1-vff)-.7), max(0., .15-vff))
            bl_inactive_error = max(bl_inactive_error, max(abs(w[i]) for i,a in enumerate(assets) if a not in active))
check("all_targets_constraints_and_BL_active_set", max(constraint_error, cap_error, bl_inactive_error) < 1e-8,
      {"budget_long_only_defensive_error": constraint_error, "position_cap_error": cap_error, "BL_inactive_asset_error": bl_inactive_error,
       "scope": "Constraints apply at target formation; drifting daily holdings are not constrained to target caps."})

# Verify all saved selection matrices, dates, objectives and globally optimal
# selected sets with a separate chunked vector calculation. This does not run
# portfolio strategies or model fitting.
combinations = np.array(list(itertools.combinations(range(30), 5)), dtype=int)
selection_error, matrix_error, optimality_error, selection_failures = 0., 0., 0., []
for j, x in enumerate(bundle["selections"]):
    t = loc(x["selection_date"])
    frame = prices.loc[:,x["universe"]].iloc[:t]
    corr = frame.pct_change(fill_method=None).iloc[1:].corr().fillna(0).to_numpy()
    expected_dist = 1-corr
    np.fill_diagonal(expected_dist, 0)
    expected_dist = np.clip((expected_dist+expected_dist.T)/2, 0, 2)
    saved = np.load(RUN / x["distance_file"])
    dist = saved["distance"]
    matrix_error = max(matrix_error, maxerr(expected_dist, dist))
    indices = [x["universe"].index(a) for a in x["selected_assets"]]
    cost = float(dist[:, indices].min(axis=1).sum())
    selection_error = max(selection_error, abs(cost-x["coverage_objective"]))
    best_cost, best = float("inf"), None
    for k in range(0, len(combinations), 2000):
        chunk = combinations[k:k+2000]
        scores = dist[:, chunk].min(axis=2).sum(axis=0)
        i = int(scores.argmin())
        if scores[i] < best_cost:
            best_cost, best = float(scores[i]), chunk[i].tolist()
    optimality_error = max(optimality_error, abs(cost-best_cost))
    if not (loc(x["lookback_start"]) == 0 and loc(x["lookback_end"]) == t-1
            and list(saved["ordered_assets"]) == x["universe"] and list(saved["selected_assets"]) == x["selected_assets"]
            and best == indices and len(indices) == 5):
        selection_failures.append(j)
check("all_actual_selection_dates_matrices_and_global_optima", not selection_failures and max(selection_error, matrix_error, optimality_error) < 1e-10,
      {"failures": selection_failures, "max_distance_error": matrix_error, "max_saved_objective_error": selection_error,
       "max_global_optimality_error": optimality_error, "combinations_per_event": len(combinations)})

cov_error, posterior_error, bl_date_error = 0., 0., []
from backtest._optimizer import _regularize_covariance
raw_returns = information.pct_change(fill_method=None).iloc[1:]
for x in bundle["bl_samples"]:
    t = loc(x["date"])
    sigma = _regularize_covariance(raw_returns.iloc[t-20:t].loc[:,x["assets"]].cov().to_numpy())
    cov_error = max(cov_error, maxerr(sigma, x["covariance"]))
    p, q, c = np.asarray(x["P"]), np.asarray(x["Q"]), np.asarray(x["confidence"])
    tau, delta = x["tau"], x["delta"]
    prior = delta*sigma@np.asarray(x["market_weights"])
    omega = np.diag(np.clip(np.diag(p@(tau*sigma)@p.T),1e-10,None)/np.clip(c,1e-6,1))
    mu = prior+tau*sigma@p.T@np.linalg.solve(p@(tau*sigma)@p.T+omega,q-p@prior)
    posterior_error = max(posterior_error, maxerr(prior, x["pi"]), maxerr(omega,x["Omega"]), maxerr(mu,x["posterior"]))
    if x["date"] not in set(ledger.decision_date):
        bl_date_error.append(str(x["date"]))
check("all_actual_BL_covariance_cutoffs_and_posterior_arithmetic", not bl_date_error and max(cov_error, posterior_error) < 1e-10,
      {"max_covariance_error": cov_error, "max_prior_omega_posterior_error": posterior_error, "date_errors": bl_date_error})

availability = pd.read_csv(OUT / "availability_ledger.csv")
for col in ["observed_at", "available_at", "decision_at"]:
    availability[col] = pd.to_datetime(availability[col], utc=True)
check("declared_availability_all_rows", len(availability) == len(prices)*prices.shape[1] and
      (availability.observed_at <= availability.available_at).all() and
      (availability.available_at <= availability.decision_at).all(), {"rows":len(availability)})
check("distinct_information_and_valuation_panels", not np.array_equal(information[["VFF","GOLD"]], prices[["VFF","GOLD"]]))
check("equity_information_equals_valuation", np.allclose(information.iloc[:,:30], prices.iloc[:,:30], atol=1e-12))
report["limitations"] = [
    "Five-session VFF availability and next-day GOLD eligibility are declared simulation assumptions, not proof of historical first publication.",
    "KBS retrospective provider-adjusted close defines price-return, not independently certified total return or point-in-time adjustment vintages.",
    "Fund NAV and GOLD sell marks are valuation proxies, not demonstrated executable trades.",
    "Parameter pre-OOS freeze unknown/possible post-hoc. Static VN30 and costs deferred to later guide steps.",
    "ML JSON retains XGBoost missing=NaN; Python accepts it but strict JSON readers do not. Optional Sortino retains legacy conditional downside RMS."
]
report["scope"] = "declared_valuation_proxy_protocol"
report["historical_publication_verified"] = False
report["actual_fund_execution_certified"] = False
report["strict_guide_recommendation"] = "NOT CERTIFIED: HISTORICAL POINT-IN-TIME OR LIVE EXECUTION"
report["determinism"] = "Separate fresh run comparison pending; this audit does not fit models."
report["post_snapshot_test_fixture_change"] = source_changes
vff = pd.read_csv(ROOT / "outputs/step1/data_static/canonical_vff.csv")
vff = vff.loc[vff.date <= str(prices.index[-1].date())].copy()
created = pd.to_datetime(vff.provider_record_created_at_utc, utc=True, errors="coerce").dt.tz_convert("Asia/Ho_Chi_Minh")
valuation = pd.to_datetime(vff.date)
vff["created_metadata_local"] = created
vff["created_metadata_calendar_lag_days"] = (created.dt.tz_localize(None).dt.normalize()-valuation).dt.days
vff["metadata_later_than_valuation_date_1500"] = created > valuation.dt.tz_localize("Asia/Ho_Chi_Minh")+pd.Timedelta(hours=15)
vff["same_valuation_date_is_portfolio_decision"] = valuation.isin(ledger.decision_date)
vff["evidence_kind"] = "observed_provider_record_metadata_not_verified_publication"
vff.to_csv(AUDIT / "vff_metadata_timing.csv",index=False)
report["NAV_metadata_observation"] = {
    "valuation_rows_through_end":len(vff), "created_metadata_present":int(created.notna().sum()),
    "created_metadata_missing":int(created.isna().sum()),
    "present_created_metadata_later_than_1500_on_valuation_date":int(vff.metadata_later_than_valuation_date_1500.sum()),
    "created_metadata_next_calendar_day":int((vff.created_metadata_calendar_lag_days == 1).sum()),
    "next_day_metadata_valuation_dates_that_are_decision_dates":vff.loc[(vff.created_metadata_calendar_lag_days==1)&vff.same_valuation_date_is_portfolio_decision,"date"].tolist(),
    "interpretation":"Observed record metadata is later than valuation-date close, but createdAt has not been established as true public publication time. The new simulation cutoff is 18:00 with declared availability assumptions. This evidence illustrates the unverified availability assumption; it does not by itself prove historical leakage."
}
# Grade native outcomes only when the endpoint exists in the April run.
# No July/May prices are used for grading.
maturity=[]
for x in predictions:
    origin=loc(x["feature_date"])
    endpoint=origin+x["prediction_horizon"]
    mature=endpoint < len(prices)
    realized=float(prices[x["asset"]].iloc[endpoint]/prices[x["asset"]].iloc[origin]-1) if mature else None
    maturity.append({"asset":x["asset"],"feature_date":prices.index[origin],"decision_date":prices.index[origin+1],
        "label_start":prices.index[origin],"prediction_horizon":x["prediction_horizon"],
        "label_end":prices.index[endpoint] if mature else None,"matured_within_frozen_April_prices":mature,
        "realized_return":realized,"prediction_mean":x["prediction_mean"],
        "correct_direction":bool(np.sign(realized)==np.sign(x["prediction_mean"])) if mature else None,
        "grading_status":"graded_native_origin" if mature else "unmatured_endpoint_outside_frozen_period"})
maturity_frame=pd.DataFrame(maturity)
maturity_frame.to_csv(AUDIT / "prediction_maturity_audit.csv",index=False)
check("prediction_grading_uses_only_matured_April_endpoints", all(x["realized_return"] is None and x["label_end"] is None for x in maturity if not x["matured_within_frozen_April_prices"]),
      {"total_predictions":len(maturity),"matured":int(maturity_frame.matured_within_frozen_April_prices.sum()),
       "unmatured_skipped":int((~maturity_frame.matured_within_frozen_April_prices).sum()),"last_price_date":str(prices.index[-1].date())})
report["mechanical_verdict"] = "PASS" if not report["failures"] else "FAIL"
report["elapsed_seconds"] = time.monotonic()-started
(AUDIT / "final_run_review.json").write_text(json.dumps(report, indent=2, allow_nan=False))
print(json.dumps({"mechanical_verdict":report["mechanical_verdict"],"failures":report["failures"],
                  "checks":{k:v for k,v in report["checks"].items() if not v["pass"]},
                  "elapsed_seconds":report["elapsed_seconds"]},indent=2))
