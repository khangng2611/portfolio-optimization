"""Offline contextual replies through the normal worker entry point."""

import json
import httpx
import pytest
from chat_service.workflow import Worker, intent_of
from test_chat import chat as chat_fixture, conversation, send
from test_chat_dialogue import last, configured
from test_chat_openai import response

chat = chat_fixture


@pytest.mark.parametrize(
    "text",
    ["Giúp tôi tạo đề xuất", "Tạo đề xuất MVO", "Tao de xuat", "Lập phương án đầu tư"],
)
def test_proposal_phrases_are_allocation(text):
    assert intent_of({"content": text}) == "allocation"


def test_contextual_reply_uses_actual_missing_fields_and_preserves_confirmation(
    chat, monkeypatch
):
    c, sessions, tools = chat
    seen = []

    def serve(request):
        body = json.loads(request.content)
        context = json.loads(body["input"])
        seen.append((body["text"]["format"]["name"], context))
        if "response" in body["text"]["format"]["name"]:
            assert context["state"]["type"] == "input_required"
            assert context["state"]["fields"] == ["strategy"]
            assert "capital_vnd" not in json.dumps(context)
            return httpx.Response(
                200,
                json=response(
                    {
                        "reply": "Mình sẽ giúp bạn chuẩn bị đề xuất. Bạn muốn chọn EW, MVO hay BL + ML?"
                    }
                ),
            )
        return httpx.Response(
            200,
            json=response(
                {
                    "intent": "allocation",
                    "strategy": "MVO" if context["content"] == "MVO nhé" else None,
                    "reference": "none",
                }
            ),
        )

    configured(monkeypatch, serve)
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "offline-context-test")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    cid = conversation(c, tools.summary["id"])
    send(c, cid, content="Giúp tôi tạo đề xuất", intent=None, strategy=None)
    assert Worker(sessions, tools).tick()
    assert last(c, cid)["content"].startswith("Mình sẽ giúp")
    send(c, cid, content="MVO nhé", intent=None, strategy=None)
    assert Worker(sessions, tools).tick()
    assert last(c, cid)["structured"]["type"] == "confirmation"
    assert not tools.allocations
    assert len(seen) == 3


@pytest.mark.parametrize(
    "reply",
    [
        "Lợi nhuận đạt 50%.",
        "Xem https://bad.example",
        "Đã chấp nhận đề xuất.",
        "Liên hệ user@example.org",
    ],
)
def test_invalid_contextual_prose_falls_back(chat, monkeypatch, reply):
    c, sessions, tools = chat
    configured(
        monkeypatch,
        lambda request: httpx.Response(200, json=response({"reply": reply})),
    )
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "offline-context-test")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    cid = conversation(c)
    send(c, cid, intent="help", strategy=None, content="Bạn có thể làm gì?")
    assert Worker(sessions, tools).tick()
    assert last(c, cid)["content"] != reply
    assert not tools.allocations


def test_no_new_budget_means_no_contextual_calls(chat, monkeypatch):
    c, sessions, tools = chat
    configured(monkeypatch, lambda _: pytest.fail("no call without new approval"))
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.delenv("KNOWLEDGE_PAID_APPROVAL", raising=False)
    cid = conversation(c)
    send(c, cid, intent="help", strategy=None, content="Bạn làm được gì?")
    assert Worker(sessions, tools).tick()


def test_dev_disabled_keeps_contextual_reply_offline(chat, monkeypatch):
    c, sessions, tools = chat
    configured(monkeypatch, lambda _: pytest.fail("consent revoked"))
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "offline-context-test")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    cid = conversation(c)
    send(c, cid, intent="help", strategy=None, content="Bạn làm được gì?")
    monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    assert Worker(sessions, tools).tick()


