"""Replay frozen Phase 1 views with serving constraints and a common execution calendar."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from portfolio_contracts.hybrid import hybrid_policy
from portfolio_core.hybrid import allocate_hybrid


PROFILES = {'conservative': 6., 'balanced': 3., 'growth': 1.5}
FEE = .001  # 10 bps per unit of one-way turnover, including the first entry from cash.
# Pilot guardrails declared before reading the scores. All must hold versus regime-only HYBRID.
GUARDRAILS = {'annual_volatility_increase': .02, 'drawdown_increase': .03,
              'turnover_ratio': 1.25}


def scores(returns, turnover):
    r = np.asarray(returns)
    nav = np.r_[1., np.cumprod(1 + r)]
    return dict(sessions=len(r), net_return=float(nav[-1] - 1),
                annual_volatility=float(r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 else None,
                max_drawdown=float((1 - nav / np.maximum.accumulate(nav)).max()),
                one_way_turnover=float(sum(turnover)))


def replay(run):
    def csv(path, *dates):
        return pd.read_csv(run / path, parse_dates=list(dates))

    config = json.loads((run / 'run_config.json').read_text())
    views = {pd.Timestamp(row['date']): row for row in json.loads((run / 'views_history.json').read_text())}
    info = csv('candidate_information_prices.csv', 'date').set_index('date')
    valuation = csv('aligned_prices.csv', 'date').set_index('date')
    assert info.index.equals(valuation.index) and set(info.columns) == set(valuation.columns)
    returns = info.pct_change(fill_method=None)
    realized = valuation[info.columns].pct_change(fill_method=None)
    assets = list(info.columns)
    selections = csv('artifacts/selection_history.csv', 'selection_date', 'lookback_end').set_index('selection_date')
    ledger = csv('artifacts/execution_ledger.csv', 'decision_date', 'execution_date', 'first_return_date')
    split = pd.Timestamp(config['SPLIT_DATE'])
    schedules = {}
    skipped = []
    for row in ledger.itertuples(index=False):
        assert row.information_timing_pass and row.decision_date < row.execution_date < row.first_return_date
        view = views[row.decision_date]
        if not any(name.endswith('_ml_xgboost') for name in view['view_names']):
            skipped.append(str(row.decision_date.date()))
            continue
        selected = selections.loc[:row.decision_date].iloc[-1]
        assert selected.lookback_end < row.decision_date
        active = [asset for asset in assets if asset in json.loads(selected.selected_assets) + ['GOLD', 'VFF']]
        p = []
        for name in view['view_names']:
            asset, kind = name.split('_', 1)
            assert asset in active
            vector = [float(a == asset) for a in assets]
            if kind.startswith('defensive_'):
                assert asset == 'VFF'
                vector = [1. if a == asset else -1. / (len(active) - 1) if a in active else 0. for a in assets]
            else:
                assert kind == 'ml_xgboost'
            p.append(vector)
        history = returns.loc[:row.decision_date].tail(20)
        assert len(history) == 20 and np.isfinite(history.to_numpy()).all()
        numerical = dict(asset_ids=assets, active_asset_ids=active, active_policy_version='user-selection-active-v1',
                         mean_returns=history.mean().tolist(), covariance=history.cov().to_numpy().tolist(),
                         market_weights=[1 / len(active) if a in active else 0. for a in assets],
                         views_p=p, views_q=view['q_values'], view_confidences=view['confidences'],
                         tau=config['BL_TAU'], delta=config['BL_DELTA'])
        regime = view['regime']
        targets = {}
        for profile, risk in PROFILES.items():
            constraints = dict(risk_aversion=max(risk, 5 if regime == 'crisis' else 1.5),
                               max_position_weight=.5, defensive_asset_ids=['VFF'],
                               min_defensive_weight=.15, max_non_defensive_weight=.7)
            pin = hybrid_policy(regime, profile)
            result = allocate_hybrid(numerical, constraints, pin)
            legs = result['diagnostics']['hybrid']
            alpha = view['hybrid_alpha']
            assert alpha == hybrid_policy(regime, 'balanced')['mvo_share']
            mvo, bl = np.asarray(legs['mvo_weights']), np.asarray(legs['bl_ml_weights'])
            targets[profile, 'profile_regime'] = np.asarray(result['weights'])
            targets[profile, 'regime_only'] = alpha * mvo + (1 - alpha) * bl
            targets[profile, 'bl_ml'] = bl
        schedules[row.first_return_date] = (regime, targets)

    keys = list(next(iter(schedules.values()))[1])
    periods = {}
    for name, days in [('pre_split', realized.loc[realized.index < split]),
                       ('holdout', realized.loc[realized.index >= split])]:
        # Start flat in each partition and enter together at its first eligible scheduled execution.
        weights = {key: np.zeros(len(assets)) for key in keys}
        tape = {key: [] for key in keys}
        turnover, regime = {}, None
        for day, ret in days.iterrows():
            if day in schedules:
                regime, targets = schedules[day]
                turnover = {key: .5 * (np.abs(target - weights[key]).sum() + abs(1 - weights[key].sum()))
                            for key, target in targets.items()}
                weights = targets.copy()
            if regime is not None:
                daily = ret.to_numpy()
                for key, weight in weights.items():
                    gross = float(weight @ daily)
                    traded = float(turnover.get(key, 0.))
                    net = (1 - FEE * traded) * (1 + gross) - 1
                    tape[key].append((regime, net, traded))
                    weights[key] = weight * (1 + daily) / (1 + gross)
                turnover = {}
        periods[name] = {}
        for key, entries in tape.items():
            periods[name]['/'.join(key)] = scores([r for _, r, _ in entries], [t for _, _, t in entries]) | {
                'by_regime': {label: scores([r for v, r, _ in entries if v == label],
                                            [t for v, _, t in entries if v == label])
                              for label in sorted({v for v, _, _ in entries})}}
    guardrail_results = {}
    for profile in PROFILES:
        proposed = periods['holdout'][profile + '/profile_regime']
        control = periods['holdout'][profile + '/regime_only']
        guardrail_results[profile] = {
            'volatility': proposed['annual_volatility'] - control['annual_volatility'] <= GUARDRAILS['annual_volatility_increase'],
            'drawdown': proposed['max_drawdown'] - control['max_drawdown'] <= GUARDRAILS['drawdown_increase'],
            'turnover': proposed['one_way_turnover'] <= GUARDRAILS['turnover_ratio'] * control['one_way_turnover'],
        }
    return dict(run=run.name, split=str(split.date()), fee_per_turnover=FEE, guardrails=GUARDRAILS,
                guardrail_results=guardrail_results, matched_rebalances=len(schedules),
                no_ml_view_decisions=skipped, periods=periods,
                input_sha256={name: hashlib.sha256((run / name).read_bytes()).hexdigest() for name in
                              ['run_config.json', 'views_history.json', 'candidate_information_prices.csv',
                               'aligned_prices.csv', 'artifacts/selection_history.csv', 'artifacts/execution_ledger.csv']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(replay(args.run), indent=2, allow_nan=False) + '\n')
