"""Developer configuration is the authority for outbound Chat calls."""

import pytest

from chat_service.llm import Dialogue, InvocationLedger
from chat_service.queue import Queue
from chat_service.models import Conversation
from test_chat import chat as chat_fixture, conversation, send, headers

chat = chat_fixture


def test_user_cannot_change_provider_policy(chat):
    c, sessions, _ = chat
    cid = conversation(c)
    for value in (True, False):
        response = c.post(
            f"/api/v1/conversations/{cid}/preferences",
            headers=headers(),
            json={"llm_consent": value, "consent_version": 2},
        )
        assert response.status_code == 403
    with sessions() as db:
        assert db.get(Conversation, cid).llm_consent is False
    assert (
        c.post(
            f"/api/v1/conversations/{cid}/preferences",
            headers=headers("bob"),
            json={"llm_consent": True},
        ).status_code
        == 404
    )
    assert (
        c.post(
            "/api/v1/conversations", headers=headers(), json={"llm_consent": True}
        ).status_code
        == 403
    )


def test_dev_policy_applies_to_old_conversations_without_rewriting_them(
    chat, monkeypatch
):
    c, sessions, _ = chat
    cid = conversation(c)
    send(c, cid)
    job = Queue(sessions).claim()
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-only")
    assert Dialogue(sessions).enabled
    assert Dialogue(sessions).context(job)[0] is not None
    calls = []
    assert InvocationLedger(sessions).invoke(
        job,
        "intent",
        lambda: (calls.append(True) or {"intent": "help"}, {"reason": "UNIT"}),
    )[0]
    assert calls == [True]
    with sessions() as db:
        assert db.get(Conversation, cid).llm_consent is False
    monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    assert not Dialogue(sessions).enabled
    assert Dialogue(sessions).context(job) == (None, None)
    assert (
        InvocationLedger(sessions).invoke(
            job, "response", lambda: (_ for _ in ()).throw(AssertionError("disabled"))
        )[1]["reason"]
        == "DEVELOPER_DISABLED"
    )


def test_embedding_flag_is_independent_of_legacy_consent(chat, monkeypatch):
    c, sessions, _ = chat
    cid = conversation(c)
    with sessions.begin() as db:
        row = db.get(Conversation, cid)
        row.llm_consent = True
        row.consent_version = 2
    send(c, cid)
    job = Queue(sessions).claim()
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.delenv("CHAT_QUERY_EMBEDDINGS_ENABLED", raising=False)
    assert (
        InvocationLedger(sessions).invoke(
            job,
            "query_embedding",
            lambda: (_ for _ in ()).throw(AssertionError("embedding disabled")),
        )[1]["reason"]
        == "EMBEDDINGS_DISABLED"
    )


def test_developer_call_cap_can_expand_within_reserved_money_budget(chat, monkeypatch):
    from uuid import uuid4
    from chat_service.models import ProviderInvocation

    c, sessions, _ = chat
    cid = conversation(c)
    send(c, cid)
    job = Queue(sessions).claim()
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit-followup-budget")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    monkeypatch.setenv("CHAT_LLM_DAILY_CALL_LIMIT", "60")
    with sessions.begin() as db:
        for _ in range(20):
            db.add(
                ProviderInvocation(
                    job_id=str(uuid4()),
                    purpose="intent",
                    owner_key=job.owner_key,
                    budget_id="unit-followup-budget",
                    reserved_usd="0.0017",
                )
            )
    ledger = InvocationLedger(sessions)
    assert (
        ledger.invoke(
            job, "response", lambda: ({"reply": "ok"}, {"reason": "UNIT"}), rag=True
        )[1]["reason"]
        == "ACCEPTANCE_BUDGET_EXHAUSTED"
    )
    monkeypatch.setenv("CHAT_LLM_APPROVAL_CALL_LIMIT", "40")
    assert ledger.invoke(
        job, "response", lambda: ({"reply": "ok"}, {"reason": "UNIT"}), rag=True
    )[0] == {"reply": "ok"}


@pytest.mark.parametrize("cap", ["invalid", "0", "-1"])
def test_invalid_approval_cap_blocks_new_spending(chat, monkeypatch, cap):
    c, sessions, _ = chat
    cid = conversation(c)
    send(c, cid)
    job = Queue(sessions).claim()
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit-invalid-cap")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    monkeypatch.setenv("CHAT_LLM_APPROVAL_CALL_LIMIT", cap)

    def forbidden():
        raise AssertionError("Invalid quota must not invoke a provider")

    assert (
        InvocationLedger(sessions).invoke(job, "response", forbidden, rag=True)[1][
            "reason"
        ]
        == "ACCEPTANCE_BUDGET_EXHAUSTED"
    )
