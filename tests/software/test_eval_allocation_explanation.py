from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_frozen_vietnamese_eval_compares_baseline_and_grounded_claims():
    from eval_allocation_explanation import evaluate

    report = evaluate()
    assert report["synthetic"] is True
    assert report["total"] == 24
    assert report["passed"] == 24
    assert (
        report["baseline_relevance"]["passed"] < report["grounded_relevance"]["passed"]
    )
    assert report["provider_calls"] == 0
    assert report["retrieval_hit_at_5"] == "N/A"
    assert report["live_integration"] == "NOT RUN"


def test_concise_eval_checks_metric_focus_absence_and_word_budgets():
    from eval_allocation_explanation import evaluate, ROOT

    report = evaluate(
        ROOT / "tests/fixtures/knowledge/eval-allocation-explanation-vi-v2.jsonl"
    )
    assert report["passed"] == report["total"]
    assert report["concision"]["passed"] == report["concision"]["total"]
    assert report["concision"]["total"] >= 12
    assert report["concision"]["after_words"] < report["concision"]["before_words"]
    injection = next(row for row in report["rows"] if row["id"] == "AE23")
    assert injection["concise_rendering"] is True
    assert "không tự chấp nhận" in injection["text"]
