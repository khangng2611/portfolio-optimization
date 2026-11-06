import asyncio
from datetime import datetime, timedelta
import json
import time
from typing import Literal
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import Field
from sqlalchemy import select, func, text, update
from sqlalchemy.exc import SQLAlchemyError

from portfolio_contracts import StrictModel, aware, canonical_hash, utcnow
from service_auth import AuthError
from service_observability import install_http_tracing
from .models import Conversation, Event, Job, Message, ProviderInvocation
from .queue import append_event, TERMINAL
from .tools import ToolError

HUMAN_ROLES = {
    "investor",
    "researcher",
    "data-operator",
    "model-reviewer",
    "system-admin",
}


class NewConversation(StrictModel):
    title: str = Field(
        default="Hội thoại mới", min_length=1, max_length=120, pattern=r"\S"
    )
    portfolio_id: UUID | None = None
    llm_consent: bool = False


class ConversationPreferences(StrictModel):
    llm_consent: bool


class Confirmation(StrictModel):
    message_id: UUID
    facts_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResumeRequest(StrictModel):
    confirmed: Literal[True]
    authorization_id: UUID


class NewMessage(StrictModel):
    content: str = Field(min_length=1, max_length=4000, pattern=r"\S")
    client_message_id: str = Field(
        min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    portfolio_id: UUID | None = None
    intent: (
        Literal["allocation", "profile", "portfolio", "market", "explain", "help"]
        | None
    ) = None
    strategy: Literal["EW", "MVO", "BL_ML"] | None = None
    recommendation_id: UUID | None = None
    confirmation: Confirmation | None = None


def conversation_json(c):
    return {
        "id": c.id,
        "title": c.title,
        "portfolio_id": c.portfolio_id,
        "active_job_id": c.active_job_id,
        "llm_consent": c.llm_consent,
        "created_at": aware(c.created_at).isoformat(),
    }


def message_json(m):
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "role": m.role,
        "content": m.content,
        "client_message_id": m.client_message_id,
        "structured": m.structured,
        "created_at": aware(m.created_at).isoformat(),
    }


def accepted(j):
    return {
        "message_id": j.message_id,
        "job_id": j.id,
        "conversation_id": j.conversation_id,
        "status_url": f"/api/v1/jobs/chat/{j.id}",
        "events_url": f"/api/v1/jobs/chat/{j.id}/events",
    }


