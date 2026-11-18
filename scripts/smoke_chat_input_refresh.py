"""Real Chat confirmation/expiry/allocation gate; verifies the same saved receipts."""

import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
from local_auth import login
from portfolio_contracts import canonical_hash
from smoke_chat import CHAT, PORTFOLIO, assert_weights, get, request, require

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "output/chat-input-refresh/chat-flow-receipt.json"


def wait_job(token, path):
    end = time.monotonic() + 110
    while time.monotonic() < end:
        job = get(CHAT, path, token)
        if job["status"] in {
            "SUCCEEDED",
            "FAILED",
            "WAITING_INPUT",
            "AUTHORIZATION_REQUIRED",
        }:
            return job
        time.sleep(0.4)
    raise RuntimeError("Chat allocation did not finish before verification timeout")


def send(token, cid, body):
    key = str(uuid4())
    code, receipt = request(
        "POST",
        CHAT + f"/api/v1/conversations/{cid}/messages",
        token=token,
        body=body | {"client_message_id": key},
        headers={"Idempotency-Key": key},
    )
    require(code == 202, "Chat message rejected")
    return wait_job(token, receipt["status_url"])


def assert_strategy(facts, strategy):
    require(
        facts.get("strategy") == strategy
        and facts.get("requested_strategy") == strategy
        and facts.get("fallback_reason") is None,
        "Allocation strategy or fallback does not match the requested gate",
    )
    if strategy == "BL_ML":
        inference = facts.get("diagnostics", {}).get("inference") or {}
        require(
            facts.get("model_bundle_id")
            and inference.get("manifest_hash") == facts["model_bundle_id"]
            and inference.get("snapshot_id") == facts["data_snapshot_id"]
            and inference.get("snapshot_hash")
            == facts["selection_proof"]["snapshot_hash"]
            and inference.get("model_family") == "phase1-asset-ensemble-v5",
            "BL_ML requires native inference with matching model/snapshot pins",
        )


def run(phase, pid, path, *, strategy="MVO"):
    token = login("alice")
    portfolio = get(PORTFOLIO, f"/api/v1/portfolios/{pid}", token)
    readiness = get(PORTFOLIO, f"/api/v1/portfolios/{pid}/readiness", token)
    selected = next(
        item for item in readiness["strategies"] if item["strategy"] == strategy
    )
    require(
        selected.get("reason_code")
        == (
            {"expired": "INPUT_EXPIRED", "stale": "VFF_STALE", "fresh": "READY"}[phase]
        ),
        f"Expected {strategy} expired/fresh real input before the requested phase",
    )
    saved = (
        json.loads(path.read_text()) if path.exists() else {"schema": 1, "cases": {}}
    )
    require(
        phase not in saved["cases"], "Receipt exists; verify it instead of replacing it"
    )
    code, conv = request(
        "POST",
        CHAT + "/api/v1/conversations",
        token=token,
        body={"title": "Input refresh verification " + phase, "portfolio_id": pid},
    )
    require(code == 201, "Cannot create isolated test conversation")
    cid = conv["id"]
    first = send(
        token,
        cid,
        {
            "content": "Tạo đề xuất " + strategy,
            "intent": "allocation",
            "strategy": strategy,
            "portfolio_id": pid,
        },
    )
    require(first["status"] == "WAITING_INPUT", "Expected a review before allocation")
    messages = get(CHAT, f"/api/v1/conversations/{cid}/messages", token)
    card = next(
        m["structured"] for m in messages if m["id"] == first["result_message_id"]
    )
    require(card["type"] == "confirmation", "Expected canonical confirmation card")
    second = send(
        token,
        cid,
        {
            "content": "Xác nhận tạo đề xuất với đầu vào đã xem.",
            "portfolio_id": pid,
            "confirmation": {
                "message_id": card["confirmation_message_id"],
                "facts_hash": card["facts_hash"],
            },
        },
    )
    entry = {
        "conversation_id": cid,
        "portfolio_id": pid,
        "jobs": [first["job_id"], second["job_id"]],
        "error": second["error"],
        "status": second["status"],
        "strategy": strategy,
    }
    if phase in {"expired", "stale"}:
        require(
            second["status"] == "FAILED"
            and second["error"]
            == {"expired": "INPUT_EXPIRED", "stale": "VFF_STALE"}[phase],
            "Expected exact input-state error",
        )
        require(
            second.get("recommendation_id") is None,
            "Expired input produced a recommendation",
        )
    else:
        require(
            second["status"] == "SUCCEEDED" and second.get("recommendation_id"),
            "Real allocation failed",
        )
        facts = get(
            PORTFOLIO, "/api/v1/recommendations/" + second["recommendation_id"], token
        )
        assert_weights(facts)
        assert_strategy(facts, strategy)
        require(
            facts["selection_context"]["data_policy_id"]
            == readiness["inputs"]["provenance"]["data_policy_id"]
            == facts["inputs_provenance"]["data_policy_id"],
            "Allocation did not retain the verified data policy",
        )
        messages = get(CHAT, f"/api/v1/conversations/{cid}/messages", token)
        result = next(
            m["structured"] for m in messages if m["id"] == second["result_message_id"]
        )
        require(
            result["facts"] == facts and result["facts_hash"] == canonical_hash(facts),
            "Canonical numerical facts mismatch",
        )
        entry["recommendation_id"] = facts["id"]
        entry["facts_hash"] = canonical_hash(facts)
        entry["bundle_hash"] = facts["bundle_hash"]
    messages = get(CHAT, f"/api/v1/conversations/{cid}/messages", token)
    entry["messages"] = [{"id": m["id"], "hash": canonical_hash(m)} for m in messages]
    entry["usage"] = [
        get(CHAT, "/api/v1/jobs/chat/" + jid, token)["provider_usage"]
        for jid in entry["jobs"]
    ]
    entry["portfolio_hash"] = canonical_hash(portfolio)
    require(
        canonical_hash(get(PORTFOLIO, f"/api/v1/portfolios/{pid}", token))
        == entry["portfolio_hash"],
        "Generating a proposal changed the portfolio",
    )
    saved["cases"][phase] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)
    print("PASS: real " + phase + " confirmation/allocation path; receipt retained")


