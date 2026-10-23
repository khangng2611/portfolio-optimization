"""Mean-variance portfolio optimisation (standard and constrained ranking variants).

Shared private helpers:
* ``_regularize_covariance`` — clean and stabilise a covariance matrix.
* ``_apply_min_weight_threshold`` — remove micro-weights only with feasible final constraints.
* ``_solve_mvo`` — run the cvxpy solver chain and check final-vector residuals.
"""

import cvxpy as cp
import numpy as np

from config import (
    MAX_POSITION_SIZE,
    MIN_WEIGHT_THRESHOLD,
    DEFAULT_DEFENSIVE_ASSETS,
    MAX_EQUITY_EXPOSURE,
    MIN_DEFENSIVE_WEIGHT,
    RISK_AVERSION_BASE,
)

CONSTRAINT_TOLERANCE = 1e-8


def _regularize_covariance(sigma: np.ndarray) -> np.ndarray:
    """Symmetrise, clip eigenvalues, and return a positive-definite covariance matrix."""
    sigma = np.asarray(sigma, dtype=float)
    sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)
    sigma = 0.5 * (sigma + sigma.T)
    eigvals, eigvecs = np.linalg.eigh(sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    return eigvecs @ np.diag(eigvals) @ eigvecs.T


def _weights_feasible(w, max_weight, defensive_indices=None, stock_indices=None,
                      min_defensive_weight=0.0, max_equity_exposure=1.0):
    """Check the constraints that apply to this final allocation."""
    tol = CONSTRAINT_TOLERANCE
    if (not np.isfinite(w).all() or abs(w.sum() - 1.0) > tol
            or w.min() < -tol or w.max() > max_weight + tol):
        return False
    if defensive_indices is not None and len(defensive_indices):
        if w[defensive_indices].sum() < min_defensive_weight - tol:
            return False
    if stock_indices is not None and len(stock_indices):
        if w[stock_indices].sum() > max_equity_exposure + tol:
            return False
    return True


def _capped_simplex(values, total, max_weight):
    """Project a vector onto non-negative capped weights with a fixed total."""
    n = len(values)
    if total < -CONSTRAINT_TOLERANCE or total > n * max_weight + CONSTRAINT_TOLERANCE:
        raise ValueError("Allocation constraints are infeasible for the available assets")
    if n == 0:
        return np.empty(0)
    total = float(np.clip(total, 0.0, n * max_weight))
    low = float(np.min(values - max_weight))
    high = float(np.max(values))
    for _ in range(80):
        shift = (low + high) / 2.0
        if np.clip(values - shift, 0.0, max_weight).sum() > total:
            low = shift
        else:
            high = shift
    return np.clip(values - (low + high) / 2.0, 0.0, max_weight)


def _project_feasible(w, max_weight, defensive_indices=None, stock_indices=None,
                      min_defensive_weight=0.0, max_equity_exposure=1.0, support=None):
    """Repair bounds/budget while preserving the legacy non-defensive grouping.

    A supplied support keeps removed positions at zero. If that support cannot
    meet the constraints, the caller retains the feasible unpruned allocation.
    """
    if not np.isfinite(max_weight) or max_weight <= 0:
        raise ValueError("max_weight must be finite and positive")
    if support is None:
        support = np.ones(len(w), dtype=bool)
    indices = np.flatnonzero(support)
    result = np.zeros_like(w)
    if defensive_indices is None and stock_indices is None:
        result[indices] = _capped_simplex(w[indices], 1.0, max_weight)
    else:
        defensive = np.asarray(defensive_indices, dtype=int)
        stocks = np.asarray(stock_indices, dtype=int)
        active_defensive = defensive[support[defensive]]
        active_stocks = stocks[support[stocks]]
        # "stocks" follows legacy code: every asset outside the defensive
        # list, including GOLD. With VFF alone, the .70 cap requires VFF>=.30.
        lower = max(0.0, min_defensive_weight if len(defensive) else 0.0,
                    1.0 - max_equity_exposure if len(stocks) else 0.0,
                    1.0 - len(active_stocks) * max_weight)
        upper = min(1.0, len(active_defensive) * max_weight)
        if lower > upper + CONSTRAINT_TOLERANCE:
            raise ValueError("Defensive/non-defensive allocation constraints are infeasible")
        defensive_total = float(np.clip(w[active_defensive].sum(), lower, upper))
        result[active_defensive] = _capped_simplex(w[active_defensive], defensive_total, max_weight)
        result[active_stocks] = _capped_simplex(w[active_stocks], 1.0 - defensive_total, max_weight)
    if not _weights_feasible(result, max_weight, defensive_indices, stock_indices,
                             min_defensive_weight, max_equity_exposure):
        raise ValueError("Could not construct a feasible final allocation")
    return result


def _apply_min_weight_threshold(weights, min_weight=MIN_WEIGHT_THRESHOLD,
                                max_weight=MAX_POSITION_SIZE, defensive_indices=None,
                                stock_indices=None, min_defensive_weight=0.0,
                                max_equity_exposure=1.0):
    """Prune micro-positions without breaking applicable portfolio constraints.

    Preserve the legacy proportional redistribution whenever it is feasible.
    Repair an infeasible pruned candidate on its retained support; if that
    support cannot fill the budget under the caps, keep the unpruned vector.
    """
    w = np.asarray(weights, dtype=float).copy()
    if w.ndim != 1 or len(w) == 0 or not np.isfinite(w).all():
        raise ValueError("Allocation weights must be a finite non-empty vector")
    w = np.maximum(w, 0.0)
    args = (max_weight, defensive_indices, stock_indices,
            min_defensive_weight, max_equity_exposure)
    if not _weights_feasible(w, *args):
        w = _project_feasible(w, *args)
    tiny_mask = w < min_weight
    if not tiny_mask.any():
        return w
    candidate = w.copy()
    candidate[tiny_mask] = 0.0
    if candidate.sum() > 0:
        candidate /= candidate.sum()
        if _weights_feasible(candidate, *args):
            return candidate
        try:
            return _project_feasible(candidate, *args, support=~tiny_mask)
        except ValueError:
            pass  # A feasible unpruned vector takes precedence over pruning.
    return w


def _solve_mvo(objective, constraints, n: int) -> np.ndarray | None:
    """Attempt to solve an MVO problem with ECOS → OSQP → SCS fallback.

    Returns the normalised weight vector on success, or ``None`` if all
    solvers fail.
    """
    problem = cp.Problem(objective, constraints)
    installed = set(cp.installed_solvers())
    for solver_name in ["ECOS", "OSQP", "SCS"]:
        if solver_name in installed:
            try:
                options = {
                    "ECOS": {"abstol": 1e-10, "reltol": 1e-10, "feastol": 1e-10},
                    "OSQP": {"eps_abs": 1e-10, "eps_rel": 1e-10, "max_iter": 100000},
                    "SCS": {"eps": 1e-9, "max_iters": 100000},
                }
                problem.solve(solver=getattr(cp, solver_name), **options[solver_name])
                if (
                    problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]
                    and problem.variables()[0].value is not None
                ):
                    w_val = problem.variables()[0].value
                    if np.asarray(w_val).shape != (n,) or not np.isfinite(w_val).all():
                        continue
                    weight = np.maximum(w_val, 0)
                    total = np.sum(weight)
                    if total > 0:
                        weight = weight / total
                        # Check the actual returned vector after clipping and
                        # normalization, not only the solver's status string.
                        problem.variables()[0].value = weight
                        if all(np.max(np.asarray(c.violation())) <= CONSTRAINT_TOLERANCE
                               for c in constraints):
                            return weight
            except Exception:
                continue
    return None


