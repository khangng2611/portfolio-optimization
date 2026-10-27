"""Durable operator-only snapshot publication. No HTTP mutation or model training."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import time
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from portfolio_contracts import canonical_hash, utcnow
from .ml import ArtifactRef
from .models import PublicationJob
from .snapshot_publisher import MarketReader, publish_snapshot, recover_publication


class IdempotencyConflict(ValueError):
    pass


def validate_request(value):
    allowed = {
        "snapshot_id",
        "snapshot_hash",
        "universe_id",
        "model",
        "approved_model_id",
        "max_age_days",
        "lookback",
        "min_returns",
    }
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Invalid publication request fields")
    result = {
        "snapshot_id": str(UUID(value["snapshot_id"])),
        "snapshot_hash": value["snapshot_hash"],
        "universe_id": value["universe_id"],
        "model": ArtifactRef.model_validate(value["model"]).model_dump()
        if value.get("model") is not None
        else None,
    }
    if value.get("approved_model_id") is not None:
        result["approved_model_id"] = str(UUID(value["approved_model_id"]))
    if not re.fullmatch(r"[a-f0-9]{64}", result["snapshot_hash"]):
        raise ValueError("Explicit snapshot hash required")
    if (
        not re.fullmatch(r"[A-Z0-9_-]{1,64}", result["universe_id"])
        or result["universe_id"] == "DEMO"
    ):
        raise ValueError("A real universe ID required")
    for name, default, low, high in [
        ("max_age_days", 7, 1, 365),
        ("lookback", 252, 2, 5000),
        ("min_returns", 60, 2, 5000),
    ]:
        result[name] = value.get(name, default)
        if type(result[name]) is not int or not low <= result[name] <= high:
            raise ValueError("Invalid publication bounds")
    if result["min_returns"] > result["lookback"]:
        raise ValueError("Minimum returns exceeds lookback")
    return result


class PublicationQueue:
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
            job = PublicationJob(
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
                    select(PublicationJob).where(PublicationJob.idempotency_key == key)
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
            return session.get(PublicationJob, job_id)

    def claim(self, *, now=None, lease_seconds=120, recover=None):
        now = now or utcnow()
        if not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        eligible = or_(
            and_(
                PublicationJob.status.in_(["QUEUED", "RETRY"]),
                PublicationJob.next_attempt_at <= now,
            ),
            and_(PublicationJob.status == "RUNNING", PublicationJob.lease_until <= now),
        )
        with self.sessions() as session:
            # A successful final attempt may have crashed before its DB commit.
            # Inspect only its immutable local intent; never perform another build
            # beyond the retry bound. Locks also fence concurrent recovery sweeps.
            exhausted = session.scalars(
                select(PublicationJob)
                .where(eligible, PublicationJob.attempts >= PublicationJob.max_attempts)
                .limit(100)
                .with_for_update(skip_locked=True)
            ).all()
            for expired in exhausted:
                result = None
                if recover:
                    try:
                        result = recover(expired)
                    except Exception:
                        pass
                session.execute(
                    update(PublicationJob)
                    .execution_options(synchronize_session=False)
                    .where(
                        PublicationJob.id == expired.id,
                        eligible,
                        PublicationJob.lease_token == expired.lease_token,
                        PublicationJob.attempts >= PublicationJob.max_attempts,
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
                select(PublicationJob.id)
                .where(eligible, PublicationJob.attempts < PublicationJob.max_attempts)
                .order_by(PublicationJob.created_at, PublicationJob.id)
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
                update(PublicationJob)
                .where(
                    PublicationJob.id == job_id,
                    eligible,
                    PublicationJob.attempts < PublicationJob.max_attempts,
                )
                .values(
                    status="RUNNING",
                    attempts=PublicationJob.attempts + 1,
                    lease_token=token,
                    lease_until=now + timedelta(seconds=lease_seconds),
                    updated_at=now,
                )
            )
            session.commit()
            return session.get(PublicationJob, job_id) if result.rowcount == 1 else None

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
                update(PublicationJob)
                .where(
                    PublicationJob.id == job.id,
                    PublicationJob.status == "RUNNING",
                    PublicationJob.lease_token == job.lease_token,
                    PublicationJob.lease_until > now,
                )
                .values(lease_until=now + timedelta(seconds=120), updated_at=now)
            )
            if locked.rowcount != 1:
                session.rollback()
                return False, None
            result = operation()
            if result is not None:
                session.execute(
                    update(PublicationJob)
                    .where(PublicationJob.id == job.id)
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
                update(PublicationJob)
                .where(
                    PublicationJob.id == job.id,
                    PublicationJob.status == "RUNNING",
                    PublicationJob.lease_token == job.lease_token,
                    PublicationJob.lease_until > now,
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
            "PUBLICATION_INVALID",
            "PUBLICATION_UNAVAILABLE",
        }:
            code = "PUBLICATION_UNAVAILABLE"
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


def enqueue_schedules(queue, schedules, *, now=None):
    """Enqueue current due UTC slot only; no discovery or unbounded outage catch-up."""
    now = now or utcnow()
    results = []
    ids = set()
    for schedule in schedules:
        if set(schedule) != {"id", "anchor", "interval_seconds", "request"}:
            raise ValueError(
                "Schedule requires explicit ID, anchor, interval and request"
            )
        identity = schedule["id"]
        interval = schedule["interval_seconds"]
        anchor = datetime.fromisoformat(schedule["anchor"])
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identity)
            or identity in ids
            or type(interval) is not int
            or not 60 <= interval <= 31_536_000
            or anchor.tzinfo is None
        ):
            raise ValueError("Invalid publication schedule")
        ids.add(identity)
        validate_request(schedule["request"])
        if now < anchor:
            continue
        slot = int((now - anchor).total_seconds() // interval)
        key = f"schedule:{identity}:{anchor.astimezone(timezone.utc).isoformat()}:{interval}:{slot}"
        results.append(queue.enqueue(key, schedule["request"], now=now))
    return results


def process_one(queue, directory, reader, *, now=None):
    job = queue.claim(
        now=now,
        recover=lambda expired: recover_publication(
            directory, expired.id, expired.body_hash
        ),
    )
    if job is None:
        return False
    try:
        owned, result = queue.publish_owned(
            job, lambda: recover_publication(directory, job.id, job.body_hash), now=now
        )
        if not owned or result is not None:
            return True
        request = job.request
        snapshot, observations = reader.load(
            request["snapshot_id"], request["snapshot_hash"]
        )
        queue.publish_owned(
            job,
            lambda: publish_snapshot(
                directory,
                snapshot,
                observations,
                expected_hash=request["snapshot_hash"],
                universe_id=request["universe_id"],
                model=request["model"],
                max_age_days=request["max_age_days"],
                lookback=request["lookback"],
                min_returns=request["min_returns"],
                publication_intent=job.id,
                intent_hash=job.body_hash,
                now=now,
            ),
            now=now,
        )
    except (ValueError, KeyError):
        queue.fail(job, "PUBLICATION_INVALID", permanent=True, now=now)
    except httpx.HTTPError:
        queue.fail(job, "MARKET_UNAVAILABLE", now=now)
    except Exception:
        # Exception text may contain credentials, remote responses or local paths.
        queue.fail(job, "PUBLICATION_UNAVAILABLE", now=now)
    return True


class CredentialMarketReader:
    def load(self, snapshot_id, snapshot_hash):
        # Refresh a narrowly scoped client token for each job, never persist it.
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            response = client.post(
                os.environ["OIDC_TOKEN_URL"],
                data={
                    "grant_type": "client_credentials",
                    "client_id": "quant-publisher",
                    "client_secret": os.environ["MARKET_READER_CLIENT_SECRET"],
                    "scope": "market:snapshot:read",
                },
            )
            response.raise_for_status()
            return MarketReader(
                os.environ["MARKET_API_URL"],
                response.json()["access_token"],
                client=client,
            ).load(snapshot_id, snapshot_hash)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    enqueue = commands.add_parser("enqueue")
    enqueue.add_argument("--key", required=True)
    enqueue.add_argument("--snapshot-id", required=True)
    enqueue.add_argument("--snapshot-hash", required=True)
    enqueue.add_argument("--universe-id", required=True)
    enqueue.add_argument("--model-file")
    enqueue.add_argument("--model-sha256")
    enqueue.add_argument("--max-attempts", type=int, default=5)
    status = commands.add_parser("status")
    status.add_argument("--job-id", required=True)
    run = commands.add_parser("run")
    run.add_argument("--once", action="store_true")
    args = parser.parse_args()
    from .runtime import sessions_from_env

    queue = PublicationQueue(sessions_from_env())
    if args.command == "enqueue":
        if bool(args.model_file) != bool(args.model_sha256):
            parser.error("Model file and hash must be supplied together")
        job = queue.enqueue(
            args.key,
            {
                "snapshot_id": args.snapshot_id,
                "snapshot_hash": args.snapshot_hash,
                "universe_id": args.universe_id,
                "model": {"file": args.model_file, "sha256": args.model_sha256}
                if args.model_file
                else None,
            },
            max_attempts=args.max_attempts,
        )
        print(json.dumps({"job_id": job.id, "status": job.status}))
    elif args.command == "status":
        job = queue.get(str(UUID(args.job_id)))
        if job is None:
            parser.exit(1, "Publication job not found\n")
        print(
            json.dumps(
                {
                    "job_id": job.id,
                    "status": job.status,
                    "attempts": job.attempts,
                    "safe_error": job.safe_error,
                    "result": job.result,
                }
            )
        )
    else:
        schedules = json.loads(os.environ.get("PUBLICATION_SCHEDULES", "[]"))
        while True:
            enqueue_schedules(queue, schedules)
            processed = process_one(
                queue, os.environ["BUNDLE_DIRECTORY"], CredentialMarketReader()
            )
            if args.once:
                break
            if not processed:
                time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(
            "Publication command failed; check configuration and safe job status"
        ) from None
