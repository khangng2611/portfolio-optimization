"""Read-only reconstruction of frozen Phase 1 evidence and two-sided SJC session quotes."""
import argparse
import importlib.util
import json
from pathlib import Path

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd

from experiments_core.src.core import prior_posterior, simulate
from experiments_core.src.frozen import BASE, BASE_RUN, READY, ROOT, sha, write_json


EXT = ROOT / "extensions_C_v1"
INPUTS = EXT / "inputs"
TZ = "Asia/Ho_Chi_Minh"
LEGACY = ROOT / "datasets/gold/gold_full.csv"
OPTIMIZER = BASE / "backtest/_optimizer.py"
ARMS = ("B1_BLnoML", "B2_BLML")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_month(html, filename):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    require("Vàng SJC 1L, 10L, 1KG · Hồ Chí Minh" in text and "triệu đồng / lượng" in text,
            f"Unexpected product or units in {filename}")
    table = soup.select_one("table.gv-table")
    require(table is not None and [h.get_text(strip=True) for h in table.select("thead th")]
            == ["Ngày", "Mua lại", "Bạn trả"], f"Unexpected quote columns in {filename}")
    year, month = map(int, Path(filename).stem.split("_"))
    rows = []
    for tr in table.select("tbody tr"):
        date_cell, bid_cell, ask_cell = tr.find_all("td", recursive=False)
        day = pd.to_datetime(date_cell.get_text(" ", strip=True).split()[0], format="%d/%m/%Y")
        require((day.year, day.month) == (year, month), f"Wrong month in {filename}")
        bid = float(bid_cell.get_text(strip=True).replace(",", ".")) * 1000
        ask = float(ask_cell.select_one(".gv-row__price").get_text(strip=True).replace(",", ".")) * 1000
        require(np.isfinite([bid, ask]).all() and 0 < bid <= ask, f"Invalid quote on {day}")
        rows.append(dict(date=day, archive_bid=bid, archive_ask=ask,
                         provider_carry_flag="không đổi" in ask_cell.get_text(" ", strip=True),
                         source_file=filename))
    require(rows, f"Missing table rows in {filename}")
    return rows


def align_quotes(archive, sessions, ledger):
    """Execution joins on session date; the decision joins on the ledger observation's local date."""
    require(sessions.is_unique and archive.index.is_unique and ledger.index.is_unique
            and sessions.equals(ledger.index), "Inconsistent or duplicate session/observation keys")
    stamp = {col: pd.to_datetime(ledger[col], utc=True).dt.tz_convert(TZ)
             for col in ("observed_at", "available_at", "decision_at")}
    observed = stamp["observed_at"].dt.normalize().dt.tz_localize(None)
    require((stamp["observed_at"] <= stamp["available_at"]).all()
            and (stamp["available_at"] <= stamp["decision_at"]).all()
            and (stamp["decision_at"] == sessions.tz_localize(TZ) + pd.Timedelta(hours=18)).all()
            and (stamp["available_at"] == (observed + pd.Timedelta(days=1)).dt.tz_localize(TZ)).all()
            and (observed < sessions).all(), "GOLD ledger violates D+1 / decision cutoff")
    dated = archive.reindex(sessions).copy()
    known = archive.reindex(pd.DatetimeIndex(observed)).set_axis(sessions)
    require(known.archive_ask.eq(ledger.price).all()
            and known.source_file.eq(ledger.source.map(lambda s: Path(s).name)).all(),
            "Ledger GOLD observation or archive source does not reconcile")
    pair = dated[["archive_bid", "archive_ask"]].notna().all(axis=1)
    executable = pair & dated.provider_carry_flag.eq(False)
    dated["bid"] = dated.archive_bid.where(executable)
    dated["ask"] = dated.archive_ask.where(executable)
    dated["execution_status"] = np.select([~pair, executable], ["archive_row_missing", "dated_two_sided"],
                                          default="flat_or_possible_carry")
    dated["known_bid"], dated["known_ask"] = known.archive_bid, known.archive_ask
    dated["known_provider_carry_flag"] = known.provider_carry_flag
    dated["known_observation_date"] = observed
    dated["known_source_file"] = known.source_file
    for col, times in stamp.items():
        dated[col] = times
    dated.index.name = "date"
    return dated


