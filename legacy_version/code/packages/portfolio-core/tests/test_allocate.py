"""Numerical and wire-contract tests with independently derived expectations."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


def request(strategy="MVO"):
    return {
        "strategy": strategy,
        "asset_ids": ["STOCK", "BOND"],
        "mean_returns": [0.08, 0.02],
        "covariance": [[0.04, 0.0], [0.0, 0.01]],
        "constraints": {
            "risk_aversion": 1.0,
            "max_position_weight": 1.0,
            "defensive_asset_ids": ["BOND"],
            "min_defensive_weight": 0.0,
            "max_non_defensive_weight": 1.0,
        },
    }


def bl_request():
    value = request("BL_ML")
    value.update(
        mean_returns=[0.001, 0.0002],
        covariance=[[0.0004, 0.0], [0.0, 0.0001]],
        market_weights=[0.5, 0.5],
        views_p=[[1.0, 0.0]],
        views_q=[0.002],
        view_confidences=[1.0],
        tau=0.05,
        delta=2.5,
    )
    return value


@pytest.fixture
def api():
    return importlib.import_module("portfolio_core")


def test_package_exists():
    assert importlib.util.find_spec("portfolio_core") is not None


def test_mvo_matches_hand_derived_two_asset_optimum(api):
    # f(x)=.02+.06x-[.04x^2+.01(1-x)^2], f'(x)=.08-.1x.
    result = api.allocate(request())
    assert result["weights"] == pytest.approx([0.8, 0.2], abs=1e-7)
    assert result["asset_ids"] == ["STOCK", "BOND"]
    assert result["status"] == "optimal"
    assert result["core_version"] == api.__version__
    assert result["diagnostics"]["objective"] == pytest.approx(0.042, abs=1e-9)
    assert max(result["diagnostics"]["constraint_residuals"].values()) <= 1e-8
    json.dumps(result, allow_nan=False)


def test_final_weights_respect_position_and_both_group_limits(api):
    value = request()
    value["constraints"].update(
        max_position_weight=0.7,
        min_defensive_weight=0.4,
        max_non_defensive_weight=0.55,
    )
    result = api.allocate(value)
    assert result["weights"] == pytest.approx([0.55, 0.45], abs=1e-7)
    assert max(result["weights"]) <= 0.7
    assert result["weights"][0] <= 0.55 + 1e-14
    assert sum(result["weights"]) == pytest.approx(1.0, abs=1e-14)


def test_small_positions_are_preserved_without_cap_breaking_redistribution(api):
    value = request()
    # f'(x)=.0795+.02-.1x gives x=.995; .5% bond must survive.
    value["mean_returns"] = [0.0995, 0.02]
    value["constraints"]["max_position_weight"] = 0.996
    weights = api.allocate(value)["weights"]
    assert weights == pytest.approx([0.995, 0.005], abs=2e-7)


def test_equal_weight_requires_feasible_equal_weights(api):
    value = request("EW")
    assert api.allocate(value)["weights"] == [0.5, 0.5]
    value["constraints"]["min_defensive_weight"] = 0.7
    with pytest.raises(api.CoreError) as caught:
        api.allocate(value)
    assert caught.value.code == "infeasible_constraints"


def test_bl_daily_units_match_hand_derived_posterior(api):
    # pi=(.0005,.000125); a unit-confidence absolute first-asset view
    # averages prior and view (.002), leaving second asset unchanged.
    result = api.allocate(bl_request())
    assert result["diagnostics"]["posterior_mean_returns"] == pytest.approx(
        [0.00125, 0.000125], abs=1e-13
    )
    # Posterior mean uncertainty: tau*Sigma diagonal, halved for first view.
    np.testing.assert_allclose(
        result["diagnostics"]["posterior_mean_covariance"],
        [[0.00001, 0.0], [0.0, 0.000005]],
        atol=1e-14,
    )
    assert result["diagnostics"]["return_units"] == "daily"
    assert result["diagnostics"]["view_count"] == 1


def test_bl_matches_legacy_posterior_on_explicit_identical_daily_inputs(api):
    root = Path(__file__).resolve().parents[3]
    legacy_path = root / "backtest" / "_black_litterman.py"
    if not legacy_path.is_file():
        pytest.skip("Legacy source is not included in the installed package")
    # Load the actual legacy calculation with its dependencies supplied locally:
    # repo config is not imported or mutated by this package or the test.
    import ast

    optimizer_path = root / "backtest" / "_optimizer.py"
    optimizer_tree = ast.parse(optimizer_path.read_text())
    regularizer_only = ast.Module(
        body=[node for node in optimizer_tree.body if isinstance(node, ast.FunctionDef) and node.name == "_regularize_covariance"],
        type_ignores=[],
    )
    scope = {"np": np, "BL_TAU": 0.05, "BL_DELTA": 2.5}
    exec(compile(regularizer_only, str(optimizer_path), "exec"), scope)
    tree = ast.parse(legacy_path.read_text())
    functions_only = ast.Module(
        body=[node for node in tree.body if isinstance(node, ast.FunctionDef)],
        type_ignores=[],
    )
    exec(compile(functions_only, str(legacy_path), "exec"), scope)
    value = bl_request()
    value.update(
        covariance=[[0.0004, 0.00006], [0.00006, 0.0001]],
        views_p=[[1.0, -1.0], [0.0, 1.0]],
        views_q=[0.0008, 0.0002],
        view_confidences=[0.7, 0.3],
        market_weights=[0.6, 0.4],
    )
    expected = scope["black_litterman_posterior_mu"](
        value["covariance"], value["market_weights"], value["views_p"],
        value["views_q"], value["view_confidences"], value["tau"], value["delta"],
    )
    np.testing.assert_allclose(api.allocate(value)["diagnostics"]["posterior_mean_returns"], expected, rtol=1e-12, atol=1e-14)


def test_singular_psd_covariance_is_regularized_and_reported(api):
    value = request()
    value["covariance"] = [[0.01, 0.01], [0.01, 0.01]]
    result = api.allocate(value)
    assert result["diagnostics"]["covariance_regularization"]["applied"] is True
    assert all(np.isfinite(result["weights"]))


@pytest.mark.parametrize("changes,code", [
    ({"strategy": "HYBRID"}, "unsupported_strategy"),
    ({"asset_ids": []}, "invalid_input"),
    ({"asset_ids": ["A", "A"]}, "invalid_input"),
    ({"asset_ids": ["A", " "]}, "invalid_input"),
    ({"mean_returns": [0.01]}, "invalid_input"),
    ({"mean_returns": [float("nan"), 0.01]}, "invalid_input"),
    ({"mean_returns": [True, 0.01]}, "invalid_input"),
    ({"mean_returns": ["0.01", 0.01]}, "invalid_input"),
    ({"covariance": [[0.01, 0.0]]}, "invalid_input"),
    ({"covariance": [[0.01], [0.0, 0.01]]}, "invalid_input"),
    ({"covariance": [[0.01, 0.002], [0.0, 0.01]]}, "invalid_covariance"),
    ({"covariance": [[0.01, 0.02], [0.02, 0.01]]}, "invalid_covariance"),
    ({"covariance": [[float("inf"), 0.0], [0.0, 0.01]]}, "invalid_input"),
    ({"market_weights": [0.4, 0.4]}, "invalid_input"),
    ({"tau": 0.0}, "invalid_input"),
    ({"delta": -1.0}, "invalid_input"),
])
def test_invalid_inputs_fail_explicitly(api, changes, code):
    value = request()
    value.update(changes)
    with pytest.raises(api.CoreError) as caught:
        api.allocate(value)
    assert caught.value.code == code
    assert caught.value.message
    assert caught.value.to_dict() == {
        "code": code, "message": caught.value.message, "details": caught.value.details,
    }
    json.dumps(caught.value.to_dict(), allow_nan=False)


@pytest.mark.parametrize("constraints,code", [
    ({"max_position_weight": 0.4}, "infeasible_constraints"),
    ({"min_defensive_weight": 0.9, "max_position_weight": 0.6}, "infeasible_constraints"),
    ({"defensive_asset_ids": [], "min_defensive_weight": 0.1}, "infeasible_constraints"),
    ({"defensive_asset_ids": [], "max_non_defensive_weight": 0.8}, "infeasible_constraints"),
    ({"defensive_asset_ids": ["UNKNOWN"]}, "invalid_input"),
    ({"defensive_asset_ids": ["BOND", "BOND"]}, "invalid_input"),
    ({"risk_aversion": float("nan")}, "invalid_input"),
    ({"risk_aversion": 0.0}, "invalid_input"),
    ({"max_position_weight": 1.1}, "invalid_input"),
    ({"max_non_defensive_weight": -0.1}, "invalid_input"),
])
def test_bad_or_infeasible_policy_never_falls_back_to_success(api, constraints, code):
    value = request()
    value["constraints"].update(constraints)
    with pytest.raises(api.CoreError) as caught:
        api.allocate(value)
    assert caught.value.code == code


@pytest.mark.parametrize("field,value", [
    ("market_weights", None), ("views_p", None), ("views_q", None),
    ("view_confidences", None), ("views_p", []), ("views_p", [[0.0, 0.0]]),
    ("views_p", [[1.0]]), ("views_q", [0.01, 0.02]),
    ("view_confidences", [1.1]), ("view_confidences", [-0.1]),
])
def test_bl_missing_or_invalid_views_fail_closed(api, field, value):
    inputs = bl_request()
    inputs[field] = value
    with pytest.raises(api.CoreError) as caught:
        api.allocate(inputs)
    assert caught.value.code in {"missing_views", "invalid_input"}


def test_parallel_policies_and_input_objects_are_isolated(api):
    permissive = request()
    defensive = request()
    defensive["constraints"]["min_defensive_weight"] = 0.7
    snapshots = [deepcopy(permissive), deepcopy(defensive)]
    values = [permissive, defensive] * 10
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(api.allocate, values))
    for i, result in enumerate(results):
        expected = [0.8, 0.2] if i % 2 == 0 else [0.3, 0.7]
        assert result["weights"] == pytest.approx(expected, abs=1e-7)
    assert [permissive, defensive] == snapshots


@pytest.mark.parametrize("defensive", [[], ["STOCK", "BOND"]])
def test_empty_or_full_defensive_group_has_feasible_budget(api, defensive):
    value = request()
    value["constraints"]["defensive_asset_ids"] = defensive
    assert api.allocate(value)["weights"] == pytest.approx([0.8, 0.2], abs=1e-7)


def test_exactly_funded_position_caps_remain_feasible(api):
    value = request()
    value.update(
        asset_ids=["STOCK", "BOND", "GOLD"],
        mean_returns=[0.08, 0.02, 0.01],
        covariance=[[0.04, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 0.03]],
    )
    value["constraints"]["max_position_weight"] = 1 / 3
    weights = api.allocate(value)["weights"]
    assert weights == pytest.approx([1 / 3] * 3, abs=1e-14)
    assert max(weights) <= 1 / 3


@pytest.mark.parametrize("bad", [None, [], "MVO", 3])
def test_nonobject_wire_input_is_structured_error(api, bad):
    with pytest.raises(api.CoreError) as caught:
        api.allocate(bad)
    assert caught.value.code == "invalid_input"


def test_unknown_fields_and_incomplete_policy_are_rejected(api):
    value = request()
    value["max_weight"] = 0.5
    with pytest.raises(api.CoreError) as caught:
        api.allocate(value)
    assert caught.value.code == "invalid_input"
    value = request()
    del value["constraints"]["risk_aversion"]
    with pytest.raises(api.CoreError) as caught:
        api.allocate(value)
    assert caught.value.code == "invalid_input"


def test_finite_but_overflowing_inputs_fail_as_structured_numerical_error(api):
    value = bl_request()
    value["delta"] = 1e308
    value["covariance"] = [[1e100, 0.0], [0.0, 1e100]]
    with pytest.raises(api.CoreError) as caught:
        api.allocate(value)
    assert caught.value.code == "numerical_failure"
