"""PUBLIC/cutoff SQL filtering precedes exact cosine and full-text rankings."""

import json
import math
from datetime import datetime
from typing import Literal
from pydantic import Field, model_validator
from sqlalchemy import text
from portfolio_contracts import StrictModel
from .corpus import MODEL, INDEX, DIMENSIONS, normalize

RETRIEVAL = "knowledge-retrieval-v2"

# Keys are phrases in the approved corpus. Aliases are used only when full-text
# matching finds nothing, so conversational filler cannot swamp an exact match.
TOPICS = {
    "equal weight": ("ew", "chia deu ty trong", "ty trong bang nhau", "phan bo deu"),
    "mvo": ("trung binh phuong sai", "mean variance"),
    "covariance": ("hiep phuong sai", "ma tran dong bien"),
    "da dang hoa": ("diversification", "phan tan rui ro"),
    "black litterman": ("blacklitterman",),
    "bl_ml": ("bl ml", "ml views", "views tu mo hinh"),
    "ho so rui ro": ("khau vi rui ro", "risk profile", "risk policy"),
    "tai san nam giu": ("phan bo muc tieu", "ty trong muc tieu", "target holdings"),
    "freshness": ("do moi du lieu", "du lieu het han", "du lieu qua han"),
    "phe duyet mo hinh": ("duyet mo hinh", "model approval"),
    "turnover": ("phi giao dich", "chi phi giao dich", "vong quay danh muc"),
    "backtest": ("kiem thu qua khu", "kiem dinh ngoai mau", "mo phong qua khu"),
}


class Query(StrictModel):
    query: str = Field(min_length=1, max_length=4000)
    corpus_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")
    as_of: datetime
    embedding: list[float] | None = Field(
        default=None, min_length=DIMENSIONS, max_length=DIMENSIONS
    )
    embedding_model: Literal["text-embedding-3-small"] | None = None
    index_version: Literal["openai-small-1536-v1"] = INDEX

    @model_validator(mode="after")
    def vector_contract(self):
        if self.as_of.tzinfo is None:
            raise ValueError("timezone required")
        if self.embedding is not None and (
            self.embedding_model != MODEL
            or not all(math.isfinite(x) for x in self.embedding)
            or not any(self.embedding)
        ):
            raise ValueError("invalid embedding")
        return self


def fuse(lexical, vector):
    scores = {}
    for branch in (lexical, vector):
        for rank, cid in enumerate(branch, 1):
            scores[cid] = scores.get(cid, 0) + 1 / (60 + rank)
    return sorted(scores, key=lambda cid: (-scores[cid], cid))[:5]


def lexical_query(query):
    normalized = " " + normalize(query) + " "
    for phrase in (
        "nghia la gi",
        "la gi",
        "giai thich",
        "tai sao can",
        "cho toi biet",
        "cho toi",
        "the nao",
    ):
        normalized = normalized.replace(" " + phrase + " ", " ")
    return normalized.strip()


def topic_query(query):
    padded = f" {query} "
    return " OR ".join(
        f'"{topic}"'
        for topic, aliases in TOPICS.items()
        if any(f" {phrase} " in padded for phrase in (topic, *aliases))
    )


def retrieve(s, query):
    params = {
        "corpus": query.corpus_id,
        "cutoff": query.as_of,
        "query": lexical_query(query.query),
    }
    # MATERIALIZED keeps the visibility/cutoff set explicit for both ranking branches.
    eligible = """WITH eligible AS MATERIALIZED (
        SELECT c.*, d.version AS document_version, d.title AS document_title,
               d.published_at, d.available_at, p.id AS corpus_id, p.body_hash AS corpus_hash
        FROM document_chunk c JOIN document_version d ON d.id=c.document_id
        JOIN corpus_document m ON m.document_id=d.id JOIN corpus p ON p.id=m.corpus_id
        JOIN active_corpus a ON a.corpus_id=p.id AND a.id=1
        WHERE p.status='READY' AND d.visibility='PUBLIC' AND d.available_at<=:cutoff
          AND (CAST(:corpus AS text) IS NULL OR p.id=CAST(:corpus AS text))) """
    lexical_sql = text(
        eligible
        + """SELECT id FROM eligible
        WHERE to_tsvector('simple',search_text) @@ websearch_to_tsquery('simple',:query)
        ORDER BY ts_rank_cd(to_tsvector('simple',search_text),websearch_to_tsquery('simple',:query)) DESC,id LIMIT 20"""
    )
    lexical = s.execute(lexical_sql, params).scalars().all()
    if not lexical and (fallback := topic_query(params["query"])):
        lexical = s.execute(lexical_sql, params | {"query": fallback}).scalars().all()
    vector = []
    if query.embedding is not None:
        vector = (
            s.execute(
                text(
                    eligible
                    + """SELECT id FROM eligible
            WHERE embedding IS NOT NULL AND embedding_model=:model AND index_version=:index
              AND 1-(embedding <=> CAST(:vector AS vector))>=0.45
            ORDER BY embedding <=> CAST(:vector AS vector),id LIMIT 20"""
                ),
                params
                | {
                    "model": MODEL,
                    "index": INDEX,
                    "vector": json.dumps(query.embedding, allow_nan=False),
                },
            )
            .scalars()
            .all()
        )
    selected = fuse(lexical, vector)
    corpus = (
        s.execute(
            text(
                """SELECT p.id,p.name,p.body_hash FROM corpus p JOIN active_corpus a ON a.corpus_id=p.id AND a.id=1 WHERE p.status='READY' AND (CAST(:corpus AS text) IS NULL OR p.id=CAST(:corpus AS text))"""
            ),
            params,
        )
        .mappings()
        .first()
    )
    result = {
        "corpus_id": corpus["id"] if corpus else query.corpus_id,
        "corpus_version": corpus["name"] if corpus else None,
        "corpus_hash": corpus["body_hash"] if corpus else None,
        "retrieval_version": RETRIEVAL,
        "index_version": INDEX,
        "mode": "HYBRID" if query.embedding is not None else "LEXICAL",
        "reason": "MATCH"
        if selected
        else "NO_EVIDENCE"
        if corpus
        else "CORPUS_UNAVAILABLE",
        "passages": [],
    }
    used = 0
    for cid in selected:
        row = (
            s.execute(
                text(eligible + "SELECT * FROM eligible WHERE id=:chunk"),
                params | {"chunk": cid},
            )
            .mappings()
            .one()
        )
        passage = {
            k: row[k]
            for k in (
                "claim_id",
                "text",
                "text_hash",
                "source_title",
                "source_url",
                "locator",
                "document_title",
                "document_version",
            )
        }
        passage.update(
            chunk_id=cid,
            document_version_id=row["document_id"],
            published_at=row["published_at"].isoformat()
            if row["published_at"]
            else None,
            available_at=row["available_at"].isoformat(),
        )
        size = len(json.dumps(passage, ensure_ascii=False).encode())
        if used + size > 8000:
            break
        used += size
        result["passages"].append(passage)
    return result
