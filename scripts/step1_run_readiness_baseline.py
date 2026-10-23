"""Execute and export an auditable current-period Step 1 baseline."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from datetime import date as CalendarDate, datetime
import hashlib
import json
import os
from pathlib import Path
import pickle
import re
import shutil
import subprocess
import sys
import time
import traceback
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/step1/readiness_20261012/candidate_workspace"
OUT = ROOT / "outputs/step1/readiness_20261012"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default(value):
    if hasattr(value,"isoformat"):
        return value.isoformat()
    if hasattr(value,"tolist"):
        return value.tolist()
    if hasattr(value,"item"):
        return value.item()
    return str(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verification-run",action="store_true")
    parser.add_argument("--start-date",type=CalendarDate.fromisoformat,default=None)
    parser.add_argument("--split-date",type=CalendarDate.fromisoformat,default=None)
    parser.add_argument("--end-date",type=CalendarDate.fromisoformat,default=None)
    parser.add_argument("--run-label",default=None)
    args = parser.parse_args()
    if args.run_label and not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}",args.run_label):
        parser.error("--run-label must contain lowercase letters, digits and hyphens")
    prefix="availability-"+(args.run_label+"-" if args.run_label else "")
    run_id = prefix+datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y%m%dT%H%M%S")
    run = OUT / "runs" / run_id
    run.mkdir(parents=True)
    destination = run / "artifacts" if args.verification_run else OUT
    destination.mkdir(exist_ok=True)
    os.environ["MPLCONFIGDIR"] = "/private/tmp/portfolio-step1-mpl"
    os.environ["XDG_CACHE_HOME"] = "/private/tmp/portfolio-step1-cache"
    sys.path.insert(0,str(BASE))
    os.chdir(BASE)
    import numpy as np
    import pandas as pd
    import cvxpy
    import config
    runtime_overrides={}
    for key,value in [("TRAIN_START_DATE",args.start_date),("SPLIT_DATE",args.split_date),("TEST_END_DATE",args.end_date)]:
        if value is not None:
            runtime_overrides[key]=value.isoformat()
            setattr(config,key,value.isoformat())
    if not (CalendarDate.fromisoformat(config.TRAIN_START_DATE)<CalendarDate.fromisoformat(config.SPLIT_DATE)<CalendarDate.fromisoformat(config.TEST_END_DATE)):
        parser.error("Require start date < split date < end date")
    config.PHASE_PERIODS={"train":(config.TRAIN_START_DATE,config.SPLIT_DATE),
        "test":(config.SPLIT_DATE,config.TEST_END_DATE),"full":(config.TRAIN_START_DATE,config.TEST_END_DATE)}
    from utils.data_loader import load_assets_config,build_price_table
    from backtest._metrics import metric_summary
    import backtest._loop as loop
    import backtest._ranking_helpers as helpers
    from gen_view.ranking.stock_selection import compute_distance_matrix
    from backtest._optimizer import _regularize_covariance

    config_values = {k:v for k,v in vars(config).items() if k.isupper()}
    source_paths = [p for p in BASE.rglob("*") if p.is_file() and p.suffix in {".py",".json"} and "__pycache__" not in p.parts and ".cache" not in p.parts]
    assets_cfg = load_assets_config()
    data_paths = {c["full_path"] for c in assets_cfg.values()} | {BASE/config.TRADING_CALENDAR_PATH}
    manifest = {"schema_version":1,"run_id":run_id,"status":"running","parent_run_id":None,
        "hypothesis":f"Declared valuation-proxy availability protocol; evaluation ending {config.TEST_END_DATE}",
        "started_at":datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
        "source":{"base_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                  "branch":subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip(),
                  "dirty_state":subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],cwd=ROOT,text=True),
                  "root":str(BASE),"runner_sha256":sha(Path(__file__)),
                  "files":[{"path":str(p.relative_to(BASE)),"sha256":sha(p)} for p in sorted(source_paths)]},
        "inputs":[{"path":str(p),"sha256":sha(p)} for p in sorted(data_paths)],
        "config":config_values,"runtime_overrides":runtime_overrides,
        "environment":json.loads((OUT/"environment.json").read_text()),
        "execution":{"argv":sys.argv,"interpreter":sys.executable,"cwd":str(BASE),
                     "stdout":str(run/"stdout.log"),"stderr":str(run/"stderr.log"),
                     "solvers":cvxpy.installed_solvers()},
        "policy":{"seeds":[42,43,44,45,46],"cache_reused":False,"walk_forward":True,
                  "calendar":"observed VNINDEX sessions","constraints_tolerance":1e-8,
                  "execution":"decision after close(t), next-close(t+1), first return after execution",
                  "holdings":"fixed shares between 5-session trades","cost":0,"decision_cutoff":"18:00 Asia/Ho_Chi_Minh","information_panel":"availability-filtered, distinct from ex-post valuation panel"},
        "limitations":["Fixed VN30 membership remains a Step 7 issue.",
                       "Historical first-publication and revision vintages remain unverified; availability is an explicit benchmark contract.",
                       "Close/NAV proxies are a frictionless valuation convention, not executable fund orders."]}
    manifest["availability_policy"] = json.loads((OUT/"availability_policy.json").read_text())
    manifest["inputs"] += [{"path":str(OUT/n),"sha256":sha(OUT/n)} for n in ["candidate_information_prices.csv","availability_ledger.csv","availability_policy.json"]]
    manifest_path = run/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,indent=2,default=default))
    (run/"run_config.json").write_text(json.dumps(config_values,indent=2,default=default))
    (run/"random_seeds.txt").write_text("42\n43\n44\n45\n46\n")
    (run/"requirements_frozen.txt").write_bytes((OUT/"requirements_frozen.txt").read_bytes())
    shutil.copy2(Path(__file__),run/"runner_source.py")
    for p in source_paths:
        target=run/"source_snapshot"/p.relative_to(BASE)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)
    (run/"initial_tracked_diff.patch").write_bytes(subprocess.check_output(["git","diff","--binary"],cwd=ROOT))
    if not args.verification_run:
        (BASE/"run_config.json").write_bytes((run/"run_config.json").read_bytes())
        (BASE/"random_seeds.txt").write_bytes((run/"random_seeds.txt").read_bytes())
        (BASE/"requirements_frozen.txt").write_bytes((run/"requirements_frozen.txt").read_bytes())
    print(str(manifest_path),flush=True)
    started = time.monotonic()
    try:
        with (run/"stdout.log").open("w") as stdout,(run/"stderr.log").open("w") as stderr,redirect_stdout(stdout),redirect_stderr(stderr):
            prices = build_price_table(config.TRAIN_START_DATE,config.TEST_END_DATE,assets_cfg,
                                       phase="full",data_mode="full",window=config.WINDOW)
            universe = prices[json.loads((BASE/"assets_1.json").read_text())["vn30_universe"]]
            market_assets = load_assets_config(selected_assets=["VNINDEX"])
            market = build_price_table(config.TRAIN_START_DATE,config.TEST_END_DATE,market_assets,
                                       phase="full",data_mode="full",window=config.WINDOW)["VNINDEX"]
            information = pd.read_csv(OUT/"candidate_information_prices.csv",index_col=0,parse_dates=True)
            common = prices.index.intersection(market.index).intersection(information.index)
            prices,market = prices.loc[common],market.loc[common]
            information=information.loc[common,prices.columns]
            universe=information[json.loads((BASE/"assets_1.json").read_text())["vn30_universe"]]
            manifest["aligned_inputs"] = {"rows":len(prices),"first_date":prices.index[0],"last_date":prices.index[-1],
                "ordered_assets":list(prices.columns),"warmup_start":prices.index[0],"evaluation_start":config.SPLIT_DATE,
                "price_matrix_sha256":hashlib.sha256(pd.util.hash_pandas_object(prices,index=True).values.tobytes()).hexdigest()}
            manifest_path.write_text(json.dumps(manifest,indent=2,default=default))
            prices.to_csv(run/"aligned_prices.csv",index_label="date")
            selections,bl_samples,rebalance_context = [],[],{}
            original_select = helpers.select_representatives
            def observe_select(frame,k=5,**kwargs):
                selected = original_select(frame,k=k,**kwargs)
                dist,names = compute_distance_matrix(frame)
                selected_indices = [names.index(a) for a in selected]
                item = {"selection_date":rebalance_context["date"],"universe":names,
                        "lookback_start":frame.index[0],"lookback_end":frame.index[-1],"selected_assets":selected,
                        "coverage_objective":float(dist[:,selected_indices].min(axis=1).sum()),
                        "distance_file":f"selection_matrices/{len(selections):04d}.npz"}
                matrix_path = run/item["distance_file"]
                matrix_path.parent.mkdir(exist_ok=True)
                np.savez_compressed(matrix_path,distance=dist,ordered_assets=names,selected_assets=selected)
                selections.append(item)
                return selected
            helpers.select_representatives = observe_select
            original_step = loop.run_ranking_step
            def observe_step(t,*a,**kw):
                rebalance_context["date"] = prices.index[t]
                if len(bl_samples)%25==0:
                    print("Decision",prices.index[t].date(),flush=True)
                return original_step(t,*a,**kw)
            loop.run_ranking_step = observe_step
            original_bl = helpers.black_litterman_posterior_mu
            def observe_bl(sigma,w,p,q,confidence,**kwargs):
                mu = original_bl(sigma,w,p,q,confidence,**kwargs)
                sigma = _regularize_covariance(sigma)
                tau,delta = kwargs.get("tau",config.BL_TAU),kwargs.get("delta",config.BL_DELTA)
                pi = delta*sigma@w
                omega = np.diag(np.clip(np.diag(p@(tau*sigma)@p.T),1e-10,None)/np.clip(confidence,1e-6,1))
                independent = pi+tau*sigma@p.T@np.linalg.solve(p@(tau*sigma)@p.T+omega,q-p@pi)
                selected = selections[-1]["selected_assets"]
                ordered = selected+["GOLD"]+config.DEFAULT_DEFENSIVE_ASSETS
                bl_samples.append({"date":rebalance_context["date"],"assets":ordered,"covariance":sigma,
                    "market_weights":w,"tau":tau,"delta":delta,"pi":pi,"P":p,"Q":q,
                    "confidence":confidence,"Omega":omega,"posterior":mu,"independent_posterior":independent,
                    "max_absolute_error":float(np.abs(mu-independent).max())})
                return mu
            helpers.black_litterman_posterior_mu = observe_bl
            first_oos_price = int((prices.index>=pd.Timestamp(config.SPLIT_DATE)).argmax())
            result = loop.backtest(prices,view_mode="ranking_absolute",ml_training_mode="walk_forward",
                ranking_universe_prices=universe,ranking_market_prices=market,warmup_end_index=first_oos_price-1,information_prices=information)
            pickle.dump({"result":result,"prices":prices,"selections":selections,"bl_samples":bl_samples},(run/"result.pkl").open("wb"))

            rows,nav_rows,return_rows,weight_rows = [],[],[],[]
            turnover = pd.DataFrame(result["turnover_history"])
            turnover.to_csv(destination/"trusted_baseline_turnover.csv",index=False)
            turnover_summary = turnover.drop_duplicates(["date","strategy"])[["date","strategy","portfolio_turnover","cash_inclusive_turnover","initial_allocation"]]
            turnover_summary.to_csv(destination/"turnover_summary.csv",index=False)
            for phase,bundle in [("IS",result["warmup_result"]),("OOS",result)]:
                for s in ["EW","MVO","BL","HYBRID"]:
                    nav = bundle[s.lower()+"_nav"]
                    stats = metric_summary(nav)
                    mask = (turnover_summary.date>nav.index[0]) & (turnover_summary.date<=nav.index[-1]) & (turnover_summary.strategy==s) & (~turnover_summary.initial_allocation)
                    stats.update(phase=phase,strategy=s,start_date=nav.index[0],end_date=nav.index[-1],
                        n_returns=len(nav)-1,total_turnover=float(turnover_summary.loc[mask,"portfolio_turnover"].sum()))
                    stats["annualized_turnover"] = stats["total_turnover"]*252/(len(nav)-1)
                    rows.append(stats)
                    for date,value in nav.items():
                        nav_rows.append({"phase":phase,"strategy":s,"date":date,"nav":value})
                    for date,value in nav.pct_change().iloc[1:].items():
                        return_rows.append({"phase":phase,"strategy":s,"date":date,"return":value})
            for record in result["rebalance_weights_history"]:
                for s in ["EW","MVO","BL","HYBRID"]:
                    for a,w in zip(result["assets"],record[s]):
                        weight_rows.append({"date":record["date"],"decision_date":record["decision_date"],"strategy":s,"asset":a,"target_weight":w})
            pd.DataFrame(rows).to_csv(destination/"trusted_baseline_metrics.csv",index=False)
            pd.DataFrame(nav_rows).to_csv(destination/"trusted_baseline_nav.csv",index=False)
            pd.DataFrame(return_rows).to_csv(destination/"trusted_baseline_daily_returns.csv",index=False)
            pd.DataFrame(weight_rows).to_csv(destination/"trusted_baseline_weights.csv",index=False)
            pd.DataFrame(result["execution_ledger"]).to_csv(destination/"execution_ledger.csv",index=False)
            pd.DataFrame([{k:json.dumps(v,default=default) if isinstance(v,list) else v for k,v in item.items()} for item in selections]).to_csv(destination/"selection_history.csv",index=False)
            (run/"views_history.json").write_text(json.dumps(result["views_history"],default=default,indent=2))
            model = result["ml_model"]
            training,predictions = model.training_audit,model.prediction_audit
            (run/"ml_training_audit.json").write_text(json.dumps(training,indent=2,default=default))
            (run/"ml_prediction_audit.json").write_text(json.dumps(predictions,indent=2,default=default))
            csv_training=[]
            for item in training:
                item=dict(item)
                cutoff=pd.Timestamp(item["input_price_end"])
                t=int(prices.index.get_loc(cutoff))+config.DEFAULT_PREDICTION_HORIZON+1
                item.update(retrain_date=prices.index[t],prediction_date=prices.index[t],execution_date=prices.index[t+1],
                    train_feature_start=item.get("train_feature_start"),train_feature_end=item.get("train_feature_end"),
                    last_label_start=item.get("last_label_start"),last_label_end=item.get("last_label_end"),
                    evidence_kind="actual_fit",fit_performed=item.get("status")=="trained")
                if item.get("status")=="trained":
                    item["pass_fail"]="PASS" if pd.Timestamp(item["last_fitting_label_end"])<pd.Timestamp(item["validation_start"]) and pd.Timestamp(item["last_label_end"])<=prices.index[t] else "FAIL"
                csv_training.append({k:json.dumps(v,default=default) if isinstance(v,(list,dict)) else v for k,v in item.items()})
            pd.DataFrame(csv_training).to_csv(destination/"ml_training_audit.csv",index=False)
            pd.DataFrame(csv_training).to_csv(destination/"training_window_audit.csv",index=False)
            pd.DataFrame([{k:json.dumps(v,default=default) if isinstance(v,(list,dict)) else v for k,v in item.items()} for item in predictions]).to_csv(destination/"ml_prediction_audit.csv",index=False)
            sample_dir=run/"bl_audit_sample"
            sample_dir.mkdir()
            for item in bl_samples:
                (sample_dir/(pd.Timestamp(item["date"]).strftime("%Y-%m-%d")+".json")).write_text(json.dumps(item,default=default,indent=2))

            constraints=[]
            for record in result["rebalance_weights_history"]:
                for s in ["EW","MVO","BL","HYBRID"]:
                    w=record[s]
                    nondef=float(sum(x for a,x in zip(result["assets"],w) if a not in config.DEFAULT_DEFENSIVE_ASSETS))
                    defensive=float(sum(x for a,x in zip(result["assets"],w) if a in config.DEFAULT_DEFENSIVE_ASSETS))
                    constraints.append({"date":record["date"],"strategy":s,"budget_error":abs(float(w.sum())-1),
                        "negative_violation":max(0,-float(w.min())),"position_cap_violation":max(0,float(w.max())-config.MAX_POSITION_SIZE),
                        "nondefensive_cap_violation":max(0,nondef-config.MAX_EQUITY_EXPOSURE) if s=="BL" else 0,
                        "defensive_floor_violation":max(0,config.MIN_DEFENSIVE_WEIGHT-defensive) if s=="BL" else 0})
            constraint_df=pd.DataFrame(constraints)
            residual_cols=[c for c in constraint_df if c not in ["date","strategy"]]
            violation_df=constraint_df[(constraint_df[residual_cols]>1e-8).any(axis=1)]
            constraint_df.to_csv(destination/"constraint_diagnostics.csv",index=False)
            violation_df.to_csv(destination/"constraint_violations.csv",index=False)
            pd.DataFrame(result["execution_ledger"]).to_csv(destination/"execution_ledger.csv",index=False)
            checks={"finite_nav":all(np.isfinite(row["nav"]) and row["nav"]>0 for row in nav_rows),
                "constraint_violations":len(violation_df),"max_constraint_residual":float(constraint_df[residual_cols].to_numpy().max()),
                "training_window_failures":sum(x.get("pass_fail")=="FAIL" for x in csv_training),
                "execution_timing_failures":sum(not x["information_timing_pass"] for x in result["execution_ledger"]),
                "max_bl_posterior_error":max(x["max_absolute_error"] for x in bl_samples),
                "selection_events":len(selections),"actual_asset_training_events":len(training),"actual_predictions":len(predictions),
                "bl_samples":len(bl_samples),"metric_rows":len(rows),"last_evaluation_date":str(prices.index[-1].date())}
            assert checks["finite_nav"] and checks["constraint_violations"]==0 and checks["training_window_failures"]==0 and checks["execution_timing_failures"]==0
            assert checks["max_bl_posterior_error"]<1e-8
            (destination/"baseline_verification.json").write_text(json.dumps(checks,indent=2))
            print(json.dumps({"checks":checks,"metrics":rows},default=default,indent=2),flush=True)
        manifest["status"]="succeeded"
        manifest["results"]={"destination":str(destination),"checks":checks,
            "artifacts":[{"path":str(p),"sha256":sha(p)} for p in destination.glob("*.csv") if p.is_file()]}
    except Exception:
        manifest["status"]="failed"
        manifest["error"]=traceback.format_exc()
        (run/"error.txt").write_text(manifest["error"])
        raise
    finally:
        manifest["finished_at"]=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
        manifest["execution"]["elapsed_seconds"]=time.monotonic()-started
        manifest_path.write_text(json.dumps(manifest,default=default,indent=2))
    print(json.dumps({"run_id":run_id,"status":manifest["status"]}),flush=True)


if __name__=="__main__":
    main()
