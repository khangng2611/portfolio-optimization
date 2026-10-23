"""Analyze the freshly rerun April-period baseline without training or tuning."""
import argparse
import hashlib
import json
from pathlib import Path
import pickle
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/step1/paper_period"
sys.path.insert(0,str(ROOT/"trusted_baseline"))
import numpy as np
import pandas as pd
from backtest._optimizer import blend_weights
from backtest._metrics import metric_summary


def default(x):
    if hasattr(x,"isoformat"):return x.isoformat()
    if hasattr(x,"tolist"):return x.tolist()
    if hasattr(x,"item"):return x.item()
    return str(x)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",required=True)
    args=parser.parse_args()
    run=ROOT/"outputs/step1/runs"/args.run_id
    manifest=json.loads((run/"manifest.json").read_text())
    assert manifest["status"]=="succeeded"
    bundle=pickle.load((run/"result.pkl").open("rb"))
    result,prices=bundle["result"],bundle["prices"]
    cfg=manifest["config"]
    OUT.mkdir(exist_ok=True)
    artifacts=run/"artifacts"
    printed=pd.read_csv(OUT/"pdf_audit/printed_table2.csv")
    printed["strategy"]=printed.strategy.replace({"BL+ML":"BL"})
    actual=pd.read_csv(artifacts/"trusted_baseline_metrics.csv")
    compared=actual.merge(printed,left_on=["phase","strategy"],right_on=["period","strategy"],validate="one_to_one")
    for a,b,name in [("final_nav","nav","nav"),("ann_return","annual_return_fraction","annual_return"),
                     ("ann_volatility","annual_volatility_fraction","annual_volatility"),
                     ("sharpe_x","sharpe_y","sharpe"),("max_drawdown","max_drawdown_fraction","max_drawdown")]:
        compared[name+"_difference"]=compared[a]-compared[b]
    compared["comparison_scope"]="Rounded PDF references versus corrected frozen-current-snapshot fresh run; not identical input data/protocol"
    compared.to_csv(OUT/"paper_vs_corrected_metrics.csv",index=False)

    views={pd.Timestamp(x["date"]):x for x in result["views_history"]}
    target_records=result["rebalance_weights_history"]
    dates=prices.index[int(cfg["WINDOW"]):]
    anchor=pd.Timestamp(result["hybrid_nav"].index[0])
    alpha_rows,alpha_nav_rows=[],[]
    errors=[]
    for coefficient in [.2,.4,.6,.8,1.]:
        targets={}
        for record in target_records:
            regime=views[pd.Timestamp(record["decision_date"])]["regime"]
            alpha=coefficient if regime=="normal" else cfg["HYBRID_REGIME_RATIOS"][regime]
            targets[pd.Timestamp(record["date"])]=blend_weights(record["MVO"],record["BL"],alpha)
        # Separate physical-unit replay: decision outputs do not depend on
        # Hybrid NAV or holdings. Each alpha changes only those blend targets.
        qty=np.zeros(prices.shape[1]);cash=1.;marked=[];turnover=[]
        for when in dates:
            quote=prices.loc[when].to_numpy()
            wealth=float(cash+qty@quote)
            if when in targets:
                pre=qty*quote/wealth
                target=targets[when]
                assert abs(float(target.sum())-1)<1e-8 and float(target.min())>=-1e-8 and float(target.max())<=.5+1e-8
                turnover.append({"date":when,"turnover":.5*float(np.abs(target-pre).sum()),"initial":cash>.999999})
                qty=wealth*target/quote
                cash=0.
            marked.append(wealth)
        full=pd.Series(marked,index=dates)
        partitions={"IS":full.loc[:anchor],"OOS":full.loc[anchor:]/full.loc[anchor]}
        if coefficient==.6:
            for phase,nav in partitions.items():
                recorded=(result["warmup_result"] if phase=="IS" else result)["hybrid_nav"]
                errors.append(float(np.max(np.abs(nav.loc[recorded.index]-recorded))))
        for phase,nav in partitions.items():
            stats=metric_summary(nav)
            total=sum(x["turnover"] for x in turnover if nav.index[0]<x["date"]<=nav.index[-1] and not x["initial"])
            stats.update(phase=phase,alpha_normal=coefficient,alpha_stress=cfg["HYBRID_MVO_RATIO_STRESS"],
                alpha_crisis=cfg["HYBRID_MVO_RATIO_CRISIS"],start_date=nav.index[0],end_date=nav.index[-1],
                n_returns=len(nav)-1,total_turnover=total,annualized_turnover=total*252/(len(nav)-1))
            alpha_rows.append(stats)
            for when,value in nav.items():
                alpha_nav_rows.append({"phase":phase,"alpha_normal":coefficient,"date":when,"nav":value})
    assert max(errors)<1e-8,errors
    alpha=pd.DataFrame(alpha_rows)
    alpha.to_csv(OUT/"corrected_alpha_sensitivity.csv",index=False)
    pd.DataFrame(alpha_nav_rows).to_csv(OUT/"corrected_alpha_nav.csv",index=False)
    alpha_printed=pd.read_csv(OUT/"pdf_audit/printed_table3.csv")
    alpha_compare=alpha[alpha.phase=="OOS"].merge(alpha_printed,on="alpha_normal",validate="one_to_one")
    alpha_compare["nav_difference"]=alpha_compare.final_nav-alpha_compare.nav
    alpha_compare["sharpe_difference"]=alpha_compare.sharpe_x-alpha_compare.sharpe_y
    alpha_compare["mdd_difference"]=alpha_compare.max_drawdown-alpha_compare.max_drawdown_fraction
    alpha_compare.to_csv(OUT/"paper_vs_corrected_alpha.csv",index=False)
    (OUT/"alpha_grid_method.json").write_text(json.dumps({"run_id":args.run_id,
        "method":"Physical-share resimulation of the paper's five alpha_normal settings using actual fresh-run independent MVO/BL legs and observed price-only regimes; no additional ML fitting or tuning",
        "alpha_stress":.3,"alpha_crisis":.1,"no_feedback_from_hybrid_holdings_to_leg_or_regime":True,
        "default_alpha_replay_max_nav_error":max(errors),"validation_tolerance":1e-8,
        "definition_alpha_1":"normal-only alpha=1; stress/crisis remain0.3/0.1, so this is not an all-regime pure-MVO allocation"},indent=2))

    # Both view-level and raw ensemble hit rates, always origin aligned and
    # scored solely inside the April run. Missing future outcomes are explicit.
    forecasts=json.loads((run/"ml_prediction_audit.json").read_text())
    scored=[]
    for item in forecasts:
        start=pd.Timestamp(item["feature_date"]);i=prices.index.get_loc(start)
        decision=prices.index[i+1];end=prices.index[i+5] if i+5<len(prices) else None
        actual_return=float(prices[item["asset"]].iloc[i+5]/prices[item["asset"]].iloc[i]-1) if end is not None else None
        scored.append({"kind":"all_raw_predictions","asset":item["asset"],"decision_date":decision,"origin_date":start,
            "outcome_end":end,"prediction":item["prediction_mean"],"realized_return":actual_return,
            "correct":bool(np.sign(item["prediction_mean"])==np.sign(actual_return)) if end is not None else None,
            "phase":"OOS" if decision>=pd.Timestamp(cfg["SPLIT_DATE"]) else "IS"})
    for decision,item in views.items():
        start=pd.Timestamp(item["prediction_origin_date"]);i=prices.index.get_loc(start)
        end=prices.index[i+5] if i+5<len(prices) else None
        for name,q in zip(item["view_names"],item["q_values"]):
            if "defensive" in name or q==0:continue
            asset=name.split("_")[0]
            assert asset in prices
            realized=float(prices[asset].iloc[i+5]/prices[asset].iloc[i]-1) if end is not None else None
            scored.append({"kind":"emitted_ML_views","asset":asset,"decision_date":decision,"origin_date":start,
                "outcome_end":end,"prediction":q,"realized_return":realized,
                "correct":bool(np.sign(q)==np.sign(realized)) if end is not None else None,
                "phase":"OOS" if decision>=pd.Timestamp(cfg["SPLIT_DATE"]) else "IS"})
    scored=pd.DataFrame(scored)
    scored.to_csv(OUT/"corrected_hitrate_details.csv",index=False)
    summary=[]
    for (kind,phase),group in scored.groupby(["kind","phase"]):
        for asset in ["Overall",*sorted(group.asset.unique())]:
            selected=group if asset=="Overall" else group[group.asset==asset]
            valid=selected.dropna(subset=["realized_return"])
            summary.append({"kind":kind,"phase":phase,"asset":asset,"n_issued":len(selected),"n_scored":len(valid),
                "n_unmatured_at_end":len(selected)-len(valid),"n_correct":int(valid.correct.sum()),
                "hit_rate":float(valid.correct.mean()) if len(valid) else None})
    summary=pd.DataFrame(summary)
    summary.to_csv(OUT/"corrected_hitrate_summary.csv",index=False)
    hit_pdf=pd.read_csv(OUT/"pdf_audit/printed_table4.csv")
    (OUT/"active_run.json").write_text(json.dumps({"run_id":args.run_id,"manifest":str(run/"manifest.json"),
        "artifact_directory":str(artifacts),"requested_end_inclusive":cfg["TEST_END_DATE"],"last_observed_session":str(prices.index[-1].date()),
        "requested_split":cfg["SPLIT_DATE"],"first_oos_return_date":str(result["hybrid_nav"].index[1].date()),
        "oos_nav_anchor":str(anchor.date()),"oos_n_returns":len(result["hybrid_nav"])-1,
        "input_matrix_sha256":manifest["aligned_inputs"]["price_matrix_sha256"],
        "paper_reference_tables":"pdf_audit/printed_table2.csv,printed_table3.csv,printed_table4.csv",
        "not_exact_historical_input_reproduction":True},indent=2))
    print(json.dumps({"run_id":args.run_id,"last_session":str(prices.index[-1].date()),
        "alpha_default_replay_error":max(errors),"hitrate":summary[(summary.phase=="OOS")&(summary.asset=="Overall")].to_dict("records")},default=default))


if __name__=="__main__":
    main()
