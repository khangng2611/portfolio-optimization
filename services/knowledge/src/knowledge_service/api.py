"""Owner API. Public operations are operator-only; retrieval is Chat-machine-only."""

from uuid import UUID, uuid4
import time
from fastapi import (
    FastAPI,
    Depends,
    Response,
    Request,
    Header,
    HTTPException,
    Query as PageQuery,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select, text, func
from sqlalchemy.exc import SQLAlchemyError
from portfolio_contracts import StrictModel, canonical_hash
from service_auth import AuthError
from service_observability import install_http_tracing
from .corpus import Manifest, MODEL, INDEX
from .models import (
    Corpus,
    ActiveCorpus,
    IndexJob,
    IndexingKey,
    LifecycleAudit,
    Chunk,
    Membership,
)
from .retrieval import Query, retrieve


class LifecycleRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=300)


def corpus_json(c, active=None, epoch=0):
    return {
        "id": c.id,
        "name": c.name,
        "status": c.status,
        "version": c.version + epoch,
        "hash": c.body_hash,
        "active": active == c.id,
    }


def job_json(j):
    return {"id": j.id, "corpus_id": j.corpus_id, "status": j.status, "error": j.error}


def create_app(*, sessions, verifier):
    app = FastAPI(title="Knowledge Service", version="0.1.0")
    bearer = HTTPBearer(auto_error=False)
    install_http_tracing(app)

    @app.middleware("http")
    async def bounds(request, call_next):
        request.state.request_id = str(uuid4())
        if request.method == "POST":
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 1048576:
                    return error(request, 413, "BODY_TOO_LARGE")
                body.extend(chunk)
            request._body = bytes(body)
        r = await call_next(request)
        r.headers["Cache-Control"] = "no-store"
        r.headers["X-Request-ID"] = request.state.request_id
        return r

    def error(request, status, code):
        return JSONResponse(
            {
                "error": {"code": code, "message": code, "retryable": status == 503},
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

    def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        try:
            if credentials is None:
                raise AuthError("missing")
            return verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(401, "UNAUTHENTICATED") from None

    def operator(request: Request, p=Depends(principal)):
        required = "knowledge:read" if request.method == "GET" else "knowledge:write"
        if "data-operator" not in p.roles or required not in p.scopes:
            raise HTTPException(403, "FORBIDDEN")
        return canonical_hash({"issuer": p.issuer, "subject": p.subject})

    def machine(p=Depends(principal)):
        if p.client_id != "chat-service" or "knowledge:retrieve" not in p.scopes:
            raise HTTPException(403, "FORBIDDEN")
        return p

    def key(value):
        import re

        if not value or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value):
            raise HTTPException(422, "IDEMPOTENCY_KEY_REQUIRED")
        return value

    def serialize(s):
        # Same owner queue/lifecycle lock across runtime instances.
        if s.bind.dialect.name == "postgresql":
            s.execute(select(func.pg_advisory_xact_lock(784512305)))

    def counts(s, corpus_id):
        total, embedded = s.execute(
            select(
                func.count(Chunk.id),
                func.count(Chunk.id).filter(
                    Chunk.embedding.is_not(None),
                    Chunk.embedding_model == MODEL,
                    Chunk.index_version == INDEX,
                ),
            )
            .join(Membership, Membership.document_id == Chunk.document_id)
            .where(Membership.corpus_id == corpus_id)
        ).one()
        return {"chunks": total, "embedded_chunks": embedded}

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with sessions() as s:
            s.execute(text("SELECT id FROM corpus LIMIT 1"))
            if s.bind.dialect.name == "postgresql":
                assert (
                    s.scalar(
                        text(
                            "SELECT extversion FROM pg_extension WHERE extname='vector'"
                        )
                    )
                    == "0.8.1"
                )
        return {"status": "ready"}

    @app.post("/api/v1/knowledge/indexing-jobs", status_code=202)
    def enqueue(
        body: Manifest,
        actor=Depends(operator),
        idempotency_key: str | None = Header(None),
    ):
        digest = canonical_hash(body.model_dump(mode="json"))
        k = key(idempotency_key)
        with sessions.begin() as s:
            serialize(s)
            alias = s.get(IndexingKey, (actor, k))
            if alias:
                if alias.body_hash != digest:
                    raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
                return job_json(s.get(IndexJob, alias.job_id))
            old = s.scalar(
                select(IndexJob).where(
                    IndexJob.actor == actor, IndexJob.idempotency_key == k
                )
            )
            if old and old.body_hash != digest:
                raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
            if not old:
                existing = s.scalar(select(Corpus).where(Corpus.body_hash == digest))
                if existing:
                    old = s.scalar(
                        select(IndexJob).where(IndexJob.corpus_id == existing.id)
                    )
            if not old:
                corpus = Corpus(
                    name=body.name,
                    body_hash=digest,
                    manifest=body.model_dump(mode="json"),
                )
                s.add(corpus)
                s.flush()
                old = IndexJob(
                    corpus_id=corpus.id,
                    actor=actor,
                    idempotency_key=k,
                    body_hash=digest,
                )
                s.add(old)
                s.flush()
            s.add(
                IndexingKey(
                    actor=actor, idempotency_key=k, body_hash=digest, job_id=old.id
                )
            )
            return job_json(old)

    @app.get("/api/v1/knowledge/indexing-jobs/{jid}")
    def job(jid: UUID, actor=Depends(operator)):
        with sessions() as s:
            j = s.get(IndexJob, str(jid))
            if not j:
                raise HTTPException(404, "NOT_FOUND")
            return job_json(j) | counts(s, j.corpus_id)

    @app.get("/api/v1/knowledge/corpora")
    def corpora(
        response: Response,
        limit: int = PageQuery(30, ge=1, le=100),
        offset: int = PageQuery(0, ge=0, le=1000000),
        actor=Depends(operator),
    ):
        with sessions() as s:
            active = s.get(ActiveCorpus, 1)
            response.headers["X-Total-Count"] = str(
                s.scalar(select(func.count()).select_from(Corpus))
            )
            response.headers["X-Limit"] = str(limit)
            response.headers["X-Offset"] = str(offset)
            return [
                corpus_json(
                    c,
                    active.corpus_id if active else None,
                    active.epoch if active else 0,
                )
                | counts(s, c.id)
                for c in s.scalars(
                    select(Corpus)
                    .order_by(Corpus.created_at.desc(), Corpus.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    def lifecycle(cid, body, action, actor, k, etag, response):
        k = key(k)
        digest = canonical_hash(
            {
                "corpus": str(cid),
                "body": body.model_dump(),
                "action": action,
                "if_match": etag,
            }
        )
        with sessions.begin() as s:
            serialize(s)
            old = s.scalar(
                select(LifecycleAudit).where(
                    LifecycleAudit.actor == actor, LifecycleAudit.idempotency_key == k
                )
            )
            if old:
                if old.body_hash != digest:
                    raise HTTPException(409, "IDEMPOTENCY_CONFLICT")
                response.headers["ETag"] = '"' + str(old.response["version"]) + '"'
                return old.response
            c = s.get(Corpus, str(cid))
            if not c:
                raise HTTPException(404, "NOT_FOUND")
            pointer = s.get(ActiveCorpus, 1)
            if etag != '"' + str(c.version + (pointer.epoch if pointer else 0)) + '"':
                raise HTTPException(412, "VERSION_CONFLICT")
            if c.status != "READY":
                raise HTTPException(409, "CORPUS_NOT_READY")
            if not pointer:
                pointer = ActiveCorpus(id=1, epoch=0)
                s.add(pointer)
            if action == "activate":
                pointer.corpus_id = c.id
            elif pointer.corpus_id == c.id:
                pointer.corpus_id = None
            c.version += 1
            pointer.epoch += 1
            result = corpus_json(c, pointer.corpus_id, pointer.epoch)
            s.add(
                LifecycleAudit(
                    actor=actor,
                    idempotency_key=k,
                    body_hash=digest,
                    corpus_id=c.id,
                    action=action,
                    reason=body.reason,
                    response=result,
                )
            )
            response.headers["ETag"] = '"' + str(result["version"]) + '"'
            return result

    @app.post("/api/v1/knowledge/corpora/{cid}/activate")
    def activate(
        cid: UUID,
        body: LifecycleRequest,
        response: Response,
        actor=Depends(operator),
        idempotency_key: str | None = Header(None),
        if_match: str | None = Header(None),
    ):
        return lifecycle(
            cid, body, "activate", actor, idempotency_key, if_match, response
        )

    @app.post("/api/v1/knowledge/corpora/{cid}/deactivate")
    def deactivate(
        cid: UUID,
        body: LifecycleRequest,
        response: Response,
        actor=Depends(operator),
        idempotency_key: str | None = Header(None),
        if_match: str | None = Header(None),
    ):
        return lifecycle(
            cid, body, "deactivate", actor, idempotency_key, if_match, response
        )

    @app.post("/internal/v1/knowledge/retrieve")
    def retrieval(body: Query, response: Response, identity=Depends(machine)):
        started = time.perf_counter()
        with sessions.begin() as s:
            if s.bind.dialect.name == "postgresql":
                s.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                s.execute(text("SET LOCAL statement_timeout='2500ms'"))
            result = retrieve(s, body)
            response.headers["Server-Timing"] = (
                f"retrieval;dur={(time.perf_counter() - started) * 1000:.3f}"
            )
            return result

    return app
