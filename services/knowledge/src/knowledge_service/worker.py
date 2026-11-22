"""Leased SQL indexing. A lost worker cannot publish or duplicate chunks."""

from datetime import timedelta
from uuid import uuid4
import time
from sqlalchemy import select, update, or_, and_, func
from decimal import Decimal
from portfolio_contracts import utcnow, canonical_hash
from service_observability import configure, log_event
from .corpus import Manifest, normalize, sha
from .models import Corpus, Document, Chunk, Membership, IndexJob, EmbeddingInvocation
from .embeddings import Embeddings, approved_budget
from .corpus import MODEL, INDEX
from .runtime import sessions_from_env


class Worker:
    def __init__(self, sessions, embedder=None):
        self.sessions = sessions
        self.embedder = embedder or Embeddings()

    def claim(self):
        now = utcnow()
        eligible = or_(
            IndexJob.status == "DRAFT",
            and_(IndexJob.status == "INDEXING", IndexJob.lease_until <= now),
        )
        with self.sessions.begin() as s:
            job = s.scalar(
                select(IndexJob)
                .where(eligible)
                .order_by(IndexJob.created_at, IndexJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if not job:
                return None
            r = s.execute(
                update(IndexJob)
                .where(IndexJob.id == job.id, eligible)
                .values(
                    status="INDEXING",
                    lease_token=str(uuid4()),
                    lease_until=now + timedelta(seconds=30),
                    attempts=IndexJob.attempts + 1,
                )
            )
            if r.rowcount != 1:
                return None
            s.get(Corpus, job.corpus_id).status = "INDEXING"
            s.flush()
            s.refresh(job)
            return job

    def complete(self, job, lease_token=None):
        now = utcnow()
        with self.sessions.begin() as s:
            fence = s.execute(
                update(IndexJob)
                .where(
                    IndexJob.id == job.id,
                    IndexJob.status == "INDEXING",
                    IndexJob.lease_token == (lease_token or job.lease_token),
                    IndexJob.lease_until > now,
                )
                .values(lease_until=now + timedelta(seconds=30))
            )
            if fence.rowcount != 1:
                return False
            current = s.get(IndexJob, job.id)
            corpus = s.get(Corpus, job.corpus_id)
            if current.attempts > 5:
                current.status = corpus.status = "FAILED"
                current.error = "RETRY_EXHAUSTED"
                return True
            manifest = Manifest.model_validate(corpus.manifest)
            for item in manifest.documents:
                doc = s.scalar(
                    select(Document).where(
                        Document.document_key == item.key,
                        Document.version == item.version,
                    )
                )
                metadata_hash = canonical_hash(item.model_dump(mode="json"))
                if doc and doc.metadata_hash != metadata_hash:
                    current.status = corpus.status = "FAILED"
                    current.error = "IMMUTABLE_VERSION_CONFLICT"
                    return True
                if not doc:
                    doc = Document(
                        document_key=item.key,
                        version=item.version,
                        content_hash=item.content_hash,
                        metadata_hash=metadata_hash,
                        title=item.title,
                        visibility=item.visibility,
                        published_at=item.published_at,
                        available_at=item.available_at,
                    )
                    s.add(doc)
                    s.flush()
                    for claim in item.claims:
                        invocation = s.get(
                            EmbeddingInvocation, sha(claim.text) + ":" + INDEX
                        )
                        output = invocation.output if invocation else None
                        s.add(
                            Chunk(
                                document_id=doc.id,
                                claim_id=claim.id,
                                text=claim.text,
                                text_hash=sha(claim.text),
                                embedding=output["embedding"] if output else None,
                                embedding_model=MODEL if output else None,
                                search_text=normalize(
                                    item.title + " " + claim.id + " " + claim.text
                                ),
                                source_title=claim.source_title,
                                source_url=claim.source_url,
                                locator=claim.locator,
                            )
                        )
                if not s.get(Membership, (corpus.id, doc.id)):
                    s.add(Membership(corpus_id=corpus.id, document_id=doc.id))
            current.status = corpus.status = "READY"
            corpus.version += 1
            current.lease_until = current.lease_token = None
            return True

    def index_embeddings(self, job):
        budget = approved_budget()
        if not budget:
            return
        with self.sessions() as s:
            manifest = Manifest.model_validate(s.get(Corpus, job.corpus_id).manifest)
        for item in manifest.documents:
            for claim in item.claims:
                key = sha(claim.text) + ":" + INDEX
                with self.sessions.begin() as s:
                    if s.bind.dialect.name == "postgresql":
                        s.execute(select(func.pg_advisory_xact_lock(784512306)))
                    fence = s.execute(
                        update(IndexJob)
                        .where(
                            IndexJob.id == job.id,
                            IndexJob.status == "INDEXING",
                            IndexJob.lease_token == job.lease_token,
                            IndexJob.lease_until > utcnow(),
                        )
                        .values(lease_until=utcnow() + timedelta(seconds=30))
                    )
                    if fence.rowcount != 1:
                        return
                    if s.get(EmbeddingInvocation, key):
                        continue
                    used = s.scalars(
                        select(EmbeddingInvocation).where(
                            EmbeddingInvocation.budget_id == budget[0]
                        )
                    ).all()
                    reservation = Decimal("0.00016")
                    if len(used) >= 50 or sum(
                        (Decimal(r.reserved_usd) for r in used), Decimal("0")
                    ) + reservation > budget[1] * Decimal("0.2"):
                        return
                    s.add(
                        EmbeddingInvocation(
                            content_key=key,
                            budget_id=budget[0],
                            reserved_usd=str(reservation),
                        )
                    )
                # Durable reservation deliberately survives an uncertain/crashed outbound call.
                value, details = self.embedder.embed(claim.text)
                with self.sessions.begin() as s:
                    record = s.get(EmbeddingInvocation, key)
                    record.output, record.details = value, details

    def tick(self):
        job = self.claim()
        if not job:
            return False
        self.index_embeddings(job)
        return self.complete(job)


def main():
    configure("knowledge-worker")
    worker = Worker(sessions_from_env())
    while True:
        try:
            if not worker.tick():
                time.sleep(0.5)
        except Exception:
            log_event("knowledge.worker.error", outcome="retry_after_lease")
            time.sleep(1)


if __name__ == "__main__":
    main()
