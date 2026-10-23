import logging
import os
import sys
import time

from kombu import Connection
from sqlalchemy import select

from portfolio_contracts import Envelope, utcnow
from portfolio_contracts.broker import consume, publish
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
            publish(connection, "quant-serving", row.payload)
            row.published_at = utcnow()


def main():
    logging.basicConfig(level=logging.INFO)
    sessions, catalog = sessions_from_env(), catalog_from_env()
    url = os.environ["BROKER_URL"]
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
            with Connection(
                url, connect_timeout=5, transport_options={"confirm_publish": True}
            ) as connection:
                dispatch_once(sessions, connection)
        except Exception:
            logging.exception("Outbox dispatch unavailable; rows retained for retry")
        time.sleep(1)


if __name__ == "__main__":
    main()
