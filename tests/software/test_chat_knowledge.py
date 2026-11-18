"""Injected provider/owner tests. Live acceptance is separately exercised over HTTP."""

from copy import deepcopy
from uuid import uuid4
import pytest
from portfolio_contracts import canonical_hash
from chat_service.models import Conversation
from chat_service.workflow import Worker, intent_of
from test_chat import chat as chat_fixture, conversation, headers, send

chat = chat_fixture


def candidates():
    import hashlib

    text = "EW chia đều tỷ trọng giữa các tài sản trong tập đầu vào."
    return {
        "corpus_id": str(uuid4()),
        "corpus_version": "knowledge-vi-v1",
        "corpus_hash": "a" * 64,
        "index_version": "openai-small-1536-v1",
        "retrieval_version": "knowledge-retrieval-v1",
        "mode": "LEXICAL",
        "reason": "MATCH",
        "passages": [
            {
                "chunk_id": str(uuid4()),
                "document_version_id": str(uuid4()),
                "document_version": 1,
                "document_title": "EW",
                "claim_id": "ew-definition",
                "text": text,
                "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                "source_title": "Reviewed notes",
                "source_url": "https://example.org/ew",
                "locator": "EW",
                "available_at": "2026-01-01T00:00:00+00:00",
                "published_at": None,
            }
        ],
    }


def test_legacy_consent_versions_cannot_be_changed_by_users(chat):
    c, sessions, _ = chat
    cid = conversation(c)
    route = f"/api/v1/conversations/{cid}/preferences"
    for version in (1, 2):
        assert (
            c.post(
                route,
                headers=headers(),
                json={"llm_consent": True, "consent_version": version},
            ).status_code
            == 403
        )
    with sessions() as db:
        assert db.get(Conversation, cid).consent_version == 1


def test_knowledge_needs_no_portfolio_and_never_allocates(chat, monkeypatch):
    c, s, t = chat
    cid = conversation(c)
    data = candidates()
    calls = []
    original = t.call

    def call(job, tool, args):
        calls.append(tool)
        if tool == "retrieve_knowledge":
            return deepcopy(data)
        return original(job, tool, args)

    monkeypatch.setattr(t, "call", call)
    r = send(c, cid, intent="knowledge", content="EW là gì?", strategy=None)
    assert r.status_code == 202, r.text
    assert Worker(s, t).tick()
    rows = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()
    card = rows[-1]["structured"]
    assert card["type"] == "knowledge"
    assert card["knowledge"]["status"] == "REFERENCE"
    assert card["knowledge"]["citations"][0]["claim_id"] == "ew-definition"
    assert card["knowledge"]["evidence_hash"] == canonical_hash(
        {k: v for k, v in card["knowledge"].items() if k != "evidence_hash"}
    )
    assert "request_allocation" not in calls and not t.allocations
    assert "get_profile" in calls


@pytest.mark.parametrize(
    "version", ["knowledge-retrieval-v1", "knowledge-retrieval-v2"]
)
def test_forged_references_never_render_prose_or_urls(version):
    from chat_service.knowledge import render_evidence

    data = candidates() | {"retrieval_version": version}
    cid = data["passages"][0]["chunk_id"]
    result = render_evidence(
        data,
        {"selected_chunk_ids": ["forged"], "candidate_hash": canonical_hash(data)},
        query_hash="b" * 64,
    )
    assert (
        result["status"] == "REFERENCE"
        and result["selection_reason"] == "INVALID_REFERENCES"
    )
    assert result["citations"][0]["chunk_id"] == cid
    assert result["retrieval_version"] == version
    bad = deepcopy(data)
    bad["passages"][0]["source_url"] = "javascript:alert(1)"
    with pytest.raises(ValueError):
        render_evidence(bad, None, query_hash="b" * 64)
    bad = deepcopy(data)
    bad["passages"][0]["text"] = "Invented weight 90%"
    with pytest.raises(ValueError):
        render_evidence(bad, None, query_hash="b" * 64)


def test_checkpoint_deactivation_abstains_without_switching_corpus(chat, monkeypatch):
    c, s, t = chat
    cid = conversation(c)
    data = candidates()
    calls = []
    original = t.call

    def call(job, tool, args):
        if tool == "retrieve_knowledge":
            calls.append(args)
            return (
                deepcopy(data)
                if len(calls) == 1
                else data
                | {"corpus_hash": None, "reason": "CORPUS_UNAVAILABLE", "passages": []}
            )
        return original(job, tool, args)

    monkeypatch.setattr(t, "call", call)
    r = send(c, cid, intent="knowledge", content="EW là gì?")
    assert r.status_code == 202
    assert Worker(s, t).tick()
    row = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1]
    assert row["structured"]["knowledge"]["status"] == "MISSING"
    assert row["structured"]["knowledge"]["citations"] == []
    assert calls[1]["corpus_id"] == data["corpus_id"]