def optimize_weight(
    mu,
    sigma,
    risk_aversion=RISK_AVERSION_BASE,
    max_weight=MAX_POSITION_SIZE,
):
    """Standard mean-variance optimisation (long-only, capped)."""
    mu = np.asarray(mu, dtype=float)
    n = len(mu)
    sigma = _regularize_covariance(sigma)

    w = cp.Variable(n)
    objective = cp.Maximize(mu @ w - risk_aversion * cp.quad_form(w, sigma))
    constraints = [cp.sum(w) == 1, w >= 0, w <= max_weight]

    result = _solve_mvo(objective, constraints, n)
    weights = result if result is not None else np.full(n, 1.0 / n)
    return _apply_min_weight_threshold(weights, max_weight=max_weight)


def optimize_weight_ranking(
    mu,
    sigma,
    assets,
    risk_aversion=RISK_AVERSION_BASE,
    max_weight=MAX_POSITION_SIZE,
    min_defensive_weight=MIN_DEFENSIVE_WEIGHT,
    max_equity_exposure=MAX_EQUITY_EXPOSURE,
    defensive_assets=DEFAULT_DEFENSIVE_ASSETS,
):
    """Constrained MVO for ranking mode with downside protection.

    Additional constraints beyond standard MVO:
    1. ``sum(defensive_assets weights) >= min_defensive_weight``
    2. ``sum(stock weights) <= max_equity_exposure``
    3. Higher ``risk_aversion`` penalises variance more heavily.
    """
    mu = np.asarray(mu, dtype=float)
    n = len(mu)
    sigma = _regularize_covariance(sigma)

    defensive_indices = [i for i, a in enumerate(assets) if a in defensive_assets]
    stock_indices = [i for i, a in enumerate(assets) if a not in defensive_assets]

    w = cp.Variable(n)
    objective = cp.Maximize(mu @ w - risk_aversion * cp.quad_form(w, sigma))

    constraints = [cp.sum(w) == 1, w >= 0, w <= max_weight]

    if defensive_indices:
        constraints.append(cp.sum(w[defensive_indices]) >= min_defensive_weight)
    if stock_indices:
        constraints.append(cp.sum(w[stock_indices]) <= max_equity_exposure)

    result = _solve_mvo(objective, constraints, n)
    weights = result if result is not None else np.full(n, 1.0 / n)
    return _apply_min_weight_threshold(
        weights, max_weight=max_weight, defensive_indices=defensive_indices,
        stock_indices=stock_indices, min_defensive_weight=min_defensive_weight,
        max_equity_exposure=max_equity_exposure,
    )


