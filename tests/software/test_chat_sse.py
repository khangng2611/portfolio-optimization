"""SSE polls preserve event-loop responsiveness and the finite stream lifetime."""

import asyncio
from contextlib import contextmanager
import threading
import time
from uuid import UUID

from fastapi.security import HTTPAuthorizationCredentials
import pytest

from chat_service.api import create_app
from portfolio_contracts import canonical_hash
import test_chat
from test_chat import Verifier, conversation, send

chat = test_chat.chat


@pytest.mark.parametrize("delayed_dependency", ["verifier", "database"])
def test_sse_poll_does_not_block_other_event_loop_work(chat, delayed_dependency):
    client, sessions, tools = chat
    cid = conversation(client, tools.summary["id"])
    receipt = send(client, cid).json()
    initial_thread = threading.get_ident()
    poll_threads = []

    class SlowVerifier(Verifier):
        def verify(self, token):
            if delayed_dependency == "verifier":
                poll_threads.append(threading.get_ident())
                time.sleep(0.2)
            return super().verify(token)

    count = 0

    @contextmanager
    def poll_sessions():
        nonlocal count
        count += 1
        if count > 1 and delayed_dependency == "database":
            poll_threads.append(threading.get_ident())
            time.sleep(0.2)
        with sessions() as session:
            yield session

    app = create_app(sessions=poll_sessions, verifier=SlowVerifier(), tools=tools)
    endpoint = next(
        route.endpoint for route in app.routes if route.path.endswith("/{jid}/events")
    )
    response = endpoint(
        UUID(receipt["job_id"]),
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="alice"),
        owner=canonical_hash({"issuer": "issuer", "subject": "alice"}),
        last_event_id=None,
    )

    async def consume():
        started = time.monotonic()
        pending = asyncio.create_task(response.body_iterator.__anext__())
        await asyncio.sleep(0.02)
        responsive_at = time.monotonic() - started
        try:
            chunk = await pending
            assert "id: 1\n" in chunk
        finally:
            await response.body_iterator.aclose()
        return responsive_at

    responsive_at = asyncio.run(consume())
    assert responsive_at < 0.12, "An SSE dependency blocked the server event loop"
    assert poll_threads and all(identity != initial_thread for identity in poll_threads)


def test_sse_wall_lifetime_closes_even_while_a_dependency_is_stalled(chat):
    client, sessions, tools = chat
    cid = conversation(client, tools.summary["id"])
    receipt = send(client, cid).json()

    class SlowVerifier(Verifier):
        def verify(self, token):
            time.sleep(0.3)
            return super().verify(token)

    app = create_app(
        sessions=sessions, verifier=SlowVerifier(), tools=tools, stream_seconds=0.05
    )
    endpoint = next(
        route.endpoint for route in app.routes if route.path.endswith("/{jid}/events")
    )
    response = endpoint(
        UUID(receipt["job_id"]),
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="alice"),
        owner=canonical_hash({"issuer": "issuer", "subject": "alice"}),
        last_event_id=None,
    )

    async def consume():
        started = time.monotonic()
        chunks = [chunk async for chunk in response.body_iterator]
        return time.monotonic() - started, chunks

    elapsed, chunks = asyncio.run(consume())
    assert elapsed < 0.15, "The stream lifetime waited for a blocked dependency"
    assert chunks == [], "A snapshot completed after expiry and was still delivered"