def test_automatic_knowledge_does_not_enter_allocation():
    for text in [
        "MVO là gì?",
        "Giải thích đa dạng hóa",
        "Tại sao cần hiệp phương sai?",
        "EW la gi?",
    ]:
        assert intent_of({"content": text}) == "knowledge"
    assert intent_of({"content": "Tạo phân bổ MVO"}) == "allocation"
    assert (
        intent_of({"content": "Tạo phân bổ MVO", "intent": "knowledge"}) == "knowledge"
    )


def test_query_embedding_requires_dev_flag_new_budget_and_never_retries(
    chat, monkeypatch
):
    from chat_service.llm import InvocationLedger
    from chat_service.queue import Queue

    c, s, t = chat
    cid = conversation(c)
    send(c, cid, intent="knowledge", content="EW là gì?")
    job = Queue(s).claim()
    calls = []
    ledger = InvocationLedger(s)

    def paid():
        calls.append(1)
        return {"embedding": [1.0] * 1536}, {"reason": "VERIFIED", "input_tokens": 20}

    assert (
        ledger.invoke(job, "query_embedding", paid)[1]["reason"]
        == "EMBEDDINGS_DISABLED"
    )
    monkeypatch.setenv("CHAT_QUERY_EMBEDDINGS_ENABLED", "1")
    assert (
        ledger.invoke(job, "query_embedding", paid)[1]["reason"]
        == "BUDGET_NOT_APPROVED"
    )
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "approved-test-budget")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.01")
    value, meta = ledger.invoke(job, "query_embedding", paid)
    assert value and len(calls) == 1
    assert ledger.invoke(job, "query_embedding", paid)[0] == value and len(calls) == 1
    monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    assert (
        ledger.invoke(job, "query_embedding", paid)[1]["reason"] == "DEVELOPER_DISABLED"
    )


def test_embedding_adapter_validates_and_default_has_no_network(monkeypatch):
    from chat_service.embeddings import Embeddings

    adapter = Embeddings()
    calls = []

    async def request(text):
        calls.append(text)
        return {
            "model": "text-embedding-3-small",
            "data": [{"index": 0, "embedding": [1.0] * 1536}],
            "usage": {"prompt_tokens": 20, "total_tokens": 20},
        }

    monkeypatch.setattr(adapter, "_request", request)
    assert adapter.embed("EW")[1]["reason"] == "BUDGET_NOT_APPROVED"
    assert not calls
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "test-only")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.01")
    assert adapter.embed("EW")[0]["embedding"] == [1.0] * 1536

    async def invalid(text):
        return {
            "model": "text-embedding-3-small",
            "data": [{"index": 0, "embedding": [0.0] * 1536}],
            "usage": {"prompt_tokens": 20, "total_tokens": 20},
        }

    monkeypatch.setattr(adapter, "_request", invalid)
    assert adapter.embed("EW")[0] is None


def test_recommendation_combined_plan_rejects_invented_facts_or_claims(monkeypatch):
    from chat_service.openai_provider import OpenAIProvider

    provider = OpenAIProvider()
    data = candidates()
    digest = "d" * 64
    result = {
        "sections": ["weights"],
        "facts_hash": digest,
        "selected_chunk_ids": [data["passages"][0]["chunk_id"]],
        "candidate_hash": canonical_hash(data),
    }
    monkeypatch.setattr(
        provider, "generate", lambda *a: (deepcopy(result), {"reason": "VERIFIED"})
    )
    sections, meta = provider.explain_with_knowledge(
        {"weights": ["0.5", "0.5"]}, digest, data, question="EW?"
    )
    assert (
        sections == ["weights"]
        and meta["knowledge_plan"]["selected_chunk_ids"] == result["selected_chunk_ids"]
    )
    result["selected_chunk_ids"] = ["forged"]
    assert provider.explain_with_knowledge({}, digest, data)[0] is None
    result["facts_hash"] = "f" * 64
    assert provider.explain_with_knowledge({}, digest, data)[0] is None


@pytest.mark.parametrize("budget", [False, True])
def test_auto_knowledge_never_uses_legacy_paid_intent(chat, monkeypatch, budget):
    c, s, t = chat
    cid = conversation(c)
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    if budget:
        monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit-test-budget")
        monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.01")
    c.post(
        f"/api/v1/conversations/{cid}/preferences",
        headers=headers(),
        json={"llm_consent": True},
    )
    calls = []
    from chat_service.openai_provider import OpenAIProvider

    monkeypatch.setattr(
        OpenAIProvider,
        "interpret",
        lambda self, ctx: (
            calls.append(ctx) or None,
            {"reason": "UNEXPECTED_INTENT_CALL"},
        ),
    )
    sent = send(c, cid, intent=None, content="EW là gì?")
    assert sent.status_code == 202
    assert Worker(s, t).tick()
    assert calls == []
    with s() as db:
        from chat_service.models import ProviderInvocation
        from sqlalchemy import select

        assert not db.scalars(
            select(ProviderInvocation).where(ProviderInvocation.purpose == "intent")
        ).all()


