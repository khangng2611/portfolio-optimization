"""Knowledge trust boundaries and durable lifecycle; SQLite is unit evidence only."""

from pathlib import Path
from copy import deepcopy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from portfolio_contracts import utcnow
from service_auth import Principal, AuthError


def payload():
    text = "EW chia đều tỷ trọng giữa các tài sản. Không bảo đảm lợi nhuận."
    markdown = "## ew-definition\n" + text + "\n"
    return {
        "name": "knowledge-v1",
        "parser_version": "markdown-claims-v1",
        "chunker_version": "approved-claims-v1",
        "review": "project-authored; source checked",
        "documents": [
            {
                "key": "ew",
                "version": 1,
                "visibility": "PUBLIC",
                "language": "vi",
                "title": "EW",
                "markdown": markdown,
                "content_hash": hashlib.sha256(markdown.encode()).hexdigest(),
                "available_at": utcnow().isoformat(),
                "published_at": None,
                "claims": [
                    {
                        "id": "ew-definition",
                        "text": text,
                        "source_title": "Project methodology",
                        "source_url": "https://example.org/ew",
                        "locator": "Equal weights",
                    }
                ],
            }
        ],
    }


class Verifier:
    def verify(self, token):
        if token == "invalid":
            raise AuthError("invalid")
        return Principal(
            "issuer",
            token,
            frozenset({"data-operator"} if token == "operator" else {"investor"}),
            frozenset(
                {"knowledge:read", "knowledge:write"}
                if token == "operator"
                else {"knowledge:retrieve"}
            ),
            "chat-service" if token == "machine" else "web",
        )


@pytest.fixture
def knowledge(tmp_path):
    from knowledge_service.models import Base
    from knowledge_service.api import create_app

    sessions = sessionmaker(
        create_engine(
            f"sqlite:///{tmp_path}/knowledge.db",
            connect_args={"check_same_thread": False},
        ),
        expire_on_commit=False,
    )
    Base.metadata.create_all(sessions.kw["bind"])
    with TestClient(create_app(sessions=sessions, verifier=Verifier())) as client:
        yield client, sessions


def headers(key="knowledge-job-01", token="operator"):
    return {"Authorization": "Bearer " + token, "Idempotency-Key": key}


def test_manifest_validation_and_root_boundary(tmp_path):
    from knowledge_service.corpus import Manifest, load_manifest, normalize

    p = payload()
    assert Manifest.model_validate(p).documents[0].claims[0].id == "ew-definition"
    assert normalize("Hiệp PHƯƠNG sai ĐỀU") == "hiep phuong sai deu"
    for change in (
        {"visibility": "PRIVATE"},
        {"content_hash": "0" * 64},
        {"markdown": "<script>alert(1)</script>"},
    ):
        bad = deepcopy(p)
        bad["documents"][0].update(change)
        with pytest.raises(ValueError):
            Manifest.model_validate(bad)
    for name in ("../outside.md", "/etc/passwd"):
        manifest = deepcopy(p)
        manifest["documents"][0]["path"] = name
        del manifest["documents"][0]["markdown"]
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(ValueError):
            load_manifest(tmp_path)
    outside = tmp_path.parent / "outside-knowledge.md"
    outside.write_text("no")
    (tmp_path / "evil.md").symlink_to(outside)
    manifest["documents"][0]["path"] = "evil.md"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_manifest(tmp_path)


