from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from service_auth import Principal, AuthError
from portfolio_contracts import utcnow
from chat_service.api import create_app
from chat_service.models import Base, Job, Message, Event
from chat_service.workflow import Worker


class Verifier:
    def verify(self, token):
        if token == "expired":
            raise AuthError("expired")
        return Principal(
            "issuer",
            token,
            frozenset({"investor"}),
            frozenset({"chat:read", "chat:write"}),
        )


class Tools:
    def __init__(self):
        self.allocations = {}
        self.expired = False
        self.summary = {
            "id": str(uuid4()),
            "name": "Mục tiêu",
            "version": 1,
            "policy_version_id": "policy-v1",
            "capital_vnd": "100000000",
            "universe_id": "DEMO",
            "constraints": {"max_position_weight": 0.5, "risk_aversion": 3},
            "risk_profile": {"version_id": str(uuid4()), "profile": "balanced"},
        }

    def grant(
        self,
        token,
        conversation_id,
        job_id,
        portfolio_id,
        authorization_id=None,
        allow_mutation=False,
    ):
        return {
            "grant_id": str(uuid4()),
            "expires_at": (utcnow() + timedelta(minutes=5)).isoformat(),
        }

    def call(self, job, tool, args):
        if self.expired:
            from chat_service.tools import ToolError

            raise ToolError("AUTHORIZATION_REQUIRED", permanent=True)
        if tool == "get_profile":
            return {"portfolio": self.summary}
        if tool == "get_portfolio_summary":
            return self.summary.copy()
        if tool == "get_market_facts":
            return {"assets": [], "as_of": "2026-11-04"}
        if tool == "request_allocation":
            self.allocations.setdefault(job.id, str(uuid4()))
            return {"job_id": self.allocations[job.id]}
        if tool == "get_allocation_job":
            return {"status": "SUCCEEDED", "recommendation_id": args["resource_id"]}
        if tool == "get_recommendation":
            return {
                "id": args["resource_id"],
                "portfolio_id": self.summary["id"],
                "weights": ["0.5", "0.5"],
                "asset_ids": ["AAA", "BBB"],
                "input_hash": "a" * 64,
                "core_version": "0.1.0",
                "policy_version_id": "policy-v1",
                "constraints": self.summary["constraints"],
            }
        raise AssertionError(tool)

    def read_recommendation(self, token, rid):
        return self.call(None, "get_recommendation", {"resource_id": rid})


@pytest.fixture
def chat(tmp_path):
    sessions = sessionmaker(
        create_engine(
            f"sqlite:///{tmp_path}/chat.db", connect_args={"check_same_thread": False}
        ),
        expire_on_commit=False,
    )
    Base.metadata.create_all(sessions.kw["bind"])
    tools = Tools()
    app = create_app(
        sessions=sessions, verifier=Verifier(), tools=tools, stream_seconds=0.05
    )
    with TestClient(app) as c:
        yield c, sessions, tools


def headers(user="alice", key=None):
    return {
        "Authorization": "Bearer " + user,
        **({"Idempotency-Key": key} if key else {}),
    }


