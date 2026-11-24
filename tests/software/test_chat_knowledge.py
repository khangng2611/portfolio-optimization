"""Injected provider/owner tests. Live acceptance is separately exercised over HTTP."""

import hashlib

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
    "version",
    [
        "knowledge-retrieval-v1",
        "knowledge-retrieval-v2",
        "knowledge-retrieval-v3",
        "knowledge-retrieval-v4", "knowledge-retrieval-v5", "knowledge-retrieval-v6",
    ],
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
    "outcome", ["match", "lexical", "invalid", "changed", "timeout", "new_ticker", "new_amount"]
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
        if outcome in {"new_ticker", "new_amount"}:
            return "tỷ trọng VIC" if outcome == "new_ticker" else "target 999 đồng"
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
    if outcome in {"new_ticker", "new_amount"}:
        assert all(a["query"] == "Cách chia vốn cho [redacted]?" for a in calls)
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
    # The rewrite found a definition, which cannot answer a question about limits.
    assert rows[-1]["structured"]["knowledge"]["status"] == "MISSING"
    assert not t.allocations


def test_portfolio_switch_discards_last_knowledge_topic(chat, monkeypatch):
    from chat_service.knowledge import previous_knowledge_topic
    from chat_service.queue import Queue

    c, sessions, tools = chat
    cid = conversation(c, tools.summary["id"])
    original = tools.call
    data = candidates()
    monkeypatch.setattr(
        tools,
        "call",
        lambda job, tool, args: data
        if tool == "retrieve_knowledge"
        else original(job, tool, args),
    )
    send(c, cid, intent="knowledge", content="EW là gì?")
    assert Worker(sessions, tools).tick()
    send(
        c,
        cid,
        intent="knowledge",
        content="Vậy nó có nhược điểm gì?",
        portfolio_id=str(uuid4()),
    )
    assert previous_knowledge_topic(sessions, Queue(sessions).claim()) is None


def test_definition_cannot_answer_guarantee_even_with_verified_provider_ids():
    from chat_service.knowledge import knowledge_answer, render_evidence

    data = candidates()
    plan = {
        "selected_chunk_ids": [data["passages"][0]["chunk_id"]],
        "candidate_hash": canonical_hash(data),
    }

    def answer(question):
        return render_evidence(data, plan, query_hash="b" * 64, question=question)

    assert answer("EW có bảo đảm lợi nhuận không?")["citations"] == []
    partial = answer("EW là gì và lợi nhuận năm tới là bao nhiêu?")
    assert partial["coverage"] == "PARTIAL"
    assert partial["selected_chunk_ids"] == plan["selected_chunk_ids"]
    assert knowledge_answer(partial).startswith(data["passages"][0]["text"])
    assert "chưa đủ căn cứ" in knowledge_answer(partial)


def approved_candidate_passages(*claim_ids):
    from pathlib import Path
    from knowledge_service.corpus import load_manifest, sha

    m = load_manifest(
        Path(__file__).resolve().parents[2]
        / "services/knowledge/corpus/candidate-20261123"
    )
    base = candidates()
    by_id = {
        c.id: base["passages"][0]
        | {
            "chunk_id": str(uuid4()),
            "document_title": d.title,
            "document_version": d.version,
            "claim_id": c.id,
            "text": c.text,
            "text_hash": sha(c.text),
            "source_title": c.source_title,
            "source_url": c.source_url,
            "locator": c.locator,
            "available_at": d.available_at.isoformat(),
        }
        for d in m.documents
        for c in d.claims
        if c.id in claim_ids
    }
    return base | {"passages": [by_id[k] for k in claim_ids]}


