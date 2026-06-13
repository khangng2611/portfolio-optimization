"""Mean-variance portfolio optimisation (standard and constrained ranking variants).

Shared private helpers:
* ``_regularize_covariance`` — clean and stabilise a covariance matrix.
* ``_solve_mvo`` — run the cvxpy solver chain with graceful fallback.
"""

import cvxpy as cp
import numpy as np

from config import (
    MAX_POSITION_SIZE,
    RANKING_DEFAULT_DEFENSIVE_ASSETS,
    RANKING_MAX_EQUITY_EXPOSURE,
    RANKING_MIN_DEFENSIVE_WEIGHT,
    RANKING_RISK_AVERSION_BASE,
)


def _regularize_covariance(sigma: np.ndarray) -> np.ndarray:
    """Symmetrise, clip eigenvalues, and return a positive-definite covariance matrix."""
    sigma = np.asarray(sigma, dtype=float)
    sigma = np.nan_to_num(sigma, nan=0.0, posinf=0.0, neginf=0.0)
    sigma = 0.5 * (sigma + sigma.T)
    eigvals, eigvecs = np.linalg.eigh(sigma)
    eigvals = np.clip(eigvals, 1e-8, None)
    return eigvecs @ np.diag(eigvals) @ eigvecs.T


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
                problem.solve(solver=getattr(cp, solver_name))
                if (
                    problem.status in [cp.OPTIMAL, cp.OPTIMAL_INACCURATE]
                    and problem.variables()[0].value is not None
                ):
                    w_val = problem.variables()[0].value
                    weight = np.maximum(w_val, 0)
                    total = np.sum(weight)
                    if total > 0:
                        return weight / total
            except Exception:
                continue
    return None


def optimize_weight(
    mu,
    sigma,
    risk_aversion=RANKING_RISK_AVERSION_BASE,
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
    return result if result is not None else np.full(n, 1.0 / n)


def optimize_weight_ranking(
    mu,
    sigma,
    assets,
    risk_aversion=RANKING_RISK_AVERSION_BASE,
    max_weight=MAX_POSITION_SIZE,
    min_defensive_weight=RANKING_MIN_DEFENSIVE_WEIGHT,
    max_equity_exposure=RANKING_MAX_EQUITY_EXPOSURE,
    defensive_assets=RANKING_DEFAULT_DEFENSIVE_ASSETS,
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
    if result is not None:
        return result

    # Fallback: give min_defensive_weight to defensive, rest equal across stocks
    fallback = np.zeros(n)
    if defensive_indices:
        def_w = min_defensive_weight / len(defensive_indices)
        for i in defensive_indices:
            fallback[i] = def_w
    if stock_indices:
        stock_w = (1.0 - min_defensive_weight) / len(stock_indices)
        for i in stock_indices:
            fallback[i] = stock_w
    return fallback