def blend_weights(
    w_mvo: np.ndarray,
    w_bl: np.ndarray,
    alpha: float,
) -> np.ndarray:
    """Convex combination ``alpha * w_mvo + (1 - alpha) * w_bl``.

    Used by the HYBRID strategy to mix MVO and BL portfolios with a
    regime-aware ``alpha`` (MVO share).  ``alpha`` is clipped to ``[0, 1]``,
    negative components are floored at zero, the result is renormalised to
    sum to 1, and the standard ``MIN_WEIGHT_THRESHOLD`` post-processing is
    applied so micro-positions are removed.

    Both inputs use the same full asset order. MVO uses the full universe;
    BL is zero-padded outside its active set. Only budget, long-only and the
    position cap apply to HYBRID; BL-specific group constraints do not.
    """
    w_mvo = np.asarray(w_mvo, dtype=float)
    w_bl = np.asarray(w_bl, dtype=float)
    if w_mvo.shape != w_bl.shape:
        raise ValueError(
            f"blend_weights: shape mismatch {w_mvo.shape} vs {w_bl.shape}"
        )

    a = float(np.clip(alpha, 0.0, 1.0))
    w = a * w_mvo + (1.0 - a) * w_bl
    w = np.maximum(w, 0.0)

    total = w.sum()
    if total <= 0:
        return _apply_min_weight_threshold(np.full_like(w, 1.0 / len(w)))
    w = w / total
    return _apply_min_weight_threshold(w)
