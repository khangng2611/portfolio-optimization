"""Human model operations: enqueue only, immutable audited review, trusted resolver."""

import os
import re
from uuid import UUID, uuid4
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select, func, update, text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from portfolio_contracts import aware, canonical_hash
from service_auth import TokenVerifier, AuthError
from quant_service.ml import read_artifact, ModelManifest
from .contracts import TrainingRequest, ReviewRequest
from .models import Model, Review, TrainingJob
from .queue import TrainingQueue, IdempotencyConflict
from .worker import validated_candidate

PATH = "/api/v1/ml"


def actor(identity):
    return canonical_hash({"issuer": identity.issuer, "subject": identity.subject})


def key_for(identity, key):
    if (
        not key
        or not 1 <= len(key) <= 128
        or any(ord(c) < 33 or ord(c) > 126 for c in key)
    ):
        raise HTTPException(
            400, "Idempotency-Key requires 1–128 visible ASCII characters"
        )
    return "human:" + actor(identity) + ":" + canonical_hash({"key": key})


def job_json(job):
    return {
        "job_id": job.id,
        "status_url": PATH + "/training-jobs/" + job.id,
        "status": job.status,
        "request": job.request,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "next_attempt_at": aware(job.next_attempt_at).isoformat(),
        "result": job.result,
        "safe_error": job.safe_error,
        "created_at": aware(job.created_at).isoformat(),
        "updated_at": aware(job.updated_at).isoformat(),
    }


def model_json(session, model):
    metadata = {
        k: v
        for k, v in model.manifest.items()
        if k not in {"model", "status", "approved_at", "approved_by"}
    }
    reviews = session.scalars(
        select(Review)
        .where(Review.model_id == model.id)
        .order_by(Review.created_at, Review.id)
    ).all()
    return {
        "model_id": model.id,
        "training_job_id": model.training_job_id,
        "status": model.status,
        "version": model.version,
        "artifact_ready": model.approved_ref is not None,
        "metadata": metadata,
        "provenance": model.provenance,
        "created_at": aware(model.created_at).isoformat(),
        "reviews": [
            {
                "review_id": r.id,
                "decision": r.decision,
                "reason": r.reason,
                "actor": r.actor,
                "created_at": aware(r.created_at).isoformat(),
            }
            for r in reviews
        ],
    }


