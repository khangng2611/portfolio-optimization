"""Loopback-only browser fixture using the same quotes and API helpers as the ledger test."""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os

import conftest  # noqa: F401 - loads the same service paths as the API test suite.
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uvicorn

from portfolio_contracts import canonical_hash
from portfolio_service import paper
from portfolio_service.api import create_app
from portfolio_service.models import AcceptedTarget, Base
from test_paper_account import DAYS, close, target
from test_workflow import Resolver, Verifier, portfolio


def serve(folder):
    os.environ["PAPER_MARKET_DIRECTORY"] = str(folder)
    engine = create_engine(
        f"sqlite:///{folder}/paper.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    app = create_app(sessions=sessions, verifier=Verifier(), resolver=Resolver())
    with TestClient(app) as client:
        pid = portfolio(client)
        index = 0
        paper.utcnow = lambda: close(DAYS[index])
        for i, day in enumerate(DAYS):
            prices = {"FPT": 80_000 + 1000 * i, "HPG": 30_000, "VFF": 25_000}
            frame = dict(
                date=day,
                as_of=close(day).isoformat(),
                source="Fixed browser quotes",
                prices=prices,
                eligible=prices,
            )
            (folder / f"{day}.json").write_text(
                json.dumps({"frame": frame, "sha256": canonical_hash(frame)})
            )
        (folder / "calendar.json").write_text(json.dumps({"sessions": DAYS}))

        def accept_asset(asset):
            tid = target(client, sessions, pid, DAYS[index], asset)
            with sessions.begin() as session:
                row = session.get(AcceptedTarget, tid)
                row.allocation = row.allocation | {
                    "capital_vnd": "10000000",
                    "strategy": "EW",
                }

        accept_asset("FPT")

        @app.get("/scenario")
        def info():
            return {"portfolio": pid, "now": close(DAYS[index]).isoformat()}

        @app.post("/scenario/session/{new_index}")
        def advance(new_index: int):
            nonlocal index
            if not index <= new_index < len(DAYS):
                raise HTTPException(400)
            index = new_index
            return info()

        @app.post("/scenario/second-target")
        def change_target():
            accept_asset("HPG")
            return info()

        uvicorn.run(app, host="127.0.0.1", port=32159, log_level="warning")


if __name__ == "__main__":
    with TemporaryDirectory(prefix="paper-portfolio-browser-") as path:
        serve(Path(path))
