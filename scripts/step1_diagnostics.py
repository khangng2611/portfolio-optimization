"""Produce Step 1 evidence from stored runs; never fit or tune a model."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import pickle
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "trusted_baseline"
OUT = ROOT / "outputs/step1"
PRIMARY = OUT / "runs/corrected-20261004T085654"
os.environ["MPLCONFIGDIR"] = "/private/tmp/portfolio-step1-mpl"
os.environ["XDG_CACHE_HOME"] = "/private/tmp/portfolio-step1-cache"
sys.path.insert(0, str(BASE))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config
from backtest._optimizer import _regularize_covariance


def default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def save_figure(fig, name):
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(OUT / "plots" / (name + "." + suffix), dpi=170)
    plt.close(fig)


def main():
    global OUT,PRIMARY
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",default=PRIMARY.name)
    parser.add_argument("--output-root",default=str(OUT))
    parser.add_argument("--legacy-nav-csv",default=str(OUT/"portfolio_static/historical_replay_daily_returns_nav.csv"))
    parser.add_argument("--legacy-label",default="Paper archived-decision replay")
    args=parser.parse_args()
    PRIMARY=ROOT/"outputs/step1/runs"/args.run_id
    OUT=Path(args.output_root).resolve()
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((PRIMARY/"manifest.json").read_text())
    if manifest["status"]!="succeeded":
        raise RuntimeError("Diagnostics require a completed successful run")
    effective=manifest["config"]
    config.SPLIT_DATE=effective["SPLIT_DATE"]
    if Path(manifest["results"]["destination"]).resolve()!=OUT:
        for p in Path(manifest["results"]["destination"]).glob("*.csv"):
            shutil.copy2(p,OUT/p.name)
        shutil.copy2(Path(manifest["results"]["destination"])/"baseline_verification.json",OUT/"baseline_verification.json")
    bundle = pickle.load((PRIMARY / "result.pkl").open("rb"))
    result, prices = bundle["result"], bundle["prices"]
    (OUT / "plots").mkdir(exist_ok=True)
    # Preserve every BL construction, including early periods with no view.
    samples = {pd.Timestamp(x["date"]): dict(x) for x in bundle["bl_samples"]}
    selection_by_date = {pd.Timestamp(x["selection_date"]): x for x in bundle["selections"]}
    selections = bundle["selections"]
    execution = {pd.Timestamp(x["decision_date"]): x for x in result["execution_ledger"]}
    targets = {pd.Timestamp(x["decision_date"]): x for x in result["rebalance_weights_history"]}
    views = {pd.Timestamp(x["date"]): x for x in result["views_history"]}
    returns = prices.pct_change().dropna()
    sample_dir = OUT / "bl_audit_sample" / "corrected"
    sample_dir.mkdir(parents=True,exist_ok=True)
    for date, view in views.items():
        chosen = next(x for x in reversed(selections) if pd.Timestamp(x["selection_date"]) <= date)
        assets = chosen["selected_assets"] + ["GOLD"] + config.DEFAULT_DEFENSIVE_ASSETS
        if date in samples:
            sample = samples[date]
            sample["posterior_applied"] = True
        else:
            t = prices.index.get_loc(date)
            # Loop uses returns.iloc[t-window:t], ending at decision close.
            history = returns.iloc[t-config.WINDOW:t][assets]
            sigma = _regularize_covariance(history.cov().to_numpy())
            equilibrium = np.ones(len(assets)) / len(assets)
            sample = {"date":date,"assets":assets,"covariance":sigma,
                "market_weights":equilibrium,"tau":config.BL_TAU,"delta":config.BL_DELTA,
                "pi":config.BL_DELTA*sigma@equilibrium,"P":[],"Q":[],"confidence":[],"Omega":[],
                "posterior":None,"posterior_applied":False,
                "expected_return_used":history.mean().to_numpy(),
                "reason":"No available view: preserved legacy sample-mean fallback; not a BL-prior portfolio."}
        sample.update(execution_date=execution[date]["execution_date"],regime=view["regime"],
            target_weights_full_order=result["assets"],target_weights_full=targets[date]["BL"],
            target_weights_active=[targets[date]["BL"][result["assets"].index(a)] for a in assets],
            source_run_id=PRIMARY.name,units="daily simple expected returns; daily squared covariance",
            provenance="Stored actual posterior inputs; no-view fallback covariance independently reconstructed")
        (sample_dir/(date.strftime("%Y-%m-%d")+".json")).write_text(json.dumps(sample,default=default,indent=2))

    # Actual feature-origin diagnostic, including outcomes unavailable at sample end.
    forecasts = json.loads((PRIMARY/"ml_prediction_audit.json").read_text())
    forecast_rows=[]
    for x in forecasts:
        date=pd.Timestamp(x["feature_date"])
        i=prices.index.get_loc(date)
        end=prices.index[i+5] if i+5<len(prices) else None
        actual=float(prices[x["asset"]].iloc[i+5]/prices[x["asset"]].iloc[i]-1) if end is not None else None
        forecast_rows.append({"asset":x["asset"],"feature_date":date,"decision_date":prices.index[i+1],
            "outcome_end":end,"prediction":x["prediction_mean"],"realized_5_session_return":actual,
            "direction_correct":bool(np.sign(actual)==np.sign(x["prediction_mean"])) if actual is not None else None,
            "phase":"OOS" if prices.index[i+1]>=pd.Timestamp(config.SPLIT_DATE) else "IS",
            "training_event_id":x["training_event_id"]})
    forecast_df=pd.DataFrame(forecast_rows)
    forecast_df.to_csv(OUT/"forecast_origin_diagnostics.csv",index=False)
    hr=[]
    for phase, group in forecast_df.groupby("phase"):
        valid=group.dropna(subset=["realized_5_session_return"])
        hr.append({"phase":phase,"n_forecasts":len(group),"n_scored":len(valid),
            "n_correct":int(valid.direction_correct.sum()),"hit_rate":float(valid.direction_correct.mean()),
            "definition":"All raw ensemble predictions, feature-origin aligned; differs from thresholded/damped legacy views"})
    pd.DataFrame(hr).to_csv(OUT/"forecast_origin_summary.csv",index=False)

    # Dates/periods are labeled explicitly; historic replay is not a fresh ML run.
    historic=pd.read_csv(args.legacy_nav_csv,parse_dates=["date"])
    corrected=pd.read_csv(OUT/"trusted_baseline_nav.csv",parse_dates=["date"])
    fig, axes=plt.subplots(1,3,figsize=(14,4),sharex=True)
    for ax,s in zip(axes,["MVO","BL","HYBRID"]):
        if "scenario" in historic:
            old=historic[historic.scenario=="historical_oos_default"].set_index("date")[s+"_NAV"]
        else:
            old=historic[(historic.phase=="OOS")&(historic.strategy==s)].set_index("date").nav
        new=corrected[(corrected.phase=="OOS")&(corrected.strategy==s)].set_index("date").nav
        ax.plot(old.index,old.values,label=args.legacy_label+": "+old.index[-1].strftime("%Y-%m-%d"),color="#ad6a1f",linewidth=1.4)
        ax.plot(new.index,new.values,label="Corrected: "+new.index[-1].strftime("%Y-%m-%d"),color="#225ea8",linewidth=1.4)
        ax.axvline(old.index[-1],color="gray",linestyle=":",linewidth=.8)
        ax.set_title(s)
        ax.set_ylabel("OOS NAV (each run starts at 1)")
        ax.grid(alpha=.2)
        ax.tick_params(axis="x",rotation=30)
        ax.legend(fontsize=7)
    fig.suptitle("Legacy vs corrected: multiple integrity differences; not an isolated component ablation")
    save_figure(fig,"legacy_vs_corrected_nav")

    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,phase in zip(axes,["IS","OOS"]):
        for s in ["EW","MVO","BL","HYBRID"]:
            series=corrected[(corrected.phase==phase)&(corrected.strategy==s)].set_index("date").nav
            ax.plot(series.index,series.values,label=s)
        ax.set_title(phase+": corrected valuation-proxy baseline")
        ax.set_ylabel("NAV")
        ax.grid(alpha=.2)
        ax.legend()
        ax.tick_params(axis="x",rotation=30)
    save_figure(fig,"corrected_nav")
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    for ax,phase in zip(axes,["IS","OOS"]):
        for s in ["EW","MVO","BL","HYBRID"]:
            series=corrected[(corrected.phase==phase)&(corrected.strategy==s)].set_index("date").nav
            ax.plot(series.index,100*(series/series.cummax()-1),label=s)
        ax.set_title(phase+": corrected drawdown")
        ax.set_ylabel("Drawdown (%)")
        ax.grid(alpha=.2)
        ax.legend()
        ax.tick_params(axis="x",rotation=30)
    save_figure(fig,"corrected_drawdown")

    diagnostics=pd.read_csv(OUT/"constraint_diagnostics.csv",parse_dates=["date"])
    fig,axes=plt.subplots(1,3,figsize=(13,3.6))
    for ax,column,title in zip(axes,["budget_error","position_cap_violation","negative_violation"],
                             ["Weight-sum error","Position-cap violation","Negative-weight violation"]):
        by_date=diagnostics.groupby("date")[column].max()
        ax.plot(by_date.index,by_date.values,color="#225ea8",linewidth=1)
        ax.axhline(1e-8,color="#d7301f",linestyle="--",label="Tolerance 1e-8")
        ax.set_ylim(-.5e-9,1.1e-8)
        ax.set_title(title)
        ax.grid(alpha=.2)
        ax.tick_params(axis="x",rotation=30)
        ax.legend(fontsize=8)
    save_figure(fig,"constraint_diagnostics")
    turnover=pd.read_csv(OUT/"turnover_summary.csv",parse_dates=["date"])
    fig,axes=plt.subplots(4,1,figsize=(12,8),sharex=True)
    for ax,s in zip(axes,["EW","MVO","BL","HYBRID"]):
        frame=turnover[(turnover.strategy==s)&(~turnover.initial_allocation)]
        ax.plot(frame.date,frame.portfolio_turnover,linewidth=.8,color="#225ea8")
        ax.set_ylabel(s)
        ax.set_ylim(0,1.05)
        ax.axvline(pd.Timestamp(config.SPLIT_DATE),color="gray",linestyle=":")
        ax.grid(alpha=.2)
    fig.suptitle("Rebalance turnover = 0.5 sum(abs(target - drifted pre-trade)); initial capital excluded")
    save_figure(fig,"turnover_history")

    training=pd.read_csv(OUT/"training_window_audit.csv")
    requested=["2020-08-07","2022-10-10",config.SPLIT_DATE,
               str((pd.Timestamp(effective["TEST_END_DATE"])-pd.Timedelta(days=30)).date())]
    fig,axes=plt.subplots(4,1,figsize=(12,8))
    for ax,when in zip(axes,requested):
        chosen=(pd.to_datetime(training.retrain_date)-pd.Timestamp(when)).abs().idxmin()
        row=training.loc[chosen]
        decision=pd.Timestamp(row.retrain_date)
        ledger=execution[decision]
        origin=prices.index[prices.index.get_loc(decision)-1]
        outcome_end=prices.index[prices.index.get_loc(origin)+5]
        markers=[("Fit label end",pd.Timestamp(row.last_fitting_label_end)),
                 ("Validation starts",pd.Timestamp(row.validation_start)),
                 ("Last train/val outcome",pd.Timestamp(row.last_label_end)),
                 ("Decision",decision),("Execute",pd.Timestamp(ledger["execution_date"])),
                 ("First return ends",pd.Timestamp(ledger["first_return_date"])),
                 ("5-session target ends",outcome_end)]
        ax.hlines(0,0,len(markers)-1,color="gray",linewidth=1)
        for j,(label,date) in enumerate(markers):
            y=.36 if j%2==0 else -.36
            ax.scatter([j],[0],color="#225ea8",zorder=3)
            ax.annotate(label+"\n"+date.strftime("%Y-%m-%d"),(j,0),xytext=(j,y),
                        ha="center",fontsize=8,arrowprops={"arrowstyle":"-","color":"gray"})
        ax.set_title(row.asset+" — prediction origin "+origin.strftime("%Y-%m-%d")+"; actual retraining and execution",fontsize=9)
        ax.set_ylim(-.65,.65)
        ax.set_xlim(-.6,len(markers)-.4)
        ax.set_yticks([])
        ax.set_xticks([])
    fig.suptitle("Walk-forward timing: actual dates; schematic spacing does not represent duration")
    save_figure(fig,"walk_forward_timing")

    # Check snapshots against original source and preserved-copy bytes.
    frozen=ROOT/"legacy_version"
    manifest=json.loads((frozen/"snapshot_manifest.json").read_text())
    issues=[]
    for item in manifest["files"]:
        snapshot=frozen/item["snapshot"]
        if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=item["sha256"]:
            issues.append({"source":item["source"],"issue":"frozen copy changed"})
        original=ROOT/item["source"]
        if original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest()!=item["sha256"]:
            issues.append({"source":item["source"],"issue":"original changed"})
    check={"frozen_files_checked":len(manifest["files"]),"issues":issues}
    (OUT/"snapshot_integrity_verification.json").write_text(json.dumps(check,indent=2))
    assert not issues,issues
    print(json.dumps({"figures":6,"BL_decision_samples":len(views),"forecast_summary":hr,"snapshot_check":check},default=default))


if __name__=="__main__":
    main()
