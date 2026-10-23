"""Audited next-close execution with fixed shares between scheduled trades.

At index t, covariance information ends at prices[t]. A decision after that
close executes at prices[t+1], and first earns prices[t+2]/prices[t+1]-1.
The original ranking feature lag and conservative training cutoff are retained.
"""
import numpy as np
import pandas as pd
from config import (
    DEFAULT_FEATURE_WINDOW, DEFAULT_PREDICTION_HORIZON, ENABLE_HYBRID_STRATEGY,
    HYBRID_MVO_RATIO_NORMAL, HYBRID_REGIME_RATIOS, INITIAL_NAV,
    ML_MIN_ALLOWED_PREDICTION_RETURN, RETRAIN_FREQUENCY, ML_TRAINING_MODE,
    REBALANCE_FREQ, VIEW_MODE, VOL_DAMPENER_HIST_WINDOW,
    VOL_DAMPENER_RECENT_WINDOW, VOL_DAMPENER_THRESHOLD, WINDOW,
    RANKING_RESELECT_FREQUENCY, RANKING_RETRAIN_FREQUENCY,
)
from gen_view.xgboost.config import MIN_TRAIN_SAMPLES
from gen_view.xgboost.xgboost_core import XGBoostEnsembleModel
from gen_view.ranking.ranking_model import XGBoostRankingModel
from gen_view.ranking.risk_management import detect_market_regime
from backtest._black_litterman import black_litterman_posterior_mu
from backtest._optimizer import blend_weights, optimize_weight
from backtest._views import generate_dynamic_views
from backtest._ranking_helpers import run_ranking_step


