"""Paid gate preparation is offline by default. Execution requires a NEW explicit budget."""

from pathlib import Path
import argparse
from decimal import Decimal, InvalidOperation
import json
import os
import time
from uuid import uuid4

PRICE_SOURCES = [
    "https://developers.openai.com/api/docs/models/text-embedding-3-small",
    "https://developers.openai.com/api/docs/pricing",
]


def dry_run(budget="0"):
    try:
        cap = Decimal(budget)
        if not cap.is_finite() or not 0 <= cap <= 1:
            raise ValueError("Supported total cap: 0..1 USD")
    except InvalidOperation:
        raise ValueError("Invalid budget") from None
    # Reserved upper bounds, not a bill: embedding <=8000 bytes/tokens; dialogue <=12000 input +384 output.
    bound = Decimal(100) * Decimal("0.00016") + Decimal(20) * Decimal("0.0017")
    return {
        "dry_run": True,
        "budget_usd": str(cap),
        "allowed_to_execute": False,
        "provider_calls": 0,
        "embedding_request_cap": 100,
        "dialogue_request_cap": 20,
        "maximum_reserved_usd": float(min(cap, bound)),
        "index_share": "20% / <=50 requests",
        "query_share": "20% / <=50 requests",
        "dialogue_share": "60% / <=20 requests",
        "price_version": "2026-11-07",
        "price_sources": PRICE_SOURCES,
        "warning": "A cap estimate, key, old consent or old Chat quota is not a new authorization.",
    }


def embedding_corpus_ready(corpus):
    return (
        corpus.get("chunks", 0) > 0
        and corpus.get("embedded_chunks", 0) == corpus["chunks"]
    )


def assess_case(case, message, job, corpus):
    from portfolio_contracts import canonical_hash

    failures = []
    card = (message or {}).get("structured") or {}
    evidence = card.get("knowledge") or {}
    actual = card.get("type")
    if actual == "recommendation":
        actual = "explain"
    if actual != case["expected_intent"]:
        failures.append("INTENT_MISMATCH")
    if job.get("recommendation_id"):
        failures.append("UNEXPECTED_MUTATION")
    citations = evidence.get("citations", [])
    if case["expected_abstention"] and citations:
        failures.append("EXPECTED_ABSTENTION")
    if case["expected_intent"] == "knowledge":
        if evidence.get("mode") != "HYBRID":
            failures.append("NO_HYBRID_TRANSPORT")
        if (
            evidence.get("corpus_id") != corpus["id"]
            or evidence.get("corpus_hash") != corpus["hash"]
        ):
            failures.append("CORPUS_CHANGED")
        if evidence.get("evidence_hash") != canonical_hash(
            {k: v for k, v in evidence.items() if k != "evidence_hash"}
        ):
            failures.append("EVIDENCE_HASH")
        selected = [c["chunk_id"] for c in citations]
        if (
            len(selected) != len(set(selected))
            or set(selected) != set(evidence.get("selected_chunk_ids", []))
            or not set(selected) <= set(evidence.get("retrieved_chunk_ids", []))
        ):
            failures.append("CITATION_REFERENCES")
        usage = job.get("provider_usage", [])
        if not any(
            u.get("purpose") == "query_embedding"
            and u.get("reason") == "VERIFIED"
            and u.get("input_tokens", 0) > 0
            for u in usage
        ):
            failures.append("NO_REAL_QUERY_USAGE")
        if not case["expected_abstention"]:
            if not citations or not {c["claim_id"] for c in citations} <= set(
                case["allowed_claim_ids"]
            ):
                failures.append("ALLOWED_CLAIMS")
            if evidence.get("status") != "VERIFIED_REFERENCES" or not any(
                u.get("purpose") == "explanation"
                and u.get("reason") == "VERIFIED"
                and u.get("input_tokens", 0) > 0
                and u.get("output_tokens", 0) > 0
                for u in usage
            ):
                failures.append("NO_VERIFIED_SELECTION_USAGE")
        elif evidence.get("status") != "MISSING":
            failures.append("ABSTENTION_STATUS")
    return {"passed": not failures, "failures": failures, "actual_intent": actual}