@pytest.mark.parametrize(
    ("question", "irrelevant", "supported"),
    [
        ("MVO có hứa hẹn sinh lời không?", "mvo-definition", "mvo-estimation"),
        (
            "Đa dạng hóa có xóa bỏ toàn bộ rủi ro thị trường không?",
            "diversification-definition",
            "diversification-limit",
        ),
        (
            "Kết quả backtest tốt có cam kết lợi nhuận tương lai không?",
            "backtest-definition",
            "backtest-limit",
        ),
        (
            "Điểm tin cậy của views trong Black Litterman có ý nghĩa gì?",
            "bl-definition",
            "bl-uncertainty",
        ),
        (
            "Chấp nhận đề xuất có tự khớp lệnh mua bán không?",
            "target-not-holdings",
            "accept-not-trade",
        ),
        (
            "Tại sao trượt giá làm thay đổi kết quả sau chi phí?",
            "turnover-definition",
            "fees-limit",
        ),
        (
            "Target có chứng minh là tôi đang nắm giữ cổ phiếu không?",
            "accept-not-trade",
            "target-not-holdings",
        ),
        (
            "Quy tắc hết hạn dữ liệu có làm thay đổi tỷ trọng của mục tiêu cũ?",
            "freshness-window",
            "freshness-history",
        ),
    ],
)
def test_question_facets_choose_an_answering_paragraph(question, irrelevant, supported):
    from chat_service.knowledge import render_evidence

    data = approved_candidate_passages(irrelevant, supported)
    answer = render_evidence(data, None, query_hash="a" * 64, question=question)
    assert [p["claim_id"] for p in answer["citations"]] == [supported]


@pytest.mark.parametrize(
    "question",
    [
        "MVO có bảo đảm lợi nhuận cho FPT không?",
        "EW có bảo đảm cho bitcoin sinh lời không?",
        "Dữ liệu VFF của danh mục tôi hôm nay đã hết hạn chưa?",
        "Mức phí giao dịch VCB chính xác bao nhiêu?",
        "Bao giờ hệ thống của tôi mở lại?",
    ],
)
def test_financial_rule_never_supplies_individual_fact(question):
    from chat_service.knowledge import render_evidence

    data = approved_candidate_passages(
        "mvo-estimation",
        "ew-limit",
        "vff-nav-availability",
        "fees-limit",
        "proposal-pause-rule",
    )
    assert not render_evidence(data, None, query_hash="a" * 64, question=question)[
        "citations"
    ]


def test_intervening_failed_job_removes_previous_knowledge_topic(chat, monkeypatch):
    from chat_service.knowledge import previous_knowledge_topic
    from chat_service.queue import Queue

    c, sessions, tools = chat
    cid = conversation(c, tools.summary["id"])
    original = tools.call
    data = candidates()
    monkeypatch.setattr(
        tools,
        "call",
        lambda j, n, a: data if n == "retrieve_knowledge" else original(j, n, a),
    )
    send(c, cid, intent="knowledge", content="EW là gì?")
    assert Worker(sessions, tools).tick()
    q = Queue(sessions)
    send(c, cid, intent="help", content="Câu khác")
    assert q.finish(q.claim(), status="FAILED", error="UNAVAILABLE")
    send(c, cid, intent="knowledge", content="Vậy nó có nhược điểm gì?")
    assert previous_knowledge_topic(sessions, q.claim()) is None


def test_claim_label_does_not_create_an_absent_caveat():
    from chat_service.knowledge import render_evidence

    data = candidates()
    data["passages"][0]["claim_id"] = "ew-limit"
    assert not render_evidence(
        data, None, query_hash="a" * 64, question="Nhược điểm EW là gì?"
    )["citations"]


@pytest.mark.parametrize(
    ("q", "claims", "gold"),
    [
        (
            "Trong phương pháp Black–Litterman, vì sao lại phối hợp prior và views?",
            ["bl-uncertainty", "bl-definition"],
            "bl-definition",
        ),
        (
            "Chia tiền bằng nhau có khiến các khoản đầu tư chịu rủi ro ngang nhau chứ?",
            ["ew-definition", "ew-limit"],
            "ew-limit",
        ),
        (
            "Còn có thể mất tiền sau khi đã đa dạng danh mục không?",
            ["diversification-definition", "diversification-limit"],
            "diversification-limit",
        ),
        (
            "Giữa target đã chấp nhận và tài sản thực sự nắm giữ có điểm gì khác?",
            ["target-not-holdings", "accept-not-trade"],
            "target-not-holdings",
        ),
        (
            "Việc xét duyệt một model candidate thuộc trách nhiệm của ai?",
            ["model-approval-definition", "model-approval-reviewer"],
            "model-approval-reviewer",
        ),
        (
            "Trong quy trình NAV VFF cơ sở, ý nghĩa của bộ đệm 5 phiên là gì?",
            ["freshness-window", "vff-nav-availability"],
            "vff-nav-availability",
        ),
    ],
)
def test_concept_and_requested_relationship_survive_paraphrase(q, claims, gold):
    from chat_service.knowledge import render_evidence

    answer = render_evidence(
        approved_candidate_passages(*claims), None, query_hash="a" * 64, question=q
    )
    assert [p["claim_id"] for p in answer["citations"]] == [gold]
    assert answer["coverage"] == "SUPPORTED"


