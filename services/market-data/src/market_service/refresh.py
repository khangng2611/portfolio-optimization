"""Durable refresh scheduling. Source I/O happens after the claim transaction closes."""

from datetime import date, timedelta
import json
from uuid import uuid4

import requests
from sqlalchemy import select

from portfolio_contracts import aware, canonical_hash, utcnow
from portfolio_contracts.market import IngestionRequest, SnapshotRequest
from .models import (
    Actor,
    IngestionJob,
    QualityReport,
    RefreshJob,
    RefreshSchedule,
    RegisteredDataset,
)
from .providers import CsvProvider
from .quality import QualityFailure, finding, validate_batch, report_json
from .refresh_provider import (
    ArtifactStore,
    PROVIDER,
    SOURCE_DOC,
    completed_cutoff,
    history_window_expired,
    HistoryWindowExpired,
    normalize,
    normalized_csv,
)
from .snapshots import build_snapshot
from .workflow import persist_observations

REFRESH_MODE = "full-adjusted-reconciliation"


def schedule_json(row):
    return row.config | {
        "id": row.id,
        "refresh_mode": REFRESH_MODE,
        "history_window_expired": history_window_expired(
            row.config["initial_start_date"], utcnow()
        ),
        "version": row.version,
        "enabled": bool(row.enabled),
        "next_run_at": aware(row.next_run_at).isoformat(),
        "last_successful_cutoff": row.last_successful_cutoff.isoformat()
        if row.last_successful_cutoff
        else None,
        "provider": PROVIDER,
        "calendar": "kbs-observed-vnindex-sessions",
        "calendar_verified": False,
        "availability_basis": "ingestion",
        "created_at": aware(row.created_at).isoformat(),
    }


def job_json(row):
    return {
        "id": row.id,
        "refresh_mode": REFRESH_MODE
        if row.start_date == date.fromisoformat(row.config["initial_start_date"])
        else "legacy-overlap",
        "schedule_id": row.schedule_id,
        "schedule_version": row.schedule_version,
        "status": row.status,
        "attempts": row.attempts,
        "start_date": row.start_date.isoformat(),
        "cutoff_date": row.cutoff_date.isoformat(),
        "error": row.error,
        "artifacts": row.artifacts,
        "source_manifest": row.source_manifest,
        "ingestion_job_ids": row.ingestion_job_ids,
        "snapshot_id": row.snapshot_id,
        "provider": PROVIDER,
        "calendar": "kbs-observed-vnindex-sessions",
        "calendar_verified": False,
        "availability_basis": "ingestion",
        "created_at": aware(row.created_at).isoformat(),
        "completed_at": aware(row.completed_at).isoformat()
        if row.completed_at
        else None,
    }


