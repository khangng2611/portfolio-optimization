"""The public data validator uses allocation tolerances without solving."""

import pytest

from portfolio_core import CoreError, validate_numerical_inputs


@pytest.mark.parametrize(
    "overrides",
    [
        {"mean_returns": [0.01]},
        {"mean_returns": [0.01, float("nan")]},
        {"covariance": [[1]]},
        {"covariance": [[1, 2], [2, 1]]},
    ],
)
def test_pure_validator_rejects_misaligned_nonfinite_and_non_psd_data(overrides):
    value = {
        "asset_ids": ["STOCK", "BOND"],
        "mean_returns": [0.01, 0.02],
        "covariance": [[1, 0], [0, 1]],
    } | overrides
    with pytest.raises(CoreError):
        validate_numerical_inputs(value)


def test_pure_validator_rejects_non_string_strategy_safely():
    with pytest.raises(CoreError):
        validate_numerical_inputs({}, strategy=["EW"])
