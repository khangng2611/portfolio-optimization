"""Operator-only control plane; requests select trusted source symbols, never URLs."""

from datetime import date, timedelta
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, Response
from pydantic import Field, model_validator
from sqlalchemy import func, select

from portfolio_contracts import StrictModel, canonical_hash, utcnow
from .models import Actor, RefreshJob, RefreshReceipt, RefreshSchedule
from .refresh import enqueue_job, job_json, schedule_json, reconcile_job
from .refresh_provider import completed_cutoff, MAX_HISTORY_DAYS, HistoryWindowExpired


class ScheduleInput(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    asset_ids: list[str] = Field(min_length=1, max_length=20)
    initial_start_date: date
    interval_minutes: int = Field(default=1440, ge=60, le=10080)
    overlap_days: int = Field(default=7, ge=1, le=60)
    max_age_days: int = Field(default=14, ge=1, le=60)
    enabled: bool = True

    @model_validator(mode="after")
    def valid_schedule(self):
        import re

        if len(set(self.asset_ids)) != len(self.asset_ids) or any(
            not re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", a) for a in self.asset_ids
        ):
            raise ValueError("Distinct bounded stock symbols required")
        cutoff = completed_cutoff(utcnow())
        if (
            not cutoff - timedelta(days=MAX_HISTORY_DAYS)
            <= self.initial_start_date
            <= cutoff
        ):
            raise ValueError(
                "Initial history must end before the current local day and span at most ten years"
            )
        return self


class SchedulePatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    asset_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)
    initial_start_date: date | None = None
    interval_minutes: int | None = Field(default=None, ge=60, le=10080)
    overlap_days: int | None = Field(default=None, ge=1, le=60)
    max_age_days: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None

    @model_validator(mode="after")
    def no_nulls(self):
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("A non-null update is required")
        return self


class RefreshInput(StrictModel):
    schedule_id: UUID