def load_context_cases():
    from pathlib import Path

    path = (
        Path(__file__).parents[1] / "fixtures/knowledge/eval-chat-context-vi-v2.jsonl"
    )
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize("case", load_context_cases(), ids=lambda case: case["id"])
def test_vietnamese_context_eval_offline(chat, monkeypatch, case):
    c, sessions, tools = chat
    response_calls = []
    turn = [0]

    def serve(request):
        body = json.loads(request.content)
        name = body["text"]["format"]["name"]
        if "response" in name:
            response_calls.append(json.loads(body["input"]))
            return httpx.Response(200, json=response({"reply": case["reply"]}))
        return httpx.Response(
            200,
            json=response(
                {
                    "intent": case["intents"][turn[0]],
                    "strategy": case.get("strategy") if turn[0] else None,
                    "reference": "none",
                }
            ),
        )

    configured(monkeypatch, serve)
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "offline-context-eval")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    # Real evidence integrity is tested elsewhere; this unit isolates dialogue.
    from test_chat_knowledge import candidates

    data = candidates()
    from hashlib import sha256

    passage = data["passages"][0]
    text = "MVO tìm sự đánh đổi giữa lợi nhuận kỳ vọng và phương sai danh mục."
    passage.update(
        claim_id="mvo-definition",
        document_title="MVO",
        text=text,
        text_hash=sha256(text.encode()).hexdigest(),
    )
    empty = data | {"passages": [], "reason": "NO_EVIDENCE"}
    original = tools.call
    monkeypatch.setattr(
        tools,
        "call",
        lambda job, name, args: (data if case.get("claim") else empty)
        if name == "retrieve_knowledge"
        else original(job, name, args),
    )
    cid = conversation(c, tools.summary["id"])
    if not case.get("developer_enabled", True):
        monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    for index, message in enumerate(case["messages"]):
        turn[0] = index
        send(c, cid, content=message, intent=None, strategy=None)
        assert Worker(sessions, tools).tick()
        result = last(c, cid)
        assert result["structured"]["type"] == case["types"][index]
        if result["structured"]["type"] == "knowledge":
            if case.get("claim"):
                assert result["content"] == text
            else:
                assert "Chưa có nguồn phù hợp" in result["content"]
        elif result["structured"]["type"] not in {"confirmation"} and case.get(
            "developer_enabled", True
        ):
            assert result["content"] == case["reply"]
    assert bool(response_calls) == (
        case.get("developer_enabled", True) and "knowledge" not in case["types"]
    )
    assert not tools.allocations
    if case.get("fields"):
        assert result["structured"]["fields"] == case["fields"]
    if "claim" in case:
        evidence = result["structured"]["knowledge"]
        assert bool(evidence["citations"]) == bool(case["claim"])


def test_response_schema_rejects_unknown_fields_and_keeps_usage(monkeypatch):
    from test_chat_openai import provider

    value = {"reply": "Mình giúp bạn.", "confirmed": True}
    result, meta = provider(
        monkeypatch, lambda _: httpx.Response(200, json=response(value))
    ).respond({})
    assert result is None and meta["reason"] == "UNVERIFIED_OUTPUT"
    assert meta["input_tokens"] == 123


def test_contextual_response_reuses_reservation_after_retry(chat, monkeypatch):
    from chat_service.llm import Dialogue
    from chat_service.queue import Queue

    c, sessions, tools = chat
    calls = []
    configured(
        monkeypatch,
        lambda _: (
            calls.append(True)
            or httpx.Response(
                200, json=response({"reply": "Bạn muốn mình giúp phần nào?"})
            )
        ),
    )
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "offline-context-retry")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    cid = conversation(c)
    send(c, cid, content="Bạn làm gì?", intent="help", strategy=None)
    job = Queue(sessions).claim()
    assert Dialogue(sessions).respond(job, {"type": "help"})[0]
    assert Dialogue(sessions).respond(job, {"type": "help"})[0]
    assert len(calls) == 1


def test_response_budget_exhaustion_creates_no_invocation(chat, monkeypatch):
    from chat_service.llm import Dialogue
    from chat_service.models import ProviderInvocation
    from chat_service.queue import Queue
    from sqlalchemy import select

    c, sessions, tools = chat
    configured(monkeypatch, lambda _: pytest.fail("budget too small"))
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "offline-small-budget")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.0001")
    cid = conversation(c)
    send(c, cid, content="Bạn làm gì?", intent="help", strategy=None)
    job = Queue(sessions).claim()
    assert (
        Dialogue(sessions).respond(job, {"type": "help"})[1]["reason"]
        == "ACCEPTANCE_BUDGET_EXHAUSTED"
    )
    with sessions() as db:
        assert not db.scalars(select(ProviderInvocation)).all()


def test_contextual_reply_still_runs_after_six_second_interpretation(chat, monkeypatch):
    c, sessions, tools = chat
    worker = Worker(sessions, tools)

    def serve(request):
        body = json.loads(request.content)
        if "response" in body["text"]["format"]["name"]:
            return httpx.Response(
                200, json=response({"reply": "Bạn muốn mình giúp phần nào?"})
            )
        worker.started -= 6
        return httpx.Response(
            200,
            json=response({"intent": "help", "strategy": None, "reference": "none"}),
        )

    configured(monkeypatch, serve)
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "offline-time-budget")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    cid = conversation(c)
    send(c, cid, content="Bạn có thể làm gì?", intent=None, strategy=None)
    assert worker.tick()
    assert last(c, cid)["content"] == "Bạn muốn mình giúp phần nào?"


