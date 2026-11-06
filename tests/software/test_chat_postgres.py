"""Opt-in PostgreSQL storage concurrency test (owner/provider fakes, not E2E evidence)."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from chat_service.api import create_app
from chat_service.models import Base
from test_chat import Tools, Verifier, conversation, headers, run, send


@pytest.mark.skipif(
    os.environ.get("CHAT_POSTGRES_TEST") != "1",
    reason="Requires local PostgreSQL storage gate",
)
def test_provider_budget_is_atomic_across_postgres_workers(monkeypatch):
    # Storage test with injected owner/provider callbacks; not paid-provider evidence.
    from chat_service.llm import InvocationLedger
    from chat_service.queue import Queue

    env = dict(
        line.split("=", 1)
        for line in Path("infra/local/.generated/.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    schema = "chat_budget_" + uuid4().hex
    admin = create_engine(
        "postgresql+psycopg://chat_migrator:"
        + env["CHAT_MIGRATOR_PASSWORD"]
        + "@localhost:5433/chat_db"
    )
    with admin.begin() as db:
        db.execute(text("CREATE SCHEMA " + schema))
    engine = admin.execution_options(schema_translate_map={None: schema})
    sessions = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("CHAT_LLM_DAILY_CALL_LIMIT", "1")
    tools, calls = Tools(), []
    try:
        with TestClient(
            create_app(sessions=sessions, verifier=Verifier(), tools=tools)
        ) as c:
            for _ in range(4):
                cid = conversation(c, tools.summary["id"])
                assert (
                    c.post(
                        f"/api/v1/conversations/{cid}/preferences",
                        headers=headers(),
                        json={"llm_consent": True},
                    ).status_code
                    == 200
                )
                assert send(c, cid).status_code == 202
            jobs = [Queue(sessions).claim() for _ in range(4)]

            def invoke(job):
                def paid():
                    calls.append(job.id)
                    return {"intent": "help"}, {"reason": "VERIFIED"}

                return InvocationLedger(sessions).invoke(job, "intent", paid)

            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(invoke, jobs))
            assert len(calls) == 1
            assert (
                sum(meta["reason"] == "DAILY_BUDGET_EXHAUSTED" for _, meta in results)
                == 3
            )
            chosen = next(job for job in jobs if job.id == calls[0])
            assert invoke(chosen)[0] == {"intent": "help"}
            assert len(calls) == 1
    finally:
        with admin.begin() as db:
            db.execute(text("DROP SCHEMA " + schema + " CASCADE"))
        admin.dispose()


@pytest.mark.skipif(
    os.environ.get("CHAT_POSTGRES_TEST") != "1",
    reason="Requires disposable local PostgreSQL and explicit opt-in",
)
def test_resume_and_new_turn_serialize_on_same_conversation():
    env = dict(
        line.split("=", 1)
        for line in Path("infra/local/.generated/.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    schema = "chat_concurrency_" + uuid4().hex
    admin = create_engine(
        "postgresql+psycopg://chat_migrator:"
        + env["CHAT_MIGRATOR_PASSWORD"]
        + "@localhost:5433/chat_db"
    )
    with admin.begin() as db:
        db.execute(text("CREATE SCHEMA " + schema))
    engine = admin.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    tools = Tools()
    original = tools.grant
    entered, release = threading.Event(), threading.Event()

    def granting(*args, **kw):
        if len(args) > 4 or kw.get("authorization_id"):
            entered.set()
            assert release.wait(5)
        return original(*args, **kw)

    tools.grant = granting
    try:
        with TestClient(
            create_app(sessions=sessions, verifier=Verifier(), tools=tools)
        ) as c:
            cid = conversation(c, tools.summary["id"])
            job = send(c, cid).json()
            tools.expired = True
            run(sessions, tools)
            tools.expired = False
            with ThreadPoolExecutor(max_workers=2) as pool:
                resumed = pool.submit(
                    c.post,
                    job["status_url"] + "/resume",
                    headers=headers(),
                    json={"confirmed": True, "authorization_id": str(uuid4())},
                )
                assert entered.wait(5)
                newer = pool.submit(send, c, cid)
                # Resume is waiting for grant I/O. New send must wait on conversation,
                # then observe resumed QUEUED state and reject a concurrent active turn.
                try:
                    premature = newer.result(timeout=0.3)
                except TimeoutError:
                    premature = None
                release.set()
                a, b = resumed.result(timeout=5), newer.result(timeout=5)
                assert a.status_code == 202, a.text
                assert b.status_code == 409, (
                    premature.status_code if premature else None,
                    b.text,
                )
    finally:
        release.set()
        with admin.begin() as db:
            db.execute(text("DROP SCHEMA " + schema + " CASCADE"))
        admin.dispose()


@pytest.mark.skipif(
    os.environ.get("CHAT_POSTGRES_TEST") != "1",
    reason="Requires disposable local PostgreSQL and explicit opt-in",
)
def test_pending_quota_is_shared_across_conversations():
    import time

    env = dict(
        line.split("=", 1)
        for line in Path("infra/local/.generated/.env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    schema = "chat_quota_" + uuid4().hex
    admin = create_engine(
        "postgresql+psycopg://chat_migrator:"
        + env["CHAT_MIGRATOR_PASSWORD"]
        + "@localhost:5433/chat_db"
    )
    with admin.begin() as db:
        db.execute(text("CREATE SCHEMA " + schema))
    engine = admin.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    tools = Tools()
    original = tools.grant

    def granting(*args, **kw):
        time.sleep(0.1)
        return original(*args, **kw)

    tools.grant = granting
    try:
        with TestClient(
            create_app(sessions=sessions, verifier=Verifier(), tools=tools)
        ) as c:
            ids = [conversation(c, tools.summary["id"]) for _ in range(6)]
            for cid in ids[:4]:
                assert send(c, cid).status_code == 202
            with ThreadPoolExecutor(max_workers=2) as pool:
                values = list(pool.map(lambda cid: send(c, cid), ids[4:]))
            assert sorted(r.status_code for r in values) == [202, 429]
    finally:
        with admin.begin() as db:
            db.execute(text("DROP SCHEMA " + schema + " CASCADE"))
        admin.dispose()
