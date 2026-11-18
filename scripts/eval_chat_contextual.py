"""Offline fixtures and real OpenAI/Chat acceptance with immutable restart receipts."""

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from local_auth import login
from smoke_chat import CHAT, PORTFOLIO, canonical_hash, get, request, require

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/fixtures/knowledge/eval-chat-context-vi-v2.jsonl"
REPORT = ROOT / "output/knowledge-rag/eval-chat-contextual-managed-live.json"
APPROVAL_UPPER_CALLS = 20
RESERVATION = Decimal("0.0017")


def cases():
    raw = DATA.read_bytes()
    require(
        hashlib.sha256(raw).hexdigest()
        == DATA.with_suffix(".sha256").read_text().strip(),
        "Frozen contextual fixture changed",
    )
    rows = [json.loads(line) for line in raw.splitlines()]
    require(
        len(rows) == 10 and len({r["id"] for r in rows}) == 10,
        "Invalid frozen contextual dataset",
    )
    return rows, hashlib.sha256(raw).hexdigest()


def preflight(approval_id, budget, enabled):
    code = """
import json,os
from decimal import Decimal
from sqlalchemy import select
from chat_service.models import ProviderInvocation
from chat_service.runtime import sessions_from_env
assert os.environ.get('CHAT_LLM_PROVIDER')=='openai'
assert os.environ.get('CHAT_CONTEXTUAL_REPLIES')=='1'
if os.environ.get('CHAT_LLM_ENABLED')=='1':
 assert os.environ.get('OPENAI_API_KEY','').strip()
with sessions_from_env()() as db:
 rows=db.scalars(select(ProviderInvocation).where(
  ProviderInvocation.budget_id==os.environ.get('KNOWLEDGE_PAID_APPROVAL')
 )).all()
 print(json.dumps({'approval':os.environ.get('KNOWLEDGE_PAID_APPROVAL'),
 'budget':os.environ.get('KNOWLEDGE_BUDGET_USD'),
 'existing_reservations':len(rows),'enabled':os.environ.get('CHAT_LLM_ENABLED')=='1'}))
"""
    result = subprocess.run(
        ["docker", "exec", "-i", "portfolio-auth-demo-chat-worker-1", "python", "-"],
        input=code,
        capture_output=True,
        text=True,
        timeout=20,
    )
    require(
        result.returncode == 0,
        "Current demo worker must load OpenAI and contextual budget overlay",
    )
    config = json.loads(result.stdout)
    require(
        config["approval"] == approval_id and Decimal(config["budget"]) == budget,
        "Approval must match the configured durable budget",
    )
    require(
        config["enabled"] == enabled,
        "Selected cases require a different developer LLM configuration",
    )
    require(
        not enabled or config["existing_reservations"] == 0,
        "Acceptance requires a fresh approval; use verify mode for existing receipts",
    )


def message(token, cid, text, pid):
    key = str(uuid4())
    code, queued = request(
        "POST",
        CHAT + f"/api/v1/conversations/{cid}/messages",
        token=token,
        body={"content": text, "client_message_id": key, "portfolio_id": pid},
        headers={"Idempotency-Key": key},
    )
    require(code == 202, "Message was rejected")
    end = time.monotonic() + 45
    while time.monotonic() < end:
        job = get(CHAT, queued["status_url"], token)
        if job["status"] in {
            "SUCCEEDED",
            "WAITING_INPUT",
            "FAILED",
            "AUTHORIZATION_REQUIRED",
        }:
            break
        time.sleep(0.3)
    require(
        job["status"] in {"SUCCEEDED", "WAITING_INPUT"},
        "Chat turn failed or exceeded deadline",
    )
    rows = get(CHAT, f"/api/v1/conversations/{cid}/messages", token)
    return job, next(m for m in rows if m["id"] == job["result_message_id"])