def create_app(*, sessions, verifier, directory):
    app = FastAPI(title="ML Platform", version="0.1.0")
    from service_observability import install_http_tracing

    install_http_tracing(app)
    bearer = HTTPBearer(auto_error=False)
    queue = TrainingQueue(sessions)

    @app.middleware("http")
    async def metadata(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers.update(
            {"X-Request-ID": request.state.request_id, "Cache-Control": "no-store"}
        )
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
    async def http_error(request, exc):
        return error(
            request,
            exc.status_code,
            {
                401: "UNAUTHENTICATED",
                403: "FORBIDDEN",
                404: "NOT_FOUND",
                409: "CONFLICT",
                428: "PRECONDITION_REQUIRED",
                503: "UNAVAILABLE",
            }.get(exc.status_code, "INVALID_REQUEST"),
            str(exc.detail),
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(request, 422, "INVALID_INPUT", "Invalid model operation input")

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return error(
            request, 503, "DATABASE_UNAVAILABLE", "ML database temporarily unavailable"
        )

    def identity(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        try:
            if credentials is None:
                raise AuthError()
            return verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(
                401, "Valid identity required", headers={"WWW-Authenticate": "Bearer"}
            ) from None

    def require(scope, role=None):
        def dependency(principal=Depends(identity)):
            if scope not in principal.scopes or (role and role not in principal.roles):
                raise HTTPException(403, "Required ML role/scope missing")
            if (
                not role
                and scope == "ml:read"
                and not ({"data-operator", "model-reviewer"} & principal.roles)
            ):
                raise HTTPException(403, "ML operator/reviewer role required")
            return principal

        return dependency

    read = require("ml:read")
    train = require("ml:train", "data-operator")
    review = require("ml:review", "model-reviewer")
    resolve = require("ml:model:read")

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            with sessions() as session:
                session.execute(text("SELECT 1 FROM ml_training_job LIMIT 1"))
        except Exception:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ready"}

    @app.post(PATH + "/training-jobs", status_code=202)
    def enqueue(
        body: TrainingRequest,
        principal=Depends(train),
        idempotency_key: str | None = Header(default=None),
    ):
        try:
            return job_json(
                queue.enqueue(
                    key_for(principal, idempotency_key), body.model_dump(mode="json")
                )
            )
        except IdempotencyConflict:
            raise HTTPException(
                409, "Idempotency-Key already used with another input"
            ) from None

    @app.get(PATH + "/training-jobs")
    def jobs(
        response: Response,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        status: str | None = Query(
            default=None, pattern="^(QUEUED|RUNNING|RETRY|SUCCEEDED|FAILED)$"
        ),
        snapshot_id: UUID | None = None,
        principal=Depends(read),
    ):
        conditions = [
            TrainingJob.idempotency_key.startswith("human:" + actor(principal) + ":")
        ]
        if status:
            conditions.append(TrainingJob.status == status)
        if snapshot_id:
            conditions.append(
                TrainingJob.request["snapshot_id"].as_string() == str(snapshot_id)
            )
        with sessions() as session:
            total = session.scalar(
                select(func.count()).select_from(TrainingJob).where(*conditions)
            )
            rows = session.scalars(
                select(TrainingJob)
                .where(*conditions)
                .order_by(TrainingJob.created_at.desc(), TrainingJob.id.desc())
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

    @app.get(PATH + "/training-jobs/{job_id}")
    def job(job_id: UUID, principal=Depends(read)):
        row = queue.get(str(job_id))
        if row is None or not row.idempotency_key.startswith(
            "human:" + actor(principal) + ":"
        ):
            raise HTTPException(404, "Training job not found")
        return job_json(row)

    @app.get(PATH + "/models")
    def models(
        response: Response,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        status: str | None = Query(
            default=None, pattern="^(CANDIDATE|APPROVED|REJECTED)$"
        ),
        principal=Depends(read),
    ):
        conditions = [Model.status == status] if status else []
        with sessions() as session:
            total = session.scalar(
                select(func.count()).select_from(Model).where(*conditions)
            )
            rows = session.scalars(
                select(Model)
                .where(*conditions)
                .order_by(Model.created_at.desc(), Model.id.desc())
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
            return [model_json(session, row) for row in rows]

    @app.get(PATH + "/models/{model_id}")
    def model(model_id: UUID, response: Response, principal=Depends(read)):
        with sessions() as session:
            row = session.get(Model, str(model_id))
            if row is None:
                raise HTTPException(404, "Model not found")
            response.headers["ETag"] = f'"{row.version}"'
            return model_json(session, row)

    @app.post(PATH + "/models/{model_id}/reviews")
    def decide(
        model_id: UUID,
        body: ReviewRequest,
        response: Response,
        principal=Depends(review),
        idempotency_key: str | None = Header(default=None),
        if_match: str | None = Header(default=None),
    ):
        key = key_for(principal, idempotency_key)
        if if_match is None:
            raise HTTPException(428, "If-Match required")
        if not re.fullmatch(r'"[1-9][0-9]{0,8}"', if_match):
            raise HTTPException(400, "Quoted model version required")
        version = int(if_match[1:-1])
        identity = str(model_id)
        digest = canonical_hash(
            {"model_id": identity, "version": version, **body.model_dump()}
        )
        with sessions() as session:
            previous = session.scalar(
                select(Review).where(Review.idempotency_key == key)
            )
            if previous:
                if previous.body_hash != digest:
                    raise HTTPException(
                        409, "Idempotency-Key already used with another decision"
                    )
                row = session.get(Model, identity)
                response.headers["ETag"] = f'"{row.version}"'
                return model_json(session, row)
            row = session.get(Model, identity)
            if row is None:
                raise HTTPException(404, "Model not found")
            if row.version != version or row.status != "CANDIDATE":
                raise HTTPException(409, "Model version or review decision changed")
            if body.decision == "APPROVED":
                try:
                    validated_candidate(directory, row.candidate_ref)
                except Exception:
                    raise HTTPException(
                        409, "Candidate model unavailable or invalid"
                    ) from None
            changed = session.execute(
                update(Model)
                .where(
                    Model.id == identity,
                    Model.version == version,
                    Model.status == "CANDIDATE",
                )
                .values(status=body.decision, version=version + 1)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "Model version changed")
            session.add(
                Review(
                    id=str(uuid4()),
                    model_id=identity,
                    actor=actor(principal),
                    idempotency_key=key,
                    body_hash=digest,
                    decision=body.decision,
                    reason=body.reason.strip(),
                    expected_version=version,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise HTTPException(409, "Review decision changed") from None
            session.refresh(row)
            response.headers["ETag"] = f'"{row.version}"'
            return model_json(session, row)

    @app.get("/internal/v1/ml/models/{model_id}/manifest")
    def manifest(model_id: UUID, principal=Depends(resolve)):
        with sessions() as session:
            row = session.get(Model, str(model_id))
            if row is None:
                raise HTTPException(404, "Model not found")
            if row.status != "APPROVED" or row.approved_ref is None:
                raise HTTPException(409, "Approved model artifact unavailable")
            try:
                approved = ModelManifest.model_validate_json(
                    read_artifact(directory, row.approved_ref)
                )
                root = Path(directory) / Path(row.approved_ref["file"]).parent
                read_artifact(
                    root, approved.model, suffixes=(".ubj",), max_bytes=20_000_000
                )
                if approved.status != "APPROVED" or approved.model_id != row.id:
                    raise ValueError()
            except Exception:
                raise HTTPException(
                    409, "Approved model artifact unavailable or invalid"
                ) from None
            return {
                "model_id": row.id,
                "manifest": {
                    "file": "ml-models/" + row.approved_ref["file"],
                    "sha256": row.approved_ref["sha256"],
                },
            }

    return app


def app_factory():
    from .runtime import sessions_from_env
    from service_observability import configure

    configure("ml-api")
    return create_app(
        sessions=sessions_from_env(),
        verifier=TokenVerifier(
            os.environ["OIDC_ISSUER"], "ml-api", os.environ["OIDC_JWKS_URL"]
        ),
        directory=os.environ["ML_ARTIFACT_DIRECTORY"],
    )