@pytest.mark.parametrize(
    "q",
    [
        "Tỷ trọng EW cho mã mới TSLA chính xác là bao nhiêu?",
        "VFF có yêu cầu trễ 19 tuần theo quy trình NAV của quỹ không?",
        "MVO chắc có lãi cho quỹ zzzunknown không?",
        "Tác giả của mô hình Black–Litterman sinh năm nào?",
        "Nếu dùng EW ở Canada thì tiền thuế là bao nhiêu?",
        "Ngày mai hệ thống mở lại lúc mấy giờ?",
    ],
)
def test_semantic_match_rejects_unpublished_scope(q):
    from chat_service.knowledge import render_evidence

    data = approved_candidate_passages(
        "ew-limit",
        "mvo-estimation",
        "bl-definition",
        "vff-nav-availability",
        "proposal-pause-rule",
    )
    assert not render_evidence(data, None, query_hash="a" * 64, question=q)["citations"]


def test_semantic_selection_requires_verbatim_evidence_and_bound_question_scope():
    from chat_service.knowledge import render_evidence
    from portfolio_contracts import canonical_hash

    data = approved_candidate_passages("ew-definition")
    p = data["passages"][0]
    support = {"chunk_id": str(p["chunk_id"]), "quote": p["text"][:55]}
    plan = {"supports": [support], "candidate_hash": canonical_hash(data), "coverage": "SUPPORTED"}
    def result(q, value):
        return render_evidence(data, value, query_hash="a"*64, question=q, metadata={"reason": "VERIFIED"})
    good = result("EW phân phần vốn theo cách nào?", plan)
    assert good["selection_reason"] == "VERIFIED_QUOTES"
    assert good["citations"][0]["text"] == p["text"]
    for invalid in [
        plan | {"supports": [support | {"quote": "Trích dẫn không tồn tại trong tài liệu này."}]},
        plan | {"candidate_hash": "c"*64},
        plan | {"coverage": "MISSING"},
        plan | {"supports": [support, support]},
    ]:
        assert result("EW phân phần vốn theo cách nào?", invalid)["selection_reason"] == "INVALID_REFERENCES"
    for q in ("EW có bảo đảm lợi nhuận cho FPT không?", "EW có bảo đảm lợi nhuận không?"):
        assert not result(q, plan)["citations"]


@pytest.mark.parametrize(("question","claim","distractor"), [
    ("MVO mô tả sự đánh đổi giữa những đại lượng nào?", "mvo-definition", "mvo-estimation"),
    ("Kết quả backtest đẹp có bảo đảm mình sẽ kiếm được tiền thật không?", "backtest-limit", "backtest-definition"),
    ("Nếu đồng ý với đề xuất thì lệnh mua bán có tự chạy không?", "accept-not-trade", "target-not-holdings"),
    ("Chỉ hỏi trong chat thì hồ sơ của mình có tự thay đổi không?", "risk-policy-boundary", "risk-policy-definition"),
    ("Khi đầu vào hết hạn, target đã lưu có bị sửa theo số liệu mới không?", "freshness-history", "freshness-window"),
])
def test_answer_the_requested_relationship(question, claim, distractor):
    from chat_service.knowledge import render_evidence
    data = approved_candidate_passages(distractor, claim)
    result = render_evidence(data, None, query_hash="c"*64, question=question)
    assert [r["claim_id"] for r in result["citations"]] == [claim]
    assert result["coverage"] == "SUPPORTED"


