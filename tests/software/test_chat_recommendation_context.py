"""Recommendation follow-ups work without a provider and stay owner/portfolio scoped."""

from datetime import timedelta
from uuid import uuid4
import pytest
from portfolio_contracts import utcnow, canonical_hash
from chat_service.models import Message, Job
from chat_service.llm import Dialogue
from chat_service.queue import Queue
from chat_service.workflow import Worker, intent_of
from test_chat import chat as chat_fixture, conversation, headers, send

chat = chat_fixture


def seed(sessions, cid, pid, *, recent=False):
    rid = str(uuid4())
    now = utcnow() - timedelta(minutes=1)
    with sessions.begin() as db:
        db.add(
            Message(
                conversation_id=cid,
                role="assistant",
                content="Đề xuất đã hiển thị",
                created_at=now,
                structured={
                    "type": "recommendation",
                    "recommendation_id": rid,
                    "facts": {"id": rid, "portfolio_id": pid},
                },
            )
        )
        if not recent:
            for i in range(6):
                db.add(
                    Message(
                        conversation_id=cid,
                        role="assistant",
                        content="Trao đổi tiếp",
                        created_at=now + timedelta(seconds=i + 1),
                        structured={"type": "help"},
                    )
                )
    return rid


@pytest.mark.parametrize(
    "question",
    [
        "Giải thích thêm về quyết định của bạn",
        "Đề xuất nào?",
        "Vì sao phân bổ như vậy?",
        "Giải thích lại đề xuất vừa rồi",
    ],
)
@pytest.mark.parametrize("explicit", [False, True])
def test_followup_resolves_last_recommendation_without_paid_intent(
    chat, monkeypatch, question, explicit
):
    c, sessions, tools = chat
    monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    pid = tools.summary["id"]
    cid = conversation(c, pid)
    rid = seed(sessions, cid, pid)
    calls = []
    original = tools.call

    def call(job, name, args):
        calls.append((name, args))
        return original(job, name, args)

    monkeypatch.setattr(tools, "call", call)
    assert (
        send(
            c,
            cid,
            content=question,
            intent="explain" if explicit else None,
            strategy=None,
        ).status_code
        == 202
    )
    assert Worker(sessions, tools).tick()
    rows = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()
    card = rows[-1]["structured"]
    assert card["type"] == "recommendation"
    assert card["recommendation_id"] == rid
    assert card["explanation_requested"] is True
    assert card["facts_hash"] == canonical_hash(card["facts"])
    assert not tools.allocations
    assert [
        args["resource_id"] for name, args in calls if name == "get_recommendation"
    ] == [rid]


def test_reference_ignores_other_conversations_and_changed_portfolio(chat):
    c, sessions, tools = chat
    cid = conversation(c, tools.summary["id"])
    seed(sessions, conversation(c, tools.summary["id"]), tools.summary["id"])
    seed(sessions, cid, str(uuid4()))
    send(c, cid, content="Giải thích thêm", intent="explain", strategy=None)
    job = Queue(sessions).claim()
    assert Dialogue(sessions).recommendation_reference(job) is None


def test_reference_honors_cutoff_owner_and_explicit_selection(chat, monkeypatch):
    c, sessions, tools = chat
    monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    pid = tools.summary["id"]
    cid = conversation(c, pid)
    old = seed(sessions, cid, pid)
    chosen = str(uuid4())
    send(
        c,
        cid,
        content="Giải thích đề xuất đã chọn",
        intent="explain",
        recommendation_id=chosen,
        strategy=None,
    )
    job = Queue(sessions).claim()
    with sessions.begin() as db:
        db.add(
            Message(
                conversation_id=cid,
                role="assistant",
                content="Future",
                created_at=utcnow() + timedelta(hours=1),
                structured={
                    "type": "recommendation",
                    "recommendation_id": str(uuid4()),
                    "facts": {"portfolio_id": pid},
                },
            )
        )
    dialogue = Dialogue(sessions)
    assert dialogue.recommendation_reference(job) == old
    owner = job.owner_key
    job.owner_key = "different-owner"
    assert dialogue.recommendation_reference(job) is None
    job.owner_key = owner
    # Return the leased job to normal queue processing without changing business facts.
    with sessions.begin() as db:
        row = db.get(Job, job.id)
        row.lease_until = utcnow() - timedelta(seconds=1)
    assert Worker(sessions, tools).tick()
    state = c.get(f"/api/v1/jobs/chat/{job.id}", headers=headers()).json()
    rows = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()
    card = next(m["structured"] for m in rows if m["id"] == state["result_message_id"])
    assert card["recommendation_id"] == chosen


