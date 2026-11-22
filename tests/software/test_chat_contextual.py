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
    data["passages"][0]["claim_id"] = "mvo-definition"
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
        if result["structured"]["type"] not in {"confirmation"} and case.get(
            "developer_enabled", True
        ):
            assert result["content"] == case["reply"]
    assert bool(response_calls) == case.get("developer_enabled", True)
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
