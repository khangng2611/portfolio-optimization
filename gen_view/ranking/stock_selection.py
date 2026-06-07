"""
Representative Stock Selection via Combinatorial Optimization
=============================================================

Selects K representative stocks from a universe by finding the globally
optimal combination that minimizes total distance to all other stocks.

Mathematical formulation:
    distance(i,j) = 1 - correlation(i,j)

    Minimize: sum over all stocks i of min_{m in M} distance(i, m)
    where M is the selected set of K representatives.

For N=30 stocks and K=5, the search space is C(30,5) = 142,506 combinations,
which is computationally trivial. The algorithm includes early-stopping pruning
to skip combinations whose partial cost already exceeds the current best.

This guarantees the GLOBAL optimum, unlike PAM which only finds a local optimum.
"""

from itertools import combinations

import numpy as np
import pandas as pd


def compute_distance_matrix(prices: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """
    Compute correlation-based distance matrix from price data.

    Parameters
    ----------
    prices : pd.DataFrame
        Price data with stocks as columns

    Returns
    -------
    tuple[np.ndarray, list[str]]
        (distance_matrix, stock_names)
    """
    # Compute returns
    returns = prices.pct_change().dropna()
    # Correlation matrix
    corr = returns.corr()

    # Constant-price (zero variance) columns produce NaN correlations.
    # Replace NaNs with 0 correlation -> distance of 1 (treated as
    # maximally dissimilar from everything else, which is appropriate:
    # a flat-line stock carries no co-movement information).
    corr = corr.fillna(0.0)

    # Distance = 1 - correlation
    dist = 1.0 - corr.values
    # Ensure diagonal is 0 and matrix is symmetric
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2.0
    # Clip negative distances (can happen with correlation > 1 due to numerical issues)
    dist = np.clip(dist, 0.0, 2.0)
    return dist, list(corr.columns)


def _find_optimal_combination(
    dist: np.ndarray,
    k: int,
) -> tuple[list[int], float]:
    """
    Find the globally optimal combination of K representatives via exhaustive search.

    Iterates over all C(N, K) combinations and selects the one with minimum
    total cost (sum of distances from each stock to its nearest representative).

    Includes early-stopping pruning: if partial cost exceeds current best,
    skip the rest of the current combination.

    Parameters
    ----------
    dist : np.ndarray
        N x N distance matrix
    k : int
        Number of representatives to select

    Returns
    -------
    tuple[list[int], float]
        (best_indices, best_cost)
    """
    n = dist.shape[0]
    best_cost = float("inf")
    best_combo: tuple[int, ...] | None = None

    for combo in combinations(range(n), k):
        cost = 0.0
        pruned = False
        for i in range(n):
            min_d = float("inf")
            for j in combo:
                d = dist[i, j]
                if d < min_d:
                    min_d = d
            cost += min_d
            # Early-stopping pruning: partial cost already worse than current best
            if cost >= best_cost:
                pruned = True
                break
        if not pruned and cost < best_cost:
            best_cost = cost
            best_combo = combo

    # Fallback: if every combination got pruned (e.g. all-zero distances),
    # return the first combination deterministically.
    if best_combo is None:
        best_combo = tuple(range(k))
        best_cost = 0.0

    return list(best_combo), best_cost


def select_representatives(
    prices: pd.DataFrame,
    k: int = 5,
    max_iter: int | None = None,  # kept for backward compatibility, unused
) -> list[str]:
    """
    Select K representative stocks using exhaustive combinatorial optimization.

    Finds the globally optimal set of K stocks that minimizes the total
    correlation-based distance from every stock to its nearest representative.

    For a universe of N=30 stocks with K=5, this evaluates C(30,5) = 142,506
    combinations with early-stopping pruning for efficiency.

    Parameters
    ----------
    prices : pd.DataFrame
        Historical price data for the stock universe (columns = stock tickers).
        Should contain ONLY the lookback window data (no future data).
    k : int
        Number of representatives to select (default: 5)
    max_iter : int, optional
        Unused. Kept for backward compatibility with the previous PAM interface.

    Returns
    -------
    list[str]
        List of K selected stock ticker names (global optimum)

    Raises
    ------
    ValueError
        If prices has fewer columns than k
    """
    if prices is None or prices.shape[1] == 0:
        raise ValueError("`prices` must contain at least one stock column.")

    stock_names = list(prices.columns)
    n_stocks = len(stock_names)

    if n_stocks < k:
        raise ValueError(
            f"Cannot select {k} representatives from {n_stocks} stocks. "
            f"Need at least k={k} stocks in the universe."
        )

    # Edge case: k == n_stocks -> every stock is a representative
    if n_stocks == k:
        return stock_names

    # Build correlation-based distance matrix
    dist, names = compute_distance_matrix(prices)

    # Defensive check: distance matrix shape must match the number of names.
    if len(names) < k:
        raise ValueError(
            f"After distance matrix construction only {len(names)} valid stocks remain, "
            f"which is fewer than k ({k})."
        )

    # Globally optimal combinatorial search
    best_indices, _best_cost = _find_optimal_combination(dist, k)

    return [names[i] for i in best_indices]