def reconcile_job(session, job, *, now=None):
    now = now or utcnow()
    if job.status in {"QUEUED", "RUNNING"} and aware(job.deadline) <= now:
        job = session.scalar(
            select(RefreshJob)
            .where(RefreshJob.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job.status in {"QUEUED", "RUNNING"} and aware(job.deadline) <= now:
            job.status, job.completed_at = "FAILED", now
            job.lease_token, job.lease_until = None, None
            job.error = {
                "code": "DEADLINE_EXCEEDED",
                "message": "Refresh deadline exceeded",
                "retryable": False,
            }
    return job


def enqueue_job(session, schedule, tick_key, now):
    active_jobs = list(
        session.scalars(
            select(RefreshJob)
            .where(
                RefreshJob.schedule_id == schedule.id,
                RefreshJob.status.in_(["QUEUED", "RUNNING"]),
            )
            .order_by(RefreshJob.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for active_job in active_jobs:
        reconcile_job(session, active_job, now=now)
    session.flush()
    existing = session.scalar(
        select(RefreshJob).where(
            RefreshJob.schedule_id == schedule.id, RefreshJob.tick_key == tick_key
        )
    )
    if existing:
        return existing
    # Schedule row lock serializes manual triggers and timer ticks. At most one
    # active job can cover this schedule, including work from earlier versions.
    active = session.scalar(
        select(RefreshJob).where(
            RefreshJob.schedule_id == schedule.id,
            RefreshJob.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    if active:
        return active
    if history_window_expired(schedule.config["initial_start_date"], now):
        raise HistoryWindowExpired(
            "Configured history exceeds the supported source window"
        )
    initial = date.fromisoformat(schedule.config["initial_start_date"])
    # KBS adjusted prices can restate the entire historical series after
    # corporate actions. Reconcile the full bounded configured window; only
    # genuinely changed/new observations append revisions during persistence.
    # overlap_days remains a minimum recheck window for future provider policies.
    start = initial
    job = RefreshJob(
        schedule_id=schedule.id,
        actor_id=schedule.actor_id,
        tick_key=tick_key,
        config=dict(schedule.config),
        schedule_version=schedule.version,
        start_date=start,
        cutoff_date=completed_cutoff(now),
        available_at=now,
        deadline=now + timedelta(hours=1),
    )
    session.add(job)
    session.flush()
    return job


def tick(sessions, *, now=None):
    now = now or utcnow()
    count = 0
    with sessions.begin() as session:
        for schedule in session.scalars(
            select(RefreshSchedule)
            .where(
                RefreshSchedule.enabled == 1,
                RefreshSchedule.next_run_at <= now,
                ~select(RefreshJob.id)
                .where(
                    RefreshJob.schedule_id == RefreshSchedule.id,
                    RefreshJob.status.in_(["QUEUED", "RUNNING"]),
                    RefreshJob.deadline > now,
                )
                .exists(),
            )
            .order_by(RefreshSchedule.next_run_at)
            .with_for_update(skip_locked=True)
            .limit(20)
        ):
            if history_window_expired(schedule.config["initial_start_date"], now):
                # Expire the schedule instead of repeatedly enqueueing a source
                # window that cannot be fetched. Never shift its pinned start.
                schedule.enabled = 0
                schedule.config = schedule.config | {"enabled": False}
                schedule.version += 1
                continue
            tick_key = (
                f"tick:{schedule.version}:{aware(schedule.next_run_at).isoformat()}"
            )
            job = enqueue_job(session, schedule, tick_key, now)
            if job.tick_key != tick_key or job.status != "QUEUED":
                continue
            # Coalesce missed ticks after downtime; never replay an unbounded backlog.
            schedule.next_run_at = now + timedelta(
                minutes=schedule.config["interval_minutes"]
            )
            count += 1
    return count


def claim(sessions, *, now=None):
    now = now or utcnow()
    with sessions.begin() as session:
        for row in session.scalars(
            select(RefreshJob)
            .where(
                (RefreshJob.status == "QUEUED")
                | ((RefreshJob.status == "RUNNING") & (RefreshJob.lease_until <= now)),
                RefreshJob.available_at <= now,
            )
            .order_by(RefreshJob.created_at, RefreshJob.id)
            .with_for_update(skip_locked=True)
            .limit(20)
        ):
            if aware(row.deadline) <= now or row.attempts >= 3:
                row.status = "FAILED"
                row.error = {
                    "code": "DEADLINE_EXCEEDED"
                    if aware(row.deadline) <= now
                    else "RETRY_EXHAUSTED",
                    "message": "Refresh retry window exhausted",
                }
                row.completed_at = now
                row.lease_token = None
                continue
            # Safely widen pending jobs accepted by an older overlap-only
            # worker; persist the effective request window before network I/O.
            row.start_date = date.fromisoformat(row.config["initial_start_date"])
            row.status, row.lease_token = "RUNNING", str(uuid4())
            row.lease_until = now + timedelta(minutes=10)
            row.attempts += 1
            session.flush()
            session.expunge(row)
            return row
    return None


class PackFailure(Exception):
    def __init__(self, cause, artifacts, packs):
        super().__init__("Source pack failed")
        self.cause, self.artifacts, self.packs = cause, artifacts, packs


def fetch_pack(job, source, store):
    artifacts, packs = [], []
    try:
        return _fetch_pack(job, source, store, artifacts, packs)
    except (
        requests.RequestException,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ArithmeticError,
    ) as exc:
        raise PackFailure(exc, artifacts, packs) from exc


def _fetch_pack(job, source, store, artifacts, packs):
    raw = source.fetch_raw("VNINDEX", job.start_date, job.cutoff_date, index=True)
    calendar_artifact = store.put(raw, "json")
    artifacts.append(
        {"asset_id": "VNINDEX", "role": "observed-calendar", "raw": calendar_artifact}
    )
    expected = [
        d.isoformat()
        for d, _ in normalize(
            store.read(calendar_artifact), "VNINDEX", job.start_date, job.cutoff_date
        )
    ]
    if (job.cutoff_date - date.fromisoformat(expected[-1])).days > job.config[
        "max_age_days"
    ]:
        raise ValueError("Observed calendar is stale")
    for symbol in job.config["asset_ids"]:
        raw = source.fetch_raw(symbol, job.start_date, job.cutoff_date)
        raw_artifact = store.put(raw, "json")
        artifact = {"asset_id": symbol, "role": "prices", "raw": raw_artifact}
        artifacts.append(artifact)
        rows = normalize(
            store.read(raw_artifact), symbol, job.start_date, job.cutoff_date
        )
        normalized = store.put(normalized_csv(rows, symbol), "csv")
        # Paths are server-owned, relative to DATASET_DIRECTORY. The refresh
        # directory is its mounted child; API and ingestion consumers read it RO.
        spec = {
            "path": f"{store.directory.name}/{normalized['file']}",
            "sha256": normalized["sha256"],
            "asset_id": symbol,
            "kind": "stock",
            "source_unit": "VND/share",
            "provider": PROVIDER,
            "data_origin": "real",
            "price_basis": "provider_adjusted",
            "price_type": "close",
            "expected_sessions": expected,
            "calendar_source": "KBS VNINDEX observed daily bars",
            "calendar_verified": False,
            "raw_sha256": raw_artifact["sha256"],
            "documentation": SOURCE_DOC,
            "availability_basis": "ingestion",
        }
        artifact["normalized"] = normalized
        observations = CsvProvider(store.directory.parent).fetch(spec)
        packs.append((spec, observations, []))
        findings = validate_batch(observations, spec)
        packs[-1] = (spec, observations, findings)
    manifest = {
        "schema_version": 1,
        "provider": PROVIDER,
        "refresh_mode": REFRESH_MODE,
        "artifacts": artifacts,
        "start_date": job.start_date.isoformat(),
        "cutoff_date": job.cutoff_date.isoformat(),
        "retrieved_at": utcnow().isoformat(),
        "calendar": "kbs-observed-vnindex-sessions",
        "calendar_verified": False,
        "availability_basis": "ingestion",
        "documentation": SOURCE_DOC,
    }
    pin = store.put(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(), "json"
    )
    return artifacts, packs, pin


def finish(sessions, claimed, store, artifacts, packs, manifest_pin, *, now=None):
    now = now or utcnow()
    with sessions.begin() as session:
        # NO KEY UPDATE serializes actor receipts while allowing FK KEY SHARE
        # checks from a scheduler that already holds a schedule row lock.
        session.scalar(
            select(Actor)
            .where(Actor.id == claimed.actor_id)
            .with_for_update(key_share=True)
        )
        schedule = session.scalar(
            select(RefreshSchedule)
            .where(RefreshSchedule.id == claimed.schedule_id)
            .with_for_update()
        )
        job = session.scalar(
            select(RefreshJob).where(RefreshJob.id == claimed.id).with_for_update()
        )
        if (
            job.status != "RUNNING"
            or job.lease_token != claimed.lease_token
            or aware(job.lease_until) <= now
        ):
            return False
        if aware(job.deadline) <= now:
            reconcile_job(session, job, now=now)
            return False
        # Verify exact immutable bytes once more after networking and before any
        # accepted SQL state is changed. Files are content-addressed and read-only.
        store.read(manifest_pin)
        for artifact in artifacts:
            store.read(artifact["raw"])
            if artifact.get("normalized"):
                store.read(artifact["normalized"])
        ingestion_ids = []
        for spec, observations, findings in packs:
            dataset_id = "REFRESH_" + canonical_hash(spec)[:56].upper()
            if session.get(RegisteredDataset, dataset_id) is None:
                session.add(
                    RegisteredDataset(
                        dataset_id=dataset_id,
                        sha256=spec["sha256"],
                        spec=spec,
                        start_date=min(r.observation_date for r in observations),
                        end_date=max(r.observation_date for r in observations),
                        registered_by=job.actor_id,
                    )
                )
            body = IngestionRequest(dataset_id=dataset_id)
            ingestion = IngestionJob(
                actor_id=job.actor_id,
                idempotency_key="refresh:" + job.id + ":" + spec["asset_id"],
                request_hash=canonical_hash(body.model_dump(mode="json")),
                input={"request": body.model_dump(mode="json"), "dataset_spec": spec},
                deadline=job.deadline,
            )
            session.add(ingestion)
            session.flush()
            ingestion.inserted_count = persist_observations(
                session, observations, spec, ingestion.id
            )
            ingestion.status = "SUCCEEDED"
            report = report_json(
                ingestion.id, "PASS", len(observations), findings, observations, spec
            )
            report |= {
                "calendar": "kbs-observed-vnindex-sessions",
                "calendar_verified": False,
                "source_manifest_sha256": manifest_pin["sha256"],
            }
            session.add(
                QualityReport(job_id=ingestion.id, status="PASS", report=report)
            )
            ingestion_ids.append(ingestion.id)
        session.flush()
        # Full adjusted-history reconciliation prevents mixing adjustment
        # vintages; persistence still deduplicates all unchanged observations.
        snapshot = build_snapshot(
            session,
            SnapshotRequest(
                provider=PROVIDER,
                asset_ids=job.config["asset_ids"],
                start_date=job.config["initial_start_date"],
                end_date=job.cutoff_date,
                as_of_date=utcnow().date(),
                max_age_days=job.config["max_age_days"],
            ),
        )
        # A provider can remove a formerly observed historical bar. There is no
        # tombstone revision in this MVP: refuse a snapshot that would silently
        # retain rows absent from the complete current source vintage.
        current_keys = {
            (row.asset_id, row.observation_date.isoformat())
            for _, observations, _ in packs
            for row in observations
        }
        selected_keys = {
            (row["asset_id"], row["observation_date"]) for row in snapshot.observations
        }
        if selected_keys != current_keys:
            raise QualityFailure([finding("MISSING_SESSIONS")], len(selected_keys))
        job.status, job.error = "SUCCEEDED", None
        job.source_manifest = manifest_pin
        job.artifacts, job.ingestion_job_ids, job.snapshot_id = (
            artifacts,
            ingestion_ids,
            snapshot.id,
        )
        job.completed_at, job.lease_token, job.lease_until = now, None, None
        # Changing a schedule's asset universe resets its cursor; completion of
        # an older pinned version must not overwrite the edited cursor.
        if schedule.version == job.schedule_version:
            schedule.last_successful_cutoff = job.cutoff_date
    return True


def fail(sessions, claimed, code, *, retryable, now=None, pack_failure=None):
    now = now or utcnow()
    with sessions.begin() as session:
        # Match trigger/completion actor→job order before FK-bearing reports.
        # NO KEY UPDATE serializes actor receipts while allowing FK KEY SHARE
        # checks from a scheduler that already holds a schedule row lock.
        session.scalar(
            select(Actor)
            .where(Actor.id == claimed.actor_id)
            .with_for_update(key_share=True)
        )
        job = session.scalar(
            select(RefreshJob).where(RefreshJob.id == claimed.id).with_for_update()
        )
        if job.status != "RUNNING" or job.lease_token != claimed.lease_token:
            return
        if pack_failure:
            job.artifacts = pack_failure.artifacts
            if not retryable:
                cause = pack_failure.cause
                findings = (
                    cause.findings
                    if isinstance(cause, QualityFailure)
                    else [finding("INVALID_SOURCE")]
                )
                ingestion = IngestionJob(
                    actor_id=job.actor_id,
                    idempotency_key=f"refresh-failure:{job.id}:{job.attempts}",
                    request_hash=canonical_hash(job.config),
                    input={"refresh_job_id": job.id, "config": job.config},
                    status="FAILED",
                    deadline=job.deadline,
                    error={
                        "code": "INVALID_DATASET",
                        "message": "Refresh source batch quarantined",
                    },
                )
                session.add(ingestion)
                session.flush()
                observations = [o for _, rows, _ in pack_failure.packs for o in rows]
                report = report_json(
                    ingestion.id,
                    "QUARANTINED",
                    len(observations),
                    findings,
                    observations,
                )
                report |= {
                    "calendar": "kbs-observed-vnindex-sessions",
                    "calendar_verified": False,
                    "scope": "atomic-refresh-batch",
                }
                session.add(
                    QualityReport(
                        job_id=ingestion.id, status="QUARANTINED", report=report
                    )
                )
                job.ingestion_job_ids = [ingestion.id]
        retry = (
            retryable
            and job.attempts < 3
            and aware(job.deadline) > now + timedelta(minutes=2)
        )
        job.status = "QUEUED" if retry else "FAILED"
        job.error = {
            "code": code,
            "message": "Trusted source unavailable; retry scheduled"
            if retry
            else "Refresh failed; inspect source coverage and immutable artifacts",
            "retryable": retry,
        }
        job.available_at = now + timedelta(seconds=60 * 2 ** (job.attempts - 1))
        job.lease_token, job.lease_until = None, None
        if not retry:
            job.completed_at = now


def run_once(sessions, source, directory, *, now=None):
    claimed = claim(sessions, now=now)
    if claimed is None:
        return False
    try:
        store = ArtifactStore(directory)
        artifacts, packs, manifest_pin = fetch_pack(claimed, source, store)
        finish(sessions, claimed, store, artifacts, packs, manifest_pin, now=now)
    except PackFailure as exc:
        retryable = isinstance(exc.cause, (requests.RequestException, OSError))
        fail(
            sessions,
            claimed,
            "SOURCE_UNAVAILABLE" if retryable else "QUALITY_REJECTED",
            retryable=retryable,
            now=now,
            pack_failure=exc,
        )
    except (requests.RequestException, OSError):
        fail(sessions, claimed, "SOURCE_UNAVAILABLE", retryable=True, now=now)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        fail(
            sessions,
            claimed,
            "QUALITY_REJECTED",
            retryable=False,
            now=now,
            pack_failure=PackFailure(exc, artifacts, packs)
            if "artifacts" in locals()
            else None,
        )
    return True
