"""Post hoc diagnostics for long periods of unchanged SJC bids and asks."""
import json

import numpy as np
import pandas as pd

from experiments_core.src.core import bootstrap_effects, return_stats
from experiments_core.src.frozen import READY, write_json


def fixed_quote_runs(archive, quotes):
    """A missing calendar date or a change on either side starts a new run."""
    pair = archive[["sjc_buy", "sjc_sell"]].sort_index()
    if pair.index.has_duplicates or not np.isfinite(pair).all().all():
        raise ValueError("Invalid archival pairs")
    changed = pair.ne(pair.shift()).any(axis=1)
    gap = pair.index.to_series().diff().ne(pd.Timedelta(days=1))
    rows = []
    for _, group in pair.groupby((changed | gap).cumsum()):
        start, end = group.index[0], group.index[-1]
        nxt = end + pd.Timedelta(days=1)
        bid, ask = group.iloc[0]
        next_bid, next_ask = pair.loc[nxt] if nxt in pair.index else (np.nan, np.nan)
        sessions = quotes.loc[start:end]
        rows.append(dict(
            start=start, end=end, calendar_days=len(group), market_sessions=len(sessions),
            eligible_market_sessions=int(sessions.ask.notna().sum()), archive_bid=bid, archive_ask=ask,
            repricing_date=nxt if pd.notna(next_bid) else pd.NaT, next_bid=next_bid, next_ask=next_ask,
            next_bid_return=next_bid / bid - 1, next_ask_return=next_ask / ask - 1,
            next_mid_return=(next_bid+next_ask) / (bid+ask) - 1))
    result = pd.DataFrame(rows).sort_values(["calendar_days", "start"], ascending=[False, True])
    if result.calendar_days.sum() != len(pair):
        raise ValueError("Fixed-price runs do not partition the archive")
    return result


def diagnose(out):
    quotes = pd.read_csv(out / "gold_quotes.csv", index_col="date", parse_dates=True)
    archive = pd.read_csv(READY / "gold_archive_daily.csv", index_col="date", parse_dates=True)
    np.testing.assert_array_equal(archive.loc[quotes.index, ["sjc_buy", "sjc_sell"]],
                                  quotes[["archive_bid", "archive_ask"]])
    runs = fixed_quote_runs(archive, quotes)
    runs.to_csv(out / "fixed_quote_runs.csv", index=False)

    daily = pd.read_csv(out / "daily.csv", parse_dates=["date"])
    paired = daily[daily.arm.isin(["B2_direct", "B2"]) & daily.gate & daily.bps.eq(10)]
    paths = paired.pivot(index="date", columns="arm", values="return")
    oos = quotes.loc["2023-10-02":"2026-04-29"]
    paths = paths.loc[oos.index]
    if paths.isna().any().any() or len(paths) != 641:
        raise ValueError("Diagnostic requires all paired OOS returns on their original dates")
    jump = pd.Timestamp("2026-02-24")
    first_flat = pd.Timestamp("2024-12-02")
    masks = {
        "full_historical_oos": np.ones(len(paths), dtype=bool),
        "truncated_before_long_runs": paths.index < first_flat,
        "long_runs_including_repricing": (paths.index >= first_flat) & (paths.index <= jump),
        "after_repricing": paths.index > jump,
        "full_excluding_repricing_day_return_only": paths.index != jump,
    }
    forecasts = pd.read_csv(out / "forecasts.csv", parse_dates=["date", "label_start", "label_end"])
    forecasts = forecasts[forecasts.view.eq("direct") & ~forecasts.crosses_split].dropna(
        subset=["q_daily", "actual", "prediction"])
    metrics = []
    for period, mask in masks.items():
        p = paths.loc[mask]
        direct, b2 = return_stats(p.B2_direct), return_stats(p.B2)
        row = dict(period=period, first_return_date=p.index[0], last_return_date=p.index[-1],
                   sessions=len(p), eligible_execution_sessions=int(oos.loc[p.index, "ask"].notna().sum()),
                   b2_net_sharpe=b2["sharpe"], direct_net_sharpe=direct["sharpe"],
                   paired_delta_sharpe=direct["sharpe"]-b2["sharpe"],
                   b2_cumulative_return=b2["final_nav"]-1, direct_cumulative_return=direct["final_nav"]-1,
                   b2_max_drawdown=b2["max_drawdown"], direct_max_drawdown=direct["max_drawdown"])
        # Deleting a day breaks adjacency. Avoid resampling blocks across the artificial gap.
        if period != "full_excluding_repricing_day_return_only":
            effect = next(x for x in bootstrap_effects(p.B2_direct, p.B2) if x["metric"] == "sharpe")
            row.update(delta_sharpe_ci_low=effect["ci_low"], delta_sharpe_ci_high=effect["ci_high"])
        f = forecasts[forecasts.date.ge(p.index[0]) & forecasts.label_end.le(p.index[-1])]
        if period == "full_excluding_repricing_day_return_only":
            # Attribution here deletes one day's return. The five-return forecast horizon
            # only contains that return if the label starts strictly before its end close.
            f = f[~((f.label_start < jump) & (jump <= f.label_end)) & f.date.ne(jump)]
        row["direct_mature_scored_forecasts"] = len(f)
        if len(f):
            row["direct_rmse"] = float(np.sqrt(np.mean((f.prediction-f.actual)**2)))
            row["zero_rmse"] = float(np.sqrt(np.mean(f.actual**2)))
        metrics.append(row)
    frame = pd.DataFrame(metrics)
    if (frame.iloc[1:4].sessions.sum() != len(paths)
            or frame.iloc[1:4].eligible_execution_sessions.sum() != oos.ask.notna().sum()):
        raise ValueError("Diagnostic windows do not partition OOS")
    frame.to_csv(out / "carry_diagnostic.csv", index=False)
    write_json(out / "carry_diagnostic.json", {
        "status": "exploratory_after_archive_inspection",
        "units": "Archived bid/ask in thousand VND/luong. Returns are decimal fractions.",
        "method": "Runs count identical published pairs on consecutive calendar dates independently of the provider flag. Return slices use the original continuous net holdings paths and frozen predictions.",
        "scope": "The truncated pre-gap slice can include earlier flat runs. Post-gap holdings, calibration and training retain the original history. Deleting the repricing day's return measures attribution only. These are neither refits on a corrected feed nor evidence of certified clean historical data.",
        "intervals": "Pointwise paired 95% moving block bootstrap intervals, 10 sessions and 1,000 replications; shorter subsamples can have few independent blocks. Omitted for the artificially discontinuous day-deleted path.",
        "forecast_scope": "Direct versus zero predictions on matched mature observations whose decision and label end lie inside each period. The day-deleted diagnostic also excludes that decision and labels whose holding-period return spans the deleted day.",
        "longest_two_runs": json.loads(runs.head(2).to_json(orient="records", date_format="iso")),
        "repricing_session": str(jump.date()), "repricing_day_b2_net_return": float(paths.loc[jump, "B2"]),
        "repricing_day_direct_net_return": float(paths.loc[jump, "B2_direct"]),
    })
