"""Real Auth/Knowledge/pgvector gate. No provider calls or fabricated business rows."""

import argparse
import json
from pathlib import Path
import time
from uuid import uuid4

from knowledge_service.corpus import load_manifest
from portfolio_contracts import canonical_hash, utcnow
from local_auth import login, service_token
from smoke_chat import request, require, GENERATED

API = "http://localhost:8006"
RECEIPT = GENERATED / "knowledge-api-receipt.json"


def tokens():
    return login("data-operator"), service_token("chat-service", "knowledge:retrieve")


def run(verify=False):
    operator, machine = tokens()

    def call(method, path, token=operator, body=None, headers=None, status=200):
        code, value = request(
            method, API + path, token=token, body=body, headers=headers
        )
        require(code == status, "Knowledge request failed: " + str(code))
        return value

    if verify:
        receipt = json.loads(RECEIPT.read_text())
    else:
        manifest = load_manifest(
            Path(__file__).resolve().parents[1] / "services/knowledge/corpus"
        )
        body = manifest.model_dump(mode="json")
        key = "knowledge-" + str(uuid4())
        submitted = call(
            "POST",
            "/api/v1/knowledge/indexing-jobs",
            body=body,
            headers={"Idempotency-Key": key},
            status=202,
        )
        replay = call(
            "POST",
            "/api/v1/knowledge/indexing-jobs",
            body=body,
            headers={"Idempotency-Key": key},
            status=202,
        )
        require(submitted["id"] == replay["id"], "Index dedupe failed")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = call("GET", "/api/v1/knowledge/indexing-jobs/" + submitted["id"])
            if job["status"] in ("READY", "FAILED"):
                break
            time.sleep(0.5)
        require(job["status"] == "READY" and job["chunks"] == 24, "Indexing not ready")
        corpora = call("GET", "/api/v1/knowledge/corpora")
        corpus = next(c for c in corpora if c["id"] == job["corpus_id"])
        active = call(
            "POST",
            "/api/v1/knowledge/corpora/" + corpus["id"] + "/activate",
            body={"reason": "Reviewed public project-authored corpus v1"},
            headers={
                "Idempotency-Key": "activate-" + str(uuid4()),
                "If-Match": '"' + str(corpus["version"]) + '"',
            },
        )
        receipt = {
            "schema": 1,
            "corpus": active,
            "as_of": utcnow().isoformat(),
            "query": "EW",
            "job_id": job["id"],
        }
    query = {
        "query": receipt["query"],
        "corpus_id": receipt["corpus"]["id"],
        "as_of": receipt["as_of"],
    }
    result = call("POST", "/internal/v1/knowledge/retrieve", token=machine, body=query)
    require(
        result["mode"] == "LEXICAL"
        and any(p["claim_id"] == "ew-definition" for p in result["passages"]),
        "Lexical evidence missing",
    )
    require(
        len(json.dumps(result["passages"], ensure_ascii=False).encode()) <= 8000,
        "Context bound failed",
    )
    current = call(
        "POST",
        "/internal/v1/knowledge/retrieve",
        token=machine,
        body={"query": "EW", "as_of": receipt["as_of"]},
    )
    require(
        current["corpus_id"] == result["corpus_id"],
        "Nullable server scope query failed",
    )
    natural = call(
        "POST",
        "/internal/v1/knowledge/retrieve",
        token=machine,
        body=query | {"query": "EW là gì?"},
    )
    require(
        any(p["claim_id"] == "ew-definition" for p in natural["passages"]),
        "Vietnamese question lexical match missing",
    )
    digest = canonical_hash(result)
    if verify:
        require(
            digest == receipt["retrieval_hash"],
            "Same corpus/chunks retrieval changed after restart",
        )
        job = call("GET", "/api/v1/knowledge/indexing-jobs/" + receipt["job_id"])
        require(
            job["status"] == "READY" and job["chunks"] == 24, "Persisted index missing"
        )
    else:
        receipt["retrieval_hash"] = digest
        # Wrong principal/audience, cutoff, no-match and vector shape rejected on real HTTP.
        call(
            "POST",
            "/internal/v1/knowledge/retrieve",
            token=operator,
            body=query,
            status=403,
        )
        no_match = call(
            "POST",
            "/internal/v1/knowledge/retrieve",
            token=machine,
            body=query | {"query": "zxqv987nonexistent"},
        )
        require(not no_match["passages"], "No-match fabricated evidence")
        cutoff = call(
            "POST",
            "/internal/v1/knowledge/retrieve",
            token=machine,
            body=query | {"as_of": "2000-01-01T00:00:00+00:00"},
        )
        require(not cutoff["passages"], "Cutoff leak")
        call(
            "POST",
            "/internal/v1/knowledge/retrieve",
            token=machine,
            body=query
            | {"embedding": [1.0] * 3, "embedding_model": "text-embedding-3-small"},
            status=422,
        )
        RECEIPT.write_text(json.dumps(receipt, indent=2))
        RECEIPT.chmod(0o600)
    print(
        "PASS: "
        + (
            "same receipt after restart"
            if verify
            else "real indexing/lexical/cutoff/auth/dedupe"
        )
        + "; paid calls=0"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify-receipt", action="store_true")
    a = p.parse_args()
    try:
        run(a.verify_receipt)
    except Exception:
        print(
            "FAIL: Knowledge gate; inspect safe phase and service health, no credentials printed"
        )
        raise SystemExit(1) from None
