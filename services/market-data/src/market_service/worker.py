import logging
import os
import sys
import time

from sqlalchemy import select, update

from portfolio_contracts import Envelope, utcnow
from portfolio_contracts.broker import connection_from_url, consume, publish
from service_observability import configure, log_event, span
from .models import IngestionJob, Outbox
from .runtime import provider_from_env, sessions_from_env
from .workflow import execute


def dispatch_once(sessions, connection, *, publisher=publish):
    with sessions.begin() as session:
        session.execute(
            update(IngestionJob)
            .where(IngestionJob.status == "QUEUED", IngestionJob.deadline <= utcnow())
            .values(
                status="FAILED",
                error={
                    "code": "DEADLINE_EXCEEDED",
                    "message": "Ingestion deadline exceeded",
                },
            )
        )
        for row in session.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .order_by(Outbox.created_at)
            .with_for_update(skip_locked=True)
            .limit(20)
        ):
            with span("outbox.dispatch", carrier=row.trace_context or {}, attributes={
                "job.id": row.payload.get("correlation_id", ""), "event.id": row.event_id,
            }) as current:
                publisher(connection, "market-data", row.payload)
                row.published_at = utcnow()
                current.set_attribute("status", "published")
                log_event("outbox.dispatch", job_id=row.payload.get("correlation_id", ""), event_id=row.event_id, status="published")


def main():
    logging.basicConfig(level=logging.INFO)
    sessions, provider = sessions_from_env(), provider_from_env()
    url = os.environ["BROKER_URL"]
    mode = sys.argv[1:]
    if mode not in (["dispatch"], ["consume"]):
        raise SystemExit("Usage: python -m market_service.worker dispatch|consume")
    configure(f"market-{mode[0]}")
    while True:
        try:
            if mode == ["consume"]:
                consume(
                    url,
                    "market-data",
                    lambda body: execute(
                        sessions, provider, Envelope.model_validate(body)
                    ),
                )
            else:
                with connection_from_url(url) as connection:
                    dispatch_once(sessions, connection)
        except Exception:
            logging.exception(
                "Market worker unavailable; durable rows/deliveries retained"
            )
        time.sleep(1)


if __name__ == "__main__":
    main()