def test_explain_question_does_not_route_to_allocation():
    assert intent_of({"content": "Vì sao phân bổ như vậy?"}) == "explain"
    assert intent_of({"content": "Đề xuất nào?"}) == "explain"
    assert intent_of({"content": "MVO là gì?"}) == "knowledge"
    assert intent_of({"content": "Tạo đề xuất MVO"}) == "allocation"


def test_llm_context_keeps_recent_text_bounded_but_retains_result_reference(chat):
    c, sessions, tools = chat
    pid = tools.summary["id"]
    cid = conversation(c, pid)
    rid = seed(sessions, cid, pid)
    send(c, cid, content="Nói thêm giúp tôi", intent=None, strategy=None)
    job = Queue(sessions).claim()
    context, reference = Dialogue(sessions).context(job)
    assert reference == rid
    assert context["has_recommendation"] is True
    assert len(context["history"]) == 4
    assert rid not in str(context)


def test_followup_keeps_reference_when_actual_provider_budget_is_exhausted(
    chat, monkeypatch
):
    c, sessions, tools = chat
    monkeypatch.setenv("CHAT_LLM_ENABLED", "1")
    monkeypatch.setenv("CHAT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-only")
    monkeypatch.setenv("CHAT_CONTEXTUAL_REPLIES", "1")
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit-exhausted-followup")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.50")
    monkeypatch.setenv("CHAT_LLM_APPROVAL_CALL_LIMIT", "0")
    cid = conversation(c, tools.summary["id"])
    rid = seed(sessions, cid, tools.summary["id"])
    send(
        c,
        cid,
        content="Giải thích thêm về quyết định của bạn",
        intent=None,
        strategy=None,
    )
    assert Worker(sessions, tools).tick()
    card = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
        "structured"
    ]
    assert card["recommendation_id"] == rid
    assert card["provider"]["reason"] == "ACCEPTANCE_BUDGET_EXHAUSTED"
    assert card["facts_hash"] == canonical_hash(card["facts"])
    assert not tools.allocations


def test_requested_explanation_uses_method_from_canonical_facts_and_cited_passage(
    chat, monkeypatch
):
    from test_chat_knowledge import candidates

    c, sessions, tools = chat
    monkeypatch.setenv("CHAT_LLM_ENABLED", "0")
    pid = tools.summary["id"]
    cid = conversation(c, pid)
    seed(sessions, cid, pid)
    data = candidates()
    import hashlib

    passage = data["passages"][0]
    passage["claim_id"] = "mvo-definition"
    passage["text"] = (
        "MVO tìm sự đánh đổi giữa lợi nhuận kỳ vọng và phương sai danh mục, dưới các ràng buộc đã chọn."
    )
    passage["text_hash"] = hashlib.sha256(passage["text"].encode()).hexdigest()
    queries = []
    original = tools.call

    def call(job, name, args):
        if name == "get_recommendation":
            return original(job, name, args) | {"strategy": "MVO"}
        if name == "retrieve_knowledge":
            queries.append(args["query"])
            return data
        return original(job, name, args)

    monkeypatch.setattr(tools, "call", call)
    send(
        c,
        cid,
        content="Giải thích thêm về quyết định của bạn",
        intent=None,
        strategy=None,
    )
    assert Worker(sessions, tools).tick()
    result = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[
        -1
    ]
    card = result["structured"]
    assert any("MVO" in query for query in queries)
    assert data["passages"][0]["text"] in result["content"]
    assert card["facts"]["strategy"] == "MVO"
    assert card["facts_hash"] == canonical_hash(card["facts"])
    assert card["knowledge"]["citations"][0]["text"] == data["passages"][0]["text"]
