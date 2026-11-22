"""Stateless allocation from validated, ordered, daily-return arrays."""

from dataclasses import dataclass
from numbers import Real

import cvxpy as cp
import numpy as np

from .errors import CoreError
from .phase1_full import validate_active_assets
from .version import __version__


@dataclass(frozen=True)
class Policy:
    risk_aversion: float
    cap: float
    defensive: np.ndarray
    non_defensive: np.ndarray
    min_defensive: float
    max_non_defensive: float
    lower_defensive: float
    upper_defensive: float


def _invalid(field: str, message: str) -> CoreError:
    return CoreError("invalid_input", message, {"field": field})


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise _invalid(field, f"{field} must be a finite number")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise _invalid(field, f"{field} must be a finite number") from None
    if not np.isfinite(result):
        raise _invalid(field, f"{field} must be a finite number")
    return result


def _fraction(value, field: str, positive=False) -> float:
    result = _number(value, field)
    if result < 0 or result > 1 or (positive and result == 0):
        raise _invalid(field, f"{field} must be in {'(0, 1]' if positive else '[0, 1]'}")
    return result


def _positive(value, field: str) -> float:
    result = _number(value, field)
    if result <= 0:
        raise _invalid(field, f"{field} must be positive")
    return result


def _vector(value, size: int, field: str) -> np.ndarray:
    if not isinstance(value, list) or len(value) != size:
        raise _invalid(field, f"{field} must be a list of length {size}")
    return np.array([_number(item, field) for item in value], dtype=float)


def _matrix(value, rows: int, cols: int, field: str) -> np.ndarray:
    if not isinstance(value, list) or len(value) != rows:
        raise _invalid(field, f"{field} must have shape ({rows}, {cols})")
    return np.array([_vector(row, cols, field) for row in value], dtype=float)


