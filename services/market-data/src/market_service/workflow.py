from decimal import Decimal

from sqlalchemy import select

from portfolio_contracts import aware, canonical_hash, utcnow
from portfolio_contracts.market import IngestCommand, IngestionRequest, UNITS
from service_observability import link_job, log_event, span
from .models import Asset, Inbox, IngestionJob, PriceRevision


def execute(sessions, provider, event):
    if event.type != "market.ingestion.requested" or event.producer != "market-data":
        raise ValueError("Unexpected Market event")
    command = IngestCommand.model_validate(event.payload)
    if str(event.correlation_id) != str(command.job_id):
        raise ValueError("Invalid correlation")
    link_job(None, command.job_id)
    attributes = {"job.id": str(command.job_id), "event.id": str(event.event_id)}
    with sessions.begin() as session:
        if session.get(Inbox, event.event_id):
            log_event("market.ingestion", job_id=str(command.job_id), event_id=str(event.event_id), outcome="duplicate_delivery")
            return
        job = session.scalar(
            select(IngestionJob)
            .where(IngestionJob.id == str(command.job_id))
            .with_for_update()
        )
        if (
            job is None
            or command.request_hash != job.request_hash
            or job.input != command.model_dump(mode="json")
        ):
            raise ValueError("Command does not match persisted job")
        session.add(Inbox(event_id=event.event_id))
        if job.status != "QUEUED":
            log_event("market.ingestion", job_id=job.id, event_id=str(event.event_id), outcome="terminal_job")
            return
        if aware(job.deadline) <= utcnow():
            job.status, job.error = (
                "FAILED",
                {"code": "DEADLINE_EXCEEDED", "message": "Ingestion deadline exceeded"},
            )
            return
        try:
            with span("market.ingestion.normalize", attributes=attributes):
                observations = command.request.observations or provider.fetch(
                    command.dataset_spec
                )
                # Revalidate downloaded observations and batch duplicates before writing.
                observations = IngestionRequest(observations=observations).observations
            with span("market.ingestion.persist", attributes=attributes) as current:
                with session.begin_nested():
                    inserted = persist_observations(session, observations, command.dataset_spec)
                job.status, job.inserted_count = "SUCCEEDED", inserted
                session.flush()
                current.set_attribute("status", "SUCCEEDED")
                log_event("market.ingestion.persist", job_id=job.id, event_id=str(event.event_id), status="SUCCEEDED")
        except (ValueError, KeyError, OSError, TypeError) as exc:
            job.status, job.error = (
                "FAILED",
                {
                    "code": "INVALID_DATASET",
                    "message": "Dataset validation failed",
                    "reason": type(exc).__name__,
                },
            )
            log_event("market.ingestion", job_id=job.id, event_id=str(event.event_id), status="FAILED", error_type=type(exc).__name__, error_code="INVALID_DATASET")


def persist_observations(session, observations, spec=None):
    count = 0
    # Asset locks serialize revisions consistently, even for concurrent datasets.
    for asset_id in sorted({row.asset_id for row in observations}):
        asset = session.scalar(
            select(Asset).where(Asset.id == asset_id).with_for_update()
        )
        sample = next(row for row in observations if row.asset_id == asset_id)
        if asset is None:
            asset = Asset(id=asset_id, kind=sample.kind, unit=UNITS[sample.kind])
            session.add(asset)
            session.flush()
        if any(
            row.kind != asset.kind for row in observations if row.asset_id == asset_id
        ):
            raise ValueError("Cannot change an existing asset's kind")
    for row in observations:
        price = (
            row.price * (1000 if row.source_unit.startswith("thousand_") else 1)
        ).quantize(Decimal("0.000001"))
        content_hash = canonical_hash(
            {
                "asset_id": row.asset_id,
                "date": row.observation_date.isoformat(),
                "price_vnd": str(price),
                "unit": UNITS[row.kind],
                "provider": row.provider,
                "price_type": row.price_type,
            }
        )
        key = [
            PriceRevision.asset_id == row.asset_id,
            PriceRevision.observation_date == row.observation_date,
            PriceRevision.provider == row.provider,
            PriceRevision.price_type == row.price_type,
        ]
        latest = session.scalar(
            select(PriceRevision)
            .where(*key)
            .order_by(PriceRevision.revision.desc())
            .limit(1)
        )
        if latest is not None and latest.content_hash == content_hash:
            continue
        revision = latest.revision if latest else 0
        now = utcnow()
        session.add(
            PriceRevision(
                asset_id=row.asset_id,
                observation_date=row.observation_date,
                price_vnd=price,
                unit=UNITS[row.kind],
                source_unit=row.source_unit,
                provider=row.provider,
                price_type=row.price_type,
                revision=revision + 1,
                content_hash=content_hash,
                published_at=row.published_at,
                available_at=now,
                ingested_at=now,
                source_hash=spec["sha256"] if spec else None,
            )
        )
        session.flush()
        count += 1
    return count