@pytest.mark.parametrize("mode", ["openai_adapter", "disabled", "quota"])
def test_source_routing_uses_owner_target_or_requests_source(chat, monkeypatch, mode):
    from uuid import uuid4

    c, sessions, tools = chat
    pid = tools.summary["id"]
    tools.summary.update(scope="saved_target", accepted_target={
        "id": str(uuid4()), "recommendation_id": str(uuid4()), "accepted_at": "2026-11-24T05:00:00Z",
        "asset_ids": ["VFF", "AAA"], "weights": ["0.41", "0.59"],
    })
    called = []

    def serve(req):
        assert mode == "openai_adapter"
        body = json.loads(req.content)
        assert set(json.loads(body["input"])) == {"question", "has_portfolio", "has_recommendation", "pending_portfolio"}
        called.append(body["text"]["format"]["name"])
        return httpx.Response(200, json=response({"source": "saved_target"}))

    configured(monkeypatch, serve)
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    if mode == "disabled":
        monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    if mode == "quota":
        monkeypatch.setenv("CHAT_LLM_DAILY_CALL_LIMIT", "0")
    cid = conversation(c, pid)
    for question in ["Phân bổ mà tôi đã chấp nhận là gì?", "Mục tiêu của tôi trong danh mục này là gì?"]:
        send(c, cid, content=question, intent=None, strategy=None)
        assert Worker(sessions, tools).tick()
        msg = last(c, cid)
        if mode != "openai_adapter" and question.startswith("Mục tiêu"):
            assert msg["structured"]["fields"] == ["source"]
            send(c, cid, content="Mình muốn xem bản đã lưu", strategy=None, intent=None)
            assert Worker(sessions, tools).tick()
            msg = last(c, cid)
        assert msg["structured"]["facts"]["accepted_target"] == tools.summary["accepted_target"]
        assert "VFF 41,00%" in msg["content"]
    assert bool(called) == (mode == "openai_adapter")
    assert not tools.allocations


@pytest.mark.parametrize(("question", "expected"), [
    ("Nếu tôi đã lưu phân bổ thì có tự giao dịch không?", "knowledge"),
    ("Tạo đề xuất mới cho danh mục đã lưu của tôi", "allocation"),
    ("Mục tiêu đã lưu trong hồ sơ rủi ro là gì?", "profile"),
    ("Mục tiêu đã lưu khác gì với tài sản đang nắm giữ?", "knowledge"),
])
def test_saved_words_do_not_override_object_or_action(question, expected):
    assert intent_of({"content": question}) == expected


@pytest.mark.parametrize(("question", "expected"), [
    ("Đề xuất đã lưu của mình có gì?", "explain"),
    ("Phân bổ trong bản nháp đã lưu gồm gì?", "source_choice"),
    ("Cơ cấu lần trước mình bấm đồng ý gồm gì?", "source_choice"),
])
def test_saved_proposal_and_accepted_allocation_are_distinct(question, expected):
    assert intent_of({"content": question}) == expected


@pytest.mark.parametrize("output", [{"source": "allocation"}, {"source": "saved_target", "portfolio_id": "other"}])
def test_source_classifier_cannot_supply_an_action_or_record(chat, monkeypatch, output):
    c, sessions, tools = chat
    configured(monkeypatch, lambda _: httpx.Response(200, json=response(output)))
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.5")
    cid = conversation(c, tools.summary["id"])
    send(c, cid, intent=None, strategy=None, content="Mục tiêu đang nói ở đây là gì?")
    assert Worker(sessions, tools).tick()
    card = last(c, cid)["structured"]
    assert card["fields"] == ["source"]
    assert card["dialogue"]["reason"] == "UNVERIFIED_OUTPUT"
    assert not tools.allocations


def test_dated_saved_target_does_not_answer_with_current_target(chat):
    c, sessions, tools = chat
    tools.summary.update(scope="saved_target", accepted_target=None)
    cid = conversation(c, tools.summary["id"])
    send(c, cid, intent=None, strategy=None, content="Mục tiêu tôi đã lưu ngày 01/09/2026 gồm gì?")
    assert Worker(sessions, tools).tick()
    message = last(c, cid)
    assert message["structured"]["fields"] == ["recommendation_id"]
    assert "lịch sử" in message["content"]