def install_refresh_routes(app, *, sessions, operator, actor, valid_key, page_headers):
    def receipt(session, actor_id, key, payload):
        session.scalar(
            select(Actor).where(Actor.id == actor_id).with_for_update(key_share=True)
        )
        digest = canonical_hash(payload)
        previous = session.scalar(
            select(RefreshReceipt).where(
                RefreshReceipt.actor_id == actor_id,
                RefreshReceipt.idempotency_key == key,
            )
        )
        if previous and previous.request_hash != digest:
            raise HTTPException(
                409, "Idempotency-Key already used with another refresh request"
            )
        return digest, previous

    def save(session, actor_id, key, digest, response):
        session.add(
            RefreshReceipt(
                actor_id=actor_id,
                idempotency_key=key,
                request_hash=digest,
                response=response,
            )
        )
        return response

    @app.get("/api/v1/market/refresh-schedules")
    def list_schedules(
        response: Response,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
        identity=Depends(operator),
    ):
        with sessions() as session:
            total = session.scalar(select(func.count()).select_from(RefreshSchedule))
            rows = [
                schedule_json(r)
                for r in session.scalars(
                    select(RefreshSchedule)
                    .order_by(RefreshSchedule.created_at.desc(), RefreshSchedule.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]
        page_headers(response, total, limit, offset)
        return rows

    @app.get("/api/v1/market/refresh-schedules/{schedule_id}")
    def get_schedule(schedule_id: UUID, response: Response, identity=Depends(operator)):
        with sessions() as session:
            row = session.get(RefreshSchedule, str(schedule_id))
            if row is None:
                raise HTTPException(404, "Refresh schedule not found")
            response.headers["ETag"] = f'"{row.version}"'
            return schedule_json(row)

    @app.post("/api/v1/market/refresh-schedules", status_code=201)
    def create_schedule(
        body: ScheduleInput,
        response: Response,
        actor_id=Depends(actor),
        identity=Depends(operator),
        idempotency_key: str | None = Header(None),
    ):
        valid_key(idempotency_key)
        data = body.model_dump(mode="json")
        with sessions.begin() as session:
            digest, previous = receipt(
                session, actor_id, idempotency_key, {"op": "create", "body": data}
            )
            if previous:
                response.headers["ETag"] = f'"{previous.response["version"]}"'
                return previous.response
            if (
                session.scalar(
                    select(func.count())
                    .select_from(RefreshSchedule)
                    .where(RefreshSchedule.actor_id == actor_id)
                )
                >= 100
            ):
                raise HTTPException(429, "At most 100 schedules per operator")
            row = RefreshSchedule(
                actor_id=actor_id,
                config=data,
                enabled=int(body.enabled),
                next_run_at=utcnow(),
            )
            session.add(row)
            session.flush()
            response.headers["ETag"] = '"1"'
            return save(session, actor_id, idempotency_key, digest, schedule_json(row))

    @app.patch("/api/v1/market/refresh-schedules/{schedule_id}")
    def update_schedule(
        schedule_id: UUID,
        body: SchedulePatch,
        response: Response,
        actor_id=Depends(actor),
        identity=Depends(operator),
        idempotency_key: str | None = Header(None),
        if_match: str | None = Header(None),
    ):
        valid_key(idempotency_key)
        if not if_match or not if_match.strip('"').isdigit():
            raise HTTPException(428, "If-Match schedule version required")
        update = body.model_dump(mode="json", exclude_unset=True)
        with sessions.begin() as session:
            digest, previous = receipt(
                session,
                actor_id,
                idempotency_key,
                {
                    "op": "patch",
                    "id": str(schedule_id),
                    "body": update,
                    "version": if_match,
                },
            )
            if previous:
                response.headers["ETag"] = f'"{previous.response["version"]}"'
                return previous.response
            row = session.scalar(
                select(RefreshSchedule)
                .where(RefreshSchedule.id == str(schedule_id))
                .with_for_update()
            )
            if not row:
                raise HTTPException(404, "Refresh schedule not found")
            if row.version != int(if_match.strip('"')):
                raise HTTPException(409, "Schedule version changed")
            try:
                # Stopping a previously accepted schedule must remain possible
                # even after its fixed history ages past the provider limit.
                config = (
                    row.config | update
                    if update == {"enabled": False}
                    else ScheduleInput.model_validate(row.config | update).model_dump(
                        mode="json"
                    )
                )
            except ValueError:
                raise HTTPException(422, "Invalid refresh schedule update") from None
            if (
                config["asset_ids"] != row.config["asset_ids"]
                or config["initial_start_date"] != row.config["initial_start_date"]
            ):
                row.last_successful_cutoff = None
            row.config, row.enabled, row.version = (
                config,
                int(config["enabled"]),
                row.version + 1,
            )
            row.next_run_at = utcnow() + timedelta(minutes=config["interval_minutes"])
            session.flush()
            response.headers["ETag"] = f'"{row.version}"'
            return save(session, actor_id, idempotency_key, digest, schedule_json(row))

    @app.post("/api/v1/market/refresh-jobs", status_code=202)
    def manual_refresh(
        body: RefreshInput,
        actor_id=Depends(actor),
        identity=Depends(operator),
        idempotency_key: str | None = Header(None),
    ):
        valid_key(idempotency_key)
        with sessions.begin() as session:
            digest, previous = receipt(
                session,
                actor_id,
                idempotency_key,
                {"op": "run", "body": body.model_dump(mode="json")},
            )
            if previous:
                return previous.response
            schedule = session.scalar(
                select(RefreshSchedule)
                .where(RefreshSchedule.id == str(body.schedule_id))
                .with_for_update()
            )
            if not schedule:
                raise HTTPException(404, "Refresh schedule not found")
            if (
                session.scalar(
                    select(func.count())
                    .select_from(RefreshJob)
                    .where(
                        RefreshJob.actor_id == schedule.actor_id,
                        RefreshJob.status.in_(["QUEUED", "RUNNING"]),
                        RefreshJob.deadline > utcnow(),
                    )
                )
                >= 5
            ):
                raise HTTPException(
                    429, "At most five active refresh jobs per schedule operator"
                )
            try:
                job = enqueue_job(
                    session,
                    schedule,
                    "manual:"
                    + canonical_hash({"actor": actor_id, "key": idempotency_key}),
                    utcnow(),
                )
            except HistoryWindowExpired:
                raise HTTPException(
                    409,
                    "Configured history exceeds 3650 days; update the start date or create a new schedule",
                ) from None
            return save(session, actor_id, idempotency_key, digest, job_json(job))

    @app.get("/api/v1/market/refresh-jobs")
    def list_jobs(
        response: Response,
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0, le=1000000),
        identity=Depends(operator),
    ):
        with sessions.begin() as session:
            total = session.scalar(select(func.count()).select_from(RefreshJob))
            rows = [
                job_json(reconcile_job(session, r))
                for r in session.scalars(
                    select(RefreshJob)
                    .order_by(RefreshJob.created_at.desc(), RefreshJob.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]
        page_headers(response, total, limit, offset)
        return rows

    @app.get("/api/v1/market/refresh-jobs/{job_id}")
    def get_job(job_id: UUID, identity=Depends(operator)):
        with sessions.begin() as session:
            job = session.get(RefreshJob, str(job_id))
            if not job:
                raise HTTPException(404, "Refresh job not found")
            return job_json(reconcile_job(session, job))
