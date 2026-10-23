"""Portable numerical oracles: run unchanged against source or an installed wheel."""

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from portfolio_core import __version__, allocate


FIXTURES = Path(__file__).with_name("fixtures")
CASES = [
    "ew_three_assets",
    "mvo_daily_interior",
    "mvo_binding_group_and_cap",
    "bl_absolute_view",
    "bl_relative_correlated_view",
]


@pytest.fixture(params=CASES)
def golden_case(request):
    return FIXTURES / f"{request.param}.json"


def load_case(path):
    assert path.is_file(), f"Missing numerical golden fixture: {path.name}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_allocation_matches_independently_derived_golden_numbers(golden_case):
    # Catches changed objective/risk covariance, confidence semantics or asset order.
    golden_case = load_case(golden_case)
    result = allocate(golden_case["request"])
    expected = golden_case["expected"]
    tolerances = golden_case["tolerances"]
    assert result["weights"] == pytest.approx(
        expected["weights"], abs=tolerances["weights_absolute"], rel=0
    )
    assert result["diagnostics"]["objective"] == pytest.approx(
        expected["objective"], abs=tolerances["objective_absolute"], rel=0
    )
    assert result["strategy"] == golden_case["request"]["strategy"]
    assert result["asset_ids"] == golden_case["request"]["asset_ids"]
    assert result["status"] == "optimal"
    assert result["core_version"] == __version__
    diagnostics = result["diagnostics"]
    assert diagnostics["return_units"] == "daily"
    assert diagnostics["solver"] == expected["solver"]
    assert diagnostics["solver_status"] == expected["solver_status"]
    if "posterior_mean_returns" in expected:
        for field in (
            "prior_implied_returns", "posterior_mean_returns", "posterior_mean_covariance"
        ):
            np.testing.assert_allclose(
                diagnostics[field], expected[field],
                atol=tolerances["posterior_absolute"], rtol=0,
            )
        assert diagnostics["effective_view_confidences"] == expected["effective_view_confidences"]
        assert diagnostics["view_count"] == len(golden_case["request"]["views_q"])


def test_golden_output_satisfies_constraints_independently_of_diagnostics(golden_case):
    # Catches unchecked post-solver redistribution and misleading residual reports.
    golden_case = load_case(golden_case)
    inputs = golden_case["request"]
    result = allocate(inputs)
    weights = result["weights"]
    policy = inputs["constraints"]
    defensive = set(policy["defensive_asset_ids"])
    defensive_weight = sum(
        weight for asset, weight in zip(inputs["asset_ids"], weights) if asset in defensive
    )
    non_defensive_weight = sum(
        weight for asset, weight in zip(inputs["asset_ids"], weights) if asset not in defensive
    )
    residuals = {
        "budget": abs(sum(weights) - 1.0),
        "long_only": max(0.0, -min(weights)),
        "max_position_weight": max(0.0, max(weights) - policy["max_position_weight"]),
        "min_defensive_weight": max(0.0, policy["min_defensive_weight"] - defensive_weight),
        "max_non_defensive_weight": max(0.0, non_defensive_weight - policy["max_non_defensive_weight"]),
    }
    tolerance = golden_case["tolerances"]["constraint_absolute"]
    assert all(np.isfinite(weights))
    assert max(residuals.values()) <= tolerance
    assert result["diagnostics"]["constraint_residuals"] == pytest.approx(
        residuals, abs=tolerance, rel=0
    )


def test_repeated_golden_request_is_deterministic_and_does_not_mutate_input(golden_case):
    # Catches shared mutable policy/input arrays and nondeterministic solver output.
    golden_case = load_case(golden_case)
    inputs = golden_case["request"]
    before = deepcopy(inputs)
    serialized = [
        json.dumps(allocate(inputs), sort_keys=True, allow_nan=False) for _ in range(3)
    ]
    assert serialized[0] == serialized[1] == serialized[2]
    assert inputs == before
