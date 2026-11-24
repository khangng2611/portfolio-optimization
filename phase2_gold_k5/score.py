"""Summarize matched daily paths and the pre-registered primary contrast."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments_core.src.core import bootstrap_effects, return_stats

HERE = Path(__file__).resolve().parent
KEY = ["arm", "gate", "bps"]


def score(out):
    protocol = json.loads((HERE / "protocol.json").read_text())
    daily = pd.read_csv(out / "daily.csv", parse_dates=["date"])
    trades = pd.read_csv(out / "trades.csv", parse_dates=["execution_date"])
    assert not daily.duplicated(KEY + ["date"]).any()
    assert np.isfinite(daily[["return", "nav"]]).all().all() and (daily.nav > 0).all()
    daily.sort_values(KEY + ["date"], inplace=True)
    actual = daily.groupby(KEY).nav.pct_change()
    assert np.allclose(daily.loc[actual.notna(), "return"], actual.dropna(), atol=1e-11)
    periods = [("retrospective", "2023-09-30", protocol["historical_end"])]
    periods.extend((f"window_{i}", a, b) for i, (a, b) in enumerate(protocol["subperiods"], 1))
    records, paired = [], []
    for period, start, end in periods:
        frame = daily.loc[daily.date.between(start, end)]
        fills = trades.loc[trades.execution_date.between(start, end)]
        paths = frame.pivot(index="date", columns=KEY, values="return")
        if paths.isna().any().any() or (period == "retrospective" and len(paths) != 641):
            raise ValueError("Unmatched historical return paths")
        for (arm, gate, bps), returns in paths.items():
            deals = fills[(fills.arm == arm) & (fills.gate == gate) & (fills.bps == bps)]
            metrics = return_stats(returns)
            records.append(dict(period=period, arm=arm, gate=gate, bps=bps, sessions=len(returns),
                                **metrics, scheduled_events=len(deals), executed_events=int(deals.status.eq("executed").sum()),
                                annual_turnover=deals.turnover.sum()*252/len(returns),
                                gold_cost_nav_units=deals.gold_cost.sum(), other_cost_nav_units=deals.other_cost.sum(),
                                gold_trade_events=int((deals.gold_weight_change.fillna(0).abs() > 1e-8).sum())))
        effect = bootstrap_effects(paths["B2_direct", True, 10], paths["B2", True, 10])
        paired.extend(dict(period=period, **row) for row in effect)
    pd.DataFrame(records).to_csv(out / "metrics.csv", index=False)
    pd.DataFrame(paired).to_csv(out / "paired.csv", index=False)
    pd.read_csv(out / "trades.csv").groupby(KEY + ["status"]).size().rename("count").to_csv(out / "events.csv")

    forecasts = pd.read_csv(out / "forecasts.csv", parse_dates=["date", "label_end"])
    errors = []
    for period, start, end in periods:
        usable = forecasts.loc[forecasts.date.between(start, end)].dropna(subset=["q_daily","actual"])
        usable = usable[(~usable.crosses_split) & usable.label_end.le(end)]
        for view, group in usable.groupby("view"):
            actual, predicted = group.actual.to_numpy(), group.prediction.to_numpy()
            errors.append(dict(period=period, view=view, n=len(group), rmse=np.sqrt(np.mean((predicted-actual)**2)),
                               zero_rmse=np.sqrt(np.mean(actual**2)), mae=np.mean(np.abs(predicted-actual)),
                               sign_accuracy=np.mean(np.sign(actual) == np.sign(predicted))))
    pd.DataFrame(errors).to_csv(out / "forecast_metrics.csv", index=False)
