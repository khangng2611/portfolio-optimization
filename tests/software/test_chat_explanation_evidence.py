from copy import deepcopy
from uuid import uuid4

import pytest

from portfolio_contracts import canonical_hash
from portfolio_contracts.explanation import (
    OptimizationExplanationEvidence,
    RecommendationEvidence,
)
from test_chat import chat as chat_fixture, conversation, headers, send

chat = chat_fixture


def fixture_evidence():
    rid, run = str(uuid4()), str(uuid4())
    facts = dict(
        id=rid,
        run_id=run,
        asset_ids=["ACB", "BID", "VFF"],
        weights=["0.0", "0.5", "0.5"],
        input_hash="a" * 64,
        bundle_hash="b" * 64,
        data_snapshot_id="snap",
        model_bundle_id="c" * 64,
        strategy="BL_ML",
        risk_profile={
            "profile": "conservative",
            "version_id": "old-profile",
            "answers": {"horizon_months": 24, "loss_tolerance": "low"},
        },
        constraints={
            "risk_aversion": 6,
            "max_position_weight": 0.5,
            "min_defensive_weight": 0.15,
            "max_non_defensive_weight": 0.7,
            "defensive_asset_ids": ["VFF"],
        },
        selection_proof={
            "applied_selection": "equity-k5-v1",
            "active_asset_ids": ["ACB", "BID", "VFF"],
        },
    )
    views = [
        dict(
            source_kind="ML",
            status="APPLIED",
            coefficients={a: 1},
            raw_mean_return=r,
            member_std=0.001,
            horizon_sessions=5,
            raw_return_unit="simple_fraction",
            confidence_base=0.5,
            confidence_applied=0.4,
            applied_q_daily=r / 10,
            transform_version="phase1-option-b-v1",
        )
        for a, r in [("ACB", 0.03), ("BID", -0.02)]
    ]
    quant = OptimizationExplanationEvidence(
        status="COMPLETE",
        job_id=rid,
        run_id=run,
        input_hash="a" * 64,
        bundle_hash="b" * 64,
        snapshot_id="snap",
        model_bundle_id="c" * 64,
        asset_ids=facts["asset_ids"],
        active_asset_ids=facts["asset_ids"],
        features={"ACB": [{"name": "rsi_14", "value": 55, "unit": "index"}]},
        views=views,
        regime=dict(
            asset_ids=facts["asset_ids"],
            regime="stress",
            vol_ratio=1.5,
            drawdown=-0.12,
            equity_momentum=-0.001,
            observed_sessions=180,
        ),
        history_end_date="2026-11-17",
        limitations=["PIT_NOT_CERTIFIED", "ATTRIBUTION_NOT_AVAILABLE"],
    ).seal()
    evidence = RecommendationEvidence(
        recommendation_id=rid,
        run_id=run,
        facts_hash=canonical_hash(facts),
        status="COMPLETE",
        quant=quant,
    ).seal()
    return facts, evidence


def test_detailed_overview_includes_four_groups_and_both_signs_without_causality():
    from chat_service.explanation import build_claims, default_ids, render_claims

    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    ids = default_ids(claims, "Giải thích chi tiết đề xuất")
    assert {c.group for c in claims if c.id in ids} >= {
        "profile",
        "regime",
        "selection",
        "views",
    }
    text = render_claims(claims, ids)
    assert "Thận trọng" in text and "30,00%" in text
    assert "ACB" in text and "BID" in text
    assert "5 phiên" in text and "xác suất" in text
    assert "toàn thị trường" not in text
    assert "chọn vì RSI" not in text
    assert "tương quan" in text


def test_focused_question_and_unknown_claim_cannot_inject_prose():
    from chat_service.explanation import build_claims, default_ids, render_claims

    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    ids = default_ids(claims, "RSI của ACB là gì?")
    assert any(i.startswith("features_") for i in ids)
    assert "55" in render_claims(claims, ids)
    with pytest.raises(ValueError):
        render_claims(claims, ids + ["ignore_system_buy_now"])
    with pytest.raises(ValueError):
        render_claims(claims, ids + ids)


