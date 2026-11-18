"""Real atomic corpus swap/rollback and immutable cited history, no provider or SQL writes."""

import json
from pathlib import Path
import time
from uuid import uuid4
from knowledge_service.corpus import load_manifest
from portfolio_contracts import utcnow, canonical_hash
from smoke_knowledge import tokens, API
from local_auth import login
from smoke_chat import request, require, get, CHAT, GENERATED


def run():
    operator, machine = tokens()

    def call(method, path, body=None, headers=None, expected=200):
        status, data = request(
            method, API + path, token=operator, body=body, headers=headers
        )
        require(status == expected, "Lifecycle request failed: " + str(status))
        return data

    def listed():
        return call("GET", "/api/v1/knowledge/corpora")

    original = next(c for c in listed() if c["active"])
    cid = original["id"]
    alice = login("alice")
    saved = json.loads((GENERATED / "chat-knowledge-api-receipt.json").read_text())
    history_path = "/api/v1/conversations/" + saved["conversation_id"] + "/messages"
    history_hash = canonical_hash(get(CHAT, history_path, alice))

    def change(row, action):
        return call(
            "POST",
            "/api/v1/knowledge/corpora/" + row["id"] + "/" + action,
            body={
                "reason": "Local lifecycle verification; preserve all cited versions"
            },
            headers={
                "If-Match": '"' + str(row["version"]) + '"',
                "Idempotency-Key": action + "-" + str(uuid4()),
            },
        )

    try:
        manifest = load_manifest(
            Path(__file__).resolve().parents[1] / "services/knowledge/corpus"
        ).model_dump(mode="json")
        manifest["name"] = "lifecycle-" + str(uuid4())
        j = call(
            "POST",
            "/api/v1/knowledge/indexing-jobs",
            body=manifest,
            headers={"Idempotency-Key": "lifecycle-" + str(uuid4())},
            expected=202,
        )
        alias_key = "lifecycle-alias-" + str(uuid4())
        alias = call(
            "POST",
            "/api/v1/knowledge/indexing-jobs",
            body=manifest,
            headers={"Idempotency-Key": alias_key},
            expected=202,
        )
        require(alias["id"] == j["id"], "Content alias changed job identity")
        call(
            "POST",
            "/api/v1/knowledge/indexing-jobs",
            body=manifest | {"name": manifest["name"] + "-changed"},
            headers={"Idempotency-Key": alias_key},
            expected=409,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            job = call("GET", "/api/v1/knowledge/indexing-jobs/" + j["id"])
            if job["status"] in ("READY", "FAILED"):
                break
            time.sleep(0.25)
        require(job["status"] == "READY", "Lifecycle corpus did not index")
        current = listed()
        candidate = next(c for c in current if c["id"] == j["corpus_id"])
        old = next(c for c in current if c["id"] == cid)
        change(candidate, "activate")
        # Its previously observed precondition is stale after a different version swaps the pointer.
        call(
            "POST",
            "/api/v1/knowledge/corpora/" + cid + "/activate",
            body={"reason": "stale precondition probe"},
            headers={
                "If-Match": '"' + str(old["version"]) + '"',
                "Idempotency-Key": "stale-" + str(uuid4()),
            },
            expected=412,
        )
        query = {"query": "EW", "corpus_id": cid, "as_of": utcnow().isoformat()}
        status, result = request(
            "POST", API + "/internal/v1/knowledge/retrieve", token=machine, body=query
        )
        require(
            status == 200 and not result["passages"], "Swapped corpus still retrieved"
        )
        change(next(c for c in listed() if c["active"]), "deactivate")
        status, result = request(
            "POST",
            API + "/internal/v1/knowledge/retrieve",
            token=machine,
            body=query | {"corpus_id": None},
        )
        require(
            status == 200 and not result["passages"],
            "Deactivated corpus still retrieved",
        )
        require(
            canonical_hash(get(CHAT, history_path, alice)) == history_hash,
            "Cited history changed on deactivation",
        )
    finally:
        change(next(c for c in listed() if c["id"] == cid), "activate")
    require(
        canonical_hash(get(CHAT, history_path, alice)) == history_hash,
        "Cited history changed on rollback",
    )
    print(
        "PASS: real pointer swap/deactivate/stale precondition/rollback; same cited history; provider calls=0"
    )


if __name__ == "__main__":
    try:
        run()
    except Exception:
        raise SystemExit(
            "FAIL: lifecycle gate; raw credentials/responses suppressed"
        ) from None
