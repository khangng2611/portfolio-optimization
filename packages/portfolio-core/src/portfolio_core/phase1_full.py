"""Pure numerical helpers for the frozen Phase 1 full-universe policy.

Price indices follow the research replay. Selection sees ``prices[:t]``;
regime and covariance see ``returns[:t]`` (returns are offset by one price).
Callers own data availability, persistence, and model review.
"""

from itertools import combinations
from numbers import Integral

import numpy as np


EQUITY_IDS = (
    'ACB', 'BID', 'CTG', 'DGC', 'FPT', 'GAS', 'GVR', 'HDB', 'HPG', 'LPB',
    'MBB', 'MSN', 'MWG', 'PLX', 'SAB', 'SHB', 'SSI', 'STB', 'TCB', 'TPB',
    'VCB', 'VHM', 'VIB', 'VIC', 'VJC', 'VNM', 'VPB', 'VRE', 'BVH', 'POW',
)
ASSET_IDS = EQUITY_IDS + ('GOLD', 'VFF')


def schedule(n_prices: int) -> dict:
    """Return completed 5-session checkpoint and its independent epoch pins.

    The first successful absolute-model fit is t=145: t-5 must exceed
    30 feature rows + 5 label rows + 100 minimum training samples.
    """
    if isinstance(n_prices, bool) or not isinstance(n_prices, Integral) or n_prices < 21:
        raise ValueError('At least 21 observed price sessions are required')
    decision = 20 + ((int(n_prices) - 1 - 20) // 5) * 5
    selection = 20 + ((decision - 20) // 20) * 20
    fit = None if decision < 145 else 145 + ((decision - 145) // 10) * 10
    return {
        'decision_index': decision,
        'selection_index': selection,
        'fit_index': fit,
        'fit_selection_index': None if fit is None else 20 + ((fit - 20) // 20) * 20,
        'covariance_start': decision - 20,
    }


def _panel(value, columns: int, field: str, *, positive=False) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=float)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f'{field} must be a finite numeric panel') from None
    if result.ndim != 2 or result.shape[1] != columns or result.shape[0] < 2:
        raise ValueError(f'{field} must have at least two rows and {columns} columns')
    if not np.isfinite(result).all() or (positive and np.any(result <= 0)):
        raise ValueError(f'{field} must contain finite' + (' positive' if positive else '') + ' values')
    return result


def distance_matrix(prices) -> np.ndarray:
    """Frozen 1-correlation distance on an explicitly cut, expanding price panel."""
    prices = _panel(prices, 30, 'prices', positive=True)
    from .selection import candidate_distance_matrix

    return candidate_distance_matrix(prices)

def select_equities(prices) -> list[int]:
    """Exhaustive K=5 medoids, preserving frozen combination and tie order.

    Pass only the thirty equities and exclude the selection decision close.
    Returns column indices in canonical universe order.
    """
    distance = distance_matrix(prices)
    best_cost = float('inf')
    best = (0, 1, 2, 3, 4)
    for combo in combinations(range(30), 5):
        # cumsum preserves the source's sequential row-wise cost accumulation.
        cost = np.cumsum(np.min(distance[:, combo], axis=1))[-1]
        if cost < best_cost:
            best_cost, best = cost, combo
    return list(best)


def regime(returns, t: int) -> dict:
    """Frozen 20/120 vol and 60-session drawdown on all 32 panel assets."""
    returns = _panel(returns, 32, 'returns')
    from .selection import candidate_regime

    return candidate_regime(returns, t)

def validate_active_assets(asset_ids, active_asset_ids) -> list[int]:
    """Validate the canonical output order and K5 + GOLD + VFF subset."""
    if not isinstance(asset_ids, list) or asset_ids != list(ASSET_IDS):
        raise ValueError('asset_ids must use the canonical Phase 1 full order')
    if (not isinstance(active_asset_ids, list) or len(active_asset_ids) != 7
            or any(not isinstance(a, str) for a in active_asset_ids)
            or active_asset_ids[-2:] != ['GOLD', 'VFF']
            or len(set(active_asset_ids)) != 7
            or not set(active_asset_ids[:5]) <= set(EQUITY_IDS)):
        raise ValueError('active_asset_ids must contain five equities followed by GOLD and VFF')
    indices = [asset_ids.index(a) for a in active_asset_ids]
    if indices != sorted(indices):
        raise ValueError('active_asset_ids must preserve the full asset order')
    return indices


def adjust_views(views: dict | None, regime_info: dict, active_asset_ids: list[str]) -> dict:
    """Dampen existing confidence and append the source VFF defensive view.

    P has seven active columns. Defensive views use VFF versus all other active
    assets, including GOLD, and are appended after the dampener is applied.
    """
    validate_active_assets(list(ASSET_IDS), active_asset_ids)
    if (not isinstance(regime_info, dict) or regime_info.get('regime') not in {'normal', 'stress', 'crisis'}
            or isinstance(regime_info.get('vol_ratio'), bool)):
        raise ValueError('regime_info must contain a valid regime and volatility ratio')
    try:
        ratio = float(regime_info['vol_ratio'])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('regime_info must contain a finite nonnegative volatility ratio') from None
    if not np.isfinite(ratio) or ratio < 0:
        raise ValueError('regime_info must contain a finite nonnegative volatility ratio')
    if views is None:
        p, q, confidence = np.empty((0, 7)), np.empty(0), np.empty(0)
    else:
        try:
            p = np.asarray(views['views_p'], dtype=float)
            q = np.asarray(views['views_q'], dtype=float)
            confidence = np.asarray(views['view_confidences'], dtype=float)
        except (KeyError, ValueError, TypeError, OverflowError):
            raise ValueError('views must contain numeric P, Q, and confidence arrays') from None
        if (p.ndim != 2 or p.shape[1] != 7 or q.shape != (len(p),)
                or confidence.shape != (len(p),) or not np.isfinite(p).all()
                or not np.isfinite(q).all() or not np.isfinite(confidence).all()
                or np.any(confidence < 0) or np.any(confidence > 1)
                or np.any(np.all(p == 0, axis=1))):
            raise ValueError('views must contain aligned finite seven-asset views and confidence in [0, 1]')
    confidence = confidence * min(1.0, 1.3 / ratio) if ratio > 0 else confidence.copy()
    if regime_info['regime'] in {'stress', 'crisis'}:
        crisis = regime_info['regime'] == 'crisis'
        row = np.full(7, -1 / 6)
        row[-1] = 1
        p = np.vstack([p, row])
        q = np.append(q, (.10 if crisis else .05) / 252)
        confidence = np.append(confidence, .8 * (1.0 if crisis else .85))
    return {'views_p': p.tolist(), 'views_q': q.tolist(), 'view_confidences': confidence.tolist()}
