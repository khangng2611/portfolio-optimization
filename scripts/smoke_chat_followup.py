"""Real read-only recommendation follow-ups; default dry run makes no API calls."""

import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
from local_auth import login
from smoke_chat import CHAT, PORTFOLIO, canonical_hash, get, request, require

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "output/knowledge-rag/followup-receipt.json"


def verify(path):
    saved = json.loads(path.read_text())
    token = login("alice")
    messages = get(
        CHAT, f"/api/v1/conversations/{saved['conversation_id']}/messages", token
    )
    for old in saved["turns"]:
        job = get(CHAT, "/api/v1/jobs/chat/" + old["job_id"], token)
        message = next(m for m in messages if m["id"] == old["message_id"])
        require(
            canonical_hash(message) == old["message_hash"]
            and job["provider_usage"] == old["usage"],
            "Saved message or usage changed",
        )
    require(
        canonical_hash(
            get(
                PORTFOLIO,
                "/api/v1/recommendations/" + saved["recommendation_id"],
                token,
            )
        )
        == saved["facts_hash"],
        "Canonical facts changed",
    )
    require(
        canonical_hash(
            get(PORTFOLIO, "/api/v1/portfolios/" + saved["portfolio_id"], token)
        )
        == saved["portfolio_hash"],
        "Portfolio changed",
    )
    print(
        "PASS: saved follow-up messages, usage, canonical facts and portfolio are unchanged"
    )


def run(path):
    require(
        not path.exists(), "Receipt already exists; verify it instead of replacing it"
    )
    token = login("alice")
    chosen = None
    for p in get(PORTFOLIO, "/api/v1/portfolios", token):
        history = get(PORTFOLIO, f"/api/v1/portfolios/{p['id']}/recommendations", token)
        if history:
            chosen = p, history[0]
            break
    require(
        chosen is not None,
        "Need an existing owner-scoped recommendation; no new allocation is created by this smoke",
    )
    portfolio, item = chosen
    pid = portfolio["id"]
    facts = get(PORTFOLIO, "/api/v1/recommendations/" + item["id"], token)
    status, conversation = request(
        "POST",
        CHAT + "/api/v1/conversations",
        token=token,
        body={"title": "Recommendation follow-up regression", "portfolio_id": pid},
    )
    require(status == 201, "Cannot create test conversation")
    cid = conversation["id"]
    saved = {
        "conversation_id": cid,
        "portfolio_id": pid,
        "recommendation_id": facts["id"],
        "facts_hash": canonical_hash(facts),
        "portfolio_hash": canonical_hash(
            get(PORTFOLIO, "/api/v1/portfolios/" + pid, token)
        ),
        "turns": [],
    }

    def save():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n")
        path.chmod(0o600)

    save()

    def turn(text, *, intent=None, rid=None, expected="recommendation"):
        key = str(uuid4())
        body = {"content": text, "portfolio_id": pid, "client_message_id": key}
        if intent:
            body["intent"] = intent
        if rid:
            body["recommendation_id"] = rid
        status, response = request(
            "POST",
            CHAT + f"/api/v1/conversations/{cid}/messages",
            token=token,
            body=body,
            headers={"Idempotency-Key": key},
        )
        require(status == 202, "Follow-up submission rejected")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            job = get(CHAT, response["status_url"], token)
            if job["status"] in {
                "SUCCEEDED",
                "WAITING_INPUT",
                "FAILED",
                "AUTHORIZATION_REQUIRED",
            }:
                break
            time.sleep(0.25)
        require(job["status"] == "SUCCEEDED", "Follow-up did not complete")
        rows = get(CHAT, f"/api/v1/conversations/{cid}/messages", token)
        message = next(m for m in rows if m["id"] == job["result_message_id"])
        card = message["structured"]
        require(card["type"] == expected, "Wrong contextual response")
        if expected == "recommendation":
            require(
                any(
                    u["purpose"] == "explanation" and u.get("reason") == "VERIFIED"
                    for u in job["provider_usage"]
                ),
                "Expected real provider explanation under the approved budget",
            )
            require(
                card["recommendation_id"] == facts["id"]
                and card["facts"] == facts
                and card["facts_hash"] == saved["facts_hash"],
                "Follow-up switched or changed the recommendation",
            )
            require(
                card.get("explanation_requested") is True,
                "Explanation must open for an explicit request",
            )
            if "Giải thích" in text and facts.get("strategy") in {"EW", "MVO", "BL_ML"}:
                citations = card.get("knowledge", {}).get("citations", [])
                require(
                    citations
                    and all(p["text"] in message["content"] for p in citations),
                    "Expected approved method passages in the explanation",
                )
            require(
                not any(u["purpose"] == "intent" for u in job["provider_usage"]),
                "Deterministic reference should not spend a paid intent call",
            )
        saved["turns"].append(
            {
                "job_id": job["job_id"],
                "message_id": message["id"],
                "message_hash": canonical_hash(message),
                "usage": job["provider_usage"],
                "question": text,
            }
        )
        save()

    turn("Giải thích đề xuất đã chọn", intent="explain", rid=facts["id"])
    turn("Bạn hỗ trợ được những việc gì?", intent="help", expected="help")
    turn("Tôi đang xem lại thông tin.", intent="help", expected="help")
    turn("Giải thích thêm về quyết định của bạn")
    turn("Đề xuất nào?")
    verify(path)
    print(
        "PASS: five real turns, both screenshot follow-ups use the same existing recommendation; no allocation submitted"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true")
    p.add_argument("--verify-receipt", action="store_true")
    p.add_argument("--receipt", type=Path, default=RECEIPT)
    args = p.parse_args()
    if args.verify_receipt:
        verify(args.receipt)
    elif args.run:
        run(args.receipt)
    else:
        print(
            "DRY RUN: five owner-scoped turns on an existing result; up to five text calls; no API/provider calls made"
        )


if __name__ == "__main__":
    main()