def run(approval, budget, output, selected=None):
    dataset, digest = cases()
    if selected:
        require(
            set(selected).issubset({row["id"] for row in dataset}), "Unknown eval case"
        )
        dataset = [row for row in dataset if row["id"] in selected]
    modes = {row.get("developer_enabled", True) for row in dataset}
    require(
        len(modes) == 1,
        "Run enabled cases D01-D09 and developer-disabled D10 separately under matching server configuration",
    )
    preflight(approval, budget, modes.pop())
    token = login("alice")
    portfolios = get(PORTFOLIO, "/api/v1/portfolios", token)
    portfolio = next(
        (p for p in portfolios if p.get("risk_profile", {}).get("version_id")), None
    )
    require(
        portfolio is not None,
        "Need an existing confirmed portfolio owned by the eval user",
    )
    pid = portfolio["id"]
    before = canonical_hash(get(PORTFOLIO, f"/api/v1/portfolios/{pid}", token))
    report = {
        "dataset_sha256": digest,
        "approval": approval,
        "budget_usd": str(budget),
        "model": "gpt-6-luna",
        "rows": [],
        "portfolio_id": pid,
        "portfolio_hash": before,
        "provider_call_cap": APPROVAL_UPPER_CALLS,
        "max_reserved_usd": str(RESERVATION * APPROVAL_UPPER_CALLS),
        "selected_cases": [row["id"] for row in dataset],
    }

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        output.chmod(0o600)

    save()
    for case in dataset:
        token = login("alice")
        code, conversation = request(
            "POST",
            CHAT + "/api/v1/conversations",
            token=token,
            body={"title": "Contextual eval " + case["id"], "portfolio_id": pid},
        )
        require(code == 201, "Cannot create eval conversation")
        cid = conversation["id"]
        for index, text in enumerate(case["messages"]):
            job, msg = message(token, cid, text, pid)
            card = msg["structured"]
            passed = card["type"] == case["types"][index]
            if case.get("fields"):
                passed = passed and card.get("fields") == case["fields"]
            if card["type"] == "confirmation":
                passed = passed and card["input"]["strategy"] == case["strategy"]
            if "claim" in case:
                evidence = card["knowledge"]
                ids = {p["claim_id"] for p in evidence["citations"]}
                passed = passed and (case["claim"] in ids if case["claim"] else not ids)
                passed = passed and evidence["evidence_hash"] == canonical_hash(
                    {k: v for k, v in evidence.items() if k != "evidence_hash"}
                )
            usage = job["provider_usage"]
            if not case.get("developer_enabled", True):
                passed = passed and not usage
            elif card["type"] != "confirmation":
                passed = passed and card.get("response", {}).get("reason") == "VERIFIED"
            report["rows"].append(
                {
                    "case": case["id"],
                    "turn": index,
                    "passed": bool(passed),
                    "conversation_id": cid,
                    "job_id": job["job_id"],
                    "message_id": msg["id"],
                    "message_hash": canonical_hash(msg),
                    "type": card["type"],
                    "reply": msg["content"],
                    "usage": usage,
                }
            )
            save()
    report["portfolio_unchanged"] = (
        canonical_hash(get(PORTFOLIO, f"/api/v1/portfolios/{pid}", token)) == before
    )
    report["passed"] = sum(row["passed"] for row in report["rows"])
    report["total"] = len(report["rows"])
    report["usage"] = {
        "calls": sum(len(row["usage"]) for row in report["rows"]),
        "input_tokens": sum(
            v.get("input_tokens", 0) for row in report["rows"] for v in row["usage"]
        ),
        "output_tokens": sum(
            v.get("output_tokens", 0) for row in report["rows"] for v in row["usage"]
        ),
        "estimated_usd": str(
            sum(
                (
                    Decimal(str(v.get("estimated_cost_usd", 0)))
                    for row in report["rows"]
                    for v in row["usage"]
                ),
                Decimal("0"),
            )
        ),
    }
    save()
    print(
        json.dumps(
            {k: report[k] for k in ("passed", "total", "usage", "portfolio_unchanged")}
        )
    )
    require(
        report["passed"] == report["total"] and report["portfolio_unchanged"],
        "Some live cases failed; review report without rerunning paid calls",
    )


def verify(output):
    report = json.loads(output.read_text())
    token = login("alice")
    for row in report["rows"]:
        job = get(CHAT, f"/api/v1/jobs/chat/{row['job_id']}", token)
        messages = get(
            CHAT, f"/api/v1/conversations/{row['conversation_id']}/messages", token
        )
        msg = next(m for m in messages if m["id"] == row["message_id"])
        require(
            canonical_hash(msg) == row["message_hash"]
            and job["provider_usage"] == row["usage"],
            "Saved message or invocation changed",
        )
    require(
        canonical_hash(
            get(PORTFOLIO, f"/api/v1/portfolios/{report['portfolio_id']}", token)
        )
        == report["portfolio_hash"],
        "Existing portfolio changed",
    )
    print(
        f"PASS: same {len(report['rows'])} message/usage receipts and portfolio after restart"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", action="store_true")
    p.add_argument("--verify-receipt", action="store_true")
    p.add_argument("--approval-id")
    p.add_argument("--budget-usd", type=Decimal, default=Decimal("0"))
    p.add_argument("--output", type=Path, default=REPORT)
    p.add_argument(
        "--cases", help="Comma-separated case IDs for a targeted regression run"
    )
    a = p.parse_args()
    rows, digest = cases()
    if a.verify_receipt:
        verify(a.output)
    elif a.run:
        require(
            a.approval_id
            and a.budget_usd.is_finite()
            and 0 < a.budget_usd <= Decimal("1"),
            "Specific approval and cap at most 1.00 USD required",
        )
        require(
            RESERVATION * APPROVAL_UPPER_CALLS <= a.budget_usd,
            "Budget below worst-case reservation",
        )
        run(
            a.approval_id,
            a.budget_usd,
            a.output,
            a.cases.split(",") if a.cases else None,
        )
    else:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "cases": len(rows),
                    "dataset_sha256": digest,
                    "max_calls": APPROVAL_UPPER_CALLS,
                    "upper_reserved_usd": str(RESERVATION * APPROVAL_UPPER_CALLS),
                    "provider_calls": 0,
                }
            )
        )


if __name__ == "__main__":
    main()