def verify(path):
    saved = json.loads(path.read_text())
    token = login("alice")
    for entry in saved["cases"].values():
        messages = {
            m["id"]: m
            for m in get(
                CHAT,
                f"/api/v1/conversations/{entry['conversation_id']}/messages",
                token,
            )
        }
        for row in entry["messages"]:
            require(
                canonical_hash(messages[row["id"]]) == row["hash"],
                "Original message changed",
            )
        for jid, usage in zip(entry["jobs"], entry["usage"], strict=True):
            require(
                get(CHAT, "/api/v1/jobs/chat/" + jid, token)["provider_usage"] == usage,
                "Invocation changed",
            )
        final_job = get(CHAT, "/api/v1/jobs/chat/" + entry["jobs"][-1], token)
        require(
            final_job["status"] == entry["status"]
            and final_job["error"] == entry["error"],
            "Original job status or failure reason changed",
        )
        if entry.get("recommendation_id"):
            facts = get(
                PORTFOLIO,
                "/api/v1/recommendations/" + entry["recommendation_id"],
                token,
            )
            assert_weights(facts)
            assert_strategy(facts, entry.get("strategy", "MVO"))
            require(
                canonical_hash(facts) == entry["facts_hash"],
                "Original recommendation facts changed",
            )
        require(
            canonical_hash(
                get(PORTFOLIO, f"/api/v1/portfolios/{entry['portfolio_id']}", token)
            )
            == entry["portfolio_hash"],
            "Existing portfolio changed",
        )
    print(f"PASS: same {len(saved['cases'])} input-state receipts after restart")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=["expired", "stale", "fresh"])
    p.add_argument("--portfolio-id")
    p.add_argument("--strategy", choices=["MVO", "BL_ML"], default="MVO")
    p.add_argument("--verify-receipt", action="store_true")
    p.add_argument("--receipt", type=Path, default=DEFAULT)
    a = p.parse_args()
    if a.verify_receipt:
        verify(a.receipt)
    else:
        require(
            a.phase and a.portfolio_id,
            "Explicit phase and isolated test portfolio required",
        )
        run(a.phase, a.portfolio_id, a.receipt, strategy=a.strategy)


if __name__ == "__main__":
    main()