def test_enqueue_dedupe_auth_and_fenced_atomic_activation(knowledge):
    from knowledge_service.worker import Worker
    from knowledge_service.models import Chunk, Corpus

    c, s = knowledge
    p = payload()
    route = "/api/v1/knowledge/indexing-jobs"
    assert c.post(route, json=p).status_code == 401
    assert c.post(route, json=p, headers=headers(token="investor")).status_code == 403
    r = c.post(route, json=p, headers=headers())
    assert r.status_code == 202, r.text
    assert c.post(route, json=p, headers=headers()).json() == r.json()
    assert (
        c.post(route, json=p | {"name": "different"}, headers=headers()).status_code
        == 409
    )
    cid = r.json()["corpus_id"]
    assert (
        c.post(
            f"/api/v1/knowledge/corpora/{cid}/activate",
            json={"reason": "reviewed"},
            headers=headers() | {"If-Match": '"1"'},
        ).status_code
        == 409
    )
    worker = Worker(s)
    job = worker.claim()
    assert job
    assert worker.complete(job, lease_token="stale") is False
    assert worker.complete(job) is True
    assert worker.complete(job) is False
    with s() as db:
        assert db.scalar(select(func.count()).select_from(Chunk)) == 1
        assert db.get(Corpus, cid).status == "READY"
    route = f"/api/v1/knowledge/corpora/{cid}/activate"
    h = headers("knowledge-activate-01") | {"If-Match": '"2"'}
    assert c.post(route, json={"reason": "reviewed"}, headers=h).status_code == 200
    assert c.post(route, json={"reason": "reviewed"}, headers=h).status_code == 200
    assert c.post(route, json={"reason": "changed"}, headers=h).status_code == 409
    assert (
        c.post(
            route,
            json={"reason": "reviewed"},
            headers=headers("stale-key") | {"If-Match": '"1"'},
        ).status_code
        == 412
    )
    assert (
        c.post(
            f"/api/v1/knowledge/corpora/{cid}/deactivate",
            json={"reason": "rollback"},
            headers=headers("deactivate-01") | {"If-Match": '"4"'},
        ).status_code
        == 200
    )
    with s() as db:
        assert db.scalar(select(func.count()).select_from(Chunk)) == 1
    # Internal route rejects a human who merely has retrieve scope.
    assert (
        c.post(
            "/internal/v1/knowledge/retrieve",
            json={"query": "EW", "as_of": utcnow().isoformat()},
            headers=headers(token="investor"),
        ).status_code
        == 403
    )


def test_vector_contract_and_rank_integrity():
    from knowledge_service.retrieval import Query, fuse

    base = {"query": "EW", "as_of": utcnow().isoformat()}
    for v in ([0.0] * 1536, [1.0] * 3, [float("nan")] * 1536):
        with pytest.raises(ValueError):
            Query.model_validate(
                base
                | {
                    "embedding": v,
                    "embedding_model": "text-embedding-3-small",
                    "index_version": "openai-small-1536-v1",
                }
            )
    with pytest.raises(ValueError):
        Query.model_validate(
            base
            | {
                "embedding": [1.0] * 1536,
                "embedding_model": "wrong",
                "index_version": "openai-small-1536-v1",
            }
        )
    assert fuse(["b", "a"], ["a", "c"]) == ["a", "b", "c"]
    with pytest.raises(ValueError):
        Query.model_validate(base | {"visibility": "PRIVATE"})


def test_index_embedding_is_reserved_once_and_checkpointed(knowledge, monkeypatch):
    from knowledge_service.worker import Worker
    from knowledge_service.models import EmbeddingInvocation, Chunk

    c, s = knowledge
    p = payload()
    assert (
        c.post("/api/v1/knowledge/indexing-jobs", json=p, headers=headers()).status_code
        == 202
    )
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "unit-test-only")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.01")

    class Provider:
        calls = 0

        def embed(self, text):
            self.calls += 1
            return {"embedding": [1.0] * 1536}, {
                "reason": "VERIFIED",
                "input_tokens": 20,
            }

    provider = Provider()
    worker = Worker(s, embedder=provider)
    job = worker.claim()
    worker.index_embeddings(job)
    worker.index_embeddings(job)
    assert provider.calls == 1
    assert worker.complete(job)
    with s() as db:
        assert db.scalar(select(func.count()).select_from(EmbeddingInvocation)) == 1
        assert db.scalar(select(Chunk)).embedding is not None


def test_eval_dataset_is_frozen_and_stratified():
    from scripts.eval_knowledge import load_cases, summarize

    cases = load_cases()
    assert len(cases) == 60
    assert sum(c["split"] == "dev" for c in cases) == 20
    assert sum(c["split"] == "heldout" for c in cases) == 40
    assert sum(c["category"] == "answerable" for c in cases) >= 20
    assert sum(c["expected_abstention"] for c in cases) >= 20
    assert summarize([{"passed": True}, {"passed": False}]) == {
        "passed": 1,
        "total": 2,
        "rate": 0.5,
    }