def reconcile(archive, quotes, valuation, eligible):
    legacy = pd.read_csv(LEGACY, index_col="date", parse_dates=True).sort_index()
    require(legacy.index.is_unique, "Legacy quote dates duplicated")
    # A full calendar exposes the archive's weekends and holidays separately from market sessions.
    days = pd.date_range(valuation.index[0], valuation.index[-1], freq="D", name="date")
    check = archive.reindex(days).join(legacy[["sjc_buy", "sjc_sell"]].add_prefix("legacy_"))
    check["is_market_session"] = days.isin(valuation.index)
    check["phase1_valuation"] = valuation
    check["phase1_eligible"] = eligible
    check = check.join(quotes[["known_observation_date", "known_ask", "known_bid", "execution_status"]])
    check["archive_ask_minus_valuation"] = check.archive_ask - check.phase1_valuation
    check["known_ask_minus_eligible"] = check.known_ask - check.phase1_eligible
    check["legacy_ask_minus_valuation"] = check.legacy_sjc_sell - check.phase1_valuation
    check["valuation_reconciliation"] = np.select(
        [~check.is_market_session, check.archive_ask.isna(), check.archive_ask_minus_valuation.eq(0)],
        ["outside_market_calendar", "archive_row_missing", "same_date_archive_ask"], default="unexplained")
    check["legacy_reconciliation"] = np.select(
        [~check.is_market_session, check.legacy_sjc_sell.isna(), check.legacy_ask_minus_valuation.eq(0),
         check.legacy_ask_minus_valuation.abs().le(50), check.provider_carry_flag.eq(True)],
        ["outside_market_calendar", "legacy_row_missing", "exact", "different_feed_within_rounding",
         "different_feed_archive_flat_or_possible_carry"], default="different_feed_exact_cause_unverified")
    check["legacy_price_unchanged_from_previous_calendar_day"] = legacy.sjc_sell.diff().eq(0).reindex(days)
    return check


