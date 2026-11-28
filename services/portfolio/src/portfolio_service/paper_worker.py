"""Advance initialized paper accounts when new verified market sessions arrive."""

import logging
from time import sleep

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from portfolio_contracts import utcnow
from .models import PaperAccount, Portfolio
from .paper import latest_targets, lock_sqlite_writer, reconcile
from .runtime import sessions_from_env


def tick(sessions):
    with sessions() as session:
        ids = session.scalars(select(PaperAccount.portfolio_id)).all()
    for portfolio_id in ids:
        try:
            with sessions.begin() as session:
                lock_sqlite_writer(session)
                portfolio = session.scalar(
                    select(Portfolio)
                    .where(Portfolio.id == portfolio_id)
                    .with_for_update(skip_locked=True)
                )
                if portfolio:
                    reconcile(
                        session.get(PaperAccount, portfolio_id),
                        latest_targets(session, portfolio),
                        utcnow(),
                    )
        except SQLAlchemyError:
            logging.exception("Paper reconciliation failed")


def main():
    sessions = sessions_from_env()
    while True:
        try:
            tick(sessions)
        except SQLAlchemyError:
            logging.exception("Paper account lookup failed")
        sleep(60)


if __name__ == "__main__":
    main()