def _asset_ids(value, field: str, allow_empty=False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise _invalid(field, f"{field} must be a list of asset identifiers")
    if any(not isinstance(item, str) or not item or item.strip() != item for item in value):
        raise _invalid(field, f"{field} must contain nonempty, trimmed strings")
    if len(set(value)) != len(value):
        raise _invalid(field, f"{field} must contain unique identifiers")
    return value.copy()


def _policy(value, assets: list[str]) -> Policy:
    fields = {"risk_aversion", "max_position_weight", "defensive_asset_ids",
              "min_defensive_weight", "max_non_defensive_weight"}
    if not isinstance(value, dict) or set(value) != fields:
        raise _invalid("constraints", "constraints must contain exactly the five documented policy fields")
    risk = _positive(value["risk_aversion"], "risk_aversion")
    cap = _fraction(value["max_position_weight"], "max_position_weight", positive=True)
    minimum = _fraction(value["min_defensive_weight"], "min_defensive_weight")
    maximum = _fraction(value["max_non_defensive_weight"], "max_non_defensive_weight")
    defensive_ids = _asset_ids(value["defensive_asset_ids"], "defensive_asset_ids", allow_empty=True)
    if not set(defensive_ids) <= set(assets):
        raise _invalid("defensive_asset_ids", "All defensive identifiers must exist in asset_ids")
    defensive = np.array([i for i, asset in enumerate(assets) if asset in defensive_ids], dtype=int)
    non_defensive = np.array([i for i, asset in enumerate(assets) if asset not in defensive_ids], dtype=int)
    lower = max(minimum, 1.0 - maximum, 1.0 - len(non_defensive) * cap, 0.0)
    upper = min(1.0, len(defensive) * cap)
    if len(assets) * cap < 1.0 - 1e-14 or lower > upper + 1e-14:
        raise CoreError("infeasible_constraints", "The position and group limits cannot fund a fully invested portfolio")
    # Resolve only round-off at coincident bounds, never relax actual policy.
    lower = min(lower, upper)
    return Policy(risk, cap, defensive, non_defensive, minimum, maximum, lower, upper)


def _covariance(value, size: int, active=None) -> tuple[np.ndarray, dict]:
    sigma = _matrix(value, size, size, "covariance")
    if active is not None:
        sigma = sigma[np.ix_(active, active)]
    if not np.allclose(sigma, sigma.T, rtol=1e-8, atol=1e-12):
        raise CoreError("invalid_covariance", "covariance must be symmetric")
    if np.any(np.diag(sigma) < 0):
        raise CoreError("invalid_covariance", "covariance cannot contain negative variances")
    symmetric = sigma / 2 + sigma.T / 2
    values, vectors = np.linalg.eigh(symmetric)
    scale = max(float(np.max(np.abs(values))), 1e-8)
    if float(values[0]) < -max(1e-12, scale * 1e-8):
        raise CoreError("invalid_covariance", "covariance must be positive semidefinite")
    floor = 1e-8
    regularized = vectors @ np.diag(np.maximum(values, floor)) @ vectors.T
    regularized = regularized / 2 + regularized.T / 2
    return regularized, {
        "applied": bool(np.any(values < floor)),
        "eigenvalue_floor": floor,
        "minimum_original_eigenvalue": float(values[0]),
        "maximum_eigenvalue_adjustment": float(max(0.0, floor - values[0])),
    }


def _views(request: dict, size: int, required: bool):
    fields = ("views_p", "views_q", "view_confidences")
    present = [request.get(field) is not None for field in fields]
    if not any(present) and not required:
        return None
    if not all(present) or not isinstance(request.get("views_p"), list) or not request["views_p"]:
        raise CoreError("missing_views", "BL_ML requires nonempty views_p, views_q, and view_confidences")
    count = len(request["views_p"])
    p = _matrix(request["views_p"], count, size, "views_p")
    q = _vector(request["views_q"], count, "views_q")
    confidence = _vector(request["view_confidences"], count, "view_confidences")
    if np.any(np.all(p == 0, axis=1)):
        raise _invalid("views_p", "Every view must involve at least one asset")
    if np.any(confidence < 0) or np.any(confidence > 1):
        raise _invalid("view_confidences", "View confidences must be in [0, 1]")
    return p, q, confidence


def _posterior(sigma, market, views, tau, delta) -> tuple[np.ndarray, dict]:
    p, q, confidence = views
    prior_covariance = tau * sigma
    pi = delta * sigma @ market
    # Exactly the legacy confidence convention, including its numeric floors.
    omega = np.maximum(np.diag(p @ prior_covariance @ p.T), 1e-10) / np.maximum(confidence, 1e-6)
    cross = prior_covariance @ p.T
    view_covariance = p @ cross + np.diag(omega)
    mu = pi + cross @ np.linalg.solve(view_covariance, q - p @ pi)
    posterior_covariance = prior_covariance - cross @ np.linalg.solve(view_covariance, cross.T)
    if not np.isfinite(mu).all() or not np.isfinite(posterior_covariance).all():
        raise CoreError("numerical_failure", "Black–Litterman posterior is not finite")
    return mu, {
        "posterior_mean_returns": mu.tolist(),
        "posterior_mean_covariance": posterior_covariance.tolist(),
        "prior_implied_returns": pi.tolist(),
        "view_count": len(q),
        "effective_view_confidences": np.maximum(confidence, 1e-6).tolist(),
        "tau": tau,
        "delta": delta,
    }


def _residuals(weights: np.ndarray, policy: Policy) -> dict[str, float]:
    return {
        "budget": float(abs(weights.sum() - 1.0)),
        "long_only": float(max(0.0, -weights.min())),
        "max_position_weight": float(max(0.0, weights.max() - policy.cap)),
        "min_defensive_weight": float(max(0.0, policy.min_defensive - weights[policy.defensive].sum())),
        "max_non_defensive_weight": float(max(0.0, weights[policy.non_defensive].sum() - policy.max_non_defensive)),
    }


def _project_group(values: np.ndarray, total: float, cap: float) -> np.ndarray:
    """Project solver round-off onto a capped simplex with fixed group mass."""
    if not len(values):
        return values.copy()
    low, high = float(values.min() - cap), float(values.max())
    for _ in range(100):
        midpoint = (low + high) / 2
        if np.clip(values - midpoint, 0, cap).sum() > total:
            low = midpoint
        else:
            high = midpoint
    result = np.clip(values - (low + high) / 2, 0, cap)
    # Final floating point residue is placed only where the cap permits it.
    residue = total - float(result.sum())
    for index in range(len(result)):
        change = min(residue, cap - result[index]) if residue > 0 else max(residue, -result[index])
        result[index] += change
        residue -= change
    return result


def _optimize(mu: np.ndarray, sigma: np.ndarray, policy: Policy) -> tuple[np.ndarray, dict]:
    weights = cp.Variable(len(mu))
    # Positive objective scaling improves daily-unit conditioning without
    # changing the optimizer or the documented risk-aversion convention.
    scale = max(float(np.max(np.abs(mu))), float(np.max(np.abs(sigma))) * policy.risk_aversion, 1e-12)
    utility = (mu / scale) @ weights - cp.quad_form(weights, cp.psd_wrap(sigma * (policy.risk_aversion / scale)))
    constraints = [cp.sum(weights) == 1, weights >= 0, weights <= policy.cap]
    if len(policy.defensive):
        constraints.append(cp.sum(weights[policy.defensive]) >= policy.min_defensive)
    if len(policy.non_defensive):
        constraints.append(cp.sum(weights[policy.non_defensive]) <= policy.max_non_defensive)
    problem = cp.Problem(cp.Maximize(utility), constraints)
    try:
        problem.solve(solver="CLARABEL", tol_gap_abs=1e-11, tol_gap_rel=1e-11, tol_feas=1e-11, max_iter=500)
    except cp.error.SolverError:
        raise CoreError("solver_failure", "The configured numerical solver could not solve this request") from None
    if problem.status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
        raise CoreError("infeasible_constraints", "The numerical solver found no feasible allocation")
    if problem.status != cp.OPTIMAL or weights.value is None:
        raise CoreError("solver_failure", "The solver did not establish an optimal allocation", {"solver_status": str(problem.status)})
    raw = np.asarray(weights.value, dtype=float)
    if not np.isfinite(raw).all():
        raise CoreError("numerical_failure", "The solver returned nonfinite weights")
    raw_residuals = _residuals(raw, policy)
    if max(raw_residuals.values()) > 1e-8:
        raise CoreError("solver_failure", "The solver returned weights outside the feasibility tolerance", {"constraint_residuals": raw_residuals})
    defensive_total = float(np.clip(raw[policy.defensive].sum(), policy.lower_defensive, policy.upper_defensive))
    result = raw.copy()
    result[policy.defensive] = _project_group(raw[policy.defensive], defensive_total, policy.cap)
    result[policy.non_defensive] = _project_group(raw[policy.non_defensive], 1.0 - defensive_total, policy.cap)
    adjustment = float(np.max(np.abs(result - raw)))
    if adjustment > 1e-7:
        raise CoreError("solver_failure", "Numerical correction would materially change the optimizer result")
    return result, {
        "solver": "CLARABEL",
        "solver_status": str(problem.status),
        "raw_constraint_residuals": raw_residuals,
        "maximum_feasibility_adjustment": adjustment,
    }


def _active_indices(request, assets, strategy):
    if "active_policy_version" in request:
        if request["active_policy_version"] != "user-selection-active-v1":
            raise _invalid("active_policy_version", "Unsupported active policy version")
        from .assets import canonical_candidates
        from .phase1_full import EQUITY_IDS

        try:
            canonical = canonical_candidates(assets)
        except ValueError as error:
            raise _invalid("asset_ids", str(error)) from None
        if assets != canonical or len(assets) < 2:
            raise _invalid("asset_ids", "At least two candidates in canonical order are required")
        active = _asset_ids(request.get("active_asset_ids"), "active_asset_ids")
        if (not set(active) <= set(assets)
                or active != [a for a in assets if a in active]):
            raise _invalid("active_asset_ids", "Active assets must preserve candidate membership and order")
        if strategy in {"EW", "MVO"}:
            if active != assets:
                raise _invalid("active_asset_ids", "EW and MVO must use all candidates")
        else:
            equities = [a for a in assets if a in EQUITY_IDS]
            if (sum(a in EQUITY_IDS for a in active) != min(5, len(equities))
                    or [a for a in active if a not in EQUITY_IDS] != [a for a in assets if a not in EQUITY_IDS]):
                raise _invalid("active_asset_ids", "BL_ML requires up to five candidate equities and every chosen alternative")
        return [assets.index(a) for a in active]
    if "active_asset_ids" not in request:
        return None
    try:
        return validate_active_assets(assets, request["active_asset_ids"])
    except ValueError as error:
        raise _invalid("active_asset_ids", str(error)) from None


def _active_market(market, indices):
    if indices is not None:
        expected = np.zeros(len(market))
        expected[indices] = 1.0 / len(indices)
        if not np.allclose(market, expected, rtol=0, atol=1e-12):
            raise _invalid("market_weights", "Active-universe prior requires equal active weights and zero inactive weights")
        return market[indices]
    return market


def _active_views(views, indices):
    if views is None or indices is None:
        return views
    p, q, confidence = views
    inactive = np.ones(p.shape[1], dtype=bool)
    inactive[indices] = False
    if np.any(p[:, inactive] != 0):
        raise _invalid("views_p", "Active-universe views cannot involve inactive assets")
    return p[:, indices], q, confidence


def _threshold_weights(weights: np.ndarray, policy: Policy) -> np.ndarray:
    """Frozen 1% pruning: retain feasibility before removing micro-positions."""
    tiny = weights < .01
    if not tiny.any():
        return weights
    candidate = weights.copy()
    candidate[tiny] = 0
    if candidate.sum() <= 0:
        return weights
    candidate /= candidate.sum()
    if max(_residuals(candidate, policy).values()) <= 1e-12:
        return candidate
    defensive = policy.defensive[~tiny[policy.defensive]]
    non_defensive = policy.non_defensive[~tiny[policy.non_defensive]]
    lower = max(policy.min_defensive, 1 - policy.max_non_defensive,
                1 - len(non_defensive) * policy.cap, 0.)
    upper = min(1., len(defensive) * policy.cap)
    if lower > upper + 1e-14:
        return weights
    total = float(np.clip(candidate[defensive].sum(), min(lower, upper), upper))
    result = np.zeros_like(weights)
    result[defensive] = _project_group(candidate[defensive], total, policy.cap)
    result[non_defensive] = _project_group(candidate[non_defensive], 1 - total, policy.cap)
    return result if max(_residuals(result, policy).values()) <= 1e-12 else weights


def _allocate(request: dict) -> dict:
    if not isinstance(request, dict):
        raise _invalid("request", "request must be an object")
    allowed = {"strategy", "asset_ids", "mean_returns", "covariance", "market_weights",
               "views_p", "views_q", "view_confidences", "constraints", "tau", "delta", "active_asset_ids", "active_policy_version"}
    if set(request) - allowed:
        raise _invalid("request", "request contains unsupported fields")
    strategy = request.get("strategy")
    if not isinstance(strategy, str) or strategy not in {"EW", "MVO", "BL_ML"}:
        raise CoreError("unsupported_strategy", "Supported strategies are EW, MVO, and BL_ML")
    assets = _asset_ids(request.get("asset_ids"), "asset_ids")
    active = _active_indices(request, assets, strategy)
    numerical_assets = assets if active is None else [assets[i] for i in active]
    mu = _vector(request.get("mean_returns"), len(assets), "mean_returns")
    if active is not None:
        mu = mu[active]
    sigma, regularization = _covariance(request.get("covariance"), len(assets), active)
    policy = _policy(request.get("constraints"), numerical_assets)
    tau = _positive(request.get("tau", 0.05), "tau")
    delta = _positive(request.get("delta", 2.5), "delta")
    views = _active_views(_views(request, len(assets), required=strategy == "BL_ML"), active)
    market = None
    if request.get("market_weights") is not None:
        market = _vector(request["market_weights"], len(assets), "market_weights")
        if np.any(market < 0) or abs(market.sum() - 1.0) > 1e-8:
            raise _invalid("market_weights", "market_weights must be nonnegative and sum to one")
        market = _active_market(market, active)
    diagnostics = {"return_units": "daily", "covariance_regularization": regularization}
    if active is not None:
        diagnostics["active_asset_ids"] = numerical_assets
    if strategy == "BL_ML":
        if market is None:
            raise _invalid("market_weights", "BL_ML requires market_weights")
        mu, posterior_details = _posterior(sigma, market, views, tau, delta)
        diagnostics.update(posterior_details)
    if strategy == "EW":
        weights = np.full(len(numerical_assets), 1.0 / len(numerical_assets))
        if max(_residuals(weights, policy).values()) > 1e-13:
            raise CoreError("infeasible_constraints", "Equal weights violate the supplied policy; EW cannot adjust its weights")
        diagnostics.update(solver=None, solver_status="not_run", maximum_feasibility_adjustment=0.0)
    else:
        weights, solver_details = _optimize(mu, sigma, policy)
        diagnostics.update(solver_details)
        if active is not None:
            before_threshold = weights
            weights = _threshold_weights(weights, policy)
            diagnostics["maximum_threshold_adjustment"] = float(np.max(np.abs(weights - before_threshold)))
            diagnostics["min_weight_threshold"] = .01
    residuals = _residuals(weights, policy)
    if max(residuals.values()) > 1e-12:
        raise CoreError("solver_failure", "Final weights violate the supplied policy", {"constraint_residuals": residuals})
    objective = float(mu @ weights - policy.risk_aversion * (weights @ sigma @ weights))
    if not np.isfinite(objective):
        raise CoreError("numerical_failure", "The allocation objective is not finite")
    diagnostics.update(objective=objective, constraint_residuals=residuals)
    if active is not None:
        full_weights = np.zeros(len(assets))
        full_weights[active] = weights
        weights = full_weights
    return {
        "strategy": strategy,
        "asset_ids": assets,
        "weights": weights.tolist(),
        "status": "optimal",
        "core_version": __version__,
        "diagnostics": diagnostics,
    }


def validate_numerical_inputs(inputs: dict, *, strategy: str = "MVO") -> None:
    """Validate explicit data without policy checks, posterior solving or allocation.

    Uses the allocator's numeric, shape and covariance tolerances. Missing model
    views and market weights are permitted for EW/MVO; BL_ML requires both.
    Success does not establish feasibility for an investor's constraints.
    """
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            if not isinstance(inputs, dict):
                raise _invalid("inputs", "inputs must be an object")
            allowed = {
                "asset_ids", "mean_returns", "covariance", "market_weights",
                "views_p", "views_q", "view_confidences", "tau", "delta", "active_asset_ids", "active_policy_version",
            }
            if set(inputs) - allowed:
                raise _invalid("inputs", "inputs contain unsupported fields")
            if not isinstance(strategy, str) or strategy not in {"EW", "MVO", "BL_ML"}:
                raise CoreError("unsupported_strategy", "Unsupported strategy")
            assets = _asset_ids(inputs.get("asset_ids"), "asset_ids")
            active = _active_indices(inputs, assets, strategy)
            _vector(inputs.get("mean_returns"), len(assets), "mean_returns")
            _covariance(inputs.get("covariance"), len(assets), active)
            _positive(inputs.get("tau", 0.05), "tau")
            _positive(inputs.get("delta", 2.5), "delta")
            _active_views(_views(inputs, len(assets), required=strategy == "BL_ML"), active)
            if inputs.get("market_weights") is not None:
                market = _vector(inputs["market_weights"], len(assets), "market_weights")
                if np.any(market < 0) or abs(market.sum() - 1.0) > 1e-8:
                    raise _invalid("market_weights", "market_weights must be nonnegative and sum to one")
                _active_market(market, active)
            elif strategy == "BL_ML":
                raise _invalid("market_weights", "BL_ML requires market_weights")
    except (np.linalg.LinAlgError, FloatingPointError, OverflowError):
        raise CoreError("numerical_failure", "Inputs exceed the stable numerical range of the allocator") from None


def allocate(request: dict) -> dict:
    """Allocate a fully invested, long-only portfolio or raise ``CoreError``.

    Inputs are explicit daily-unit data; no training, data access, mutation,
    legacy imports, environment variables, or global policy is consulted.
    See the package README for the versioned contract and parity limits.
    """
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _allocate(request)
    except (np.linalg.LinAlgError, FloatingPointError, OverflowError):
        raise CoreError("numerical_failure", "Inputs exceed the stable numerical range of the allocator") from None
