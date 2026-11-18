"""Full-universe numerical parity against the frozen research functions."""

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from portfolio_core import CoreError, allocate, validate_numerical_inputs
from portfolio_core.phase1_full import (
    ASSET_IDS, EQUITY_IDS, adjust_views, distance_matrix, regime, schedule, select_equities,
)

REFERENCE = json.loads((Path(__file__).parent / 'fixtures/phase1_full_reference.json').read_text())


def base_returns():
    result = np.random.default_rng(314159).normal(.0004, .01, (180, 32))
    result[:, 30] *= .7
    result[:, 31] = .00012
    return result


def full_request(case):
    active = REFERENCE['selected_indices'] + [30, 31]
    p = np.zeros((len(case['q']), 32))
    p[:, active] = case['p']
    market = np.zeros(32)
    market[active] = 1 / 7
    return {
        'strategy': 'BL_ML', 'asset_ids': list(ASSET_IDS),
        'active_asset_ids': [ASSET_IDS[i] for i in active],
        'mean_returns': case['mean_returns'], 'covariance': case['covariance'],
        'market_weights': market.tolist(), 'views_p': p.tolist(),
        'views_q': case['q'], 'view_confidences': case['confidence'],
        'constraints': {'risk_aversion': 5.0 if case['name'] == 'crisis' else 1.5,
                        'max_position_weight': .5, 'defensive_asset_ids': ['VFF'],
                        'min_defensive_weight': .15, 'max_non_defensive_weight': .7},
    }


def test_expanding_selection_distance_and_order_match_actual_frozen_functions():
    prices = 100 * np.cumprod(1 + base_returns()[:, :30], axis=0)
    assert list(ASSET_IDS) == REFERENCE['assets']
    assert list(EQUITY_IDS) == REFERENCE['assets'][:30]
    np.testing.assert_allclose(distance_matrix(prices), REFERENCE['distance'], atol=1e-14, rtol=0)
    selected = select_equities(prices)
    assert selected == REFERENCE['selected_indices']
    cost = np.cumsum(np.min(distance_matrix(prices)[:, selected], axis=1))[-1]
    assert cost == pytest.approx(REFERENCE['selection_cost'], abs=1e-13)


def test_selector_ties_keep_first_lexicographic_combination_even_for_constant_prices():
    assert select_equities(np.ones((20, 30))) == [0, 1, 2, 3, 4]


@pytest.mark.parametrize('n,expected', [
    (21, (20, 20, None, None)), (145, (140, 140, None, None)),
    (146, (145, 140, 145, 140)), (161, (160, 160, 155, 140)),
    (166, (165, 160, 165, 160)), (170, (165, 160, 165, 160)),
])
def test_observed_session_schedule_keeps_selection_and_fit_epochs_separate(n, expected):
    result = schedule(n)
    assert tuple(result[k] for k in ('decision_index', 'selection_index', 'fit_index', 'fit_selection_index')) == expected
    assert result['covariance_start'] == result['decision_index'] - 20


@pytest.mark.parametrize('case', REFERENCE['cases'], ids=lambda c: c['name'])
def test_regime_and_adjusted_views_match_full_panel_frozen_functions(case):
    returns = base_returns()
    returns[-60:] += case['shift']
    info = regime(returns, len(returns))
    assert info['regime'] == case['regime']['regime']
    for key in ('vol_ratio', 'drawdown', 'equity_momentum'):
        assert info[key] == pytest.approx(case['regime'][key], abs=1e-13)
    active_ids = [ASSET_IDS[i] for i in REFERENCE['selected_indices']] + ['GOLD', 'VFF']
    p = np.zeros((5, 7))
    p[:, :5] = np.eye(5)
    initial = {'views_p': p.tolist(), 'views_q': [.0005, .0007, -.0003, .0012, .0001],
               'view_confidences': [.4, .5, .6, .7, .8]}
    actual = adjust_views(initial, info, active_ids)
    for key, ref in [('views_p', 'p'), ('views_q', 'q'), ('view_confidences', 'confidence')]:
        np.testing.assert_allclose(actual[key], case[ref], atol=1e-14, rtol=0)
    if info['regime'] != 'normal':
        assert actual['views_p'][-1][-2] == -1 / 6  # GOLD remains non-defensive.
        assert actual['views_p'][-1][-1] == 1
    changed = returns.copy()
    changed[160:] = -.99
    assert regime(changed, 160) == regime(returns, 160)


@pytest.mark.parametrize('case', REFERENCE['cases'], ids=lambda c: c['name'])
def test_active_bl_posterior_weights_and_constraints_match_frozen_suboptimizer(case):
    request = full_request(case)
    before = deepcopy(request)
    validate_numerical_inputs({k: v for k, v in request.items() if k not in {'strategy', 'constraints'}}, strategy='BL_ML')
    result = allocate(request)
    assert request == before
    assert result['asset_ids'] == list(ASSET_IDS)
    active = REFERENCE['selected_indices'] + [30, 31]
    inactive = [i for i in range(32) if i not in active]
    assert np.array(result['weights'])[inactive].tolist() == [0.] * 25
    np.testing.assert_allclose(result['weights'], case['weights'], atol=1e-7, rtol=0)
    diagnostics = result['diagnostics']
    assert diagnostics['active_asset_ids'] == request['active_asset_ids']
    assert diagnostics['covariance_regularization']['applied'] is True
    assert diagnostics['min_weight_threshold'] == .01
    np.testing.assert_allclose(diagnostics['posterior_mean_returns'], case['posterior'], atol=1e-12, rtol=0)
    assert sum(result['weights']) == pytest.approx(1, abs=1e-12)
    assert .3 - 1e-12 <= result['weights'][-1] <= .5 + 1e-12
    assert max(result['weights']) <= .5 + 1e-12


