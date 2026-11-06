from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json

import httpx
import pytest

from portfolio_contracts import utcnow
from chat_service.models import Job
from chat_service.queue import Queue
from test_chat import chat as chat_fixture, conversation, headers, send, run
from test_chat_openai import response

chat = chat_fixture


def consent(c, cid, value=True, user="alice"):
    return c.post(
        f"/api/v1/conversations/{cid}/preferences",
        headers=headers(user),
        json={"llm_consent": value},
    )


def configured(monkeypatch, handler):
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )


def last(c, cid):
    return c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1]


def test_consent_defaults_off_and_is_owner_scoped(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    assert (
        c.get(f"/api/v1/conversations/{cid}", headers=headers()).json()["llm_consent"]
        is False
    )
    assert consent(c, cid, user="bob").status_code == 404
    assert consent(c, cid).json()["llm_consent"] is True
    assert consent(c, cid, False).json()["llm_consent"] is False


def test_llm_allocation_still_requires_structured_confirmation(chat, monkeypatch):
    c, s, t = chat
    captured = []

    def serve(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=response(
                {"intent": "allocation", "strategy": "MVO", "reference": "none"}
            ),
        )

    configured(monkeypatch, serve)
    cid = conversation(c, t.summary["id"])
    assert consent(c, cid).status_code == 200
    receipt = send(
        c,
        cid,
        content="Chia vốn theo mean variance giúp tôi",
        intent=None,
        strategy=None,
    ).json()
    assert run(s, t)
    assert not t.allocations
    message = last(c, cid)
    assert message["structured"]["type"] == "confirmation"
    assert message["structured"]["input"]["strategy"] == "MVO"
    assert message["structured"]["dialogue"]["reason"] == "VERIFIED"
    assert len(captured) == 1
    assert (
        c.get(receipt["status_url"], headers=headers()).json()["status"]
        == "WAITING_INPUT"
    )


def test_strategy_followup_uses_same_conversation_context(chat, monkeypatch):
    c, s, t = chat
    captured = []

    def serve(request):
        body = json.loads(request.content)
        captured.append(json.loads(body["input"]))
        return httpx.Response(
            200,
            json=response(
                {
                    "intent": "allocation",
                    "strategy": "MVO" if len(captured) > 1 else None,
                    "reference": "none",
                }
            ),
        )

    configured(monkeypatch, serve)
    other = conversation(c, t.summary["id"])
    send(c, other, content="private other conversation")
    run(s, t)
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    send(c, cid, content="Giúp tôi chia vốn", intent=None, strategy=None)
    run(s, t)
    assert last(c, cid)["structured"]["fields"] == ["strategy"]
    send(c, cid, content="MVO nhé", intent=None, strategy=None)
    run(s, t)
    assert last(c, cid)["structured"]["type"] == "confirmation"
    assert captured[-1]["previous"]["fields"] == ["strategy"]
    assert "private other" not in json.dumps(captured)
    assert not t.allocations


def test_revoked_consent_and_explicit_intents_do_not_spend(chat, monkeypatch):
    c, s, t = chat
    configured(monkeypatch, lambda _: pytest.fail("no provider call allowed"))
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    send(c, cid)
    run(s, t)  # explicit UI intent is authoritative, no interpretation
    send(c, cid, content="Do something", intent=None, strategy=None)
    consent(c, cid, False)
    run(s, t)
    assert last(c, cid)["structured"]["type"] == "help"


def test_paid_plan_replay_uses_saved_output_and_global_budget_survives_restart(
    chat, monkeypatch
):
    from chat_service.llm import InvocationLedger

    c, s, t = chat
    monkeypatch.setenv("CHAT_LLM_DAILY_CALL_LIMIT", "1")
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    send(c, cid)
    job = Queue(s).claim()
    ledger = InvocationLedger(s)
    result = {"intent": "profile", "strategy": None, "reference": "none"}
    calls = []

    def call():
        calls.append(1)
        return result, {"reason": "VERIFIED", "input_tokens": 100, "output_tokens": 20}

    assert ledger.invoke(job, "intent", call)[0] == result
    assert InvocationLedger(s).invoke(job, "intent", call)[0] == result
    assert len(calls) == 1
    cid2 = conversation(c, t.summary["id"])
    consent(c, cid2)
    send(c, cid2)
    second = Queue(s).claim()
    assert (
        ledger.invoke(second, "intent", call)[1]["reason"] == "DAILY_BUDGET_EXHAUSTED"
    )
    assert len(calls) == 1


def test_uncertain_paid_call_is_not_repeated_after_crash(chat):
    from chat_service.llm import InvocationLedger

    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    send(c, cid)
    q = Queue(s)
    old = q.claim()

    def crash():
        raise RuntimeError("simulated crash before provider receipt commit")

    with pytest.raises(RuntimeError):
        InvocationLedger(s).invoke(old, "intent", crash)
    with s.begin() as db:
        db.get(Job, old.id).lease_until = utcnow() - timedelta(seconds=1)
    new = q.claim()
    out, meta = InvocationLedger(s).invoke(
        new, "intent", lambda: pytest.fail("must not repeat")
    )
    assert out is None and meta["reason"] == "PROVIDER_BUDGET_EXHAUSTED"
    assert (
        InvocationLedger(s).invoke(old, "explanation", lambda: pytest.fail("fenced"))[
            1
        ]["reason"]
        == "LEASE_LOST"
    )


def test_concurrent_workers_respect_global_daily_cap(chat, monkeypatch):
    from chat_service.llm import InvocationLedger

    c, s, t = chat
    monkeypatch.setenv("CHAT_LLM_DAILY_CALL_LIMIT", "1")
    for _ in range(4):
        cid = conversation(c, t.summary["id"])
        consent(c, cid)
        send(c, cid)
    jobs = [Queue(s).claim() for _ in range(4)]
    calls = []

    def work(job):
        def paid():
            calls.append(job.id)
            return {}, {"reason": "VERIFIED"}

        return InvocationLedger(s).invoke(job, "intent", paid)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(work, jobs))
    assert len(calls) == 1
    assert sum(meta["reason"] == "DAILY_BUDGET_EXHAUSTED" for _, meta in results) == 3


