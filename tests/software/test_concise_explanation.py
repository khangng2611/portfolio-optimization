import pytest

from portfolio_contracts import canonical_hash
from chat_service.explanation import (
    build_claims,
    default_ids,
    render_claims,
    validate_plan,
)
from test_chat_explanation_evidence import fixture_evidence


def reseal(evidence):
    for body in (evidence["quant"], evidence):
        body["evidence_hash"] = canonical_hash(
            {k: v for k, v in body.items() if k != "evidence_hash"}
        )
    return evidence


def test_rsi_answer_contains_only_requested_metric_asset_and_frozen_date():
    facts, evidence = fixture_evidence()
    evidence["quant"]["features"]["ACB"].append(
        {"name": "macd_hist", "value": 0.123, "unit": "thousand_vnd"}
    )
    claims = build_claims(facts, reseal(evidence))
    ids = default_ids(claims, "RSI của ACB là bao nhiêu?")
    assert ids == ["features_ACB_rsi_14"]
    answer = render_claims(claims, ids, concise=True)
    assert "55" in answer and "ACB" in answer and "2026-11-17" in answer
    assert "MACD" not in answer and "confidence" not in answer
    assert len(answer.split()) < 40


def test_overview_is_short_but_full_claims_remain_available():
    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    ids = default_ids(claims, "Vì sao phân bổ như vậy?")
    short = render_claims(claims, ids, concise=True)
    full = render_claims(claims, ids)
    assert len(short.split()) < 90
    assert len(short.split()) < len(full.split())
    assert "Thận trọng" in short and "30,00%" in short
    assert short.startswith("Đề xuất phân bổ vốn vào 2 tài sản.")
    assert "BID 50,00%" in short and "VFF 50,00%" in short
    assert "Nhóm phòng thủ chiếm 50,00%" in short
    assert "căng thẳng" in short and "20/120" not in short
    assert "ACB" not in short and "dự báo ensemble" not in short
    assert "0%: ACB" in full
    detailed = render_claims(claims, default_ids(claims, "Giải thích chi tiết đề xuất"))
    assert "hướng tăng" in detailed and "hướng giảm" in detailed


@pytest.mark.parametrize("status", ["COMPLETE", "PARTIAL"])
def test_no_negative_view_is_only_concluded_for_complete_retained_evidence(status):
    facts, evidence = fixture_evidence()
    evidence["status"] = evidence["quant"]["status"] = status
    view = evidence["quant"]["views"][1]
    view["raw_mean_return"], view["applied_q_daily"] = 0.02, 0.002
    claims = build_claims(facts, reseal(evidence))
    text = render_claims(
        claims, default_ids(claims, "Có view âm nào không?"), concise=True
    )
    if status == "COMPLETE":
        assert "không có view âm" in text.casefold() and "2 ML views đã lưu" in text
    else:
        assert "chưa đủ" in text.casefold()
        assert "không có view âm" not in text


def test_missing_rsi_of_named_asset_does_not_return_another_metric():
    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    text = render_claims(claims, default_ids(claims, "RSI của BID?"), concise=True)
    assert "chưa lưu" in text.casefold() and "55" not in text
    assert "ACB" not in text


def test_confidence_question_keeps_warning_and_daily_q_units():
    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    text = render_claims(
        claims, default_ids(claims, "Confidence và Q của ACB thế nào?"), concise=True
    )
    assert "không phải xác suất" in text and "/ngày" in text


def test_provider_schema_and_client_reject_out_of_scope_claims(monkeypatch):
    from chat_service.openai_provider import OpenAIProvider

    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    provider = OpenAIProvider()
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-only")
    captured = []

    async def response(payload, _timeout, _timing, _started):
        import json

        captured.append(payload)
        return {
            "status": "completed",
            "usage": {"input_tokens": 10, "output_tokens": 10},
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "facts_hash": canonical_hash(facts),
                                    "evidence_hash": evidence["evidence_hash"],
                                    "selected_claim_ids": ["view_BID"],
                                }
                            ),
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(provider, "_request", response)
    value, meta = provider.explain_claims(
        canonical_hash(facts),
        evidence["evidence_hash"],
        claims,
        question="RSI của ACB?",
    )
    assert value is None and meta["reason"] == "UNVERIFIED_OUTPUT"
    items = captured[0]["text"]["format"]["schema"]["properties"]["selected_claim_ids"]
    assert items["items"]["enum"] == ["features_ACB_rsi_14"]


