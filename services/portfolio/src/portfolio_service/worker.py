import logging
import os
import sys
import time

from sqlalchemy import select

from portfolio_contracts import Envelope, utcnow
from portfolio_contracts.broker import connection_from_url, consume, publish
from service_observability import configure, log_event, span
from .models import Job, Outbox
from .runtime import sessions_from_env
from .workflow import consume_result


def dispatch_once(sessions, connection):
    with sessions.begin() as session:
        rows = session.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .with_for_update(skip_locked=True)
            .limit(20)
        )
        for row in rows:
            with span("outbox.dispatch", carrier=row.trace_context or {}, attributes={
                "job.id": row.payload.get("correlation_id", ""), "event.id": row.event_id,
            }) as current:
                publish(connection, "portfolio", row.payload)
                row.published_at = utcnow()
                current.set_attribute("status", "published")
                log_event("outbox.dispatch", job_id=row.payload.get("correlation_id", ""), event_id=row.event_id, status="published")
        for job in session.scalars(
            select(Job)
            .where(Job.status == "QUEUED", Job.deadline < utcnow())
            .with_for_update(skip_locked=True)
        ):
            job.status, job.error = (
                "FAILED",
                {"code": "DEADLINE_EXCEEDED", "message": "Quá thời hạn xử lý."},
            )


def main():
    sessions = sessions_from_env()
    url = os.environ["BROKER_URL"]
    logging.basicConfig(level=logging.INFO)
    if sys.argv[1:] not in (["consume"], ["dispatch"]):
        raise SystemExit("Usage: python -m portfolio_service.worker dispatch|consume")
    configure(f"portfolio-{sys.argv[1]}")
    if sys.argv[1:] == ["consume"]:
        consume(
            url,
            "portfolio",
            lambda body: consume_result(sessions, Envelope.model_validate(body)),
        )
        return
    if sys.argv[1:] != ["dispatch"]:
        raise SystemExit("Usage: python -m portfolio_service.worker dispatch|consume")
    while True:
        try:
            with connection_from_url(url) as connection:
                dispatch_once(sessions, connection)
        except Exception:
            logging.exception("Outbox dispatch unavailable; rows retained for retry")
        time.sleep(1)


if __name__ == "__main__":
    main()
