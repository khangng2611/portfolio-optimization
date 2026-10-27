from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from portfolio_contracts import Envelope, aware, canonical_hash, utcnow
from portfolio_contracts.market import (
    DatasetRegistration,
    IngestCommand,
    IngestionRequest,
    SnapshotRequest,
)
from service_auth import AuthError
from service_observability import (
    capture_context,
    install_http_tracing,
    link_job,
    log_event,
    span,
    trace_fields,
)
from .models import (
    Actor,
    Asset,
    IngestionJob,
    Outbox,
    PriceRevision,
    Snapshot,
    RegisteredDataset,
    DatasetRegistrationReceipt,
)
from .registry import bootstrap, metadata, dataset_json
from .quality import terminal_quality
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

    def operator(identity=Depends(principal)):
        if "data-operator" not in identity.roles:
            raise HTTPException(403, "Data operator role required")
        return identity

    def page_headers(response, total, limit, offset):
        response.headers["X-Total-Count"] = str(total)
        response.headers["X-Limit"] = str(limit)
        response.headers["X-Offset"] = str(offset)

    def valid_key(value):
        if (
            not value
            or not 1 <= len(value) <= 128
            or any(ord(c) < 33 or ord(c) > 126 for c in value)
        ):
            raise HTTPException(
                400, "Idempotency-Key requires 1–128 visible ASCII characters"
            )

    @app.get("/api/v1/market/dataset-inventory")
    def dataset_inventory(
        response: Response,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
        identity=Depends(operator),
    ):
        try:
            ids = provider.inventory_ids()
            page_ids = ids[offset : offset + limit]
            with sessions() as session:
                registered = dict(
                    session.execute(
                        select(
                            RegisteredDataset.dataset_id, RegisteredDataset.sha256
                        ).where(RegisteredDataset.dataset_id.in_(page_ids))
                    ).all()
                )
            result = []
            for dataset_id in page_ids:
                spec = provider.spec(dataset_id)
                try:
                    start, end = provider.coverage(spec)
                    item = metadata(dataset_id, spec, start, end) | {"available": True}
                except (ValueError, OSError, UnicodeError):
                    item = metadata(dataset_id, spec) | {"available": False}
                item |= {
                    "registered": dataset_id in registered,
                    "registered_sha256": registered.get(dataset_id),
                }
                result.append(item)
        except (ValueError, KeyError, OSError, TypeError):
            raise HTTPException(
                422, "Trusted inventory unavailable or invalid"
            ) from None
        page_headers(response, len(ids), limit, offset)
        return result

    @app.get("/api/v1/market/datasets")
    def datasets(
        response: Response,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
        identity=Depends(operator),
    ):
        with sessions() as session:
            total = session.scalar(select(func.count()).select_from(RegisteredDataset))
            rows = session.scalars(
                select(RegisteredDataset)
                .order_by(RegisteredDataset.dataset_id)
                .offset(offset)
                .limit(limit)
            )
            result = [dataset_json(row) for row in rows]
        page_headers(response, total, limit, offset)
        return result

    @app.post("/api/v1/market/datasets", status_code=201)
    def register_dataset(
        body: DatasetRegistration,
        actor_id=Depends(actor),
        identity=Depends(operator),
        idempotency_key: str | None = Header(default=None),
    ):
        valid_key(idempotency_key)
        digest = canonical_hash(body.model_dump(mode="json"))
        with sessions.begin() as session:
            session.scalar(select(Actor).where(Actor.id == actor_id).with_for_update())
            receipt = session.scalar(
                select(DatasetRegistrationReceipt).where(
                    DatasetRegistrationReceipt.actor_id == actor_id,
                    DatasetRegistrationReceipt.idempotency_key == idempotency_key,
                )
            )
            if receipt:
                if receipt.request_hash != digest:
                    raise HTTPException(
                        409, "Idempotency-Key already used with another input"
                    )
                return receipt.response
            existing = session.get(RegisteredDataset, body.dataset_id)
            if existing:
                if existing.sha256 != body.expected_sha256:
                    raise HTTPException(409, "Registered dataset checksum is immutable")
                result = dataset_json(existing)
            else:
                try:
                    spec = provider.spec(body.dataset_id)
                    if spec["sha256"] != body.expected_sha256:
                        raise HTTPException(
                            409, "Expected checksum does not match trusted inventory"
                        )
                    coverage = provider.coverage(spec)
                    row = bootstrap(
                        session,
                        provider,
                        body.dataset_id,
                        actor_id,
                        spec=spec,
                        coverage=coverage,
                    )
                    if row.sha256 != body.expected_sha256:
                        raise HTTPException(
                            409, "Registered dataset checksum is immutable"
                        )
                except (ValueError, KeyError, OSError, TypeError, UnicodeError):
                    raise HTTPException(
                        422, "Trusted dataset unavailable or invalid"
                    ) from None
                result = dataset_json(row)
            session.add(
                DatasetRegistrationReceipt(
                    actor_id=actor_id,
                    idempotency_key=idempotency_key,
                    request_hash=digest,
                    response=result,
                )
            )
            return result

    @app.get("/api/v1/market/ingestions")
    def ingestions(
        response: Response,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
        identity=Depends(operator),
    ):
        with sessions.begin() as session:
            total = session.scalar(select(func.count()).select_from(IngestionJob))
            rows = session.scalars(
                select(IngestionJob)
                .order_by(IngestionJob.created_at.desc(), IngestionJob.id)
                .offset(offset)
                .limit(limit)
            )
            result = []
            for row in rows:
                quality = terminal_quality(session, row)
                result.append(
                    {
                        "job_id": row.id,
                        "dataset_id": row.input["request"].get("dataset_id"),
                        "status": row.status,
                        "inserted_count": row.inserted_count,
                        "error": row.error,
                        "quality_status": quality.status if quality else "PENDING",
                        "quality_url": f"/api/v1/market/ingestions/{row.id}/quality",
                        "created_at": aware(row.created_at).isoformat(),
                    }
                )
        page_headers(response, total, limit, offset)
        return result

    @app.get("/api/v1/market/ingestions/{job_id}/quality")
    def quality_report(job_id: UUID, identity=Depends(operator)):
        with sessions.begin() as session:
            job = session.get(IngestionJob, str(job_id))
            if job is None:
                raise HTTPException(404, "Ingestion job not found")
            quality = terminal_quality(session, job)
            return (
                quality.report
                if quality
                else {
                    "job_id": str(job_id),
                    "status": "PENDING",
                    "row_count": 0,
                    "findings": [],
                }
            )

    @app.get("/api/v1/market/snapshots")
    def snapshots(
        response: Response,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
        identity=Depends(operator),
    ):
        with sessions() as session:
            total = session.scalar(select(func.count()).select_from(Snapshot))
            result = [
                snapshot_json(row)
                for row in session.scalars(
                    select(Snapshot)
                    .order_by(Snapshot.created_at.desc(), Snapshot.id)
                    .offset(offset)
                    .limit(limit)
                )
            ]
        page_headers(response, total, limit, offset)
        return result

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
        normalized = body.model_dump(mode="json")
        for row in normalized.get("observations") or []:
            for key in ("data_origin", "price_basis"):
                if row.get(key) == "unverified":
                    row.pop(key)
        request_hash = canonical_hash(normalized)
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
                    spec = bootstrap(session, provider, body.dataset_id, actor_id).spec
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
            serialized_command = command.model_dump(mode="json") | {
                "request": normalized
            }
            event = Envelope(
                type="market.ingestion.requested",
                producer="market-data",
                correlation_id=job_id,
                payload=serialized_command,
            )
            with span(
                "market.job.persist",
                attributes={"job.id": job_id, "event.id": event.event_id},
            ):
                context = capture_context()
                session.add_all(
                    [
                        IngestionJob(
                            id=job_id,
                            actor_id=actor_id,
                            idempotency_key=idempotency_key,
                            request_hash=request_hash,
                            input=serialized_command,
                            deadline=utcnow() + timedelta(minutes=15),
                            trace_context=context,
                        ),
                        Outbox(
                            event_id=event.event_id,
                            payload=event.model_dump(mode="json"),
                            trace_context=context,
                        ),
                    ]
                )
                session.flush()
                log_event(
                    "market.job.persist",
                    job_id=job_id,
                    event_id=event.event_id,
                    status="QUEUED",
                )
            return {
                "job_id": job_id,
                "status_url": f"/api/v1/jobs/market/{job_id}",
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
            terminal_quality(session, job)
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

    def snapshot_reader(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        try:
            if credentials is None:
                raise AuthError()
            identity = verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(401, "Valid service identity required") from None
        if "market:snapshot:read" not in identity.scopes:
            raise HTTPException(403, "Missing market:snapshot:read scope")
        return identity

    @app.get("/internal/v1/market/snapshots/{snapshot_id}")
    def internal_snapshot(snapshot_id: UUID, identity=Depends(snapshot_reader)):
        with sessions() as session:
            value = session.get(Snapshot, str(snapshot_id))
            if value is None:
                raise HTTPException(404, "Snapshot not found")
            return snapshot_json(value)

    @app.get("/internal/v1/market/snapshots/{snapshot_id}/observations")
    def internal_observations(snapshot_id: UUID, identity=Depends(snapshot_reader)):
        with sessions() as session:
            value = session.get(Snapshot, str(snapshot_id))
            if value is None:
                raise HTTPException(404, "Snapshot not found")
            return value.observations

    from .refresh_api import install_refresh_routes
    install_refresh_routes(app, sessions=sessions, operator=operator, actor=actor, valid_key=valid_key, page_headers=page_headers)
    return app