def replay_arm(arm, valuation, information_returns, calendar, menus, optimizer, settings):
    phase = pd.read_csv(INPUTS / f"{arm}_posterior_audit.csv", index_col="decision_date", parse_dates=True)
    saved_targets = pd.read_csv(INPUTS / f"{arm}_weights.csv", parse_dates=["decision_date", "execution_date"])
    target_panel = saved_targets.pivot(index="decision_date", columns="asset", values="target_weight")[valuation.columns]
    require(phase.index.equals(calendar.index) and target_panel.index.equals(calendar.index),
            f"{arm} decision dates disagree")
    targets = {}
    errors = {"covariance": 0., "mu": 0., "prior": 0., "target_weight": 0., "constraint_residual": 0.}
    for date, row in phase.iterrows():
        names = menus.loc[date] + ["GOLD", "VFF"]
        require(names == json.loads(row.assets), f"{arm} active assets on {date}")
        t = valuation.index.get_loc(date)
        sigma = information_returns.iloc[t - settings["window"]:t].cov().loc[names, names].to_numpy()
        params = [np.asarray(json.loads(row[c])) for c in ("P", "Q", "confidence")]
        require(len(params[0]) == row.n_ml_views and (arm == "B2_BLML" or not len(params[0])),
                f"{arm} view count on {date}")
        pi = prior_posterior(sigma, settings["delta"], settings["tau"])
        mu = prior_posterior(sigma, settings["delta"], settings["tau"], *params)
        weights = optimizer.optimize_weight_ranking(
            mu, sigma, names, risk_aversion=settings["risk_aversion"], max_weight=settings["max_position"],
            min_defensive_weight=settings["VFF_floor_nominal"], max_equity_exposure=settings["non_VFF_cap"],
            defensive_assets=["VFF"])
        target = pd.Series(0., index=valuation.columns)
        target.loc[names] = weights
        residual = max(abs(target.sum() - 1), -target.min(), target.max() - settings["max_position"],
                       settings["VFF_floor_nominal"] - target.VFF, target.drop("VFF").sum() - settings["non_VFF_cap"])
        require(residual <= settings["constraint_tolerance"], f"{arm} constraint violation on {date}")
        targets[date] = target.to_numpy()
        for key, diff in (("covariance", sigma - json.loads(row.covariance)), ("mu", mu - json.loads(row.mu)),
                          ("prior", pi - json.loads(row.pi)), ("target_weight", target - target_panel.loc[date]),
                          ("constraint_residual", residual - row.constraint_max_residual)):
            errors[key] = max(errors[key], float(np.abs(diff).max()))
    result = simulate(valuation, targets, start_index=settings["window"])
    for name, actual in (("nav", result["nav"].to_frame("nav")), ("daily_weights", result["daily_weights"]),
                         ("daily_returns", result["nav"].pct_change().iloc[1:].to_frame("return"))):
        expected = pd.read_csv(INPUTS / f"{arm}_{name}.csv", index_col="date", parse_dates=True)
        require(expected.index.equals(actual.index) and expected.columns.equals(actual.columns),
                f"{arm} {name} dates or assets disagree")
        errors[name] = float(np.abs(expected.to_numpy() - actual.to_numpy()).max())
    keys = ["decision_date", "execution_date", "asset"]
    stored = saved_targets.set_index(keys).sort_index()
    actual = result["weights"].set_index(keys).sort_index()
    require(stored.index.equals(actual.index), f"{arm} event holding keys disagree")
    for col in ["pre_trade_weight", "weight_change"]:
        errors[col] = float((stored[col] - actual[col]).abs().max())
    trade_dates = ["decision_date", "execution_date", "first_return_date"]
    trades = result["trades"].set_index("decision_date")
    frozen = pd.read_csv(INPUTS / f"{arm}_trades.csv", parse_dates=trade_dates).set_index("decision_date")
    require(trades.index.equals(calendar.index) and trades.index.equals(frozen.index)
            and trades.execution_date.equals(frozen.execution_date)
            and trades.execution_date.equals(calendar.assumed_execution_date)
            and trades.first_return_date.equals(frozen.first_return_date)
            and trades.initial_allocation.equals(frozen.initial_allocation), f"{arm} trading schedule disagrees")
    indices = calendar.decision_index.to_numpy()
    require(np.array_equal(trades.execution_date, valuation.index[indices + 1])
            and np.array_equal(trades.first_return_date, valuation.index[indices + 2]), f"{arm} t+1/t+2 violation")
    for col in ["turnover", "traded_notional"]:
        errors[col] = float((trades[col] - frozen[col]).abs().max())
    require(all(np.isfinite(v) and v <= 1e-9 for v in errors.values()), f"{arm} replay errors {errors}")
    return dict(status="PASS", daily_nav_rows=len(result["nav"]), daily_return_rows=len(result["daily_weights"]),
                events=len(trades), t_plus_one_execution_and_t_plus_two_first_return=True,
                maximum_absolute_differences=errors, terminal_gross_nav=float(result["nav"].iloc[-1]))