def create_app(*, sessions, verifier, tools, stream_seconds=85):
    app = FastAPI(title="Chat Service", version="0.1.0")
    install_http_tracing(app)
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def headers(request, call_next):
        request.state.request_id = str(uuid4())
        r = await call_next(request)
        r.headers["Cache-Control"] = "no-store"
        r.headers["X-Request-ID"] = request.state.request_id
        return r

    def error(request, status, code):
        return JSONResponse(
            {
                "error": {
                    "code": code,
                    "message": code,
                    "retryable": status in (502, 503),
                },
                "request_id": request.state.request_id,
            },
            status_code=status,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(request, 422, "INVALID_INPUT")

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request, exc):
        return error(request, 503, "DATABASE_UNAVAILABLE")

    @app.exception_handler(ToolError)
    async def tool_error(request, exc):
        return error(
            request,
            403
            if exc.code == "AUTHORIZATION_REQUIRED"
            else 409
            if exc.permanent
            else 503,
            exc.code,
        )

    @app.exception_handler(httpx.HTTPError)
    async def dependency_error(request, exc):
        return error(request, 503, "DEPENDENCY_UNAVAILABLE")

    def principal(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        try:
            if credentials is None:
                raise AuthError("missing")
            identity = verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(401, "UNAUTHENTICATED") from None
        scope = "chat:read" if request.method == "GET" else "chat:write"
        if scope not in identity.scopes or not HUMAN_ROLES.intersection(identity.roles):
            raise HTTPException(403, "FORBIDDEN")
        return canonical_hash({"issuer": identity.issuer, "subject": identity.subject})

    def owned(s, cid, owner):
        c = s.scalar(
            select(Conversation).where(
                Conversation.id == str(cid), Conversation.owner_key == owner
            )
        )
        if not c:
            raise HTTPException(404, "NOT_FOUND")
        return c

    def page(response, s, query, limit, offset):
        response.headers["X-Total-Count"] = str(
            s.scalar(select(func.count()).select_from(query.subquery()))
        )
        response.headers["X-Limit"], response.headers["X-Offset"] = (
            str(limit),
            str(offset),
        )

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with sessions() as s:
            s.execute(text("SELECT id FROM conversation LIMIT 1"))
        return {"status": "ready"}

    @app.post("/api/v1/conversations", status_code=201)
    def create(body: NewConversation, owner=Depends(principal)):
        with sessions.begin() as s:
            c = Conversation(
                owner_key=owner,
                title=body.title.strip(),
                portfolio_id=str(body.portfolio_id) if body.portfolio_id else None,
                llm_consent=body.llm_consent,
            )
            s.add(c)
            s.flush()
            return conversation_json(c)

    @app.get("/api/v1/conversations")
    def conversations(
        response: Response,
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1_000_000),
        owner=Depends(principal),
    ):
        with sessions() as s:
            q = select(Conversation).where(Conversation.owner_key == owner)
            page(response, s, q, limit, offset)
            return [
                conversation_json(c)
                for c in s.scalars(
                    q.order_by(Conversation.created_at.desc(), Conversation.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.get("/api/v1/conversations/{cid}")
    def conversation(cid: UUID, owner=Depends(principal)):
        with sessions() as s:
            return conversation_json(owned(s, cid, owner))

    @app.post("/api/v1/conversations/{cid}/preferences")
    def preferences(cid: UUID, body: ConversationPreferences, owner=Depends(principal)):
        with sessions.begin() as s:
            c = owned(s, cid, owner)
            c.llm_consent = body.llm_consent
            s.flush()
            return conversation_json(c)

    @app.get("/api/v1/conversations/{cid}/messages")
    def messages(
        cid: UUID,
        response: Response,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1_000_000),
        owner=Depends(principal),
    ):
        with sessions() as s:
            owned(s, cid, owner)
            q = select(Message).where(Message.conversation_id == str(cid))
            page(response, s, q, limit, offset)
            return [
                message_json(m)
                for m in s.scalars(
                    q.order_by(Message.created_at, Message.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    def lock_owner(s, owner):
        # Serialize quotas across all conversations of an owner. SQLite already
        # serializes the conditional writes below; PostgreSQL needs a user lock.
        if s.bind.dialect.name == "postgresql":
            s.execute(select(func.pg_advisory_xact_lock(int(owner[:15], 16))))

    @app.post("/api/v1/conversations/{cid}/messages", status_code=202)
    def send(
        cid: UUID,
        body: NewMessage,
        credentials: HTTPAuthorizationCredentials = Depends(bearer),
        owner=Depends(principal),
        idempotency_key: str | None = Header(default=None),
    ):
        if idempotency_key != body.client_message_id:
            raise HTTPException(400, "KEY_MUST_MATCH_CLIENT_MESSAGE_ID")
        digest = canonical_hash(body.model_dump(mode="json"))
        with sessions.begin() as s:
            lock_owner(s, owner)
            # Locks even on SQLite, so concurrent HTTP retries resolve the first receipt.
            s.execute(
                update(Conversation)
                .where(Conversation.id == str(cid), Conversation.owner_key == owner)
                .values(title=Conversation.title)
            )
            c = owned(s, cid, owner)
            old = s.scalar(
                select(Message).where(
                    Message.conversation_id == c.id,
                    Message.client_message_id == body.client_message_id,
                )
            )
            if old:
                if old.body_hash != digest:
                    raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
                return accepted(s.scalar(select(Job).where(Job.message_id == old.id)))
            active = s.get(Job, c.active_job_id) if c.active_job_id else None
            if active and active.status not in TERMINAL:
                raise HTTPException(409, "TURN_IN_PROGRESS")
            pending = s.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.owner_key == owner, Job.status.not_in(TERMINAL))
            )
            recent = s.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.owner_key == owner,
                    Job.created_at > utcnow() - timedelta(hours=1),
                )
            )
            if pending >= 5 or recent >= 100:
                raise HTTPException(429, "QUOTA_EXCEEDED")
            jid, mid = str(uuid4()), str(uuid4())
            request = body.model_dump(mode="json")
            if body.confirmation:
                card = s.get(Message, str(body.confirmation.message_id))
                if (
                    not card
                    or card.conversation_id != c.id
                    or card.role != "assistant"
                    or not card.structured
                    or card.structured.get("type") != "confirmation"
                    or card.structured.get("facts_hash") != body.confirmation.facts_hash
                    or card.consumed_by
                ):
                    raise HTTPException(409, "INVALID_CONFIRMATION")
                card.consumed_by = jid
                request["confirmed_input"] = card.structured["input"]
            pid = str(body.portfolio_id) if body.portfolio_id else c.portfolio_id
            if (
                body.confirmation
                and request["confirmed_input"]["portfolio"]["id"] != pid
            ):
                raise HTTPException(409, "INVALID_CONFIRMATION")
            grant = tools.grant(
                credentials.credentials,
                c.id,
                jid,
                pid,
                allow_mutation=bool(body.confirmation),
            )
            c.portfolio_id, c.active_job_id = pid, jid
            request["portfolio_id"] = pid
            s.add(
                Message(
                    id=mid,
                    conversation_id=c.id,
                    role="user",
                    content=body.content.strip(),
                    client_message_id=body.client_message_id,
                    body_hash=digest,
                )
            )
            s.flush()
            j = Job(
                id=jid,
                conversation_id=c.id,
                owner_key=owner,
                message_id=mid,
                request=request,
                grant_id=grant["grant_id"],
                grant_expires_at=datetime.fromisoformat(grant["expires_at"]),
                deadline=utcnow() + timedelta(seconds=180),
                event_sequence=0,
            )
            s.add(j)
            s.flush()
            append_event(s, j, "accepted", {"message_id": mid, "job_id": jid})
            return accepted(j)

    def owned_job(s, jid, owner):
        j = s.scalar(select(Job).where(Job.id == str(jid), Job.owner_key == owner))
        if not j:
            raise HTTPException(404, "NOT_FOUND")
        owned(s, j.conversation_id, owner)
        return j

    @app.get("/api/v1/jobs/chat/{jid}")
    def job(jid: UUID, owner=Depends(principal)):
        with sessions() as s:
            j = owned_job(s, jid, owner)
            return accepted(j) | {
                "status": j.status,
                "stage": j.stage,
                "error": j.error,
                "recommendation_id": j.recommendation_id,
                "result_message_id": j.result_message_id,
                "last_event_id": j.event_sequence,
                "attempts": j.attempts,
                "provider_usage": [
                    {
                        "purpose": call.purpose,
                        **(call.details or {"reason": "RESERVED"}),
                    }
                    for call in s.scalars(
                        select(ProviderInvocation)
                        .where(ProviderInvocation.job_id == j.id)
                        .order_by(
                            ProviderInvocation.created_at, ProviderInvocation.purpose
                        )
                    )
                ],
            }

    @app.post("/api/v1/jobs/chat/{jid}/cancel")
    def cancel(jid: UUID, body: StrictModel, owner=Depends(principal)):
        with sessions.begin() as s:
            s.execute(
                update(Job)
                .where(Job.id == str(jid), Job.owner_key == owner)
                .values(lease_token=Job.lease_token)
            )
            j = owned_job(s, jid, owner)
            if j.status not in TERMINAL:
                j.status, j.lease_token, j.lease_until = "CANCELLED", None, None
                append_event(s, j, "cancelled", {"job_id": j.id})
            return {"job_id": j.id, "status": j.status}

    @app.post("/api/v1/jobs/chat/{jid}/resume", status_code=202)
    def resume(
        jid: UUID,
        body: ResumeRequest,
        credentials: HTTPAuthorizationCredentials = Depends(bearer),
        owner=Depends(principal),
    ):
        with sessions.begin() as s:
            lock_owner(s, owner)
            cid = s.scalar(
                select(Job.conversation_id).where(
                    Job.id == str(jid), Job.owner_key == owner
                )
            )
            if cid is None:
                raise HTTPException(404, "NOT_FOUND")
            # Same lock order as send: conversation before job. Otherwise resume
            # and a new turn can both become active while grant HTTP is in flight.
            s.execute(
                update(Conversation)
                .where(Conversation.id == cid, Conversation.owner_key == owner)
                .values(title=Conversation.title)
            )
            s.execute(
                update(Job)
                .where(Job.id == str(jid), Job.owner_key == owner)
                .values(lease_token=Job.lease_token)
            )
            j = owned_job(s, jid, owner)
            if j.reauthorization_id == str(body.authorization_id):
                return accepted(j)
            if j.status != "AUTHORIZATION_REQUIRED":
                raise HTTPException(409, "RESUME_NOT_REQUIRED")
            pending = s.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.owner_key == owner, Job.status.not_in(TERMINAL))
            )
            if pending >= 5:
                raise HTTPException(429, "QUOTA_EXCEEDED")
            c = owned(s, j.conversation_id, owner)
            if c.active_job_id != j.id:
                raise HTTPException(409, "NEWER_TURN_EXISTS")
            grant = tools.grant(
                credentials.credentials,
                c.id,
                j.id,
                j.request.get("portfolio_id"),
                str(body.authorization_id),
                allow_mutation=bool(j.request.get("confirmed_input")),
            )
            j.reauthorization_id = str(body.authorization_id)
            j.grant_id = grant["grant_id"]
            j.grant_expires_at = datetime.fromisoformat(grant["expires_at"])
            j.status, j.error, j.attempts = "QUEUED", None, 0
            j.deadline, j.next_attempt_at = utcnow() + timedelta(seconds=180), utcnow()
            append_event(
                s, j, "stage_changed", {"stage": j.stage, "status": "REAUTHORIZED"}
            )
            return accepted(j)

    @app.get("/api/v1/jobs/chat/{jid}/events")
    def events(
        jid: UUID,
        credentials: HTTPAuthorizationCredentials = Depends(bearer),
        owner=Depends(principal),
        last_event_id: str | None = Header(default=None),
    ):
        if last_event_id is not None and (
            not last_event_id.isascii()
            or not last_event_id.isdigit()
            or len(last_event_id) > 12
        ):
            raise HTTPException(400, "INVALID_EVENT_ID")
        after = int(last_event_id or "0")
        with sessions() as s:
            owned_job(s, jid, owner)

        def poll(cursor):
            # Keep each session and all lazy ORM reads inside one worker thread.
            verifier.verify(credentials.credentials)
            with sessions() as s:
                j = owned_job(s, jid, owner)
                first = s.scalar(
                    select(func.min(Event.sequence)).where(Event.job_id == j.id)
                )
                reset = cursor > j.event_sequence or (
                    cursor < j.event_sequence and (first is None or cursor < first - 1)
                )
                rows = (
                    []
                    if reset
                    else s.scalars(
                        select(Event)
                        .where(Event.job_id == j.id, Event.sequence > cursor)
                        .order_by(Event.sequence)
                        .limit(100)
                    ).all()
                )
                return (
                    reset,
                    accepted(j)["status_url"],
                    [
                        (e.sequence, e.type, json.dumps(e.payload, ensure_ascii=False))
                        for e in rows
                    ],
                    j.status in TERMINAL,
                    j.event_sequence,
                )

        async def stream():
            cursor, heartbeat = after, time.monotonic()
            deadline = heartbeat + stream_seconds
            while time.monotonic() < deadline:
                try:
                    reset, status_url, rows, done, sequence = await asyncio.wait_for(
                        asyncio.to_thread(poll, cursor),
                        timeout=min(5.0, deadline - time.monotonic()),
                    )
                except AuthError:
                    if time.monotonic() < deadline:
                        yield "event: session_expired\ndata: {}\n\n"
                    return
                except (TimeoutError, SQLAlchemyError):
                    # Reconnect rechecks ownership and replays the durable cursor.
                    # Timing out a thread discards its snapshot; it cannot publish.
                    return
                if time.monotonic() >= deadline:
                    return
                if reset:
                    yield (
                        "event: reset_required\ndata: "
                        + json.dumps({"status_url": status_url})
                        + "\n\n"
                    )
                    return
                for event_id, kind, payload in rows:
                    if time.monotonic() >= deadline:
                        return
                    cursor = event_id
                    yield f"id: {event_id}\nevent: {kind}\ndata: {payload}\n\n"
                if done and cursor >= sequence:
                    return
                if time.monotonic() - heartbeat >= 15:
                    yield ": heartbeat\n\n"
                    heartbeat = time.monotonic()
                await asyncio.sleep(min(0.25, max(0, deadline - time.monotonic())))

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    @app.get("/api/v1/recommendations/{rid}/explanation")
    def explanation(
        rid: UUID,
        credentials: HTTPAuthorizationCredentials = Depends(bearer),
        owner=Depends(principal),
    ):
        facts = tools.read_recommendation(credentials.credentials, str(rid))
        with sessions() as s:
            jobs = s.scalars(
                select(Job)
                .where(
                    Job.owner_key == owner,
                    Job.recommendation_id == str(rid),
                    Job.status == "SUCCEEDED",
                )
                .order_by(Job.created_at.desc())
            ).all()
            for j in jobs:
                m = s.get(Message, j.result_message_id)
                if (
                    m
                    and m.structured
                    and m.structured.get("facts_hash") == canonical_hash(facts)
                ):
                    return message_json(m)
        return {"status": "NOT_GENERATED", "recommendation_id": str(rid)}

    return app