@pytest.mark.parametrize(
    ("question", "claims", "expected"),
    [
        (
            "EW và MVO có bảo đảm lợi nhuận không?",
            ["ew-definition", "mvo-estimation"],
            ["mvo-estimation"],
        ),
        (
            "EW có bảo đảm lợi nhuận và hoàn lại vốn gốc không?",
            ["ew-limit"],
            ["ew-limit"],
        ),
    ],
)
def test_compound_assurance_requires_support_for_each_subject_and_object(
    question, claims, expected
):
    from chat_service.knowledge import render_evidence

    data = approved_candidate_passages(*claims)
    plan = {
        "supports": [
            {"chunk_id": p["chunk_id"], "quote": p["text"]} for p in data["passages"]
        ],
        "coverage": "SUPPORTED",
        "candidate_hash": canonical_hash(data),
    }
    for proposed in [None, plan]:
        answer = render_evidence(
            data,
            proposed,
            query_hash="a" * 64,
            question=question,
            metadata={"reason": "VERIFIED"},
        )
        assert [p["claim_id"] for p in answer["citations"]] == expected
        assert answer["coverage"] == "PARTIAL"


def test_verbatim_substring_cannot_drop_the_negation_of_a_guarantee():
    from chat_service.knowledge import render_evidence

    data = approved_candidate_passages("ew-limit")
    plan = {
        "supports": [
            {"chunk_id": data["passages"][0]["chunk_id"], "quote": "bảo đảm lợi nhuận"}
        ],
        "coverage": "SUPPORTED",
        "candidate_hash": canonical_hash(data),
    }
    answer = render_evidence(
        data,
        plan,
        query_hash="b" * 64,
        question="EW có bảo đảm lợi nhuận không?",
        metadata={"reason": "VERIFIED"},
    )
    assert answer["selection_reason"] == "INVALID_REFERENCES"
    assert "không bảo đảm lợi nhuận" in answer["citations"][0]["text"]


def test_clause_selection_reports_exact_unanswered_question_and_rejects_bad_spans():
    from chat_service.knowledge import render_evidence, knowledge_answer
    data = candidates()
    p = data["passages"][0]
    q = "EW là gì? Giá vàng ngày mai bao nhiêu?"
    parts = [{"index": 0, "chunk_id": p["chunk_id"], "quote": p["text"]},
             {"index": 1, "chunk_id": None, "quote": None}]
    def run(parts):
        return render_evidence(data, {"candidate_hash": canonical_hash(data), "parts":parts},
                               query_hash="b"*64, metadata={"reason":"VERIFIED"}, question=q)
    ev = run(parts)
    assert ev["selection_reason"] == "VERIFIED_CLAUSES"
    assert ev["coverage"] == "PARTIAL" and "Giá vàng ngày mai bao nhiêu" in knowledge_answer(ev)
    assert [(c["chunk_id"], c["text_hash"]) for c in ev["citations"]] == [(p["chunk_id"], p["text_hash"])]
    for bad in ([parts[0]], [parts[1],parts[1]], [dict(parts[0],quote="Một câu hoàn toàn tự tạo"),parts[1]]):
        assert run(bad)["selection_reason"] == "INVALID_REFERENCES"


def test_provider_rewrite_only_after_empty_lexical_result(chat, monkeypatch):
    c, s, tools = chat
    data = candidates()
    calls = []
    original = tools.call
    def retrieve(job, tool, args):
        if tool != "retrieve_knowledge":
            return original(job, tool, args)
        if args["query"] == "equal weight":
            return data
        return data | {"reason": "NO_EVIDENCE", "passages": []}
    worker = Worker(s, tools)
    def generate(purpose, context, schema):
        calls.append((purpose, context))
        return {"query":"equal weight"}, {"reason":"VERIFIED"}
    monkeypatch.setenv("CHAT_KNOWLEDGE_REWRITE", "1")
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "rewrite-test")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.01")
    monkeypatch.setattr(tools, "call", retrieve)
    monkeypatch.setattr(worker.dialogue.provider, "generate", generate)
    cid = conversation(c)
    question = "Cách chia vốn cho user@example.org?"
    assert send(c, cid, intent="knowledge", content=question).status_code == 202
    assert worker.tick()
    ev = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1]["structured"]["knowledge"]
    assert calls == [("knowledge_rewrite", {"question": "Cách chia vốn cho [redacted]?", "previous_topic": None})]
    assert ev["rewritten_query_hash"] and ev["citations"] and not tools.allocations


