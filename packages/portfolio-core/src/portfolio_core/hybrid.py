"""Phase 1 blend with a versioned adjustment for the confirmed risk profile."""

import numpy as np

from .allocator import _covariance, _policy, _residuals, allocate


def allocate_hybrid(numerical, constraints, pin):
    assets = numerical['asset_ids']
    shared = dict(asset_ids=assets, mean_returns=numerical['mean_returns'],
                  covariance=numerical['covariance'], constraints=constraints)
    mvo = allocate(shared | {'strategy': 'MVO', 'active_asset_ids': assets,
                            'active_policy_version': numerical['active_policy_version']})
    bl = allocate(numerical | {'strategy': 'BL_ML', 'constraints': constraints})
    alpha = pin['mvo_share']
    weights = alpha * np.array(mvo['weights']) + (1 - alpha) * np.array(bl['weights'])
    ew = np.full(len(assets), 1 / len(assets))
    policy = _policy(constraints, assets)
    sigma, _ = _covariance(shared['covariance'], len(assets))
    comparison = pin | {
        'bl_ml_weights': bl['weights'], 'mvo_weights': mvo['weights'],
        'ew_weights': ew.tolist(),
        'daily_volatility': {k: float(np.sqrt(w @ sigma @ w)) for k, w in
                             [('hybrid', weights), ('mvo', np.array(mvo['weights'])), ('ew', ew)]},
        'covariance_window_sessions': 20,
    }
    # The BL objective only describes that branch. Do not present it as the blend's objective.
    diagnostics = {k: v for k, v in bl['diagnostics'].items() if k != 'objective'}
    diagnostics.update(hybrid=comparison, constraint_residuals=_residuals(weights, policy))
    result = bl | {'strategy': 'HYBRID', 'weights': weights.tolist(), 'diagnostics': diagnostics}
    return result