def test_subset_covariance_repair_and_posterior_ignore_inactive_block():
    request = full_request(REFERENCE['cases'][0])
    original = allocate(request)
    active = set(REFERENCE['selected_indices'] + [30, 31])
    covariance = np.array(request['covariance'])
    # Cross correlations must be sliced away before repair; only active covariance is used.
    inactive = [i for i in range(32) if i not in active]
    covariance[np.ix_(inactive, inactive)] = np.eye(25) * 1e7
    request['covariance'] = covariance.tolist()
    actual = allocate(request)
    assert actual['weights'] == original['weights']
    assert actual['diagnostics']['posterior_mean_returns'] == original['diagnostics']['posterior_mean_returns']


@pytest.mark.parametrize('change', [
    {'active_asset_ids': ['GOLD', 'VFF']},
    {'active_asset_ids': ['ACB', 'BID', 'CTG', 'DGC', 'BAD', 'GOLD', 'VFF']},
    {'active_asset_ids': ['CTG', 'ACB', 'BID', 'DGC', 'FPT', 'GOLD', 'VFF']},
    {'market_weights': [1 / 32] * 32},
    {'asset_ids': list(reversed(ASSET_IDS))},
])
def test_active_subset_validation_rejects_wrong_members_order_and_market_prior(change):
    request = full_request(REFERENCE['cases'][0]) | change
    with pytest.raises(CoreError):
        allocate(request)
    numerical = {k: v for k, v in request.items() if k not in {'strategy', 'constraints'}}
    with pytest.raises(CoreError):
        validate_numerical_inputs(numerical, strategy='BL_ML')


def test_policy_feasibility_is_checked_on_active_assets():
    request = full_request(REFERENCE['cases'][0])
    request['constraints']['max_position_weight'] = .1
    with pytest.raises(CoreError) as error:
        allocate(request)
    assert error.value.code == 'infeasible_constraints'


def test_threshold_matches_frozen_proportional_repair_and_fallback():
    from portfolio_core.allocator import _policy, _threshold_weights
    for case in REFERENCE['thresholds']:
        constraints = full_request(REFERENCE['cases'][0])['constraints'] | {'max_position_weight': case['max_weight']}
        case_policy = _policy(constraints, ['A', 'B', 'C', 'D', 'E', 'GOLD', 'VFF'])
        result = _threshold_weights(np.array(case['input']), case_policy)
        np.testing.assert_allclose(result, case['output'], atol=1e-13, rtol=0)
    # The cap repair redistributes onto the retained support without restoring a micro-position.
    assert _threshold_weights(np.array([.004, .496, .5]), _policy({
        'risk_aversion': 1., 'max_position_weight': .5, 'defensive_asset_ids': ['VFF'],
        'min_defensive_weight': .15, 'max_non_defensive_weight': .7,
    }, ['A', 'GOLD', 'VFF'])).tolist() == pytest.approx([0, .5, .5], abs=1e-13)


@pytest.mark.parametrize('value', [0, 20, True, 145.5])
def test_schedule_rejects_invalid_price_history(value):
    with pytest.raises(ValueError):
        schedule(value)


@pytest.mark.parametrize('value', [np.ones((2, 29)), np.ones((1, 30)), np.full((4, 30), np.nan), np.zeros((4, 30))])
def test_selector_rejects_invalid_price_panel(value):
    with pytest.raises(ValueError):
        select_equities(value)


def test_regime_rejects_invalid_panel_and_index():
    for value, t in [(np.zeros((30, 7)), 20), (np.full((30, 32), np.nan), 20), (np.zeros((30, 32)), 31)]:
        with pytest.raises(ValueError):
            regime(value, t)


def test_defensive_only_views_and_view_trust_boundaries():
    active = list(EQUITY_IDS[:5]) + ['GOLD', 'VFF']
    normal = adjust_views(None, {'regime': 'normal', 'vol_ratio': 1.}, active)
    assert normal == {'views_p': [], 'views_q': [], 'view_confidences': []}
    crisis = adjust_views(None, {'regime': 'crisis', 'vol_ratio': 2.}, active)
    assert crisis['view_confidences'] == [.8]  # Newly injected views bypass the dampener.
    assert crisis['views_q'] == [.1 / 252]
    for bad in [
        {'views_p': [[0.] * 7], 'views_q': [0.], 'view_confidences': [.5]},
        {'views_p': [[1.] * 6], 'views_q': [0.], 'view_confidences': [.5]},
        {'views_p': [[1.] * 7], 'views_q': [float('nan')], 'view_confidences': [.5]},
        {'views_p': [[1.] * 7], 'views_q': [0.], 'view_confidences': [1.1]},
    ]:
        with pytest.raises(ValueError):
            adjust_views(bad, {'regime': 'normal', 'vol_ratio': 1.}, active)


def test_core_rejects_views_on_inactive_equities_and_missing_model_views():
    request = full_request(REFERENCE['cases'][0])
    request['views_p'][0][0] = 1
    with pytest.raises(CoreError):
        allocate(request)
    request = full_request(REFERENCE['cases'][0])
    for key in ('views_p', 'views_q', 'view_confidences'):
        request.pop(key)
    with pytest.raises(CoreError) as error:
        allocate(request)
    assert error.value.code == 'missing_views'