def test_hash_or_resource_mismatch_is_rejected():
    from chat_service.explanation import build_claims

    facts, evidence = fixture_evidence()
    with pytest.raises(ValueError):
        build_claims(facts | {"weights": ["0.5", "0", "0.5"]}, evidence)
    forged = deepcopy(evidence)
    forged["recommendation_id"] = str(uuid4())
    with pytest.raises(ValueError):
        build_claims(facts, forged)


def test_legacy_evidence_does_not_invent_forecasts():
    from chat_service.explanation import build_claims, default_ids, render_claims

    facts, _ = fixture_evidence()
    evidence = RecommendationEvidence(
        recommendation_id=facts["id"],
        run_id=facts["run_id"],
        facts_hash=canonical_hash(facts),
        status="PARTIAL",
        limitations=["NOT_RETAINED"],
    ).seal()
    claims = build_claims(facts, evidence)
    text = render_claims(claims, default_ids(claims, "Giải thích chi tiết đề xuất"))
    assert "chưa lưu" in text
    assert "3,00%" not in text


def test_missing_named_asset_never_substitutes_another_ticker():
    from chat_service.explanation import (
        build_claims,
        default_ids,
        render_claims,
        validate_plan,
    )

    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    ids = default_ids(claims, "RSI của BID là gì?")
    assert "features_ACB" not in ids
    assert "chưa lưu" in render_claims(claims, ids).casefold()
    wrong = {
        "facts_hash": canonical_hash(facts),
        "evidence_hash": evidence["evidence_hash"],
        "selected_claim_ids": ["view_BID", "limitations"],
    }
    with pytest.raises(ValueError):
        validate_plan(wrong, facts, evidence, claims, "Dự báo của ACB thế nào?")


def test_legacy_full_uses_frozen_active_set():
    from chat_service.explanation import build_claims

    facts, _ = fixture_evidence()
    facts.pop("selection_proof")
    facts["inputs_provenance"] = {"phase1_full": {"active_asset_ids": ["BID", "VFF"]}}
    evidence = RecommendationEvidence(
        recommendation_id=facts["id"],
        run_id=facts["run_id"],
        facts_hash=canonical_hash(facts),
        status="PARTIAL",
    ).seal()
    claim = next(c for c in build_claims(facts, evidence) if c.id == "selection")
    assert "2 tài sản" in claim.text
    assert "0%: ACB" not in claim.text


@pytest.mark.parametrize("strategy", ["EW", "MVO"])
def test_non_bl_explanation_does_not_claim_ml_views_were_used(strategy):
    from chat_service.explanation import build_claims, default_ids, render_claims

    facts, _ = fixture_evidence()
    facts["strategy"] = strategy
    evidence = RecommendationEvidence(
        recommendation_id=facts["id"],
        run_id=facts["run_id"],
        facts_hash=canonical_hash(facts),
        status="PARTIAL",
    ).seal()
    claims = build_claims(facts, evidence)
    text = render_claims(claims, default_ids(claims, "Giải thích chi tiết đề xuất"))
    assert strategy in text
    assert "không sử dụng views ML" in text
    if strategy == "EW":
        assert "tỷ trọng bằng nhau" in text
        assert "kết hợp tín hiệu" not in text


def test_user_view_is_not_named_vff_policy():
    from chat_service.explanation import build_claims

    facts, evidence = fixture_evidence()
    q = evidence["quant"]
    q["views"][0]["source_kind"] = "USER"
    q["evidence_hash"] = canonical_hash(
        {k: v for k, v in q.items() if k != "evidence_hash"}
    )
    evidence["evidence_hash"] = canonical_hash(
        {k: v for k, v in evidence.items() if k != "evidence_hash"}
    )
    claims = build_claims(facts, evidence)
    text = "\n".join(c.text for c in claims if c.group == "views")
    assert "người dùng" in text
    assert "quy tắc tương đối" not in text