def test_clause_split_keeps_compound_pair_and_separates_new_question():
    from chat_service.knowledge import question_parts
    assert question_parts("MVO cân bằng lợi nhuận và rủi ro, còn RSI đo gì?") == [
        "MVO cân bằng lợi nhuận và rủi ro", "RSI đo gì"
    ]


def test_clause_quote_cannot_reverse_a_negative_source_statement():
    from chat_service.knowledge import render_evidence
    text = "Chiến lược này không thực hiện giao dịch khi chấp nhận mục tiêu."
    passage = candidates()["passages"][0] | {"text": text, "text_hash": hashlib.sha256(text.encode()).hexdigest()}
    data = candidates() | {"passages": [passage]}
    plan = {"candidate_hash": canonical_hash(data), "parts": [
        {"index": 0, "chunk_id": passage["chunk_id"], "quote": "thực hiện giao dịch khi chấp nhận mục tiêu"}
    ]}
    result = render_evidence(data, plan, metadata={"reason": "VERIFIED"}, question="Chiến lược này làm gì?", query_hash="b"*64)
    assert result["selection_reason"] == "INVALID_REFERENCES"


def test_checked_clause_requires_requested_limitation_in_source():
    from chat_service.knowledge import render_evidence
    data = candidates()
    p = data["passages"][0]
    plan = {"candidate_hash": canonical_hash(data), "parts": [{"index": 0, "chunk_id": p["chunk_id"], "quote": p["text"]}]}
    result = render_evidence(data, plan, metadata={"reason":"VERIFIED"}, question="EW có nhược điểm gì?", query_hash="b"*64)
    assert result["selection_reason"] == "INVALID_REFERENCES" and not result["citations"]


@pytest.mark.parametrize("present", [True, False])
def test_asset_allocation_definition_needs_its_own_source(chat, monkeypatch, present):
    c, sessions, tools = chat
    cid = conversation(c)
    data = approved_candidate_passages("target-not-holdings")
    from pathlib import Path
    from knowledge_service.corpus import load_manifest
    release = load_manifest(Path(__file__).resolve().parents[2] / "services/knowledge/corpus/release-20261124")
    doc = next(d for d in release.documents if d.key == "asset-allocation")
    claim = next(c for c in doc.claims if c.id == "asset-allocation-definition")
    definition = claim.text
    if present:
        data["passages"].append(data["passages"][0] | dict(
            chunk_id=str(uuid4()), claim_id=claim.id, document_title=doc.title, text=definition,
            source_url=claim.source_url, text_hash=hashlib.sha256(definition.encode()).hexdigest()))
    original = tools.call
    monkeypatch.setattr(tools, "call", lambda j,t,a: data if t=="retrieve_knowledge" else original(j,t,a))
    assert send(c,cid,intent=None,strategy=None,content="Phân bổ tài sản là gì?").status_code == 202
    worker = Worker(sessions, tools)
    monkeypatch.setattr(worker.dialogue, "select_knowledge", lambda *a, **kw: pytest.fail("Explicit glossary term needs no classifier"))
    assert worker.tick()
    msg=c.get(f"/api/v1/conversations/{cid}/messages",headers=headers()).json()[-1]
    evidence=msg["structured"]["knowledge"]
    assert [p["claim_id"] for p in evidence["citations"]] == (["asset-allocation-definition"] if present else [])
    assert msg["content"] == (definition if present else "Chưa có nguồn phù hợp trong tài liệu đã duyệt để trả lời câu hỏi này.")
    assert evidence["coverage"] == ("SUPPORTED" if present else "MISSING")
    assert not tools.allocations
