"""
Relative View Generation from Ranking Scores
=============================================

Converts ranking model output into Black-Litterman relative views.

Mathematical formulation:
    Given K stocks ranked by predicted performance:
        Stock_1 (best) > Stock_2 > ... > Stock_K (worst)

    Generate relative views:
        View_i: Stock_ranked_i outperforms Stock_ranked_j

    P matrix construction:
        P[view, long_stock]  = +1
        P[view, short_stock] = -1
        P[view, other]       =  0

    Q vector:
        Q[view] = spread * (rank_diff / K) / TRADING_DAYS_PER_YEAR
        (daily expected outperformance)

    Confidence (used to derive Omega):
        confidence = clip(
            base_conf + margin_bonus - disagreement_penalty,
            conf_min, conf_max,
        )
        where:
            margin_bonus         = (score_long - score_short) * margin_scale
            disagreement_penalty = (std_long + std_short) / 2 * disagreement_scale

View Generation Strategy
------------------------
Given K ranked stocks indexed [0 = best, ..., K-1 = worst]:
    - Pair every top-half stock i with every bottom-half stock j (j > K//2 - 1
      adjusted by i) to produce ~K views rather than K*(K-1)/2 to avoid
      overconstraining Black-Litterman.

For K = 5 the produced views are:
    1. rank 0 > rank 4   (diff 4)
    2. rank 0 > rank 3   (diff 3)
    3. rank 0 > rank 2   (diff 2)
    4. rank 1 > rank 4   (diff 3)
    5. rank 1 > rank 3   (diff 2)
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from config import (
    RANKING_PREDICTION_HORIZON,  # noqa: F401  (re-exported for downstream callers)
    RANKING_VIEW_SPREAD,
    TRADING_DAYS_PER_YEAR,
)
from gen_view.ranking.config import (
    RANKING_CONF_BASE,
    RANKING_CONF_MAX,
    RANKING_CONF_MIN,
    RANKING_DISAGREEMENT_SCALE,
    RANKING_MARGIN_SCALE,
)


def generate_ranking_relative_views(
    rank_scores: dict[str, float],
    ensemble_std: dict[str, float],
    assets: list[str],
    spread: float = RANKING_VIEW_SPREAD,
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray], list[str]]:
    """
    Generate relative views from ranking scores for Black-Litterman.

    Creates pairwise relative views between top-ranked and bottom-ranked stocks.
    Only stocks present in the ``assets`` list (the optimization universe) are
    eligible to appear in any view; non-stock assets such as Gold or MBBOND
    keep zero coefficients in every row of the P matrix.

    View generation strategy
    ------------------------
    - Sort ranked stocks (intersected with ``assets``) by score, descending.
    - For each stock ``i`` in the top half, pair it with bottom-half stocks
      ``j`` such that ``j > K//2 + i - 1``. This yields ~K views for K stocks
      (instead of the K*(K-1)/2 produced by full pairwise enumeration).

    Parameters
    ----------
    rank_scores : dict[str, float]
        Ranking scores from the model. Higher = predicted outperformer.
    ensemble_std : dict[str, float]
        Standard deviation across ensemble predictions per stock. Missing
        entries default to 0.0 (interpreted as "no disagreement information").
    assets : list[str]
        Full asset list in the optimization (includes Gold, MBBOND, etc.).
        The columns of the returned ``P`` matrix correspond to this list.
    spread : float, optional
        Annual spread used to scale relative view magnitudes
        (default: ``RANKING_VIEW_SPREAD`` = 0.03 = 3%).

    Returns
    -------
    tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, list[str]]
        ``(P, Q, confidence, view_names)``:

        - ``P``: shape ``(n_views, n_assets)``, +1 for the long stock,
          -1 for the short stock, 0 elsewhere.
        - ``Q``: shape ``(n_views,)``, daily expected outperformance per view.
        - ``confidence``: shape ``(n_views,)``, dynamic per-view confidence
          values clipped to ``[RANKING_CONF_MIN, RANKING_CONF_MAX]``.
        - ``view_names``: human-readable view descriptions (e.g.,
          ``"VNM > HPG (rank diff 4)"``).

        Returns ``(None, None, None, [])`` when ``rank_scores`` is empty or
        fewer than two ranked stocks intersect ``assets``.
    """
    # --- Guard: empty input ------------------------------------------------
    if not rank_scores:
        return None, None, None, []

    # --- Restrict to ranked stocks that are part of the optimization -------
    asset_to_idx = {asset: i for i, asset in enumerate(assets)}
    ranked_in_assets = [
        (stock, score)
        for stock, score in rank_scores.items()
        if stock in asset_to_idx
    ]

    if len(ranked_in_assets) < 2:
        return None, None, None, []

    # Sort by score descending (best first)
    ranked_in_assets.sort(key=lambda item: item[1], reverse=True)
    ranked_stocks = [stock for stock, _ in ranked_in_assets]
    ranked_scores = [score for _, score in ranked_in_assets]
    K = len(ranked_stocks)

    # --- Build (long_idx, short_idx) pairs ---------------------------------
    # For i in [0, K//2): pair with j in (K//2 + i - 1, K-1].
    pair_indices: list[tuple[int, int]] = []
    top_half = max(K // 2, 1)  # ensure at least one "top" rank when K == 2 or 3
    for i in range(top_half):
        # j strictly greater than (K//2 + i - 1) and at most K - 1.
        j_lower_exclusive = (K // 2) + i - 1
        for j in range(K - 1, j_lower_exclusive, -1):
            if j <= i:
                continue
            pair_indices.append((i, j))

    # Fallback safety: if the strategy yields no pair (degenerate K), fall
    # back to a single best-vs-worst view.
    if not pair_indices:
        pair_indices = [(0, K - 1)]

    n_assets = len(assets)
    n_views = len(pair_indices)

    P = np.zeros((n_views, n_assets), dtype=float)
    Q = np.zeros(n_views, dtype=float)
    confidence = np.zeros(n_views, dtype=float)
    view_names: list[str] = []

    daily_scale = spread / float(TRADING_DAYS_PER_YEAR)

    for v, (i_long, j_short) in enumerate(pair_indices):
        long_stock = ranked_stocks[i_long]
        short_stock = ranked_stocks[j_short]
        long_idx = asset_to_idx[long_stock]
        short_idx = asset_to_idx[short_stock]

        # P matrix row: +1 long, -1 short, 0 elsewhere
        P[v, long_idx] = 1.0
        P[v, short_idx] = -1.0

        # Q: daily expected outperformance proportional to rank gap
        rank_diff = j_short - i_long
        Q[v] = daily_scale * (rank_diff / K)

        # Confidence (dynamic)
        score_long = float(ranked_scores[i_long])
        score_short = float(ranked_scores[j_short])
        std_long = float(ensemble_std.get(long_stock, 0.0))
        std_short = float(ensemble_std.get(short_stock, 0.0))
        confidence[v] = _compute_view_confidence(
            score_long=score_long,
            score_short=score_short,
            std_long=std_long,
            std_short=std_short,
        )

        view_names.append(
            f"{long_stock} > {short_stock} (rank diff {rank_diff})"
        )

    return P, Q, confidence, view_names


def _compute_view_confidence(
    score_long: float,
    score_short: float,
    std_long: float,
    std_short: float,
) -> float:
    """
    Compute dynamic confidence for a single relative view.

    Formula
    -------
        margin               = score_long - score_short
        margin_bonus         = margin * RANKING_MARGIN_SCALE
        disagreement_penalty = (std_long + std_short) / 2 * RANKING_DISAGREEMENT_SCALE
        confidence           = clip(
            RANKING_CONF_BASE + margin_bonus - disagreement_penalty,
            RANKING_CONF_MIN,
            RANKING_CONF_MAX,
        )

    Higher score margin -> higher confidence.
    Higher ensemble disagreement -> lower confidence.

    Parameters
    ----------
    score_long : float
        Ranking score of the long (outperforming) stock.
    score_short : float
        Ranking score of the short (underperforming) stock.
    std_long : float
        Ensemble standard deviation for the long stock.
    std_short : float
        Ensemble standard deviation for the short stock.

    Returns
    -------
    float
        Confidence value in ``[RANKING_CONF_MIN, RANKING_CONF_MAX]``.
    """
    margin = score_long - score_short
    margin_bonus = margin * RANKING_MARGIN_SCALE
    disagreement_penalty = (std_long + std_short) / 2.0 * RANKING_DISAGREEMENT_SCALE
    confidence = RANKING_CONF_BASE + margin_bonus - disagreement_penalty
    return float(np.clip(confidence, RANKING_CONF_MIN, RANKING_CONF_MAX))