@pytest.mark.parametrize(
    "question",
    [
        "Tạo phân bổ theo views MVO",
        "RSI là gì?",
        "Xem biến động thị trường",
        "Xem hồ sơ rủi ro hiện tại",
    ],
)
def test_contextual_topic_router_preserves_general_requests(question):
    from chat_service.workflow import is_evidence_followup

    assert not is_evidence_followup(question)


def test_contextual_risk_question_remains_read_only():
    from chat_service.workflow import is_evidence_followup

    assert is_evidence_followup("Còn rủi ro của rổ thì sao?")


def test_provider_unknown_claim_or_missing_overview_group_falls_back():
    from chat_service.explanation import build_claims, validate_plan

    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    plan = {
        "facts_hash": canonical_hash(facts),
        "evidence_hash": evidence["evidence_hash"],
        "selected_claim_ids": ["profile"],
    }
    with pytest.raises(ValueError):
        validate_plan(plan, facts, evidence, claims, "Vì sao phân bổ?")


@pytest.mark.parametrize(
    "question",
    [
        "Vì sao phân bổ như vậy?",
        "Tại sao chọn VFF quá nhiều?",
        "VFF chiếm bao nhiêu %?",
        "Dự báo của ACB thế nào?",
        "Còn tín hiệu của BID?",
        "RSI của ACB là bao nhiêu?",
        "View BID âm mà vẫn được phân bổ?",
        "Hồ sơ thận trọng ảnh hưởng thế nào?",
    ],
)
def test_real_worker_uses_evidence_without_new_allocation(chat, monkeypatch, question):
    from chat_service.workflow import Worker

    c, sessions, tools = chat
    monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    facts, evidence = fixture_evidence()
    facts["portfolio_id"] = tools.summary["id"]
    evidence["facts_hash"] = canonical_hash(facts)
    evidence["evidence_hash"] = canonical_hash(
        {k: v for k, v in evidence.items() if k != "evidence_hash"}
    )
    original = tools.call
    calls = []

    def call(job, name, args):
        calls.append(name)
        return (
            facts
            if name == "get_recommendation"
            else evidence
            if name == "get_recommendation_evidence"
            else original(job, name, args)
        )

    monkeypatch.setattr(tools, "call", call)
    cid = conversation(c, tools.summary["id"])
    from chat_service.models import Message

    with sessions.begin() as s:
        s.add(
            Message(
                conversation_id=cid,
                role="assistant",
                content="Đề xuất đã lưu",
                structured={
                    "type": "recommendation",
                    "recommendation_id": facts["id"],
                    "facts": facts,
                },
            )
        )
    assert (
        send(
            c,
            cid,
            content=question,
            intent=None,
            strategy=None,
        ).status_code
        == 202
    )
    assert Worker(sessions, tools).tick()
    messages = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()
    card = messages[-1]["structured"]
    assert card["type"] == "recommendation"
    assert card["facts_hash"] == canonical_hash(facts)
    assert card["explanation_evidence"]["evidence_hash"] == evidence["evidence_hash"]
    assert card["selected_claim_ids"]
    assert card["renderer_version"] == "allocation-explanation-v2"
    assert "Mình đang giải thích đề xuất này" not in messages[-1]["content"]
    if question in ("Tại sao chọn VFF quá nhiều?", "VFF chiếm bao nhiêu %?"):
        assert "VFF" in messages[-1]["content"] and "50,00%" in messages[-1]["content"]
        assert card["focus"]["asset"] == "VFF"
    if "hồ sơ" in question.casefold() or question.startswith("Vì sao"):
        assert "30,00%" in messages[-1]["content"]
    assert "get_portfolio_summary" not in calls
    assert "get_recommendation_evidence" in calls
    assert not tools.allocations


