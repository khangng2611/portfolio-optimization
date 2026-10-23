# portfolio-core

Installable, deterministic numerical package for explicit-input portfolio allocation.
It has no imports from the research repository, no market-data access, no training,
and no environment-based or mutable global policy. Each call owns its arrays and
solver problem. Dependency versions are pinned in `pyproject.toml`.

## Install and call

```sh
python -m pip install ./packages/portfolio-core
```

```python
from portfolio_core import CoreError, allocate

request = {
    "strategy": "MVO",
    "asset_ids": ["STOCK", "BOND"],
    "mean_returns": [0.0008, 0.0002],
    "covariance": [[0.0004, 0.0], [0.0, 0.0001]],
    "constraints": {
        "risk_aversion": 1.0,
        "max_position_weight": 0.8,
        "defensive_asset_ids": ["BOND"],
        "min_defensive_weight": 0.2,
        "max_non_defensive_weight": 0.8,
    },
}
try:
    result = allocate(request)
except CoreError as error:
    failure = error.to_dict()  # {"code": ..., "message": ..., "details": {...}}
```

The public API is `allocate(request: dict) -> dict`. Input data use JSON-compatible
lists and finite numbers. Asset identifiers are unique, nonempty strings without
leading or trailing whitespace. Asset order applies to all vectors, covariance
axes, view columns, and returned weights. Defensive identifiers must be a subset
of that universe. Unknown fields, numeric strings, booleans used as numbers,
missing policy fields, and incompatible shapes are rejected.

All means and view returns must be **daily simple returns**; covariance is the
corresponding daily-return covariance. The package never annualizes or otherwise
converts units. The caller is responsible for supplying compatible data, cutoff,
universe and model provenance; the numerical interface cannot infer units from
numbers or verify that a view was produced by an approved model.

## Strategies

| Strategy | Behavior and required inputs |
| --- | --- |
| `EW` | Exactly `1 / n` for every asset. Raises `infeasible_constraints` if those equal weights violate any policy, even if a different feasible allocation exists. |
| `MVO` | Maximizes `mu @ w - risk_aversion * (w @ Sigma @ w)` using the supplied mean returns and regularized covariance. |
| `BL_ML` | Computes a Black–Litterman posterior from explicit prepared views, then applies the same constrained MVO objective using posterior means and the original regularized return covariance. No ML inference or training occurs here. |

Every strategy requires `mean_returns`, `covariance`, and all five constraint
fields. `BL_ML` additionally requires nonnegative, unit-sum `market_weights` and
nonempty `views_p` (`k × n`), `views_q` (`k`), and `view_confidences` (`k`). Each view
must have at least one nonzero coefficient. Confidence must be in `[0, 1]`.
Optional `tau` and `delta` default to `0.05` and `2.5` and must be positive.
Any optional numerical inputs supplied to another strategy are still validated.

Black–Litterman uses the existing research posterior convention:

```text
pi = delta * Sigma @ market_weights
A = tau * Sigma
Omega = diag(max(diag(P @ A @ P.T), 1e-10) / max(confidences, 1e-6))
posterior_mu = pi + A @ P.T @ solve(P @ A @ P.T + Omega, Q - P @ pi)
posterior_mean_covariance = A - A @ P.T @ solve(P @ A @ P.T + Omega, P @ A)
```

The floors in this formula preserve the legacy confidence convention: zero
confidence has very small influence, and confidence one is not a hard equality
view. Diagnostics report effective confidence values. The reported posterior
mean covariance describes uncertainty of the mean; it is **not** a posterior
predictive return covariance and is not substituted into the allocation risk
term.

## Constraints, covariance, and solver behavior

All portfolios are long-only, fully invested, and constrained by:

```text
0 <= w[i] <= max_position_weight
sum(w) = 1
sum(w[defensive_asset_ids]) >= min_defensive_weight
sum(w[other assets]) <= max_non_defensive_weight
```

Risk aversion must be positive, the position cap must be in `(0, 1]`, and both
group limits must be in `[0, 1]`. Empty groups still have zero weight; their
constraints are never silently ignored. Capacity checks reject infeasible
combinations before optimization.

Covariance must be finite, symmetric within `rtol=1e-8, atol=1e-12`, and positive
semidefinite. Negative diagonal variances are rejected. Eigenvalues below
`-max(1e-12, 1e-8 * max(abs(eigenvalues), 1e-8))` are rejected; numerical drift
within that bound may be regularized. Eigenvalues are floored at `1e-8`, matching
the legacy numerical floor. Diagnostics report the original minimum eigenvalue
and the largest adjustment. Nonfinite data and materially indefinite covariance
are never sanitized into success.

MVO uses the pinned CLARABEL solver through CVXPY, with explicit tolerances and a
positive scaling of its objective for conditioning. Only an `optimal` solver
status is accepted. There is no fallback to equal weights or an unchecked
allocation. Raw feasibility violations above `1e-8` fail. Smaller floating point
drift is projected onto capped group simplices; adjustments above `1e-7` fail.
All returned weights are checked again with maximum permitted residual `1e-12`.
No minimum-position threshold or proportional redistribution is applied.

The same request and pinned runtime produce repeatable results without shared
policy state. Floating point values may vary slightly across CPU/BLAS/platform
versions; bitwise reproducibility across platforms is not promised.

## Result and failures

Successful output has these fields:

```text
strategy, asset_ids, weights, status="optimal", core_version, diagnostics
```

`weights` is an ordered list, not a map. Diagnostics include the objective in the
supplied daily units, covariance regularization, solver status, and nonnegative
constraint residuals for budget, long-only, position, and both group limits.
Solver allocations include raw residuals and maximum feasibility adjustment.
EW reports `solver=null`, `solver_status="not_run"`. BL also reports posterior
means, posterior mean covariance, prior implied returns and view metadata.

`CoreError` inherits `ValueError` and exposes `.code`, `.message`, `.details` and
`.to_dict()`. Machine-readable codes are:

| Code | Meaning |
| --- | --- |
| `invalid_input` | Invalid shape, value, asset list, policy or missing required input. |
| `invalid_covariance` | Material asymmetry, negative variance or indefinite covariance. |
| `unsupported_strategy` | Any strategy outside `EW`, `MVO`, `BL_ML`. |
| `missing_views` | Empty or incomplete prepared BL views. |
| `infeasible_constraints` | No feasible allocation, or equal weights violate an EW policy. |
| `solver_failure` | Solver did not establish an optimal, feasible result. |
| `numerical_failure` | Overflow, failed linear algebra or nonfinite numerical output. |

## Verification and legacy parity limits

```sh
python -m pip install './packages/portfolio-core[test]'
python -m pytest packages/portfolio-core/tests
python -m build --wheel packages/portfolio-core
```

Tests include independently derived two-asset MVO and daily-unit BL values,
final caps/group limits, preservation of small valid positions, invalid and
infeasible inputs, singular PSD covariance, exact capacity boundaries, concurrent
policies and caller-input immutability. When the research source is present, a
test evaluates the actual legacy posterior and regularizer function bodies on
the same explicit inputs; it does not import or modify repository configuration.

This establishes **posterior formula parity for the tested explicit numerical
inputs only**. It does not establish full `ranking_absolute`, backtest, selected
universe, data processing, view generation, trained-model, regime, rebalancing or
performance-metric parity. `BL_ML` means optimization from supplied prepared
views; it does not certify live inference. HYBRID and other legacy modes are
unsupported. The new solver path intentionally differs from legacy fallback,
clipping, threshold and redistribution behavior so that returned allocations
retain their constraints. A wheel can be imported and used outside the research
repository with only its declared runtime dependencies.