def plan_run(saved, approval, budget, cases, corpus):
    if saved:
        if (
            saved["approval_id"] != approval
            or Decimal(saved["budget_usd"]) != Decimal(budget)
            or saved["corpus"]["id"] != corpus["id"]
            or saved["corpus"]["hash"] != corpus["hash"]
        ):
            raise ValueError(
                "Existing paid receipt binds a different budget/corpus; never replace it"
            )
        if set(saved["cases"]) != {c["id"] for c in cases}:
            raise ValueError("Representative case set changed")
        return saved
    return {
        "schema": 2,
        "approval_id": approval,
        "budget_usd": budget,
        "corpus": corpus,
        "conversation_id": None,
        "conversation_state": "NOT_STARTED",
        "cases": {
            c["id"]: {
                "client_message_id": str(uuid4()),
                "state": "PENDING",
                "job_id": None,
            }
            for c in cases
        },
    }


def save_receipt(path, saved):
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".knowledge-paid-",
        delete=False,
    ) as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
        temporary = f.name
    os.replace(temporary, path)


def worker_budget_preflight(approval, budget):
    import subprocess

    root = Path(__file__).resolve().parents[1]
    code = """import os,sys,json
from decimal import Decimal
wanted=json.loads(sys.argv[1])
assert os.environ.get('KNOWLEDGE_PAID_APPROVAL')==wanted['approval']
assert Decimal(os.environ.get('KNOWLEDGE_BUDGET_USD','0'))==Decimal(wanted['budget'])
assert bool(os.environ.get('OPENAI_API_KEY'))
if wanted['chat']:
 assert os.environ.get('CHAT_LLM_PROVIDER')=='openai'
 assert os.environ.get('CHAT_LLM_ENABLED')=='1'
 assert os.environ.get('CHAT_QUERY_EMBEDDINGS_ENABLED')=='1'
 assert 0<int(os.environ.get('CHAT_LLM_DAILY_CALL_LIMIT','0'))<=20
print('PASS')
"""
    for worker in ("chat-worker", "knowledge-worker"):
        command = [
            "docker",
            "compose",
            "--env-file",
            str(root / "infra/local/.generated/.env"),
            "-f",
            str(root / "infra/local/compose.yaml"),
            "exec",
            "-T",
            worker,
            "python",
            "-",
            json.dumps(
                {
                    "approval": approval,
                    "budget": budget,
                    "chat": worker == "chat-worker",
                }
            ),
        ]
        result = subprocess.run(
            command, input=code, text=True, capture_output=True, timeout=20
        )
        if result.returncode:
            raise ValueError(
                "Worker budget/key configuration does not match this new approval"
            )