def conversation(c, pid=None):
    r = c.post(
        "/api/v1/conversations",
        headers=headers(),
        json={"title": "Phân bổ", "portfolio_id": pid},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def send(c, cid, **changes):
    body = {
        "content": "Tạo phân bổ",
        "client_message_id": str(uuid4()),
        "intent": "allocation",
        "strategy": "MVO",
    } | changes
    return c.post(
        f"/api/v1/conversations/{cid}/messages",
        headers=headers(key=body["client_message_id"]),
        json=body,
    )


def run(s, t, **kwargs):
    return Worker(s, t, **kwargs).tick()


def test_dedupe_conflict_ownership_and_paging(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    key = str(uuid4())
    r = send(c, cid, client_message_id=key)
    assert r.status_code == 202, r.text
    assert send(c, cid, client_message_id=key).json() == r.json()
    assert send(c, cid, client_message_id=key, content="Khác").status_code == 409
    assert send(c, cid, client_message_id=key, strategy="EW").status_code == 409
    job = r.json()["job_id"]
    for url in [
        f"/conversations/{cid}",
        f"/conversations/{cid}/messages",
        f"/jobs/chat/{job}",
        f"/jobs/chat/{job}/events",
    ]:
        assert c.get("/api/v1" + url, headers=headers("bob")).status_code == 404
        assert c.get("/api/v1" + url).status_code == 401
    assert (
        c.get(
            f"/api/v1/conversations/{cid}/messages?limit=1", headers=headers()
        ).headers["x-total-count"]
        == "1"
    )
    assert (
        c.get(f"/api/v1/jobs/chat/{job}", headers=headers("expired")).status_code == 401
    )
    with s() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 1


def test_no_allocation_until_explicit_confirmation_and_canonical_result(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    r = send(c, cid).json()
    assert run(s, t)
    j = c.get(r["status_url"], headers=headers()).json()
    assert j["status"] == "WAITING_INPUT"
    assert not t.allocations
    card = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
        "structured"
    ]
    assert card["type"] == "confirmation"
    confirm = send(
        c,
        cid,
        content="Xác nhận",
        confirmation={
            "message_id": card["confirmation_message_id"],
            "facts_hash": card["facts_hash"],
        },
    )
    assert confirm.status_code == 202, confirm.text
    for _ in range(4):
        run(s, t)
    j = c.get(confirm.json()["status_url"], headers=headers()).json()
    assert j["status"] == "SUCCEEDED", j
    assert len(t.allocations) == 1
    messages = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()
    result = messages[-1]
    assert result["structured"]["type"] == "recommendation"
    assert result["structured"]["facts"]["input_hash"] == "a" * 64
    assert result["structured"]["explanation_status"] == "TEMPLATE"
    assert result["structured"]["facts"]["weights"] == ["0.5", "0.5"]
    assert (
        c.get(j["events_url"], headers=headers())
        .headers["content-type"]
        .startswith("text/event-stream")
    )


def test_stale_confirmation_and_missing_input_do_not_mutate(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    send(c, cid)
    run(s, t)
    card = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
        "structured"
    ]
    t.summary["version"] = 2
    send(
        c,
        cid,
        confirmation={
            "message_id": card["confirmation_message_id"],
            "facts_hash": card["facts_hash"],
        },
    )
    run(s, t)
    assert not t.allocations
    assert (
        c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
            "structured"
        ]["reason"]
        == "STALE_CONFIRMATION"
    )
    cid = conversation(c)
    send(c, cid)
    run(s, t)
    assert not t.allocations


def test_concurrent_duplicates_single_job(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: send(c, cid, client_message_id=key), range(4)))
    assert all(v.status_code == 202 for v in values), [
        (v.status_code, v.text) for v in values
    ]
    assert len({v.json()["job_id"] for v in values}) == 1


def test_sse_sequence_replay_gap_and_snapshot(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    r = send(c, cid).json()
    run(s, t)
    url = r["events_url"]
    all_events = c.get(url, headers=headers()).text
    assert "event: accepted" in all_events and "event: input_required" in all_events
    replay = c.get(url, headers=headers() | {"Last-Event-ID": "1"}).text
    assert "id: 1\n" not in replay and "event: input_required" in replay
    with s.begin() as db:
        db.query(Event).filter(
            Event.job_id == r["job_id"], Event.sequence <= 2
        ).delete()
    assert (
        "event: reset_required"
        in c.get(url, headers=headers() | {"Last-Event-ID": "1"}).text
    )
    assert (
        "event: reset_required"
        in c.get(url, headers=headers() | {"Last-Event-ID": "999"}).text
    )
    assert c.get(url, headers=headers() | {"Last-Event-ID": "-1"}).status_code == 400


def test_lease_restart_fencing_deadline_and_grant_expiry(chat):
    from chat_service.queue import Queue

    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    send(c, cid)
    q = Queue(s)
    old = q.claim()
    assert old
    assert q.claim() is None
    later = utcnow() + timedelta(seconds=40)
    new = q.claim(now=later)
    assert new and new.id == old.id and new.lease_token != old.lease_token
    assert not q.finish(old, status="FAILED", now=later)
    assert q.finish(new, status="FAILED", error="TEST", now=later)
    cid2 = conversation(c, t.summary["id"])
    r2 = send(c, cid2).json()
    with s.begin() as db:
        db.get(Job, r2["job_id"]).deadline = utcnow() - timedelta(seconds=1)
    run(s, t)
    assert (
        c.get(r2["status_url"], headers=headers()).json()["error"]
        == "DEADLINE_EXCEEDED"
    )
    cid3 = conversation(c, t.summary["id"])
    r3 = send(c, cid3).json()
    t.expired = True
    run(s, t)
    assert (
        c.get(r3["status_url"], headers=headers()).json()["status"]
        == "AUTHORIZATION_REQUIRED"
    )


def test_bounded_retry_and_crash_after_owner_success_keeps_key(chat):
    import httpx
    from chat_service.queue import Queue

    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    send(c, cid)
    run(s, t)
    card = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
        "structured"
    ]
    response = send(
        c,
        cid,
        confirmation={
            "message_id": card["confirmation_message_id"],
            "facts_hash": card["facts_hash"],
        },
    ).json()
    run(s, t)  # persist SUBMIT
    q = Queue(s)
    crashed = q.claim()
    owner_result = t.call(crashed, "request_allocation", {})
    with s.begin() as db:
        db.get(Job, crashed.id).lease_until = utcnow() - timedelta(seconds=1)
    run(s, t)  # after restart, call same owner key
    assert len(t.allocations) == 1
    with s() as db:
        assert db.get(Job, crashed.id).dependency_id == owner_result["job_id"]
    run(s, t)
    assert (
        c.get(response["status_url"], headers=headers()).json()["status"] == "SUCCEEDED"
    )
    cid = conversation(c, t.summary["id"])
    response = send(c, cid).json()
    original = t.call
    t.call = lambda *args: (_ for _ in ()).throw(httpx.ConnectError("down"))
    for _ in range(5):
        run(s, t)
        with s.begin() as db:
            db.get(Job, response["job_id"]).next_attempt_at = utcnow()
    assert c.get(response["status_url"], headers=headers()).json()["status"] == "FAILED"
    assert c.get(response["status_url"], headers=headers()).json()["attempts"] == 5
    t.call = original