def test_claim_selector_receives_only_redacted_current_question(chat, monkeypatch):
    from chat_service.llm import Dialogue
    from chat_service.openai_provider import OpenAIProvider

    c, s, t = chat
    cid = conversation(c)
    c.post(
        f"/api/v1/conversations/{cid}/preferences",
        headers=headers(),
        json={"llm_consent": True},
    )
    send(c, cid, intent="knowledge", content="EW cho test@example.org là gì?")
    from chat_service.queue import Queue

    job = Queue(s).claim()
    captured = []
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit-test-budget")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.01")
    monkeypatch.setattr(
        OpenAIProvider,
        "generate",
        lambda self, purpose, context, schema: (
            captured.append(context) or None,
            {"reason": "UNIT"},
        ),
    )
    Dialogue(s).select_knowledge(job, candidates())
    assert captured and captured[0]["question"] == "EW cho [redacted] là gì?"
    assert "profile" not in captured[0] and "history" not in captured[0]


def test_slow_turn_uses_lexical_references_and_preserves_canonical_budget(
    chat, monkeypatch
):
    c, s, t = chat
    cid = conversation(c)
    c.post(
        f"/api/v1/conversations/{cid}/preferences",
        headers=headers(),
        json={"llm_consent": True, "consent_version": 2},
    )
    send(c, cid, intent="knowledge", content="EW là gì?")
    from chat_service.queue import Queue

    job = Queue(s).claim()
    worker = Worker(s, t)
    worker.started = 0
    import chat_service.workflow as workflow

    monkeypatch.setattr(workflow.time, "monotonic", lambda: 6)
    calls = []
    monkeypatch.setattr(
        worker.dialogue,
        "embed_query",
        lambda *a: (calls.append("embedding") or None, {"reason": "unexpected"}),
    )
    monkeypatch.setattr(
        worker.dialogue,
        "select_knowledge",
        lambda *a: (calls.append("selection") or None, {"reason": "unexpected"}),
    )
    original = t.call
    data = candidates()
    monkeypatch.setattr(
        t,
        "call",
        lambda j, tool, args: data
        if tool == "retrieve_knowledge"
        else original(j, tool, args),
    )
    assert worker.knowledge(job)["status"] == "REFERENCE"
    assert calls == []


@pytest.mark.parametrize(
    "outcome", ["match", "lexical", "invalid", "changed", "timeout"]
)
def test_rewrite_fallback_is_bounded_and_preserves_evidence(chat, monkeypatch, outcome):
    c, s, t = chat
    cid = conversation(c)
    data = candidates()
    empty = data | {"reason": "NO_EVIDENCE", "passages": []}
    attempts, calls = [], []
    original = t.call

    def rewrite(question, topic):
        attempts.append((question, topic))
        if outcome == "timeout":
            raise TimeoutError
        return {"query": "EW"} if outcome == "invalid" else "equal weight"

    def call(job, tool, args):
        if tool != "retrieve_knowledge":
            return original(job, tool, args)
        calls.append(args)
        if args["query"] == "equal weight":
            return data if outcome != "changed" else data | {"corpus_hash": "b" * 64}
        return data if outcome == "lexical" else empty

    monkeypatch.setattr(t, "call", call)
    question = "Cách chia vốn cho user@example.org?"
    assert send(c, cid, intent="knowledge", content=question).status_code == 202
    assert Worker(s, t, query_rewriter=rewrite).tick()
    ev = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
        "structured"
    ]["knowledge"]
    assert ev["evidence_hash"] == canonical_hash(
        {k: v for k, v in ev.items() if k != "evidence_hash"}
    )
    assert bool(ev["citations"]) == (outcome in {"match", "lexical"})
    assert ("rewritten_query_hash" in ev) == (outcome == "match")
    assert attempts == (
        [] if outcome == "lexical" else [("Cách chia vốn cho [redacted]?", None)]
    )
    assert all("embedding" not in args for args in calls)
    if outcome in {"match", "changed"}:
        assert calls[1] == calls[0] | {
            "query": "equal weight",
            "corpus_id": data["corpus_id"],
        }
    assert not t.allocations


def test_followup_rewrite_uses_only_previous_cited_topic_in_same_conversation(
    chat, monkeypatch
):
    c, s, t = chat
    cid = conversation(c)
    other = conversation(c)
    data = candidates()
    empty = data | {"reason": "NO_EVIDENCE", "passages": []}
    original = t.call
    monkeypatch.setattr(
        t,
        "call",
        lambda job, tool, args: (
            data if args["query"] in {"EW là gì?", "equal weight"} else empty
        )
        if tool == "retrieve_knowledge"
        else original(job, tool, args),
    )
    attempts = []

    def rewrite(question, topic):
        attempts.append((question, topic))
        return "equal weight"

    worker = Worker(s, t, query_rewriter=rewrite)
    send(c, cid, intent="knowledge", content="EW là gì?")
    assert worker.tick()
    question = "Vậy nó có nhược điểm gì?"
    send(c, other, intent="knowledge", content=question)
    assert worker.tick()
    send(c, cid, intent=None, content=question)
    assert worker.tick()
    assert attempts == [(question, "EW")]
    rows = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()
    assert (
        rows[-1]["structured"]["knowledge"]["citations"][0]["claim_id"]
        == "ew-definition"
    )
    assert not t.allocations