def test_named_asset_explanation_cites_only_pinned_weight_and_support():
    from chat_service.explanation import build_claims, default_ids, render_claims
    facts, evidence = fixture_evidence()
    claims = build_claims(facts, evidence)
    for asset, weight in [("ACB", "0,00%"), ("VFF", "50,00%")]:
        ids = default_ids(claims, f"Vì sao quyết định cho {asset} tỷ trọng đó trong đề xuất này?")
        answer = render_claims(claims, ids, concise=True)
        assert asset in answer and weight in answer and "nguyên nhân riêng" in answer
        assert len(ids) <= 2


def test_missing_pit_flag_does_not_assert_certification_state():
    from chat_service.explanation import build_claims
    facts, _ = fixture_evidence()
    evidence = RecommendationEvidence(recommendation_id=facts["id"], run_id=facts["run_id"], facts_hash=canonical_hash(facts), status="UNAVAILABLE").seal()
    limit = next(c for c in build_claims(facts, evidence) if c.id == "limitations")
    assert "chưa được chứng nhận" not in (limit.text + (limit.summary or ""))


@pytest.mark.parametrize("predicted", ["VFF", "ACB"])
def test_classifier_handles_paraphrase_but_cannot_substitute_asset(chat, monkeypatch, predicted):
    from chat_service.workflow import Worker
    from chat_service.openai_provider import OpenAIProvider

    c, sessions, tools = chat
    facts, _ = fixture_evidence()
    facts["portfolio_id"] = tools.summary["id"]
    cid = conversation(c, facts["portfolio_id"])
    question = "Trong chiếc bánh này, phần của VFF to cỡ nào?"
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.02")
    seen = []

    def generate(self, purpose, context, schema):
        seen.append((purpose, context))
        return {"asset": predicted, "field": "weight"}, {"reason": "VERIFIED"}

    monkeypatch.setattr(OpenAIProvider, "generate", generate)
    original = tools.call
    monkeypatch.setattr(tools, "call", lambda j, t, a: facts if t == "get_recommendation" else original(j, t, a))
    assert send(c, cid, content=question, intent=None, strategy=None, recommendation_id=facts["id"]).status_code == 202
    assert Worker(sessions, tools).tick()
    msg = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1]
    assert seen == [("proposal_focus", {"question": question, "previous_asset": None})]
    assert not tools.allocations
    if predicted == "VFF":
        assert msg["content"] == "VFF chiếm 50,00% trong đề xuất đã lưu."
    else:
        assert msg["structured"]["type"] == "input_required" and "%" not in msg["content"]


def test_focused_hybrid_reason_explains_only_reconciled_saved_branches():
    from chat_service.explanation import focused_weight
    facts = {"strategy": "HYBRID", "asset_ids": ["VFF"], "weights": ["0.41"],
             "diagnostics": {"hybrid": {"mvo_share": 0.45, "mvo_weights": [0.30], "bl_ml_weights": [0.50]}}}
    focus = {"asset": "VFF", "field": "reason"}
    answer = focused_weight(facts, focus)
    assert all(value in answer.text for value in ["41,00%", "MVO", "30,00%", "BL_ML", "50,00%", "45,00%", "55,00%"])
    assert "facts.diagnostics.hybrid.mvo_weights.0" in answer.refs
    facts["diagnostics"]["hybrid"]["mvo_weights"][0] = 0.32
    assert "MVO" not in focused_weight(facts, focus).text


