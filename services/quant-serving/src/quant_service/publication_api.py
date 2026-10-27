"""Human operation of the SQL publication queue; catalog writes remain worker-only."""

from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, Query, Response
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from portfolio_contracts import aware, canonical_hash
from service_auth import AuthError
from .models import PublicationJob
from .publication_worker import IdempotencyConflict, PublicationQueue, validate_request


PATH = "/api/v1/market/publications"
Status = Literal["QUEUED", "RUNNING", "RETRY", "SUCCEEDED", "FAILED"]


class PublicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    universe_id: str = Field(pattern=r"^[A-Z0-9_-]{1,64}$")
    max_age_days: int = Field(
        default=7,
        strict=True,
        ge=1,
        le=30,
        description="Maximum snapshot age in calendar days (1–30).",
    )
    lookback: int = Field(default=252, strict=True, ge=2, le=5000)
    min_returns: int = Field(default=60, strict=True, ge=2, le=5000)

    @model_validator(mode="after")
    def immutable_pins(self):
        validate_request(self.model_dump(mode="json"))
        return self


def actor_prefix(identity):
    # This durable namespace provides ownership without storing raw OIDC claims
    # or requiring an actor-table migration. CLI/scheduler namespaces stay separate.
    return (
        "human:"
        + canonical_hash({"issuer": identity.issuer, "subject": identity.subject})
        + ":"
    )


def job_json(job):
    return {
        "job_id": job.id,
        "status_url": f"{PATH}/{job.id}",
        "status": job.status,
        "request": {key: job.request[key] for key in PublicationRequest.model_fields},
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "next_attempt_at": aware(job.next_attempt_at).isoformat(),
        # Worker references also contain a local filename. Only immutable public
        # identifiers belong in this human API, never filesystem references.
        "result": {
            key: job.result[key] for key in ("bundle_id", "sha256") if key in job.result
        }
        if job.result is not None
        else None,
        "safe_error": job.safe_error,
        "created_at": aware(job.created_at).isoformat(),
        "updated_at": aware(job.updated_at).isoformat(),
    }


def install_publication_api(app, *, sessions, verifier, bearer):
    queue = PublicationQueue(sessions)

    @app.middleware("http")
    async def publication_metadata(request, call_next):
        if not request.url.path.startswith(PATH):
            return await call_next(request)
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
                "request_id": getattr(request.state, "request_id", str(uuid4())),
            },
            headers=headers,
        )

    @app.exception_handler(HTTPException)
    async def publication_http_error(request, exc):
        if not request.url.path.startswith(PATH):
            return await http_exception_handler(request, exc)
        return error(
            request,
            exc.status_code,
            {
                401: "UNAUTHENTICATED",
                403: "FORBIDDEN",
                404: "NOT_FOUND",
                409: "CONFLICT",
            }.get(exc.status_code, "INVALID_REQUEST"),
            str(exc.detail),
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def publication_validation_error(request, exc):
        if not request.url.path.startswith(PATH):
            return await request_validation_exception_handler(request, exc)
        return error(request, 422, "INVALID_INPUT", "Invalid publication input")

    @app.exception_handler(SQLAlchemyError)
    async def publication_database_error(request, exc):
        return error(
            request,
            503,
            "DATABASE_UNAVAILABLE",
            "Quant database temporarily unavailable",
        )

    def operator_identity(
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
        if (
            "quant:publish" not in identity.scopes
            or "data-operator" not in identity.roles
        ):
            raise HTTPException(403, "Publication operator role/scope required")
        return identity

    @app.post(PATH, status_code=202)
    def enqueue_publication(
        body: PublicationRequest,
        identity=Depends(operator_identity),
        idempotency_key: str | None = Header(default=None),
    ):
        if (
            not idempotency_key
            or not 1 <= len(idempotency_key) <= 128
            or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key)
        ):
            raise HTTPException(
                400, "Idempotency-Key requires 1–128 visible ASCII characters"
            )
        key = actor_prefix(identity) + canonical_hash({"key": idempotency_key})
        try:
            job = queue.enqueue(key, body.model_dump(mode="json"))
        except IdempotencyConflict:
            raise HTTPException(
                409, "Idempotency-Key already used with another input"
            ) from None
        return job_json(job)

    @app.get(PATH)
    def list_publications(
        response: Response,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        status: Status | None = None,
        snapshot_id: UUID | None = None,
        identity=Depends(operator_identity),
    ):
        conditions = [PublicationJob.idempotency_key.startswith(actor_prefix(identity))]
        if status is not None:
            conditions.append(PublicationJob.status == status)
        if snapshot_id is not None:
            conditions.append(
                PublicationJob.request["snapshot_id"].as_string() == str(snapshot_id)
            )
        with sessions() as session:
            total = session.scalar(
                select(func.count()).select_from(PublicationJob).where(*conditions)
            )
            rows = session.scalars(
                select(PublicationJob)
                .where(*conditions)
                .order_by(PublicationJob.created_at.desc(), PublicationJob.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            response.headers.update(
                {
                    "X-Total-Count": str(total),
                    "X-Limit": str(limit),
                    "X-Offset": str(offset),
                }
            )
            return [job_json(row) for row in rows]

    @app.get(PATH + "/{job_id}")
    def get_publication(job_id: UUID, identity=Depends(operator_identity)):
        job = queue.get(str(job_id))
        if job is None or not job.idempotency_key.startswith(actor_prefix(identity)):
            raise HTTPException(404, "Publication job not found")
        return job_json(job)
