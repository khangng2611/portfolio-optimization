"""Serve one lexical eval arm from a new local, disposable PostgreSQL database."""

import argparse
from pathlib import Path
import re

import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from knowledge_service.api import create_app
from knowledge_service.corpus import load_manifest
from knowledge_service.models import ActiveCorpus, Base, Corpus
from knowledge_service.worker import Worker
from service_auth import AuthError, Principal
from portfolio_contracts import canonical_hash


class Verifier:
    def __init__(self, indexing=False):
        self.indexing = indexing

    def verify(self, token):
        if not self.indexing and token == "p3-local-read":
            return Principal(
                "eval",
                "machine",
                frozenset(),
                frozenset({"knowledge:retrieve"}),
                "chat-service",
            )
        if self.indexing and token == "p3-local-index":
            return Principal(
                "eval",
                "operator",
                frozenset({"data-operator"}),
                frozenset({"knowledge:read", "knowledge:write"}),
                "web",
            )
        raise AuthError("invalid")


def seed(engine, sessions, manifest):
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    with TestClient(
        create_app(sessions=sessions, verifier=Verifier(indexing=True))
    ) as client:
        headers = {
            "Authorization": "Bearer p3-local-index",
            "Idempotency-Key": "eval-index-corpus",
        }
        response = client.post(
            "/api/v1/knowledge/indexing-jobs",
            json=manifest.model_dump(mode="json"),
            headers=headers,
        )
        response.raise_for_status()
        corpus_id = response.json()["corpus_id"]
        worker = Worker(sessions)
        # complete() builds lexical chunks only. Embedding reservations run in a separate worker step.
        if not worker.complete(worker.claim()):
            raise RuntimeError("Index job lost its lease")
        response = client.get("/api/v1/knowledge/corpora", headers=headers)
        response.raise_for_status()
        row = next(row for row in response.json() if row["id"] == corpus_id)
        assert row["status"] == "READY" and row["embedded_chunks"] == 0
        response = client.post(
            f"/api/v1/knowledge/corpora/{corpus_id}/activate",
            headers=headers
            | {
                "If-Match": f'"{row["version"]}"',
                "Idempotency-Key": "eval-activate-corpus",
            },
            json={"reason": "Isolated lexical evaluation"},
        )
        response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-port", type=int, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--read-existing",
        action="store_true",
        help="Read the existing matching corpus and chunk IDs without indexing",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"rag_eval_[a-z0-9_]+", args.database):
        parser.error(
            "Use a new rag_eval_* database in the disposable PostgreSQL container"
        )
    engine = create_engine(
        f"postgresql+psycopg://postgres@127.0.0.1:{args.postgres_port}/{args.database}"
    )
    manifest = load_manifest(args.corpus)
    sessions = sessionmaker(engine, expire_on_commit=False)
    if args.read_existing:
        with sessions() as s:
            corpus_hash = s.scalar(
                select(Corpus.body_hash)
                .join(ActiveCorpus, ActiveCorpus.corpus_id == Corpus.id)
                .where(ActiveCorpus.id == 1, Corpus.status == "READY")
            )
        if corpus_hash != canonical_hash(manifest.model_dump(mode="json")):
            parser.error("Existing active corpus differs from requested manifest")
    else:
        if inspect(engine).get_table_names():
            parser.error("The eval database must be empty for indexing")
        seed(engine, sessions, manifest)
    uvicorn.run(
        create_app(sessions=sessions, verifier=Verifier()),
        host="127.0.0.1",
        port=args.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
