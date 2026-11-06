"""ML-owned durable leases; no cross-service database access."""

from datetime import timedelta
from uuid import uuid4
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from portfolio_contracts import canonical_hash, utcnow
from .models import TrainingJob
from .contracts import TrainingRequest


class IdempotencyConflict(ValueError):
    pass


def validate_request(value):
    return TrainingRequest.model_validate(value).model_dump(mode="json")


class TrainingQueue:
    def __init__(self, sessions):
        self.sessions = sessions

    def enqueue(self, key, request, *, now=None, max_attempts=5):
        now = now or utcnow()
        if (
            not isinstance(key, str)
            or not 1 <= len(key) <= 200
            or type(max_attempts) is not int
            or not 1 <= max_attempts <= 10
        ):
            raise ValueError("Invalid publication key or retry bound")
        request = validate_request(request)
        body_hash = canonical_hash({"request": request, "max_attempts": max_attempts})
        with self.sessions() as session:
            job = TrainingJob(
                id=str(uuid4()),
                idempotency_key=key,
                body_hash=body_hash,
                request=request,
                status="QUEUED",
                attempts=0,
                max_attempts=max_attempts,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                job = session.scalar(
                    select(TrainingJob).where(TrainingJob.idempotency_key == key)
                )
                if job is None:
                    raise
                if job.body_hash != body_hash:
                    raise IdempotencyConflict(
                        "Publication key already has different immutable pins"
                    ) from None
            return job

    def get(self, job_id):
        with self.sessions() as session:
            return session.get(TrainingJob, job_id)

    def claim(self, *, now=None, lease_seconds=120, recover=None):
        now = now or utcnow()
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        eligible = or_(
            and_(
                TrainingJob.status.in_(["QUEUED", "RETRY"]),
                TrainingJob.next_attempt_at <= now,
            ),
            and_(TrainingJob.status == "RUNNING", TrainingJob.lease_until <= now),
        )
        with self.sessions() as session:
            # A successful final attempt may have crashed before its DB commit.
            # Inspect only its immutable local intent; never perform another build
            # beyond the retry bound. Locks also fence concurrent recovery sweeps.
            exhausted = session.scalars(
                select(TrainingJob)
                .where(eligible, TrainingJob.attempts >= TrainingJob.max_attempts)
                .limit(100)
                .with_for_update(skip_locked=True)
            ).all()
            for expired in exhausted:
                result = None
                if recover:
                    try:
                        result = recover(expired, session)
                    except Exception:
                        pass
                session.execute(
                    update(TrainingJob)
                    .execution_options(synchronize_session=False)
                    .where(
                        TrainingJob.id == expired.id,
                        eligible,
                        TrainingJob.lease_token == expired.lease_token,
                        TrainingJob.attempts >= TrainingJob.max_attempts,
                    )
                    .values(
                        status="SUCCEEDED" if result else "FAILED",
                        result=result,
                        safe_error=None if result else "LEASE_EXHAUSTED",
                        lease_token=None,
                        lease_until=None,
                        updated_at=now,
                    )
                )
            candidates = (
                select(TrainingJob.id)
                .where(eligible, TrainingJob.attempts < TrainingJob.max_attempts)
                .order_by(TrainingJob.created_at, TrainingJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job_id = session.scalar(candidates)
            if job_id is None:
                session.commit()
                return None
            token = str(uuid4())
            # The conditional UPDATE also fences races on SQLite, where FOR UPDATE is ignored.
            result = session.execute(
                update(TrainingJob)
                .where(
                    TrainingJob.id == job_id,
                    eligible,
                    TrainingJob.attempts < TrainingJob.max_attempts,
                )
                .values(
                    status="RUNNING",
                    attempts=TrainingJob.attempts + 1,
                    lease_token=token,
                    lease_until=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
            )
            session.commit()
            return session.get(TrainingJob, job_id) if result.rowcount == 1 else None

    def publish_owned(self, job, operation, *, now=None):
        """Fence every catalog/artifact side effect with a held DB row lock.

        Market I/O happens before this section. A conditional update acquires
        the row's write lock, validates the current lease, and renews it. Keep
        that lock until both local publication and result persistence finish;
        reclaimers skip this row even if the extended wall-clock lease expires.
        A crash rolls back the DB transaction; the immutable intent remains
        recoverable by the next valid owner.
        """
        now = now or utcnow()
        with self.sessions() as session:
            locked = session.execute(
                update(TrainingJob)
                .where(
                    TrainingJob.id == job.id,
                    TrainingJob.status == "RUNNING",
                    TrainingJob.lease_token == job.lease_token,
                    TrainingJob.lease_until > now,
                )
                .values(lease_until=now + timedelta(seconds=600), updated_at=now)
            )
            if locked.rowcount != 1:
                session.rollback()
                return False, None
            result = operation(session)
            if result is not None:
                session.execute(
                    update(TrainingJob)
                    .where(TrainingJob.id == job.id)
                    .values(
                        status="SUCCEEDED",
                        result=result,
                        safe_error=None,
                        lease_token=None,
                        lease_until=None,
                        updated_at=now,
                    )
                )
            session.commit()
            return True, result

    def _finish(self, job, values, now):
        with self.sessions() as session:
            changed = session.execute(
                update(TrainingJob)
                .where(
                    TrainingJob.id == job.id,
                    TrainingJob.status == "RUNNING",
                    TrainingJob.lease_token == job.lease_token,
                    TrainingJob.lease_until > now,
                )
                .values(**values, lease_token=None, lease_until=None, updated_at=now)
            )
            session.commit()
            return changed.rowcount == 1

    def complete(self, job, result, *, now=None):
        return self._finish(
            job,
            {"status": "SUCCEEDED", "result": result, "safe_error": None},
            now or utcnow(),
        )

    def fail(self, job, code, *, now=None, permanent=False):
        now = now or utcnow()
        if code not in {
            "MARKET_UNAVAILABLE",
            "TRAINING_INVALID",
            "TRAINING_UNAVAILABLE",
        }:
            code = "TRAINING_UNAVAILABLE"
        return self._finish(
            job,
            {
                "status": "FAILED"
                if permanent or job.attempts >= job.max_attempts
                else "RETRY",
                "safe_error": code,
                "next_attempt_at": now
                + timedelta(seconds=min(3600, 30 * 2 ** (job.attempts - 1))),
            },
            now,
        )
