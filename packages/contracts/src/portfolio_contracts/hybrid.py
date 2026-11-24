"""Pins and result checks shared by Quant and Portfolio without solver dependencies."""

import math


SERVING_POLICY = 'phase1-hybrid-profile-v1'
FORWARD_POLICY = 'hybrid-growth-normal-mvo60-v1'


def hybrid_policy(regime, profile, version=SERVING_POLICY):
    if version not in (SERVING_POLICY, FORWARD_POLICY):
        raise ValueError('Unknown HYBRID policy version')
    shares = {'normal': .60, 'stress': .30, 'crisis': .10}
    multipliers = {'conservative': .75, 'balanced': 1., 'growth': 1.25}
    if regime not in shares or profile not in multipliers:
        raise ValueError('HYBRID requires a known regime and confirmed risk profile')
    share = shares[regime] * multipliers[profile]
    if version == FORWARD_POLICY and (regime, profile) == ('normal', 'growth'):
        share = .60
    return {'version': version, 'mvo_share': round(share, 6)}


def constraint_violations(assets, weights, constraints, *, tolerance=1e-12):
    defensive = sum(w for a, w in zip(assets, weights) if a in constraints['defensive_asset_ids'])
    checks = {
        'budget': abs(sum(weights) - 1), 'long_only': -min(weights),
        'position_cap': max(weights) - constraints['max_position_weight'],
        'defensive_floor': constraints['min_defensive_weight'] - defensive,
        'non_defensive_cap': 1 - defensive - constraints['max_non_defensive_weight'],
    }
    return [key for key, residual in checks.items() if residual > tolerance]


def validate_hybrid_weights(assets, bl_active, constraints, pin, result):
    comparison = result['diagnostics'].get('hybrid')
    if not isinstance(comparison, dict) or any(comparison.get(k) != v for k, v in pin.items()):
        raise ValueError('HYBRID policy does not match accepted command')

    def vector(key):
        values = comparison.get(key)
        if (not isinstance(values, list) or len(values) != len(assets)
                or any(type(w) not in (int, float) or not math.isfinite(w) for w in values)):
            raise ValueError('Invalid HYBRID weight vector')
        return values

    mvo, bl, ew = (vector(key) for key in ('mvo_weights', 'bl_ml_weights', 'ew_weights'))
    if any(constraint_violations(assets, w, constraints) for w in (mvo, bl)):
        raise ValueError('HYBRID branch violates portfolio constraints')
    if any(w != 0 for a, w in zip(assets, bl) if a not in bl_active):
        raise ValueError('HYBRID BL_ML branch has weight outside its active assets')
    alpha = pin['mvo_share']
    if any(abs(w - (alpha * m + (1 - alpha) * b)) > 1e-12 for w, m, b in zip(result['weights'], mvo, bl)):
        raise ValueError('HYBRID blend does not match its branches')
    if ew != [1 / len(assets)] * len(assets) or comparison.get('ew_constraint_violations') != constraint_violations(assets, ew, constraints):
        raise ValueError('HYBRID equal-weight reference does not match its constraints')
    volatility = comparison.get('daily_volatility')
    if (not isinstance(volatility, dict) or set(volatility) != {'hybrid', 'mvo', 'ew'}
            or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in volatility.values())
            or comparison.get('covariance_window_sessions') != 20):
        raise ValueError('Invalid HYBRID comparison metrics')
