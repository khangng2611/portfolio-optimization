from copy import deepcopy

import numpy as np
import pytest

from portfolio_core import CoreError, allocate, validate_numerical_inputs
from portfolio_core.phase1_full import EQUITY_IDS, distance_matrix, select_equities
from portfolio_core.selection import (
    candidate_distance_matrix,
    select_candidate_equities,
)


@pytest.mark.parametrize("count", [0, 1, 5, 6, 30])
def test_k5_uses_only_candidate_equities_and_preserves_canonical_ties(count):
    ids = list(EQUITY_IDS[:count])
    assert select_candidate_equities(np.ones((40, count)), ids) == ids[:5]


def test_generic_selection_matches_frozen_full30_and_uses_supplied_endpoint():
    prices = 100 * np.cumprod(
        1 + np.random.default_rng(10).normal(0, 0.01, (150, 30)), axis=0
    )
    np.testing.assert_array_equal(
        candidate_distance_matrix(prices), distance_matrix(prices)
    )
    assert select_candidate_equities(prices, list(EQUITY_IDS)) == [
        EQUITY_IDS[i] for i in select_equities(prices)
    ]
    subset = [0, 2, 5, 8, 10, 18]
    cut = prices[:100, subset]
    expected = select_candidate_equities(cut, [EQUITY_IDS[i] for i in subset])
    prices[100:] *= 1e5
    assert (
        select_candidate_equities(prices[:100, subset], [EQUITY_IDS[i] for i in subset])
        == expected
    )


@pytest.mark.parametrize(
    "ids,prices",
    [
        (["FPT", "ACB"], np.ones((20, 2))),
        (["FPT", "GOLD"], np.ones((20, 2))),
        (["FPT", "FPT"], np.ones((20, 2))),
        (["BAD"], np.ones((20, 1))),
        (["FPT"], np.full((20, 1), np.nan)),
    ],
)
def test_generic_selector_rejects_invalid_ids_order_and_history(ids, prices):
    with pytest.raises(ValueError):
        select_candidate_equities(prices, ids)


def request(strategy="BL_ML"):
    candidates = list(EQUITY_IDS[:8]) + ["GOLD", "VFF"]
    active = (
        list(EQUITY_IDS[:5]) + ["GOLD", "VFF"] if strategy == "BL_ML" else candidates
    )
    p = [[float(a == "ACB") for a in candidates]]
    return dict(
        strategy=strategy,
        asset_ids=candidates,
        active_asset_ids=active,
        active_policy_version="user-selection-active-v1",
        mean_returns=[0.001] * len(candidates),
        covariance=(np.eye(len(candidates)) * 0.0001).tolist(),
        market_weights=[1 / len(active) if a in active else 0 for a in candidates],
        views_p=p,
        views_q=[0.002],
        view_confidences=[0.7],
        constraints=dict(
            risk_aversion=1.5,
            max_position_weight=0.5,
            defensive_asset_ids=["VFF"],
            min_defensive_weight=0.15,
            max_non_defensive_weight=0.7,
        ),
    )


def test_generic_active_allocation_maps_candidate_order_with_exact_inactive_zero():
    value = request()
    before = deepcopy(value)
    validate_numerical_inputs(
        {k: v for k, v in value.items() if k not in {"strategy", "constraints"}},
        strategy="BL_ML",
    )
    result = allocate(value)
    assert value == before
    assert result["asset_ids"] == value["asset_ids"]
    assert result["weights"][5:8] == [0.0, 0.0, 0.0]
    assert sum(result["weights"]) == pytest.approx(1, abs=1e-12)
    assert 0.3 - 1e-12 <= result["weights"][-1] <= 0.5 + 1e-12
    assert max(result["weights"]) <= 0.5 + 1e-12
    assert result["diagnostics"]["active_asset_ids"] == value["active_asset_ids"]