def backtest(prices, window=WINDOW, rebalance_freq=REBALANCE_FREQ,
             initial_nav=INITIAL_NAV, view_mode=VIEW_MODE, ml_model=None,
             ml_min_return_threshold=ML_MIN_ALLOWED_PREDICTION_RETURN,
             ml_training_mode=ML_TRAINING_MODE, retrain_frequency=RETRAIN_FREQUENCY,
             ranking_universe_prices=None, ranking_market_prices=None, warmup_end_index=0):
    returns = prices.pct_change(fill_method=None).iloc[1:]
    if returns.isna().any().any() or not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Backtest requires finite aligned prices")
    if len(returns) <= window:
        raise ValueError("Insufficient observations for covariance window")
    assets = list(prices.columns)
    m = len(assets)
    strategies = ["EW", "MVO", "BL"] + (["HYBRID"] if ENABLE_HYBRID_STRATEGY else [])
    weights = {s: np.zeros(m) for s in strategies}
    cash = {s: 1.0 for s in strategies}
    nav = {s: [initial_nav] for s in strategies}
    nav_dates = [prices.index[window]]
    daily_weights = {s: [] for s in strategies}
    rebalance_dates, views_history, target_history, executions, turnover_rows = [], [], [], [], []
    pending = None
    warmup_result = None
    ranking_state = None
    if view_mode in ("ranking", "ranking_absolute"):
        if ranking_universe_prices is None or ranking_market_prices is None:
            raise ValueError("Ranking modes require aligned universe and market data")
        if not (ranking_universe_prices.index.equals(prices.index) and ranking_market_prices.index.equals(prices.index)):
            raise ValueError("Ranking inputs must align exactly with portfolio price dates")
        ranking_state = {
            "ranking_model": XGBoostRankingModel() if view_mode == "ranking" else None,
            "ranking_abs_model": XGBoostEnsembleModel() if view_mode == "ranking_absolute" else None,
            "selected_stocks": None, "last_reselect_t": -RANKING_RESELECT_FREQUENCY,
            "last_ranking_retrain_t": -(RETRAIN_FREQUENCY if view_mode == "ranking_absolute" else RANKING_RETRAIN_FREQUENCY),
        }
    last_retrain_t = -retrain_frequency
    if view_mode in ("ml", "combined") and ml_training_mode == "walk_forward" and ml_model is None:
        ml_model = XGBoostEnsembleModel()

    for t in range(window, len(returns)):
        decision_date = prices.index[t]
        return_date = prices.index[t+1]
        if warmup_end_index > 0 and t == warmup_end_index:
            warmup_result = {s.lower()+"_nav": pd.Series(nav[s],index=nav_dates) for s in strategies}
            nav = {s: [initial_nav] for s in strategies}
            nav_dates = [decision_date]
            daily_weights = {s: [] for s in strategies}

        if pending is not None:
            targets = pending["targets"]
            for s in strategies:
                pre = weights[s].copy()
                target = np.asarray(targets[s],dtype=float)
                pre_cash = cash[s]
                asset_turnover = 0.5*float(np.abs(target-pre).sum())
                cash_inclusive = asset_turnover+0.5*abs(pre_cash)
                for i,a in enumerate(assets):
                    turnover_rows.append({"date": decision_date, "decision_date": pending["decision_date"],
                        "strategy": s, "asset": a, "pre_trade_weight": pre[i], "target_weight": target[i],
                        "weight_change": target[i]-pre[i], "portfolio_turnover": asset_turnover,
                        "cash_inclusive_turnover": cash_inclusive, "initial_allocation": bool(pre_cash>0.999999),
                        "pre_trade_cash_weight": pre_cash})
                weights[s],cash[s] = target.copy(),0.0
            executions.append({**{k:v for k,v in pending.items() if k!="targets"},
                "execution_date": decision_date, "first_return_date": return_date,
                "execution_price": "next exchange-session close; fund/gold valuation proxies",
                "information_timing_pass": bool(pending["decision_date"]<decision_date<return_date)})
            target_history.append({"date":decision_date,"decision_date":pending["decision_date"],
                **{s:targets[s].copy() for s in strategies}})
            rebalance_dates.append(decision_date)
            pending = None

        if (t-window)%rebalance_freq == 0:
            hist = returns.iloc[t-window:t]
            mu,sigma = hist.mean().values,hist.cov().values
            mvo_target = optimize_weight(mu,sigma)
            if ranking_state is not None:
                bl_target,_,regime,record = run_ranking_step(
                    t,ranking_state,view_mode,mu,sigma,returns,assets,
                    ranking_universe_prices,ranking_market_prices)
            else:
                if view_mode in ("ml","combined") and ml_training_mode == "walk_forward":
                    horizon = getattr(ml_model,"prediction_horizon",DEFAULT_PREDICTION_HORIZON)
                    fw = getattr(ml_model,"feature_window",DEFAULT_FEATURE_WINDOW)
                    train_end = t-horizon
                    if t-last_retrain_t>=retrain_frequency and train_end>=MIN_TRAIN_SAMPLES+fw:
                        ml_model.train(prices.iloc[:train_end],verbose=False)
                        last_retrain_t = t
                effective = ml_model
                if hasattr(effective,"is_trained") and not effective.is_trained:
                    effective = None
                p,q,confidence,names = generate_dynamic_views(
                    prices.iloc[:t],assets,view_mode,ml_model=effective,
                    ml_min_return_threshold=ml_min_return_threshold)
                if confidence is not None and view_mode in ("ml","combined"):
                    recent = returns.iloc[max(0,t-VOL_DAMPENER_RECENT_WINDOW):t].std().mean()
                    long = returns.iloc[max(0,t-VOL_DAMPENER_HIST_WINDOW):t].std().mean()
                    ratio = recent/long if long>0 else 1.0
                    if ratio>VOL_DAMPENER_THRESHOLD:
                        confidence = confidence*VOL_DAMPENER_THRESHOLD/ratio
                regime = detect_market_regime(returns,t)
                mu_bl = black_litterman_posterior_mu(sigma,np.full(m,1/m),p,q,confidence) if p is not None else mu
                bl_target = optimize_weight(mu_bl,sigma)
                record = {"view_names":names,"q_values":[] if q is None else q.tolist(),
                          "confidences":[] if confidence is None else confidence.tolist()}
            targets = {"EW":np.full(m,1/m),"MVO":mvo_target,"BL":bl_target}
            if ENABLE_HYBRID_STRATEGY:
                alpha = HYBRID_REGIME_RATIOS.get(regime["regime"],HYBRID_MVO_RATIO_NORMAL)
                targets["HYBRID"] = blend_weights(mvo_target,bl_target,alpha)
                record.update(regime=regime["regime"],hybrid_alpha=float(alpha))
            for s,w in targets.items():
                if not np.isfinite(w).all() or abs(float(w.sum())-1)>1e-8 or float(w.min())<-1e-8:
                    raise AssertionError(f"Invalid target {s} at {decision_date}")
            feature_date = prices.index[t-1]
            correlation_date = (ranking_universe_prices.index[ranking_state["last_reselect_t"]-1]
                                if ranking_state is not None else pd.NaT)
            record.update(date=decision_date,prediction_origin_date=feature_date,
                          latest_feature_date=feature_date,latest_covariance_date=decision_date)
            views_history.append(record)
            pending = {"targets":targets,"decision_date":decision_date,
                "latest_feature_date":feature_date,"latest_correlation_date":correlation_date,
                "latest_covariance_date":decision_date,
                "prediction_time":f"after close {decision_date.date()}",
                "weight_calculation_time":f"after prediction {decision_date.date()}"}

        r = returns.iloc[t].values
        for s in strategies:
            before = weights[s].copy()
            rp = float(np.dot(before,r))
            nav[s].append(nav[s][-1]*(1+rp))
            daily_weights[s].append(before)
            weights[s] = before*(1+r)/(1+rp)
            cash[s] = cash[s]/(1+rp)
            if abs(float(weights[s].sum())+cash[s]-1)>1e-8:
                raise AssertionError("Holdings budget drift inconsistency")
        nav_dates.append(return_date)

    # A final-close order can execute even when its first future return is
    # outside the sample. Record the trade without inventing a return.
    if pending is not None:
        execution_date = prices.index[-1]
        targets = pending["targets"]
        for s in strategies:
            pre,pre_cash = weights[s].copy(),cash[s]
            target = np.asarray(targets[s],dtype=float)
            asset_turnover = 0.5*float(np.abs(target-pre).sum())
            for i,a in enumerate(assets):
                turnover_rows.append({"date":execution_date,"decision_date":pending["decision_date"],
                    "strategy":s,"asset":a,"pre_trade_weight":pre[i],"target_weight":target[i],
                    "weight_change":target[i]-pre[i],"portfolio_turnover":asset_turnover,
                    "cash_inclusive_turnover":asset_turnover+0.5*abs(pre_cash),
                    "initial_allocation":bool(pre_cash>0.999999),"pre_trade_cash_weight":pre_cash})
            weights[s],cash[s] = target.copy(),0.0
        executions.append({**{k:v for k,v in pending.items() if k!="targets"},
            "execution_date":execution_date,"first_return_date":None,
            "execution_status":"end_of_sample_no_return",
            "execution_price":"final observed exchange-session close; fund/gold valuation proxies",
            "information_timing_pass":bool(pending["decision_date"]<execution_date)})
        target_history.append({"date":execution_date,"decision_date":pending["decision_date"],
            **{s:targets[s].copy() for s in strategies}})
        rebalance_dates.append(execution_date)
        pending = None

    model = ranking_state["ranking_abs_model"] if ranking_state is not None and view_mode=="ranking_absolute" else ml_model
    result = {"returns":returns,"assets":assets,"view_mode":view_mode,
        "rebalance_dates":rebalance_dates,"views_history":views_history,
        "rebalance_weights_history":target_history,"execution_ledger":executions,
        "turnover_history":turnover_rows,"warmup_result":warmup_result,
        "ml_model":model,"unexecuted_final_order":pending}
    for s in strategies:
        result[s.lower()+"_nav"] = pd.Series(nav[s],index=nav_dates)
        result[s.lower()+"_weights_hist"] = np.array(daily_weights[s])
    return result
