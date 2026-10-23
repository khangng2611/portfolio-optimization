from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from portfolio_contracts import Envelope, aware, canonical_hash, utcnow
from portfolio_contracts.market import IngestCommand, IngestionRequest, SnapshotRequest
from service_auth import AuthError
from service_observability import (
    capture_context, install_http_tracing, link_job, log_event, span, trace_fields,
)
from .models import Actor, Asset, IngestionJob, Outbox, PriceRevision, Snapshot
from .snapshots import build_snapshot, observation_json, snapshot_json

HUMAN_ROLES = {
    "investor",
    "researcher",
    "data-operator",
    "model-reviewer",
    "system-admin",
}


def create_app(*, sessions, verifier, provider):
    app = FastAPI(title="Market Data Service", version="0.1.0")
    install_http_tracing(app)
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def request_metadata(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    def error(request, status, code, message, headers=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {"code": code, "message": message, "retryable": status == 503},
                "request_id": request.state.request_id,
            },
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(
            request,
            exc.status_code,
            {
                401: "UNAUTHENTICATED",
                403: "FORBIDDEN",
                404: "NOT_FOUND",
                409: "CONFLICT",
                429: "QUOTA_EXCEEDED",
                503: "DEPENDENCY_UNAVAILABLE",
            }.get(exc.status_code, "INVALID_REQUEST"),
            str(exc.detail),
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(
            request, 422, "INVALID_INPUT", "Invalid ingestion or snapshot input"
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return error(
            request,
            503,
            "DATABASE_UNAVAILABLE",
            "Market database temporarily unavailable",
        )

    def principal(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        try:
            if credentials is None:
                raise AuthError()
            identity = verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(
                401, "Valid identity required", headers={"WWW-Authenticate": "Bearer"}
            ) from None
        scope = "market:read" if request.method == "GET" else "market:write"
        allowed = HUMAN_ROLES if request.method == "GET" else {"data-operator"}
        if scope not in identity.scopes or not allowed.intersection(identity.roles):
            raise HTTPException(403, "Market role/scope required")
        return identity

    def actor(identity=Depends(principal)):
        with sessions.begin() as session:
            value = session.scalar(
                select(Actor).where(
                    Actor.issuer == identity.issuer, Actor.subject == identity.subject
                )
            )
            if value is None:
                try:
                    with session.begin_nested():
                        value = Actor(issuer=identity.issuer, subject=identity.subject)
                        session.add(value)
                        session.flush()
                except IntegrityError:
                    value = session.scalar(
                        select(Actor).where(
                            Actor.issuer == identity.issuer,
                            Actor.subject == identity.subject,
                        )
                    )
            return value.id

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        with sessions() as session:
            session.execute(text("SELECT 1 FROM asset LIMIT 1"))
        return {"status": "ready"}

    @app.post("/api/v1/market/ingestions", status_code=202)
    def ingest(
        body: IngestionRequest,
        actor_id=Depends(actor),
        idempotency_key: str | None = Header(default=None),
    ):
        if (
            not idempotency_key
            or not 1 <= len(idempotency_key) <= 128
            or any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key)
        ):
            raise HTTPException(
                400, "Idempotency-Key requires 1–128 visible ASCII characters"
            )
        request_hash = canonical_hash(body.model_dump(mode="json"))
        with sessions.begin() as session:
            session.scalar(select(Actor).where(Actor.id == actor_id).with_for_update())
            existing = session.scalar(
                select(IngestionJob).where(
                    IngestionJob.actor_id == actor_id,
                    IngestionJob.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise HTTPException(
                        409, "Idempotency-Key already used with another input"
                    )
                log_event("market.job.accept", job_id=existing.id, outcome="duplicate")
                return {
                    "job_id": existing.id,
                    "status_url": f"/api/v1/jobs/market/{existing.id}",
                    **trace_fields(existing.trace_context),
                }
            pending = session.scalar(
                select(func.count())
                .select_from(IngestionJob)
                .where(
                    IngestionJob.actor_id == actor_id,
                    IngestionJob.status == "QUEUED",
                    IngestionJob.deadline > utcnow(),
                )
            )
            if pending >= 5:
                raise HTTPException(429, "At most five pending ingestions per actor")
            spec = None
            if body.dataset_id:
                try:
                    spec = provider.spec(body.dataset_id)
                except (ValueError, KeyError, OSError, TypeError):
                    raise HTTPException(
                        422, "Registered dataset unavailable or invalid"
                    ) from None
            job_id = str(uuid4())
            command = IngestCommand(
                job_id=job_id,
                request_hash=request_hash,
                request=body,
                dataset_spec=spec,
            )
            event = Envelope(
                type="market.ingestion.requested",
                producer="market-data",
                correlation_id=job_id,
                payload=command.model_dump(mode="json"),
            )
            with span("market.job.persist", attributes={"job.id": job_id, "event.id": event.event_id}):
                context = capture_context()
                session.add_all(
                    [
                        IngestionJob(
                            id=job_id,
                            actor_id=actor_id,
                            idempotency_key=idempotency_key,
                            request_hash=request_hash,
                            input=command.model_dump(mode="json"),
                            deadline=utcnow() + timedelta(minutes=15),
                            trace_context=context,
                        ),
                        Outbox(event_id=event.event_id, payload=event.model_dump(mode="json"), trace_context=context),
                    ]
                )
                session.flush()
                log_event("market.job.persist", job_id=job_id, event_id=event.event_id, status="QUEUED")
            return {
                "job_id": job_id, "status_url": f"/api/v1/jobs/market/{job_id}",
                **trace_fields(context),
            }

    @app.get("/api/v1/jobs/market/{job_id}")
    def get_job(job_id: UUID, actor_id=Depends(actor)):
        with sessions.begin() as session:
            job = session.scalar(
                select(IngestionJob)
                .where(
                    IngestionJob.id == str(job_id), IngestionJob.actor_id == actor_id
                )
                .with_for_update()
            )
            if job is None:
                raise HTTPException(404, "Ingestion job not found")
            link_job(job.trace_context, job.id)
            if job.status == "QUEUED" and aware(job.deadline) <= utcnow():
                job.status, job.error = (
                    "FAILED",
                    {
                        "code": "DEADLINE_EXCEEDED",
                        "message": "Ingestion deadline exceeded",
                    },
                )
            return {
                "job_id": job.id,
                "status": job.status,
                "inserted_count": job.inserted_count,
                "error": job.error,
                **trace_fields(job.trace_context),
            }

    @app.get("/api/v1/market/assets")
    def assets(identity=Depends(principal)):
        with sessions() as session:
            return [
                {"asset_id": row.id, "kind": row.kind, "unit": row.unit}
                for row in session.scalars(select(Asset).order_by(Asset.id).limit(1000))
            ]

    @app.get("/api/v1/market/prices")
    def prices(
        asset_id: str,
        start_date: date,
        end_date: date,
        limit: int = Query(default=1000, ge=1, le=5000),
        identity=Depends(principal),
    ):
        if start_date > end_date:
            raise HTTPException(422, "Invalid price date range")
        with sessions() as session:
            return [
                observation_json(row)
                for row in session.scalars(
                    select(PriceRevision)
                    .where(
                        PriceRevision.asset_id == asset_id,
                        PriceRevision.observation_date.between(start_date, end_date),
                    )
                    .order_by(
                        PriceRevision.observation_date,
                        PriceRevision.provider,
                        PriceRevision.price_type,
                        PriceRevision.revision,
                    )
                    .limit(limit)
                )
            ]

    @app.post("/api/v1/market/snapshots", status_code=201)
    def snapshot(body: SnapshotRequest, identity=Depends(principal)):
        with sessions.begin() as session:
            try:
                value = build_snapshot(session, body)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
            return snapshot_json(value)

    @app.get("/api/v1/market/snapshots/{snapshot_id}")
    def get_snapshot(snapshot_id: UUID, identity=Depends(principal)):
        with sessions() as session:
            value = session.get(Snapshot, str(snapshot_id))
            if value is None:
                raise HTTPException(404, "Snapshot not found")
            return snapshot_json(value)

    @app.get("/api/v1/market/snapshots/{snapshot_id}/observations")
    def snapshot_observations(snapshot_id: UUID, identity=Depends(principal)):
        with sessions() as session:
            value = session.get(Snapshot, str(snapshot_id))
            if value is None:
                raise HTTPException(404, "Snapshot not found")
            return value.observations

    return app