def audit(out: Path):
    """Rebuild quotes and both gross controls from frozen sources, returning the audit summary."""
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    valuation = pd.read_csv(INPUTS / "prices_valuation.csv", index_col="date", parse_dates=True)
    sessions = valuation.index
    require(sessions.is_unique and sessions.is_monotonic_increasing, "Invalid valuation calendar")

    def record(path, source, unit="metadata", dates=None, rows=None, expected_hash=None):
        key = str(path.relative_to(ROOT))
        digest = sha(path)
        require(expected_hash is None or digest == expected_hash, f"Frozen hash mismatch: {key}")
        entry = dict(path=key, source=source, unit=unit, sha256=digest, bytes=path.stat().st_size,
                     verified_against_previous_hash=expected_hash is not None)
        if dates is not None:
            unique = pd.DatetimeIndex(pd.to_datetime(dates)).normalize().dropna().unique()
            entry.update(first=unique.min().date().isoformat(), last=unique.max().date().isoformat(),
                         distinct_dates=len(unique), matched_market_sessions=len(unique.intersection(sessions)))
        if rows is not None:
            entry["rows"] = int(rows)
        manifest[key] = entry

    frozen = json.loads((EXT / "baseline_manifest.json").read_text())
    snapshot = {item["snapshot"]: item for item in frozen["files"]}
    require(set(snapshot) == {p.name for p in INPUTS.iterdir() if p.is_file()}, "Unexpected input pack contents")
    for name, item in snapshot.items():
        path = INPUTS / name
        dates, rows, unit = None, None, "configuration, protocol or provenance"
        if path.suffix == ".csv":
            frame = pd.read_csv(path)
            field = next((key for key in ("date", "decision_date", "session_date", "selection_date")
                          if key in frame), None)
            dates = frame[field] if field else None
            rows = len(frame)
            if name.startswith("prices_") or name == "availability_ledger.csv":
                unit = "thousand VND/share, thousand VND/luong GOLD, thousand VND/VFF unit"
            elif "weights" in name or "trades" in name:
                unit = "fraction of portfolio NAV"
            elif "posterior" in name:
                unit = "daily simple returns, daily return covariance, dimensionless P and confidence"
            elif "daily_returns" in name or "_nav." in name:
                unit = "daily simple return or unitless continuous NAV"
            else:
                unit = "portfolio metrics or selection events as named in headers"
            if name == "baseline_metrics.csv":
                dates = pd.concat([frame.start_date, frame.end_date])
        record(path, item["source"], unit, dates, rows, item["sha256"])
    publication = json.loads((EXT / "publication_manifest.json").read_text())
    published = {item["path"]: item["sha256"] for item in publication["files"]}
    record(EXT / "publication_manifest.json", "Phase 1 extension release")
    record(EXT / "baseline_manifest.json", "Phase 1 extension frozen-input register",
           expected_hash=published.get("extensions_C_v1/baseline_manifest.json"))
    phase1 = json.loads((INPUTS / "baseline_run_manifest.json").read_text())
    pinned = {item["path"]: item["sha256"] for item in phase1["files"]}
    for path in [OPTIMIZER, ROOT / "experiments_core/src/core.py", BASE_RUN / "run_config.json"]:
        record(path, "Phase 1 optimizer, accounting or configuration", expected_hash=pinned[str(path.relative_to(ROOT))])
    record(ROOT / "config.py", "Active module supplying the frozen optimizer's imported defaults")
    for name in ["rebalance_calendar.csv", "selected_k5_events.csv"]:
        path = EXT / name
        frame = pd.read_csv(path)
        record(path, "Phase 1 extension release", "session dates and tickers",
               frame.decision_date, len(frame), published[str(path.relative_to(ROOT))])
    for name, field, unit in (("ml_prediction_audit", "feature_date", "raw five-session simple return"),
                              ("ml_training_audit", "retrain_date", "fit and label timing records"),
                              ("selection_history", "selection_date", "K5 constituents and source window")):
        path = BASE_RUN / "artifacts" / f"{name}.csv"
        frame = pd.read_csv(path)
        record(path, f"Step 1 {BASE_RUN.name}", unit, frame[field], len(frame), pinned[str(path.relative_to(ROOT))])
    predictions = pd.read_csv(BASE_RUN / "artifacts/ml_prediction_audit.csv")
    require((predictions.feature_date == predictions.label_start).all() and predictions.prediction_horizon.eq(5).all(),
            "Original equity label contract changed")
    path = BASE_RUN / "ml_prediction_audit.json"
    record(path, "Step 1 ensemble member predictions", "raw five-session simple return",
           predictions.feature_date, len(predictions), pinned[str(path.relative_to(ROOT))])

    archive_manifest_path = READY / "gold_archive_manifest.json"
    archive_manifest = json.loads(archive_manifest_path.read_text())
    record(archive_manifest_path, "GiaVang.TV download receipt with URL, retrieval time and sha256")
    raw = []
    for item in archive_manifest["records"]:
        path = READY / "gold_archive_raw" / item["file"]
        rows = parse_month(path.read_text(), path.name)
        record(path, item["url"], "million VND/luong as published, one decimal place",
               [r["date"] for r in rows], len(rows), item["sha256"])
        raw.extend(rows)
    archive = pd.DataFrame(raw).set_index("date").sort_index()
    daily_path = READY / "gold_archive_daily.csv"
    daily = pd.read_csv(daily_path, index_col="date", parse_dates=True)
    policy = json.loads((INPUTS / "availability_policy.json").read_text())
    archive_hash = next(r["sha256"] for r in policy["source_rows"] if r["asset"] == "GOLD")
    record(daily_path, "Step 1 SJC-HCM archive normalization", "thousand VND/luong",
           daily.index, len(daily), archive_hash)
    normalized = daily.rename(columns={"sjc_buy": "archive_bid", "sjc_sell": "archive_ask"})
    require(archive.equals(normalized.loc[:, archive.columns]), "Two-sided archive or carry flags changed")
    legacy = pd.read_csv(LEGACY, usecols=["date"])
    record(LEGACY, "PNJ Edge TPHCM SJC via crawl/gold.py; calendar-filled series",
           "thousand VND/luong", legacy.date, len(legacy))
    record(ROOT / "crawl/gold.py", "Legacy PNJ normalization and fill policy")

    ledger = pd.read_csv(INPUTS / "availability_ledger.csv", parse_dates=["session_date"])
    available = pd.to_datetime(ledger.available_at, utc=True)
    require((pd.to_datetime(ledger.observed_at, utc=True) <= available).all()
            and (available <= pd.to_datetime(ledger.decision_at, utc=True)).all(), "Ledger cutoff violation")
    eligible = pd.read_csv(INPUTS / "prices_eligible.csv", index_col="date", parse_dates=True)
    require(eligible.index.equals(sessions) and eligible.columns.equals(valuation.columns)
            and ledger.pivot(index="session_date", columns="asset", values="price")[eligible.columns].equals(eligible),
            "Information panel disagrees with ledger")
    gold = ledger[ledger.asset.eq("GOLD")].set_index("session_date").sort_index()
    quotes = align_quotes(archive, sessions, gold)
    reconciliation = reconcile(archive, quotes, valuation.GOLD, eligible.GOLD)
    require(quotes.known_ask.eq(eligible.GOLD).all() and quotes.archive_ask.eq(valuation.GOLD).all(),
            "Unexplained SJC price panel reconciliation")
    quotes.to_csv(out / "gold_quotes.csv", index_label="date")
    reconciliation.to_csv(out / "reconcile.csv", index_label="date")

    calendar = pd.read_csv(EXT / "rebalance_calendar.csv", index_col="decision_date",
                           parse_dates=["decision_date", "assumed_execution_date"])
    selected = pd.read_csv(EXT / "selected_k5_events.csv", index_col="decision_date", parse_dates=True)
    require(selected.index.equals(calendar.index) and selected.selection_state_id.equals(calendar.selection_state_id)
            and np.array_equal(sessions[calendar.decision_index], calendar.index), "K5 calendar mismatch")
    selection = pd.read_csv(INPUTS / "selection_history.csv").query("experiment_id == 'A3_ProposedK5'")
    selection = selection.set_index("selection_date")
    require((selection.history_end < selection.index).all(), "K5 formation uses unavailable data")
    menus = calendar.selection_state_id.map(selection.selected_assets).map(json.loads)
    require(menus.tolist() == selected[[f"ticker_{i}" for i in range(1, 6)]].values.tolist()
            and (calendar.selection_state_id <= calendar.index.strftime("%Y-%m-%d")).all(), "K5 membership mismatch")
    settings = phase1["plan"]["allocation"]
    require(np.array_equal(calendar.decision_index, np.arange(settings["window"], len(sessions)-1, settings["rebalance"]))
            and np.array_equal(pd.to_datetime(selection.index),
                               sessions[settings["window"]::phase1["plan"]["selection"]["cadence"]]),
            "K5 reselection or rebalance cadence changed")
    spec = importlib.util.spec_from_file_location("phase1_frozen_optimizer", OPTIMIZER)
    optimizer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(optimizer)
    require(optimizer.MIN_WEIGHT_THRESHOLD == settings["min_weight"], "Optimizer pruning floor changed")
    info_returns = eligible.pct_change(fill_method=None).iloc[1:]
    arms = {arm: replay_arm(arm, valuation, info_returns, calendar, menus, optimizer, settings) for arm in ARMS}
    since = pd.Timestamp(phase1["plan"]["OOS"]["first_return"])
    receipt = {
        "status": "PASS", "arms": arms,
        "method": "Recomputed 20-return covariance through decision close, equal-weight BL prior and posterior from frozen stock P/Q/confidence, solved frozen optimizer, replayed positions at original single-price valuation.",
        "decision_cutoff": policy["decision_cutoff"], "gold_available": "observation day + 1 calendar day, 00:00 local",
        "quote_unit": "thousand VND per luong", "archive_identity": "SJC 1L, 10L, 1KG, Ho Chi Minh",
        "archive_limitation": "Rounded historical daily close; publication times and executable fills unverified. 'không đổi' is a flat ask/change flag that can represent a provider carry. Treating all flagged rows as unavailable for a new fill is conservative.",
        "legacy_limitation": "PNJ uses a separate TPHCM feed, may select the first intraday entry and fills calendar gaps. Its flattened CSV lacks per-row source timestamps. A repeated price or rounding-compatible difference cannot identify the exact cause.",
        "coverage": {
            "market_start": str(sessions[0].date()), "market_end": str(sessions[-1].date()),
            "market_sessions": len(sessions), "archive_calendar_days": len(archive),
            "missing_archive_days_within_span": len(pd.date_range(archive.index[0], archive.index[-1]).difference(archive.index)),
            "raw_months": len(archive_manifest["records"]), "archive_market_both_sides": int(quotes.archive_ask.notna().sum()),
            "eligible_known_pairs": int(quotes.known_ask.notna().sum()), "same_date_archive_ask_matches": int(quotes.archive_ask.eq(valuation.GOLD).sum()),
            "same_date_legacy_ask_matches": int(reconciliation.legacy_ask_minus_valuation.eq(0).sum()),
            "execution_proxy_sessions": int(quotes.ask.notna().sum()),
            "flat_or_possible_carry_market_sessions": int(quotes.execution_status.eq("flat_or_possible_carry").sum()),
            "flat_ask_flag_but_changed_bid_sessions": int((archive.archive_bid.diff().ne(0) & archive.provider_carry_flag).reindex(sessions).sum()),
            "scheduled_t_plus_one_sessions": len(calendar),
            "scheduled_t_plus_one_unavailable": int(quotes.loc[calendar.assumed_execution_date, "ask"].isna().sum()),
            "historical_oos_sessions": int((sessions >= since).sum()),
            "historical_oos_execution_proxy_sessions": int(quotes.loc[since:, "ask"].notna().sum()),
            "frozen_stock_prediction_rows": len(predictions), "frozen_stock_predictions_start_on_feature_date": True,
            "first_original_stock_prediction": predictions.feature_date.min(), "last_original_stock_prediction": predictions.feature_date.max(),
        },
        "last_previously_evaluated_matched_session": str(sessions[-1].date()),
        "eligibility": "Per-session eligibility is explicit in gold_quotes.csv. Full matched history is retrospective; a future confirmatory cohort must start after protocol registration.",
    }
    write_json(out / "input_manifest.json", {
        "timezone": TZ, "decision_cutoff": policy["decision_cutoff"],
        "market_sessions_denominator": len(sessions), "coverage_basis": "Dates intersected with frozen valuation sessions. Static configurations and aggregated metrics have no session-level observations.",
        "policy": {k: policy[k] for k in ["execution", "gold", "equity_return", "VFF", "assumptions"]},
        "files": [manifest[k] for k in sorted(manifest)],
    })
    write_json(out / "replay.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    audit(parser.parse_args().out)
