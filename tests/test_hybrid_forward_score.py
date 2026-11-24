import copy
import json

import numpy as np
import pandas as pd
import pytest

from scripts.hybrid_forward_score import score


ASSETS = ["FPT", "VCB", "VFF"]


def inputs(n=8):
    index = pd.bdate_range("2026-11-24", periods=n)
    sessions = index.strftime("%Y-%m-%d").tolist()
    marks = pd.DataFrame(100.0, index=index, columns=ASSETS)
    weights = {
        profile: {method: [.4, .2, .4] for method in ("candidate", "regime_only", "v1", "bl_ml")}
        for profile in ("conservative", "balanced", "growth")
    }
    weights["growth"]["v1"] = [.45, .15, .4]
    ledger = [{"session": sessions[0], "status": "DECIDED", "timing_verified": True,
               "weights": weights, "regime": "normal"}]
    for session in sessions[5::5]:
        ledger.append({"session": session, "status": "HOLD", "reason": "VFF_STALE"})
    return ledger, marks, sessions


def test_next_close_fill_and_first_mark_after_execution_with_drift_on_hold():
    ledger, marks, sessions = inputs()
    marks["FPT"] = [80, 100, 110, 110, 110, 110, 110, 120]
    report = score(ledger, marks, sessions, ASSETS)
    result = report["profiles"]["growth"]["candidate"]
    # Initial 25% rise before the fill is excluded. Four tenths invested at 100
    # earns 20% on that capital, less the entry fee. HOLD never resets weights.
    assert result["net_return"] == pytest.approx(.999 * 1.08 - 1)
    assert result["one_way_turnover"] == pytest.approx(1)
    assert result["sessions"] == len(sessions)
    assert result["max_drawdown"] == pytest.approx(.001)
    assert report["decisions"][0]["execution_session"] == sessions[1]
    assert report["decisions"][0]["first_return_session"] == sessions[2]
    assert report["missed_decisions"] == [{"session": sessions[5], "reason": "VFF_STALE"}]
    assert report["status"] == "PASS"
    json.dumps(report, allow_nan=False)


def test_fee_on_final_close_and_no_out_of_period_execution():
    ledger, marks, sessions = inputs(7)
    ledger[1] = copy.deepcopy(ledger[0]) | {"session": sessions[5]}
    for variants in ledger[1]["weights"].values():
        for key in variants:
            variants[key] = [.2, .4, .4]
    report = score(ledger, marks, sessions, ASSETS)
    book = report["profiles"]["balanced"]["candidate"]
    assert book["one_way_turnover"] == pytest.approx(1.2)
    assert book["net_return"] == pytest.approx(.999 * (1 - .0002) - 1)
    assert report["decisions"][1]["first_return_session"] is None
    short = score(ledger, marks, sessions[:6], ASSETS)
    assert short["profiles"]["balanced"]["candidate"]["one_way_turnover"] == 1
    assert short["decisions"][1]["execution_session"] is None


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "late", "unexplained_hold", "bad_weight", "reversed", "carry_gap"])
def test_invalid_calendar_marks_or_decisions_block_scoring(mutation):
    ledger, marks, sessions = inputs()
    if mutation == "missing":
        ledger.pop()
    elif mutation == "extra":
        ledger.append(dict(ledger[-1], session=sessions[-1]))
    elif mutation == "duplicate":
        ledger.append(ledger[0])
    elif mutation == "late":
        ledger[0]["timing_verified"] = False
    elif mutation == "unexplained_hold":
        del ledger[1]["reason"]
    elif mutation == "bad_weight":
        ledger[0]["weights"]["growth"]["candidate"] = [.7, .1, .2]
    elif mutation == "reversed":
        sessions.reverse()
    elif mutation == "carry_gap":
        marks.loc[marks.index[-1], "VCB"] = np.nan
    with pytest.raises(ValueError):
        score(ledger, marks, sessions, ASSETS)


def test_no_changed_normal_growth_allocation_blocks_even_if_metrics_pass():
    ledger, marks, sessions = inputs()
    growth = ledger[0]["weights"]["growth"]
    growth["v1"] = growth["candidate"].copy()
    report = score(ledger, marks, sessions, ASSETS)
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert all(report["checks"]["growth"].values())
    assert report["informative_normal_executions"] == 0


def test_all_missed_cutoffs_are_cash_and_never_pass():
    ledger, marks, sessions = inputs()
    ledger[0] = {"session": sessions[0], "status": "HOLD", "reason": "MODEL_UNAVAILABLE"}
    report = score(ledger, marks, sessions, ASSETS)
    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["profiles"]["growth"]["v1"]["net_return"] == 0
    assert len(report["missed_decisions"]) == 2


def test_any_profile_can_fail_the_quantitative_gate_and_regime_returns_reconcile():
    ledger, marks, sessions = inputs()
    ledger[0]["weights"]["conservative"]["regime_only"] = [.3, .3, .4]
    marks["FPT"] = [100, 100, 160, 100, 160, 100, 160, 100]
    report = score(ledger, marks, sessions, ASSETS)
    assert report["checks"]["conservative"]["volatility"] is False
    assert report["status"] == "FAIL"
    assert report["regimes"]["normal"] == {"sessions_held": 6, "executions": 1}
    for results in report["profiles"].values():
        for metrics in results.values():
            attributed = np.prod([1 + r for r in metrics["net_return_by_regime"].values()])
            assert attributed == pytest.approx(1 + metrics["net_return"])


def test_target_with_only_execution_fee_observed_is_insufficient():
    ledger, marks, sessions = inputs(2)
    report = score(ledger, marks, sessions, ASSETS)
    assert report["profiles"]["growth"]["candidate"]["net_return"] == pytest.approx(-.001)
    assert report["status"] == "INSUFFICIENT_EVIDENCE"


def test_recorded_asset_order_and_solver_tolerance_match_decision():
    ledger, marks, sessions = inputs()
    ledger[0]["assets"] = ASSETS[::-1]
    with pytest.raises(ValueError, match="asset order"):
        score(ledger, marks, sessions, ASSETS)
    ledger[0]["assets"] = ASSETS
    for delta, valid in [(5e-9, True), (2e-8, False)]:
        ledger[0]["weights"]["growth"]["v1"] = [.5 + delta, .1 - delta, .4]
        if valid:
            assert score(ledger, marks, sessions, ASSETS)["status"] == "PASS"
        else:
            with pytest.raises(ValueError, match="weights"):
                score(ledger, marks, sessions, ASSETS)