def test_small_candidate_sets_use_all_assets_and_policy_feasibility():
    value = request()
    value.update(
        asset_ids=["FPT", "VFF"],
        active_asset_ids=["FPT", "VFF"],
        mean_returns=[0.001, 0.0001],
        covariance=[[0.0001, 0], [0, 0.00001]],
        market_weights=[0.5, 0.5],
        views_p=[[1, 0]],
    )
    assert allocate(value)["weights"] == pytest.approx([0.5, 0.5], abs=1e-12)
    value["constraints"]["max_position_weight"] = 0.4
    with pytest.raises(CoreError):
        allocate(value)


@pytest.mark.parametrize("strategy", ["EW", "MVO"])
def test_ew_mvo_do_not_silently_use_k5(strategy):
    value = request(strategy)
    value["active_asset_ids"] = value["active_asset_ids"][:5] + ["GOLD", "VFF"]
    with pytest.raises(CoreError):
        allocate(value)


@pytest.mark.parametrize(
    "patch",
    [
        {"active_policy_version": "unknown"},
        {"active_asset_ids": ["BID", "ACB", "CTG", "DGC", "FPT", "GOLD", "VFF"]},
        {"active_asset_ids": ["ACB", "BID", "CTG", "DGC", "GOLD", "VFF"]},
        {"asset_ids": ["GOLD", "FPT", "VFF"]},
    ],
)
def test_invalid_active_candidate_contract_rejected(patch):
    with pytest.raises(CoreError):
        allocate(request() | patch)


def test_generic_opt_in_does_not_relax_legacy_full32_contract():
    value = request()
    value.pop("active_policy_version")
    with pytest.raises(CoreError):
        allocate(value)


def test_candidate_regime_is_candidate_only_and_matches_frozen_full_formula():
    from portfolio_core.selection import candidate_regime
    from portfolio_core.phase1_full import regime

    returns = np.random.default_rng(8).normal(0, 0.01, (150, 32))
    assert candidate_regime(returns, 150) == regime(returns, 150)
    subset = candidate_regime(returns[:, [4, 31]], 150)
    returns[:, 0] = -0.2
    assert candidate_regime(returns[:, [4, 31]], 150) == subset


def test_shared_custom_constraints_and_feasibility_keep_policy_bounds():
    from portfolio_core.selection import (
        effective_candidate_constraints,
        check_candidate_feasibility,
    )

    policy = request()["constraints"] | {
        "risk_aversion": 0.5,
        "max_position_weight": 0.8,
        "min_defensive_weight": 0.0,
        "max_non_defensive_weight": 1.0,
        "defensive_asset_ids": ["GOLD"],
    }
    effective = effective_candidate_constraints(policy, {"regime": "crisis"})
    assert effective == {
        "risk_aversion": 5.0,
        "max_position_weight": 0.5,
        "min_defensive_weight": 0.15,
        "max_non_defensive_weight": 0.7,
        "defensive_asset_ids": ["VFF"],
    }
    assert (
        check_candidate_feasibility(["FPT"], effective, "BL_ML")
        == "INSUFFICIENT_ASSETS"
    )
    assert (
        check_candidate_feasibility(["FPT", "GOLD"], effective, "MVO")
        == "DEFENSIVE_ASSET_REQUIRED"
    )
    assert check_candidate_feasibility(["FPT", "VFF"], effective, "MVO") is None
    assert (
        check_candidate_feasibility(
            ["FPT", "VFF"], effective | {"max_position_weight": 0.4}, "BL_ML"
        )
        == "CONSTRAINTS_INFEASIBLE"
    )
    assert (
        check_candidate_feasibility(list(EQUITY_IDS[:3]) + ["VFF"], effective, "EW")
        == "CONSTRAINTS_INFEASIBLE"
    )
    assert (
        check_candidate_feasibility(["FPT", "VFF"], None, "MVO")
        == "RISK_PROFILE_REQUIRED"
    )


def test_generic_covariance_repair_ignores_inactive_block_before_eigendecomposition():
    value = request()
    expected = allocate(value)
    sigma = np.array(value["covariance"])
    sigma[5:8, 5:8] = np.eye(3) * 1e8
    value["covariance"] = sigma.tolist()
    assert allocate(value)["weights"] == expected["weights"]
