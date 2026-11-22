"""Real zero-budget Knowledge → Chat evidence; verify the same saved messages after restart."""

import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
from portfolio_contracts import canonical_hash
from smoke_chat import (
    CHAT,
    PORTFOLIO,
    GENERATED,
    login,
    request,
    get,
    require,
    SmokeFailure,
)

RECEIPT = GENERATED / "chat-knowledge-api-receipt.json"


def run(verify=False, outage=False, receipt_override=None):
    alice = login("alice")
    bob = login("bob")
    receipt_path = (
        RECEIPT.with_name("chat-knowledge-outage-api-receipt.json")
        if outage
        else RECEIPT
    )
    receipt_path = receipt_override or receipt_path
    if verify:
        saved = json.loads(receipt_path.read_text())
    else:
        status, conv = request(
            "POST",
            CHAT + "/api/v1/conversations",
            token=alice,
            body={"title": "Knowledge zero-budget gate"},
        )
        require(status == 201, "Create Knowledge conversation failed")
        cid = conv["id"]
        saved = {"schema": 1, "conversation_id": cid, "messages": [], "jobs": []}

        def turn(content, **extra):
            key = str(uuid4())
            body = {
                "content": content,
                "intent": "knowledge",
                "client_message_id": key,
            } | extra
            status, submitted = request(
                "POST",
                CHAT + f"/api/v1/conversations/{cid}/messages",
                token=alice,
                body=body,
                headers={"Idempotency-Key": key},
            )
            require(status == 202, "Knowledge message rejected")
            end = time.monotonic() + 60
            while time.monotonic() < end:
                job = get(CHAT, submitted["status_url"], alice)
                if job["status"] in ("SUCCEEDED", "FAILED", "AUTHORIZATION_REQUIRED"):
                    break
                time.sleep(0.25)
            require(job["status"] == "SUCCEEDED", "Knowledge job did not finish")
            require(
                not job["provider_usage"],
                "Zero-budget turn created provider invocation",
            )
            rows = get(CHAT, f"/api/v1/conversations/{cid}/messages", alice)
            message = next(m for m in rows if m["id"] == job["result_message_id"])
            card = message["structured"]
            e = card["knowledge"]
            require(
                e["evidence_hash"]
                == canonical_hash({k: v for k, v in e.items() if k != "evidence_hash"}),
                "Evidence hash mismatch",
            )
            saved["messages"].append(
                {"id": message["id"], "structured_hash": canonical_hash(card)}
            )
            saved["jobs"].append(
                {"id": job["job_id"], "provider_usage": job["provider_usage"]}
            )
            return card

        first = turn("EW là gì?")
        if outage:
            require(
                first["knowledge"]["status"] == "MISSING",
                "Knowledge outage did not abstain",
            )
            previous = json.loads((GENERATED / "chat-api-receipt.json").read_text())
            facts = get(
                PORTFOLIO,
                "/api/v1/recommendations/" + previous["recommendation_id"],
                alice,
            )
            card = turn(
                "MVO",
                intent="explain",
                portfolio_id=previous["portfolio_id"],
                recommendation_id=previous["recommendation_id"],
            )
            require(
                card["facts"] == facts and card["facts_hash"] == canonical_hash(facts),
                "Knowledge outage changed canonical facts",
            )
            require(
                card["knowledge"]["status"] == "MISSING",
                "Canonical explanation did not expose missing Knowledge",
            )

        else:
            require(
                first["type"] == "knowledge"
                and first["knowledge"]["status"] == "REFERENCE"
                and first["knowledge"]["citations"],
                "Knowledge lexical references missing",
            )
            for version, value in ((1, True), (2, True), (2, False)):
                status, pref = request(
                    "POST",
                    CHAT + f"/api/v1/conversations/{cid}/preferences",
                    token=alice,
                    body={"llm_consent": value, "consent_version": version},
                )
                require(
                    status == 403,
                    "Provider settings must be developer-managed",
                )
            missing = turn("zxqv987nonexistent")
            require(
                missing["knowledge"]["status"] == "MISSING",
                "No-evidence did not abstain",
            )
            previous = json.loads((GENERATED / "chat-api-receipt.json").read_text())
            facts = get(
                PORTFOLIO,
                "/api/v1/recommendations/" + previous["recommendation_id"],
                alice,
            )
            card = turn(
                "MVO",
                intent="explain",
                portfolio_id=previous["portfolio_id"],
                recommendation_id=previous["recommendation_id"],
            )
            require(
                card["facts"] == facts and card["facts_hash"] == canonical_hash(facts),
                "RAG changed canonical facts",
            )
            require(
                card["knowledge"]["citations"],
                "Recommendation reference evidence missing",
            )
        receipt_path.write_text(json.dumps(saved, indent=2))
        receipt_path.chmod(0o600)
    cid = saved["conversation_id"]
    rows = get(CHAT, f"/api/v1/conversations/{cid}/messages", alice)
    for old in saved["messages"]:
        message = next(m for m in rows if m["id"] == old["id"])
        require(
            canonical_hash(message["structured"]) == old["structured_hash"],
            "Same message/evidence changed",
        )
    for old in saved["jobs"]:
        job = get(CHAT, "/api/v1/jobs/chat/" + old["id"], alice)
        require(
            job["provider_usage"] == old["provider_usage"], "Invocation count changed"
        )
        for suffix in ("", "/events"):
            status, _ = request(
                "GET", CHAT + "/api/v1/jobs/chat/" + old["id"] + suffix, token=bob
            )
            require(status == 404, "Cross-owner job/SSE exposed")
    status, _ = request(
        "GET", CHAT + f"/api/v1/conversations/{cid}/messages", token=bob
    )
    require(status == 404, "Cross-owner evidence exposed")
    print(
        "PASS: "
        + (
            "same receipt/history/evidence/invocations"
            if verify
            else "real knowledge/consent/canonical-fidelity/ownership"
        )
        + "; paid calls=0"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--verify-receipt", action="store_true")
    p.add_argument("--outage", action="store_true")
    p.add_argument("--receipt", type=Path)
    a = p.parse_args()
    try:
        run(a.verify_receipt, a.outage, a.receipt)
    except SmokeFailure as e:
        print("FAIL: " + str(e))
        raise SystemExit(1) from None
    except Exception as e:
        print("FAIL: " + type(e).__name__ + "; no credentials printed")
        raise SystemExit(1) from None