def test_plan_cannot_answer_rsi_with_whole_feature_dump_or_extra_claims():
    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    for ids in [["features_ACB", "limitations"], ["features_ACB_rsi_14", "view_BID"]]:
        with pytest.raises(ValueError):
            validate_plan(
                {
                    "facts_hash": canonical_hash(facts),
                    "evidence_hash": evidence["evidence_hash"],
                    "selected_claim_ids": ids,
                },
                facts,
                evidence,
                claims,
                "RSI của ACB?",
            )


def test_risk_followup_selects_only_basket_context():
    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    assert default_ids(claims, "Còn rủi ro của rổ?") == ["regime"]


def test_confidence_followup_routes_read_only_without_paid_intent():
    from chat_service.workflow import is_evidence_followup

    assert is_evidence_followup("Confidence và Q của CTG thế nào?")


def test_below_threshold_forecast_does_not_look_applied_in_short_answer():
    facts, evidence = fixture_evidence()
    view = evidence["quant"]["views"][0]
    view.update(
        status="BELOW_THRESHOLD",
        raw_mean_return=0.0005,
        applied_q_daily=None,
        confidence_applied=None,
    )
    claims = build_claims(facts, reseal(evidence))
    text = render_claims(claims, default_ids(claims, "View của ACB?"), concise=True)
    assert "không" in text and "BL" in text and "ngưỡng" in text


@pytest.mark.parametrize(
    "question,expected",
    [
        ("BID có view âm nào không?", ["view_BID", "limitations"]),
        ("RSI của NVL?", ["features_missing"]),
        ("Momentum 15 phiên của ACB?", ["features_missing"]),
        ("RSI7 của ACB?", ["features_missing"]),
    ],
)
def test_reviewed_focus_boundaries(question, expected):
    facts, evidence = fixture_evidence()
    assert default_ids(build_claims(facts, evidence), question) == expected


def test_many_metrics_ask_to_narrow_instead_of_silently_truncating():
    from pathlib import Path
    from portfolio_contracts.explanation import (
        OptimizationExplanationEvidence,
        RecommendationEvidence,
    )
    import json

    base = json.loads(
        Path(
            "tests/fixtures/knowledge/allocation-explanation-facts-v1.json"
        ).read_text()
    )
    facts = base["facts"]
    evidence = RecommendationEvidence(
        recommendation_id=facts["id"],
        run_id=facts["run_id"],
        facts_hash=canonical_hash(facts),
        status="COMPLETE",
        quant=OptimizationExplanationEvidence(**base["quant"]).seal(),
    ).seal()
    claims = build_claims(facts, evidence)
    ids = default_ids(claims, "Momentum 5, 10, 20 phiên của ACB, BID và CTG?")
    assert ids == ["features_scope_required"]
    assert "ít mã hoặc chỉ số hơn" in render_claims(claims, ids, concise=True)


def test_partial_features_remain_readable_without_views_or_end_date():
    facts, evidence = fixture_evidence()
    evidence["status"] = evidence["quant"]["status"] = "PARTIAL"
    evidence["quant"]["views"] = []
    evidence["quant"]["history_end_date"] = None
    claims = build_claims(facts, reseal(evidence))
    text = render_claims(claims, default_ids(claims, "RSI của ACB?"), concise=True)
    assert "55" in text and "None" not in text
    assert "chưa lưu ngày" in text.casefold()


def test_indicator_spelling_from_ui_routes_without_paid_intent():
    from chat_service.workflow import is_evidence_followup

    assert is_evidence_followup("RSI14 của ACB?")


@pytest.mark.parametrize("members,expected", [
    (["ACB", "BID", "VFF"], "Nhóm phòng thủ chiếm 100,00%, so với mức tối thiểu 15,00%"),
    ([], "Nhóm phòng thủ chiếm 0,00%"),
    (None, "Chưa đủ dữ kiện để đối chiếu tỷ trọng thực tế"),
])
def test_overview_uses_only_pinned_defensive_members_and_available_floor(members, expected):
    facts, evidence = fixture_evidence()
    limits = facts["constraints"]
    del limits["max_non_defensive_weight"]
    limits["defensive_asset_ids"] = members
    evidence["facts_hash"] = canonical_hash(facts)
    claims = build_claims(facts, reseal(evidence))
    answer = render_claims(claims, default_ids(claims), concise=True)
    assert expected in answer