def test_invalid_model_confirmation_falls_back_without_mutation(chat, monkeypatch):
    c, s, t = chat
    configured(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json=response(
                {
                    "intent": "allocation",
                    "strategy": "MVO",
                    "reference": "none",
                    "confirmed": True,
                }
            ),
        ),
    )
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    send(c, cid, content="Đồng ý làm hết", intent=None, strategy=None)
    run(s, t)
    assert not t.allocations and last(c, cid)["structured"]["type"] == "help"


def test_model_cannot_pick_strategy_without_user_evidence(chat, monkeypatch):
    c, s, t = chat
    configured(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json=response(
                {"intent": "allocation", "strategy": "MVO", "reference": "none"}
            ),
        ),
    )
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    send(c, cid, content="Giúp tôi chia vốn", intent=None, strategy=None)
    run(s, t)
    assert last(c, cid)["structured"]["fields"] == ["strategy"]
    assert not t.allocations


def test_strategy_extraction_accepts_ui_bl_plus_ml_spelling(chat, monkeypatch):
    c, s, t = chat
    configured(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            json=response(
                {"intent": "allocation", "strategy": "BL_ML", "reference": "none"}
            ),
        ),
    )
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    send(c, cid, content="BL + ML nhé", intent=None, strategy=None)
    run(s, t)
    assert last(c, cid)["structured"]["type"] == "confirmation"
    assert last(c, cid)["structured"]["input"]["strategy"] == "BL_ML"
    assert not t.allocations


def test_job_reports_all_durable_provider_usage_including_interpretation(
    chat, monkeypatch
):
    from chat_service.llm import InvocationLedger

    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    receipt = send(c, cid).json()
    job = Queue(s).claim()
    ledger = InvocationLedger(s)
    for purpose in ("intent", "explanation"):
        ledger.invoke(
            job,
            purpose,
            lambda: (
                {},
                {"reason": "VERIFIED", "input_tokens": 100, "output_tokens": 20},
            ),
        )
    status = c.get(receipt["status_url"], headers=headers()).json()
    assert {p["purpose"] for p in status["provider_usage"]} == {"intent", "explanation"}
    assert sum(p["input_tokens"] for p in status["provider_usage"]) == 200
    assert c.get(receipt["status_url"], headers=headers("bob")).status_code == 404


def test_revoked_owner_grant_blocks_paid_interpretation(chat, monkeypatch):
    from chat_service.models import ProviderInvocation
    from sqlalchemy import select, func

    c, s, t = chat
    calls = []

    def serve(request):
        calls.append(1)
        return httpx.Response(
            200,
            json=response({"intent": "profile", "strategy": None, "reference": "none"}),
        )

    configured(monkeypatch, serve)
    cid = conversation(c, t.summary["id"])
    consent(c, cid)
    receipt = send(
        c, cid, content="Nhắc lại mức chịu rủi ro của tôi", intent=None, strategy=None
    ).json()
    t.expired = True
    run(s, t)
    assert (
        c.get(receipt["status_url"], headers=headers()).json()["status"]
        == "AUTHORIZATION_REQUIRED"
    )
    assert not calls
    with s() as db:
        assert db.scalar(select(func.count()).select_from(ProviderInvocation)) == 0