def test_read_scope_does_not_grant_lifecycle_write(knowledge, monkeypatch):
    from knowledge_service.api import create_app

    c, s = knowledge

    class ReadOnly:
        def verify(self, token):
            return Principal(
                "issuer",
                "operator",
                frozenset({"data-operator"}),
                frozenset({"knowledge:read"}),
                "web",
            )

    with TestClient(create_app(sessions=s, verifier=ReadOnly())) as client:
        assert (
            client.get("/api/v1/knowledge/corpora", headers=headers()).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/knowledge/indexing-jobs", json=payload(), headers=headers()
            ).status_code
            == 403
        )


def test_lifecycle_precondition_fences_stale_activation_of_a_different_corpus(
    knowledge,
):
    from knowledge_service.worker import Worker

    c, s = knowledge
    first = payload()
    second = deepcopy(first)
    second["name"] = "other-corpus"
    route = "/api/v1/knowledge/indexing-jobs"
    ids = []
    for n, body in enumerate((first, second)):
        r = c.post(route, json=body, headers=headers("index-" + str(n) + "-key"))
        ids.append(r.json()["corpus_id"])
        assert Worker(s).tick()
    listed = c.get("/api/v1/knowledge/corpora", headers=headers()).json()
    versions = {r["id"]: r["version"] for r in listed}
    for n, cid in enumerate(ids):
        r = c.post(
            f"/api/v1/knowledge/corpora/{cid}/activate",
            json={"reason": "activate"},
            headers=headers("activate-" + str(n) + "-key")
            | {"If-Match": '"' + str(versions[cid]) + '"'},
        )
        assert r.status_code == (200 if n == 0 else 412)


def test_body_limit_stops_reading_before_unbounded_upload(knowledge):
    import asyncio
    import httpx

    c, s = knowledge

    async def stream():
        yield b"x" * 1048577
        raise AssertionError("Read past the upload budget")

    async def invoke():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=c.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/knowledge/indexing-jobs",
                content=stream(),
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 413

    asyncio.run(invoke())


def test_content_dedupe_records_every_acknowledged_key(knowledge):
    c, s = knowledge
    body = payload()
    route = "/api/v1/knowledge/indexing-jobs"
    a = c.post(route, json=body, headers=headers("first-request-key"))
    assert a.status_code == 202
    b = c.post(route, json=body, headers=headers("second-request-key"))
    assert b.status_code == 202 and b.json()["id"] == a.json()["id"]
    changed = deepcopy(body)
    changed["name"] = "changed"
    assert (
        c.post(route, json=changed, headers=headers("second-request-key")).status_code
        == 409
    )


def test_versioned_cli_manifest_replays_exact_availability():
    from knowledge_service.cli import indexing_manifest

    root = Path(__file__).resolve().parents[2] / "services/knowledge/corpus"
    stamp = "2026-11-07T00:00:00+00:00"
    assert indexing_manifest(root, 2, stamp).model_dump(
        mode="json"
    ) == indexing_manifest(root, 2, stamp).model_dump(mode="json")
    with pytest.raises(ValueError):
        indexing_manifest(root, 2, None)


def test_editorial_candidate_preserves_active_versions_and_hash():
    from knowledge_service.corpus import load_manifest
    from portfolio_contracts import canonical_hash

    root = Path(__file__).resolve().parents[2] / "services/knowledge/corpus"
    baseline = load_manifest(root)
    candidate = load_manifest(root / "candidate-20261123")
    assert (
        canonical_hash(baseline.model_dump(mode="json"))
        == "a8d21c647e8a514510873dce49b8414b7fc32921840c74b53a383b189e9600d4"
    )
    original = {d.key: d for d in baseline.documents}
    for document in candidate.documents:
        old = original.get(document.key)
        if old and document.version == old.version:
            assert document == old
        elif old:
            assert document.version > old.version
            assert document.available_at > old.available_at


@pytest.mark.parametrize(
    ("question", "term"),
    [
        ("Rủi ro danh mục chỉ do từng tài sản quyết định sao?", "rui ro danh muc"),
        ("Chấp nhận đề xuất có thực hiện giao dịch luôn không?", "chap nhan de xuat"),
        ("Trượt giá làm giảm lãi sau chi phí thế nào?", "truot gia"),
        ("Target có chứng minh quyền sở hữu cổ phiếu không?", "tai san nam giu"),
    ],
)
def test_fallback_looks_for_the_requested_concept(question, term):
    from knowledge_service.retrieval import lexical_query, topic_query

    assert f'"{term}"' in topic_query(lexical_query(question))
