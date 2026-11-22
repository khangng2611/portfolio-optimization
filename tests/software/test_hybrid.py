import numpy as np
import pytest

from portfolio_core import allocate
from portfolio_core.hybrid import allocate_hybrid
from portfolio_contracts.hybrid import constraint_violations, hybrid_policy, validate_hybrid_weights


@pytest.mark.parametrize('regime,expected', [
    ('normal', (.45, .60, .75)), ('stress', (.225, .30, .375)),
    ('crisis', (.075, .10, .125)),
])
def test_phase1_mix_by_regime_and_profile(regime, expected):
    assert tuple(hybrid_policy(regime, p)['mvo_share'] for p in ('conservative', 'balanced', 'growth')) == pytest.approx(expected)


def test_hybrid_blends_distinct_universes_and_flags_infeasible_ew():
    ids = ['ACB', 'BID', 'CTG', 'DGC', 'FPT', 'GAS', 'GOLD', 'VFF']
    active = [a for a in ids if a != 'GAS']
    numerical = dict(asset_ids=ids, active_asset_ids=active,
                     active_policy_version='user-selection-active-v1',
                     mean_returns=[.001] * 8, covariance=(np.eye(8) * .0001).tolist(),
                     market_weights=[1 / 7 if a in active else 0 for a in ids],
                     views_p=[[1., 0., 0., 0., 0., 0., 0., 0.]],
                     views_q=[.002], view_confidences=[.8])
    constraints = dict(risk_aversion=5, max_position_weight=.5,
                       defensive_asset_ids=['VFF'], min_defensive_weight=.15,
                       max_non_defensive_weight=.7)
    pin = hybrid_policy('crisis', 'growth')
    r = allocate_hybrid(numerical, constraints, pin)
    bl = allocate(numerical | dict(strategy='BL_ML', constraints=constraints))
    comparison = r['diagnostics']['hybrid']
    assert r['strategy'] == 'HYBRID'
    assert comparison['bl_ml_weights'] == bl['weights']
    assert comparison['bl_ml_weights'][5] == 0 < r['weights'][5]
    comparison['ew_constraint_violations'] = constraint_violations(ids, comparison['ew_weights'], constraints)
    assert comparison['ew_constraint_violations']
    validate_hybrid_weights(ids, active, constraints, pin, r)
    r['weights'][0] += .01
    with pytest.raises(ValueError, match='blend'):
        validate_hybrid_weights(ids, active, constraints, pin, r)
