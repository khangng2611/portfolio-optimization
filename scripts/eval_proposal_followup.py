"""Compare Vietnamese asset follow-ups with an existing owner's saved recommendation."""

import argparse
from decimal import Decimal
import json

import httpx
from pathlib import Path

from eval_knowledge_openai import reserve_protocol, round_ceiling
from chat_service.explanation import percent
from knowledge_eval_stack import ROOT, api_url, docker, owner_stack, wait_ready
from local_auth import login
from portfolio_contracts import canonical_hash
from smoke_allocation_explanation import ledger, wait_message
from smoke_chat import PORTFOLIO, get, request, require

CASES = ROOT / "tests/fixtures/knowledge/eval-proposal-followup-vi.jsonl"
CAP = Decimal("0.02")
APPROVAL = "proposal-context-20261124"


def reserve_paid_turns(directory, output, turn_count):
    reserve_protocol(directory, APPROVAL, turn_count * Decimal("0.0017"), output, ceiling=round_ceiling("clauses-v5"))


def run(args):
    cases = [json.loads(line) for line in CASES.read_text().splitlines()]
    turns = [
        dict(question="VFF có tỷ trọng bao nhiêu?", asset="VFF", field="weight"),
        *cases,
    ]
    require(len(turns) * Decimal("0.0017") <= CAP * Decimal("0.6"), "Over budget")
    if args.mode == "dry-run":
        print(f"Up to {len(turns)} text calls, USD {CAP} cap, no embeddings")
        return
    require(args.source and args.output, "Provide source receipt and fresh output path")
    source = json.loads(args.source.read_text())
    rid, pid = source["recommendation_id"], source["portfolio_id"]
    token = login("alice")
    endpoint = f"/api/v1/recommendations/{rid}"
    facts = get(PORTFOLIO, endpoint, token)
    evidence = get(PORTFOLIO, endpoint + "/evidence", token)
    digest = canonical_hash(facts)
    require(
        digest == source["facts_hash"] and facts["portfolio_id"] == pid,
        "Saved facts changed",
    )
    paid = args.mode == "openai"
    result = dict(mode=args.mode, recommendation_id=rid, facts_hash=digest, turns=[])
    with args.output.open("x") as receipt:
        args.output.chmod(0o600)
        if paid:
            reserve_paid_turns(ROOT / "output/rag-quality-v3/paid-approvals", args.output, len(turns))
        with owner_stack(
            paid=paid,
            approval=APPROVAL if paid else "",
            cap=CAP if paid else 0,
            limit=len(turns) if paid else 0,
            saved_portfolio=True, chat_flags=("CHAT_CONTEXT_FOLLOWUPS",),
        ) as (chat, _, worker):
            try:
                state = ledger(worker)
                require(
                    not state["rows"] and not state["config"]["embeddings_enabled"],
                    "Unexpected preflight state",
                )
                require(
                    state["config"]["enabled"] == paid
                    and state["config"]["has_key"] == paid,
                    "Provider configuration",
                )
                code, conv = request(
                    "POST",
                    chat + "/api/v1/conversations",
                    token=token,
                    body={"portfolio_id": pid},
                )
                require(code == 201, "Cannot create eval conversation")
                for i, case in enumerate(turns):
                    body = dict(portfolio_id=pid, content=case["question"])
                    if i == 0:
                        body.update(intent="explain", recommendation_id=rid)
                    job, message = wait_message(token, conv["id"], body, chat_base=chat)
                    card = message["structured"]
                    focus = dict(asset=case["asset"], field=case["field"])
                    idx = facts["asset_ids"].index(case["asset"])
                    answer = message["content"]
                    selected = [
                        c
                        for c in card.get("explanation_claims", [])
                        if c["id"] in card["selected_claim_ids"]
                    ]
                    result["turns"].append(
                        dict(
                            question=case["question"],
                            answer=answer,
                            focus=card.get("focus"),
                            job_id=job["job_id"],
                            refs=[c["refs"] for c in selected],
                        )
                    )
                    require(
                        card.get("focus") == focus
                        and card.get("facts_hash") == digest
                        and card["recommendation_id"] == rid
                        and card.get("explanation_evidence") == evidence,
                        "Focus or saved evidence mismatch",
                    )
                    require(
                        len(selected) == 1
                        and f"facts.weights.{idx}" in selected[0]["refs"]
                        and percent(facts["weights"][idx]) in answer
                        and answer == selected[0]["text"],
                        "Answer or citation mismatch",
                    )
                    if paid and case.get("classifier"):
                        require(
                            card["dialogue"]["reason"] == "VERIFIED",
                            "Classifier fallback",
                        )
                messages_path = f"/api/v1/conversations/{conv['id']}/messages?limit=100"
                before = canonical_hash(get(chat, messages_path, token))
                before_usage = ledger(worker)["rows"]
                chat_api = worker.removesuffix("-worker") + "-api"
                docker("restart", chat_api, worker)
                chat = api_url(chat_api)
                wait_ready(
                    lambda: httpx.get(chat + "/health/ready", timeout=2).is_success
                )
                require(
                    canonical_hash(get(chat, messages_path, token)) == before
                    and ledger(worker)["rows"] == before_usage,
                    "Restart changed the saved conversation or usage",
                )
                result["restart_verified"] = {
                    "conversation_id": conv["id"],
                    "messages_hash": before,
                }
            finally:
                usage = ledger(worker)["rows"]
                result["usage"] = usage
                receipt.write(json.dumps(result, ensure_ascii=False, indent=2))
            require(
                len(usage) == (sum(bool(r.get("classifier")) for r in turns) if paid else 0), "Unexpected provider calls"
            )
            require(
                all(
                    row["purpose"] == "proposal_focus"
                    and row["usage"]["reason"] == "VERIFIED"
                    and row["usage"]["input_tokens"]
                    and row["usage"]["output_tokens"]
                    for row in usage
                ),
                "Missing real usage",
            )
    print(
        f"{len(cases)}/{len(cases)} implicit follow-ups passed, {len(usage)} provider calls"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["dry-run", "offline", "openai"], default="dry-run"
    )
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    run(parser.parse_args())
