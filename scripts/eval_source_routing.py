"""Compare actual Chat tool calls with owner snapshots on a frozen Vietnamese split."""

import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from chat_service.explanation import percent
from eval_knowledge_openai import index_candidate, reserve_protocol
from knowledge_eval_stack import ROOT, docker, owner_stack
from local_auth import login
from portfolio_contracts import canonical_hash
from smoke_allocation_explanation import ledger, wait_message
from smoke_chat import PORTFOLIO, get, request, require

CASES = ROOT / "tests/fixtures/knowledge/eval-source-routing-vi-v1.jsonl"
LIMIT = 12
BOUND = Decimal("0.0017") * LIMIT


def check(case, msg, tools, target, corpus, pid):
    card = msg["structured"]
    if "request_allocation" in tools:
        return False
    source = case["source"]
    if source == "saved_target" and case.get("unbound"):
        return card.get("fields") == ["portfolio_id"] and not (
            {"get_portfolio_summary", "retrieve_knowledge"} & set(tools)
        )
    if source == "saved_target":
        facts = card.get("facts", {})
        expected = {
            key: target[key] for key in ("id", "recommendation_id", "accepted_at")
        }
        expected.update(
            {key: target["allocation"][key] for key in ("asset_ids", "weights")}
        )
        return (
            facts.get("accepted_target") == expected
            and facts.get("id") == pid
            and card.get("facts_hash") == canonical_hash(facts)
            and "get_portfolio_summary" in tools
            and "retrieve_knowledge" not in tools
            and all(
                f"{asset} {percent(weight)}" in msg["content"]
                for asset, weight in zip(
                    expected["asset_ids"], expected["weights"], strict=True
                )
                if Decimal(weight) > 0
            )
        )
    if source == "clarify":
        return card.get("fields") == ["source"] and set(tools) <= {"get_profile"}
    if source == "knowledge":
        ev = card.get("knowledge", {})
        return (
            "retrieve_knowledge" in tools
            and ev.get("corpus_hash") == corpus["hash"]
            and [c["claim_id"] for c in ev["citations"]]
            == ["asset-allocation-definition"]
            and msg["content"] == ev["citations"][0]["text"]
        )
    if source == "gold_quote":
        return (
            card.get("facts", {}).get("scope") == "gold_quote"
            and "get_market_facts" in tools
        )
    return (
        card.get("recommendation_id") == target["recommendation_id"]
        and "get_recommendation" in tools
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("dry-run", "offline", "quota", "openai"), default="dry-run"
    )
    parser.add_argument("--portfolio")
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require(
        sha256(CASES.read_bytes()).hexdigest()
        == CASES.with_suffix(".sha256").read_text().strip(),
        "Split changed",
    )
    cases = [json.loads(line) for line in CASES.read_text().splitlines()]
    probes = [
        {
            "id": "P1",
            "text": "Cơ cấu lần trước mình bấm đồng ý gồm gì?",
            "source": "saved_target" if args.mode == "openai" else "clarify",
        },
    ]
    if args.mode == "dry-run":
        print(
            f"{len(cases)} held-out cases and {len(probes)} development probe, at most {LIMIT} text calls, USD {BOUND} reserved, zero embeddings"
        )
        return
    require(
        args.portfolio and args.output and not args.output.exists(),
        "Provide a QA portfolio and a fresh receipt path",
    )
    paid = args.mode == "openai"
    approval = "source-route-" + uuid4().hex[:12]
    packet = {"mode": args.mode, "cases": []}
    token = login("alice")
    pid = args.portfolio
    target = get(PORTFOLIO, f"/api/v1/portfolios/{pid}/dashboard", token)[
        "accepted_target"
    ]
    require(target, "QA portfolio needs an accepted target")
    args.output.touch(mode=0o600, exist_ok=False)
    if paid:
        reserve_protocol(
            ROOT / "output/rag-quality-v3/paid-approvals",
            approval,
            BOUND,
            args.output,
            ceiling=Decimal("10"),
        )
    with owner_stack(
        paid=args.mode != "offline",
        approval=approval,
        cap="0.04",
        limit=LIMIT if paid else 0,
        source_root=args.source_root.resolve(),
        staged_portfolio=True,
    ) as (chat, knowledge, worker):
        corpus = index_candidate(
            knowledge, ROOT / "services/knowledge/corpus/release-20261124"
        )
        try:
            for case in cases + probes:
                scope = (
                    {}
                    if case.get("unbound")
                    else {
                        "portfolio_id": pid,
                        "recommendation_id": target["recommendation_id"],
                    }
                )
                code, conv = request(
                    "POST",
                    chat + "/api/v1/conversations",
                    token=token,
                    body={"portfolio_id": scope.get("portfolio_id")},
                )
                require(code == 201, "Conversation failed")
                job, msg = wait_message(
                    token, conv["id"], scope | {"content": case["text"]}, chat_base=chat
                )
                code = """import sys,json
from sqlalchemy import select
from chat_service.models import ToolCall
from chat_service.runtime import sessions_from_env
with sessions_from_env()() as s:
 print(json.dumps(s.scalars(select(ToolCall.tool).where(ToolCall.job_id==sys.argv[1]).order_by(ToolCall.created_at)).all()))
"""
                tools = json.loads(
                    docker("exec", worker, "python", "-c", code, job["job_id"])
                )
                packet["cases"].append(
                    {
                        "id": case["id"],
                        "job": job["job_id"],
                        "conversation": conv["id"],
                        "message": msg["id"],
                        "message_hash": canonical_hash(msg),
                        "tools": tools,
                        "card": msg["structured"].get("type"),
                        "answer": msg["content"],
                        "passed": check(case, msg, tools, target, corpus, pid),
                    }
                )
            docker("restart", worker)
            for row in packet["cases"]:
                history = get(
                    chat, f"/api/v1/conversations/{row['conversation']}/messages", token
                )
                saved = next(m for m in history if m["id"] == row["message"])
                require(
                    canonical_hash(saved) == row["message_hash"],
                    "Stored receipt changed after restart",
                )
            packet["restart_verified"] = len(packet["cases"])
        finally:
            packet["usage"] = ledger(worker)["rows"]
            args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2))
    passed = sum(c["passed"] for c in packet["cases"][: len(cases)])
    print(
        f"{args.mode}: {passed}/{len(cases)} passed; probe={packet['cases'][-1]['passed']}; {len(packet['usage'])} provider reservations"
    )
    if not all(c["passed"] for c in packet["cases"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