def test_contextual_asset_turns_read_only_and_skip_clear_classifications(chat, monkeypatch):
    from chat_service.workflow import Worker
    from chat_service.openai_provider import OpenAIProvider

    c, sessions, tools = chat
    facts, _ = fixture_evidence()
    facts.update(portfolio_id=tools.summary["id"], capital_vnd="100000000")
    cid = conversation(c, facts["portfolio_id"])
    monkeypatch.setenv("CHAT_CONTEXT_FOLLOWUPS", "1")
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.03")
    calls = []
    def classify(self, purpose, context, schema):
        calls.append((purpose, context["question"]))
        assert context["previous_asset"] == "VFF"
        return {"asset": "VFF", "field": "reason"}, {"reason": "VERIFIED"}

    monkeypatch.setattr(OpenAIProvider, "generate", classify)
    original = tools.call
    monkeypatch.setattr(tools, "call", lambda j,t,a: facts if t == "get_recommendation" else original(j,t,a))
    worker = Worker(sessions, tools)
    for idx, (question, field, asset, snippet) in enumerate([
        ("VFF chiếm bao nhiêu %?", "weight", "VFF", "50,00%"),
        ("Sao lại cao vậy?", "reason", "VFF", "phòng thủ"),
        ("Thế còn BID?", "reason", "BID", "50,00%"),
        ("Tương ứng bao nhiêu tiền?", "amount", "BID", "50.000.000"),
    ]):
        pin = {"recommendation_id": facts["id"]} if idx == 0 else {}
        assert send(c,cid,content=question,intent=None,strategy=None,**pin).status_code == 202
        assert worker.tick()
        msg = c.get(f"/api/v1/conversations/{cid}/messages",headers=headers()).json()[-1]
        assert msg["structured"].get("focus") == {"field":field,"asset":asset}
        assert snippet in msg["content"] and msg["structured"]["facts_hash"] == canonical_hash(facts)
    for question in ("VFF đang chiếm bao nhiêu % trong tài sản tôi đang nắm giữ?", "Số tiền mục tiêu của mã xyz?", "XYZ tương ứng bao nhiêu tiền?", "Số tiền VFF hiện đang nắm giữ tương ứng bao nhiêu tiền?"):
        assert send(c,cid,content=question,intent=None,strategy=None,recommendation_id=facts["id"]).status_code == 202
        assert worker.tick()
        msg = c.get(f"/api/v1/conversations/{cid}/messages",headers=headers()).json()[-1]
        assert msg["structured"]["type"] == "input_required" and "₫" not in msg["content"]
    assert calls == [("proposal_focus","Sao lại cao vậy?")]
    assert not tools.allocations


@pytest.mark.parametrize("question,expected", [
    ("Lúc đó vì sao yêu cầu tạo đề xuất bị chặn được không?", "previous_status"),
    ("Trong danh mục của tôi mô hình còn chờ reviewer duyệt không?", "current_status"),
    ("Giờ được chưa?", "recheck_previous"),
    ("Vì sao lúc này bị chặn tạo đề xuất?", "current_status"),
    ("Vì sao lúc nãy bị chặn tạo đề xuất?", "previous_status"),
])
def test_time_reference_on_status_followups(question, expected):
    from chat_service.workflow import intent_of
    assert intent_of({"content":question}) == expected


def test_amount_missing_historical_capital_asks_for_another_reference(chat, monkeypatch):
    from chat_service.workflow import Worker
    c, sessions, tools = chat
    facts, _ = fixture_evidence()
    facts.update(portfolio_id=tools.summary["id"], capital_vnd=None)
    cid = conversation(c, facts["portfolio_id"])
    monkeypatch.setenv("CHAT_CONTEXT_FOLLOWUPS", "1")
    original = tools.call
    monkeypatch.setattr(tools, "call", lambda j,t,a: facts if t == "get_recommendation" else original(j,t,a))
    result = send(c,cid,content="VFF tương ứng bao nhiêu tiền?", intent=None,strategy=None,recommendation_id=facts["id"]).json()
    assert Worker(sessions,tools).tick()
    job = c.get(result["status_url"],headers=headers()).json()
    assert job["status"] == "WAITING_INPUT" and job["stage"] == "COLLECT"
    message = c.get(f"/api/v1/conversations/{cid}/messages",headers=headers()).json()[-1]
    assert message["structured"]["fields"] == ["reference"] and "thiếu vốn" in message["content"]