def test_reconfirmation_cannot_be_reused_or_injected(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    send(c, cid)
    run(s, t)
    card = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[-1][
        "structured"
    ]
    confirm = {
        "message_id": card["confirmation_message_id"],
        "facts_hash": card["facts_hash"],
    }
    assert (
        send(c, conversation(c, t.summary["id"]), confirmation=confirm).status_code
        == 409
    )
    r = send(c, cid, confirmation=confirm)
    assert r.status_code == 202
    assert send(c, cid).status_code == 409
    for _ in range(4):
        run(s, t)
    assert send(c, cid, confirmation=confirm).status_code == 409
    assert send(c, cid, intent="allocation", weights=[1.0]).status_code == 422


def test_explicit_resume_reuses_job_and_dependency(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    response = send(c, cid).json()
    t.expired = True
    run(s, t)
    assert (
        c.get(response["status_url"], headers=headers()).json()["status"]
        == "AUTHORIZATION_REQUIRED"
    )
    path = response["status_url"] + "/resume"
    assert (
        c.post(
            path,
            headers=headers(),
            json={"confirmed": False, "authorization_id": str(uuid4())},
        ).status_code
        == 422
    )
    assert (
        c.post(
            path,
            headers=headers("bob"),
            json={"confirmed": True, "authorization_id": str(uuid4())},
        ).status_code
        == 404
    )
    t.expired = False
    r = c.post(
        path,
        headers=headers(),
        json={"confirmed": True, "authorization_id": str(uuid4())},
    )
    assert r.status_code == 202, r.text
    assert r.json()["job_id"] == response["job_id"]
    run(s, t)
    assert (
        c.get(response["status_url"], headers=headers()).json()["status"]
        == "WAITING_INPUT"
    )


def test_resume_cannot_exceed_pending_owner_quota(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    r = send(c, cid).json()
    t.expired = True
    run(s, t)
    t.expired = False
    for _ in range(5):
        assert send(c, conversation(c, t.summary["id"])).status_code == 202
    response = c.post(
        r["status_url"] + "/resume",
        headers=headers(),
        json={"confirmed": True, "authorization_id": str(uuid4())},
    )
    assert response.status_code == 429


def test_backend_role_scope_and_safe_event_payloads(chat):
    c, s, t = chat

    class Restricted:
        def verify(self, token):
            return Principal(
                "issuer",
                token,
                frozenset() if token == "no-role" else frozenset({"investor"}),
                frozenset({"chat:read"}),
            )

    with TestClient(
        create_app(sessions=s, verifier=Restricted(), tools=t)
    ) as restricted:
        assert (
            restricted.get(
                "/api/v1/conversations", headers=headers("no-role")
            ).status_code
            == 403
        )
        assert (
            restricted.post(
                "/api/v1/conversations", headers=headers("reader"), json={}
            ).status_code
            == 403
        )
    cid = conversation(c, t.summary["id"])
    r = send(c, cid, content="Bearer private-user-pasted-value").json()
    run(s, t)
    stream = c.get(r["events_url"], headers=headers()).text
    assert "private-user-pasted-value" not in stream
    with s() as db:
        job = db.get(Job, r["job_id"])
        assert job.grant_id not in stream


def test_provider_budget_survives_crash_before_final_message(chat):
    c, s, t = chat
    cid = conversation(c, t.summary["id"])
    r = send(c, cid, intent="explain", recommendation_id=str(uuid4())).json()

    class CountingProvider:
        calls = 0

        def explain(self, facts, digest):
            self.calls += 1
            return None, {"reason": "NOT_CONFIGURED"}

    provider = CountingProvider()
    worker = Worker(s, t, provider=provider)
    claimed = worker.q.claim()
    facts = t.call(claimed, "get_recommendation", {"resource_id": r["job_id"]})
    worker.q.finish = lambda *a, **kw: False  # crash after paid provider call
    assert worker.explain(claimed, facts) is False
    assert provider.calls == 1
    with s.begin() as db:
        db.get(Job, claimed.id).lease_until = utcnow() - timedelta(seconds=1)
    Worker(s, t, provider=provider).tick()
    assert provider.calls == 1
    result = c.get(f"/api/v1/conversations/{cid}/messages", headers=headers()).json()[
        -1
    ]
    assert result["structured"]["provider"]["reason"] == "PROVIDER_BUDGET_EXHAUSTED"
