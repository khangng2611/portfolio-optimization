import logging
import os
import sys
import time

from sqlalchemy import select

from portfolio_contracts import Envelope, utcnow
from portfolio_contracts.broker import connection_from_url, consume, publish
from service_observability import configure, log_event, span
from .models import Outbox
from .runtime import catalog_from_env, sessions_from_env
from .workflow import execute


def dispatch_once(sessions, connection):
    with sessions.begin() as session:
        for row in session.scalars(
            select(Outbox)
            .where(Outbox.published_at.is_(None))
            .with_for_update(skip_locked=True)
            .limit(20)
        ):
            with span("outbox.dispatch", carrier=row.trace_context or {}, attributes={
                "job.id": row.payload.get("correlation_id", ""), "event.id": row.event_id,
            }) as current:
                publish(connection, "quant-serving", row.payload)
                row.published_at = utcnow()
                current.set_attribute("status", "published")
                log_event("outbox.dispatch", job_id=row.payload.get("correlation_id", ""), event_id=row.event_id, status="published")


def main():
    logging.basicConfig(level=logging.INFO)
    sessions, catalog = sessions_from_env(), catalog_from_env()
    url = os.environ["BROKER_URL"]
    if sys.argv[1:] not in (["consume"], ["dispatch"]):
        raise SystemExit("Usage: python -m quant_service.worker dispatch|consume")
    configure(f"quant-{sys.argv[1]}")
    if sys.argv[1:] == ["consume"]:
        consume(
            url,
            "quant-serving",
            lambda body: execute(sessions, catalog, Envelope.model_validate(body)),
        )
        return
    if sys.argv[1:] != ["dispatch"]:
        raise SystemExit("Usage: python -m quant_service.worker dispatch|consume")
    while True:
        try:
            with connection_from_url(url) as connection:
                dispatch_once(sessions, connection)
        except Exception:
            logging.exception("Outbox dispatch unavailable; rows retained for retry")
        time.sleep(1)


if __name__ == "__main__":
    main()
