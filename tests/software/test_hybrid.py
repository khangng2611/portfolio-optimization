import numpy as np
import pytest

from portfolio_core import allocate
from portfolio_core.hybrid import allocate_hybrid
from portfolio_contracts.hybrid import constraint_violations, hybrid_policy, validate_hybrid_weights


@pytest.mark.parametrize('regime,expected', [
    ('normal', (.45, .60, .75)), ('stress', (.225, .30, .375)),
    ('crisis', (.075, .10, .125)),
])
def test_phase1_mix_by_regime_and_profile(regime, expected):
    assert tuple(hybrid_policy(regime, p)['mvo_share'] for p in ('conservative', 'balanced', 'growth')) == pytest.approx(expected)


def test_hybrid_blends_distinct_universes_and_flags_infeasible_ew():
    ids = ['ACB', 'BID', 'CTG', 'DGC', 'FPT', 'GAS', 'GOLD', 'VFF']
    active = [a for a in ids if a != 'GAS']
    numerical = dict(asset_ids=ids, active_asset_ids=active,
                     active_policy_version='user-selection-active-v1',
                     mean_returns=[.001] * 8, covariance=(np.eye(8) * .0001).tolist(),
                     market_weights=[1 / 7 if a in active else 0 for a in ids],
                     views_p=[[1., 0., 0., 0., 0., 0., 0., 0.]],
                     views_q=[.002], view_confidences=[.8])
    constraints = dict(risk_aversion=5, max_position_weight=.5,
                       defensive_asset_ids=['VFF'], min_defensive_weight=.15,
                       max_non_defensive_weight=.7)
    pin = hybrid_policy('crisis', 'growth')
    r = allocate_hybrid(numerical, constraints, pin)
    bl = allocate(numerical | dict(strategy='BL_ML', constraints=constraints))
    comparison = r['diagnostics']['hybrid']
    assert r['strategy'] == 'HYBRID'
    assert comparison['bl_ml_weights'] == bl['weights']
    assert comparison['bl_ml_weights'][5] == 0 < r['weights'][5]
    comparison['ew_constraint_violations'] = constraint_violations(ids, comparison['ew_weights'], constraints)
    assert comparison['ew_constraint_violations']
    validate_hybrid_weights(ids, active, constraints, pin, r)
    r['weights'][0] += .01
    with pytest.raises(ValueError, match='blend'):
        validate_hybrid_weights(ids, active, constraints, pin, r)


def test_locked_forward_candidate_changes_only_growth_normal():
    version = 'hybrid-growth-normal-mvo60-v1'
    for regime in ('normal', 'stress', 'crisis'):
        for profile in ('conservative', 'balanced', 'growth'):
            original = hybrid_policy(regime, profile)
            candidate = hybrid_policy(regime, profile, version)
            expected = .60 if (regime, profile) == ('normal', 'growth') else original['mvo_share']
            assert candidate == {'version': version, 'mvo_share': expected}
            assert original['version'] == 'phase1-hybrid-profile-v1'
    with pytest.raises(ValueError):
        hybrid_policy('normal', 'growth', 'unknown')


def test_reviewed_report_is_required_for_new_candidate_pins(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import hashlib
    import json
    from portfolio_service import hybrid_release as release

    path = tmp_path / "final.json"
    monkeypatch.setattr(release, "FINAL_REPORT", path)
    monkeypatch.delenv("HYBRID_REVIEWED_REPORT_SHA256", raising=False)
    assert release.reviewed_version() == release.SERVING_POLICY
    monkeypatch.setenv("HYBRID_LOCAL_RETROSPECTIVE_POLICY", release.FORWARD_POLICY)
    assert release.reviewed_version() == release.FORWARD_POLICY
    after_close = datetime(2027, 12, 1, tzinfo=timezone.utc)
    report = {"status": "PASS", "policy": release.FORWARD_POLICY, "evaluation_period": ["2026-11-24", "2027-11-23"],
              "informative_normal_executions": 1,
              "checks": {p: dict(volatility=True, drawdown=True, turnover=True) for p in ("conservative", "balanced", "growth")}}
    path.write_text(json.dumps(report))
    monkeypatch.setenv("HYBRID_REVIEWED_REPORT_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    assert release.reviewed_version(datetime(2026, 11, 24, tzinfo=timezone.utc)) is None
    assert release.reviewed_version(after_close) == release.FORWARD_POLICY
    path.write_text(json.dumps(report | {"status": "FAIL"}))
    assert release.reviewed_version(after_close) is None
    monkeypatch.setenv("HYBRID_REVIEWED_REPORT_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    assert release.reviewed_version(after_close) is None