def execute(budget, approval_id, verify=False, receipt_path=None):
    import re
    import fcntl
    from smoke_chat import CHAT, GENERATED, login, request, get, require
    from smoke_knowledge import tokens, API
    from portfolio_contracts import canonical_hash
    from eval_knowledge import load_cases, DATA

    report = dry_run(budget)
    require(
        Decimal(budget) > 0
        and re.fullmatch(r"[A-Za-z0-9_-]{8,100}", approval_id or ""),
        "New specific approval ID and positive USD cap required",
    )
    path = receipt_path or GENERATED / "knowledge-paid-receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        saved = json.loads(path.read_text()) if path.exists() else None
        chosen = {"A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "S01", "S05"}
        cases = [r for r in load_cases() if r["id"] in chosen]
        dataset_hash = DATA.with_suffix(".sha256").read_text().strip()
        if verify:
            require(
                saved is not None,
                "No paid receipt exists; verification never creates a replacement",
            )
            corpus = saved["corpus"]
        else:
            require(
                os.environ.get("KNOWLEDGE_PAID_APPROVAL") == approval_id
                and Decimal(os.environ.get("KNOWLEDGE_BUDGET_USD", "0"))
                == Decimal(budget),
                "Explicit environment approval/cap mismatch",
            )
            require(
                os.environ.get("KNOWLEDGE_PRICE_REVIEWED") == "2026-11-07",
                "Recheck the official price sheet before enabling execution",
            )
            worker_budget_preflight(approval_id, budget)
            operator, _ = tokens()
            status, corpora = request(
                "GET", API + "/api/v1/knowledge/corpora", token=operator
            )
            require(status == 200, "Cannot inspect embedding corpus prerequisite")
            corpus = next((c for c in corpora if c["active"]), None)
            require(
                corpus and embedding_corpus_ready(corpus),
                "Active READY corpus must contain real embeddings for every chunk",
            )
        saved = plan_run(saved, approval_id, budget, cases, corpus)
        require(
            saved.get("dataset_sha256", dataset_hash) == dataset_hash,
            "Frozen case dataset changed",
        )
        saved["dataset_sha256"] = dataset_hash
        save_receipt(path, saved)
        alice = login("alice")
        if not saved["conversation_id"]:
            require(
                not verify and saved["conversation_state"] == "NOT_STARTED",
                "Uncertain conversation creation requires owner API reconciliation; never create a replacement",
            )
            saved["conversation_state"] = "CREATING"
            save_receipt(path, saved)
            status, conversation = request(
                "POST",
                CHAT + "/api/v1/conversations",
                token=alice,
                body={
                    "title": "Knowledge paid " + approval_id,
                },
            )
            require(
                status == 201,
                "Conversation creation outcome must be reconciled before retry",
            )
            saved["conversation_id"] = conversation["id"]
            saved["conversation_state"] = "CREATED"
            save_receipt(path, saved)
        cid = saved["conversation_id"]
        for case in cases:
            item = saved["cases"][case["id"]]
            if not item["job_id"]:
                require(
                    not verify, "Incomplete case receipt; verification creates no job"
                )
                item["state"] = "POSTING"
                save_receipt(path, saved)
                # The stable key/body are already durable. Retrying this POST cannot create a new paid job.
                status, accepted = request(
                    "POST",
                    CHAT + f"/api/v1/conversations/{cid}/messages",
                    token=alice,
                    body={
                        "content": case["messages"][-1],
                        "client_message_id": item["client_message_id"],
                    },
                    headers={"Idempotency-Key": item["client_message_id"]},
                )
                require(status == 202, "Case POST uncertain; resume the same saved key")
                item["job_id"] = accepted["job_id"]
                item["state"] = "ACCEPTED"
                save_receipt(path, saved)
            deadline = time.monotonic() + 60
            while True:
                job = get(CHAT, "/api/v1/jobs/chat/" + item["job_id"], alice)
                if (
                    job["status"]
                    in (
                        "SUCCEEDED",
                        "FAILED",
                        "AUTHORIZATION_REQUIRED",
                        "WAITING_INPUT",
                        "CANCELLED",
                    )
                    or verify
                ):
                    break
                require(
                    time.monotonic() < deadline,
                    "Saved job still pending; resume it without replacement",
                )
                time.sleep(0.25)
            rows = get(CHAT, f"/api/v1/conversations/{cid}/messages", alice)
            message = next(
                (m for m in rows if m["id"] == job.get("result_message_id")), None
            )
            current_hash = canonical_hash(message["structured"]) if message else None
            if item.get("completed"):
                require(
                    current_hash == item["structured_hash"]
                    and job["provider_usage"] == item["usage"],
                    "Same paid receipt/evidence/invocations changed",
                )
            else:
                require(
                    not verify,
                    "Incomplete saved case requires resume, not verification",
                )
                item.update(
                    completed=True,
                    state=job["status"],
                    message_id=job.get("result_message_id"),
                    structured_hash=current_hash,
                    usage=job["provider_usage"],
                    assessment=assess_case(case, message, job, corpus),
                )
                save_receipt(path, saved)
            if "UNEXPECTED_MUTATION" in item["assessment"]["failures"]:
                break
        assessments = [
            v["assessment"] for v in saved["cases"].values() if v.get("completed")
        ]
        usage = [u for v in saved["cases"].values() for u in v.get("usage", [])]
        report.update(
            dry_run=False,
            representative_cases=len(assessments),
            passed_cases=sum(a["passed"] for a in assessments),
            representative_gate="PASS"
            if len(assessments) == 10 and all(a["passed"] for a in assessments)
            else "FAIL",
            case_results={k: v.get("assessment") for k, v in saved["cases"].items()},
            usage=usage,
            uncertain_reservations=sum("input_tokens" not in u for u in usage),
            release_gate="NOT_ACCEPTED: full eval and human support review required",
            note="Read ingestion/query/dialogue totals with knowledge_usage.py --approval-id; estimates are not an invoice.",
        )
        return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--budget-usd", default="0")
    p.add_argument("--approval-id")
    p.add_argument("--receipt", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--verify-receipt", action="store_true")
    a = p.parse_args()
    if a.execute and a.dry_run:
        p.error("Choose dry-run or execute")
    if a.verify_receipt and not a.execute:
        p.error("verify-receipt requires execute mode but makes no provider calls")
    try:
        result = (
            execute(a.budget_usd, a.approval_id, a.verify_receipt, a.receipt)
            if a.execute
            else dry_run(a.budget_usd)
        )
    except Exception:
        raise SystemExit(
            "Acceptance stopped; preserve its receipt and reconcile/resume existing work. No credentials printed."
        ) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if a.execute and result["representative_gate"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
