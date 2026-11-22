"""Real local APIs and same-receipt verification; no synthetic HTTP responses."""

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from local_auth import login
from portfolio_contracts import canonical_hash
from smoke_chat import CHAT, PORTFOLIO, get, request, require

DEFAULT_WORKER = "portfolio-auth-demo-chat-worker-1"
UPPER_CALLS = 8
RESERVATION = Decimal("0.0017")
QUESTIONS = [
    "Vì sao phân bổ như vậy?",
    "View tích cực và tiêu cực được dùng thế nào?",
    "Xu hướng và biến động của rổ ra sao?",
    "Hồ sơ rủi ro liên quan thế nào?",
    "Vì sao chọn cổ phiếu trong đề xuất này?",
    "RSI của ACB là bao nhiêu?",
    "Còn tín hiệu của BID?",
]


def paid_outcome(cards, usage):
    verified_jobs = {
        r["job_id"]
        for r in usage
        if r.get("purpose") == "explanation"
        and r.get("usage", {}).get("reason") == "VERIFIED"
        and r.get("usage", {}).get("input_tokens", 0) > 0
        and r.get("usage", {}).get("output_tokens", 0) > 0
    }
    verified = [
        row
        for row in cards
        if row["job_id"] in verified_jobs
        and row["card"].get("explanation_status") == "VERIFIED"
        and row["card"].get("provider", {}).get("reason") == "VERIFIED"
        and row["card"].get("selected_claim_ids")
    ]
    return dict(
        status="PASS" if cards and len(verified) == len(cards) else "FAIL",
        verified_turns=len(verified),
        expected_turns=len(cards),
    )


def ledger(worker=DEFAULT_WORKER):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", worker):
        raise ValueError("Invalid local worker name")
    code = """
import json,os
from sqlalchemy import select
from chat_service.models import ProviderInvocation
from chat_service.runtime import sessions_from_env
with sessions_from_env()() as db:
 rows=db.scalars(select(ProviderInvocation).order_by(ProviderInvocation.job_id,ProviderInvocation.purpose)).all()
 print(json.dumps({'config':{'enabled':os.environ.get('CHAT_LLM_ENABLED')=='1',
 'embeddings_enabled':os.environ.get('CHAT_QUERY_EMBEDDINGS_ENABLED')=='1',
 'has_key':bool(os.environ.get('OPENAI_API_KEY','').strip()),
 'model':os.environ.get('CHAT_OPENAI_MODEL'), 'approval':os.environ.get('KNOWLEDGE_PAID_APPROVAL'),
 'budget':os.environ.get('KNOWLEDGE_BUDGET_USD','0'),
 'calls_limit':int(os.environ.get('CHAT_LLM_APPROVAL_CALL_LIMIT','20')),
 'daily_limit':int(os.environ.get('CHAT_LLM_DAILY_CALL_LIMIT','20'))},
 'rows':[{'job_id':r.job_id,'purpose':r.purpose,'budget_id':r.budget_id,
 'reserved_usd':r.reserved_usd,'created_at':r.created_at.isoformat(),
 'usage':{k:v for k,v in (r.details or {}).items() if k in ['reason','input_tokens','output_tokens','estimated_cost_usd','model']}} for r in rows]}))
"""
    result = subprocess.run(
        ["docker", "exec", "-i", worker, "python", "-"],
        input=code,
        capture_output=True,
        text=True,
        timeout=20,
    )
    require(
        result.returncode == 0,
        "Cannot read local worker config/usage; no calls permitted",
    )
    return json.loads(result.stdout)


def budget_preflight(config, usage, provider, approval=None, max_cost=None):
    reasons = []
    if config.get("embeddings_enabled"):
        reasons.append("EMBEDDINGS_MUST_BE_DISABLED")
    if provider == "template":
        if config.get("enabled"):
            reasons.append("WORKER_PROVIDER_ENABLED")
    else:
        try:
            cap = Decimal(max_cost or "0")
            configured = Decimal(config.get("budget", "0"))
            if not cap.is_finite() or cap <= 0 or cap != configured:
                reasons.append("BUDGET_MUST_MATCH_EXPLICIT_CAP")
            if (
                not config.get("enabled")
                or not config.get("has_key")
                or config.get("model") != "gpt-6-luna"
            ):
                reasons.append("PROVIDER_NOT_READY")
            if not approval or approval != config.get("approval"):
                reasons.append("APPROVAL_MISMATCH")
            reserved = Decimal(usage.get("reserved_usd", "0"))
            if reserved + UPPER_CALLS * RESERVATION > cap * Decimal("0.6"):
                reasons.append("RESERVATION_CAP_EXCEEDED")
            if int(usage.get("reservations", 0)) + UPPER_CALLS > int(
                config.get("calls_limit", 0)
            ):
                reasons.append("APPROVAL_CALL_LIMIT")
            if int(usage.get("daily_calls", 0)) + UPPER_CALLS > int(
                config.get("daily_limit", 0)
            ):
                reasons.append("DAILY_CALL_LIMIT")
        except (InvalidOperation, TypeError, ValueError):
            reasons.append("INVALID_BUDGET")
    return dict(
        allowed=not reasons,
        reasons=reasons,
        provider=provider,
        upper_calls=0 if provider == "template" else UPPER_CALLS,
        upper_reserved_usd="0"
        if provider == "template"
        else str(UPPER_CALLS * RESERVATION),
        input_token_cap=12000,
        output_token_cap=384,
        estimate_basis="Existing adapter estimates: input USD0.125/output USD0.50 per million; not a provider invoice or newly verified pricing.",
        usage=usage,
    )


def preflight(provider, approval=None, max_cost=None, worker=DEFAULT_WORKER):
    from datetime import datetime, timezone

    state = ledger(worker)
    rows = [
        r for r in state["rows"] if r["budget_id"] == state["config"].get("approval")
    ]
    usage = dict(
        reservations=len(rows),
        reserved_usd=str(sum((Decimal(r["reserved_usd"]) for r in rows), Decimal("0"))),
        estimated_usd=str(
            sum(
                (Decimal(str(r["usage"].get("estimated_cost_usd", 0))) for r in rows),
                Decimal("0"),
            )
        ),
        daily_calls=sum(
            r["created_at"][:10] == datetime.now(timezone.utc).date().isoformat()
            for r in state["rows"]
        ),
    )
    return budget_preflight(state["config"], usage, provider, approval, max_cost)


def wait_message(token, cid, body):
    key = str(uuid4())
    code, queued = request(
        "POST",
        CHAT + f"/api/v1/conversations/{cid}/messages",
        token=token,
        headers={"Idempotency-Key": key},
        body=body | {"client_message_id": key},
    )
    require(code == 202, "Message rejected")
    end = time.monotonic() + 60
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
        job["status"] in {"SUCCEEDED", "WAITING_INPUT"}, "Chat job did not complete"
    )
    messages = get(CHAT, f"/api/v1/conversations/{cid}/messages?limit=100", token)
    return job, next(m for m in messages if m["id"] == job["result_message_id"])


def onboarding_body(strategy, source=None):
    body = dict(name="EXPLANATION TEST CHAT", capital_vnd="100000000")
    if strategy == "BL_ML":
        profile = (source or {}).get("risk_profile") or {}
        candidates = ((source or {}).get("asset_selection") or {}).get(
            "candidate_asset_ids"
        )
        if not profile.get("answers") or not candidates:
            raise ValueError(
                "Native smoke requires a confirmed source profile and candidate revision"
            )
        return body | dict(
            capital_vnd=source["capital_vnd"],
            asset_ids=candidates,
            answers=profile["answers"],
        )
    return body | dict(
        universe_id="DEMO",
        answers=dict(
            questionnaire_version="risk-v1",
            horizon_months=60,
            liquidity_need="medium",
            loss_tolerance="medium",
            experience="experienced",
        ),
    )


def run(
    path,
    provider="template",
    approval=None,
    max_cost=None,
    worker=DEFAULT_WORKER,
    strategy="MVO",
    source_portfolio_id=None,
):
    path = Path(path)
    require(not path.exists(), "Refuse to replace an existing receipt; use verify")
    check = preflight(provider, approval, max_cost, worker)
    require(check["allowed"], "Preflight blocked: " + ",".join(check["reasons"]))
    before = ledger(worker)["rows"]
    token = login("alice")
    source = (
        get(PORTFOLIO, f"/api/v1/portfolios/{source_portfolio_id}", token)
        if source_portfolio_id
        else None
    )
    code, portfolio = request(
        "POST",
        PORTFOLIO + "/api/v1/onboarding/portfolios",
        token=token,
        body=onboarding_body(strategy, source),
    )
    require(code == 201, "Test onboarding failed")
    pid = portfolio["id"]
    code, conversation = request(
        "POST", CHAT + "/api/v1/conversations", token=token, body={"portfolio_id": pid}
    )
    require(code == 201, "Test conversation failed")
    cid = conversation["id"]
    jobs, cards = [], []
    job, message = wait_message(
        token,
        cid,
        dict(
            portfolio_id=pid,
            content="Tạo đề xuất " + strategy,
            intent="allocation",
            strategy=strategy,
        ),
    )
    jobs.append(job["job_id"])
    card = message["structured"]
    require(card["type"] == "confirmation", "Explicit confirmation card missing")
    job, message = wait_message(
        token,
        cid,
        dict(
            portfolio_id=pid,
            content="Xác nhận tạo đề xuất với đầu vào đã xem.",
            confirmation={
                "message_id": message["id"],
                "facts_hash": card["facts_hash"],
            },
        ),
    )
    jobs.append(job["job_id"])
    card = message["structured"]
    require(card["type"] == "recommendation", "Canonical allocation card missing")
    cards.append({"job_id": job["job_id"], "card": card})
    rid = card["recommendation_id"]
    initial_evidence = card.get("explanation_evidence") or {}
    if strategy == "BL_ML":
        require(
            initial_evidence.get("status") == "COMPLETE"
            and card["facts"]["strategy"] == "BL_ML"
            and not card["facts"].get("fallback_reason")
            and not card["facts"].get("demo"),
            "Native BL_ML complete evidence gate failed",
        )
    feature_assets = list((initial_evidence.get("quant") or {}).get("features", {}))
    questions = QUESTIONS[:5] + (
        [
            f"RSI của {feature_assets[0]} là bao nhiêu?",
            f"Còn tín hiệu của {feature_assets[-1]}?",
        ]
        if feature_assets
        else QUESTIONS[5:]
    )
    for question in questions:
        job, message = wait_message(
            token,
            cid,
            dict(
                portfolio_id=pid,
                content=question,
                recommendation_id=rid,
            ),
        )
        jobs.append(job["job_id"])
        card = message["structured"]
        cards.append({"job_id": job["job_id"], "card": card})
        require(
            card["type"] == "recommendation"
            and card["recommendation_id"] == rid
            and card.get("selected_claim_ids"),
            "Grounded follow-up missing",
        )
    facts = get(PORTFOLIO, f"/api/v1/recommendations/{rid}", token)
    evidence = get(PORTFOLIO, f"/api/v1/recommendations/{rid}/evidence", token)
    require(
        card["facts_hash"] == canonical_hash(facts)
        and card["explanation_evidence"] == evidence,
        "Canonical facts/evidence mismatch",
    )
    dashboard = get(PORTFOLIO, f"/api/v1/portfolios/{pid}/dashboard", token)
    require(dashboard["accepted_target"] is None, "Explanation must not accept target")
    rows = get(CHAT, f"/api/v1/conversations/{cid}/messages?limit=100", token)
    usage = [r for r in ledger(worker)["rows"] if r["job_id"] in jobs]
    if provider == "template":
        require(not usage, "Template mode produced provider reservations")
        require(
            ledger(worker)["rows"] == before,
            "Provider ledger changed during template acceptance",
        )
    provider_gate = (
        paid_outcome(cards, usage) if provider == "openai" else {"status": "NOT RUN"}
    )
    receipt = dict(
        portfolio_id=pid,
        conversation_id=cid,
        recommendation_id=rid,
        job_ids=jobs,
        facts_hash=canonical_hash(facts),
        evidence_hash=evidence["evidence_hash"],
        message_hash=canonical_hash(rows),
        facts=facts,
        evidence=evidence,
        messages=rows,
        usage=usage,
        provider=provider,
        demo=bool(facts.get("demo")),
        native_bl_ml="PASS" if strategy == "BL_ML" else "NOT RUN",
        hybrid="NOT RUN",
        paid_provider=provider_gate["status"],
        paid_provider_details=provider_gate,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return dict(
        status="PASS"
        if provider != "openai" or provider_gate["status"] == "PASS"
        else "PARTIAL",
        receipt=str(path),
        recommendation_id=rid,
        evidence_status=evidence["status"],
        provider_calls=len(usage),
        demo=bool(facts.get("demo")),
    )


def verify_receipt(path, worker=DEFAULT_WORKER):
    receipt = json.loads(Path(path).read_text())
    token = login("alice")
    rid = receipt["recommendation_id"]
    facts = get(PORTFOLIO, f"/api/v1/recommendations/{rid}", token)
    evidence = get(PORTFOLIO, f"/api/v1/recommendations/{rid}/evidence", token)
    rows = get(
        CHAT,
        f"/api/v1/conversations/{receipt['conversation_id']}/messages?limit=100",
        token,
    )
    require(canonical_hash(facts) == receipt["facts_hash"], "Original facts changed")
    require(evidence == receipt["evidence"], "Original evidence changed")
    require(
        canonical_hash(rows) == receipt["message_hash"],
        "Original messages/citations/claim plan changed",
    )
    usage = [r for r in ledger(worker)["rows"] if r["job_id"] in receipt["job_ids"]]
    require(usage == receipt["usage"], "Original usage changed")
    require(
        get(
            PORTFOLIO, f"/api/v1/portfolios/{receipt['portfolio_id']}/dashboard", token
        )["accepted_target"]
        is None,
        "Unexpected target",
    )
    return dict(
        status="PASS", recommendation_id=rid, same_receipt=True, new_provider_calls=0
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--verify-receipt", action="store_true")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--provider", choices=["template", "openai"], default="template"
    )
    parser.add_argument("--approval-id")
    parser.add_argument("--max-cost-usd")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--worker-container", default=DEFAULT_WORKER)
    parser.add_argument("--strategy", choices=["MVO", "BL_ML"], default="MVO")
    parser.add_argument("--source-portfolio-id")
    args = parser.parse_args()
    if args.verify_receipt:
        report = verify_receipt(args.receipt, args.worker_container)
    elif args.dry_run:
        report = preflight(
            args.provider, args.approval_id, args.max_cost_usd, args.worker_container
        )
    else:
        report = run(
            args.receipt,
            args.provider,
            args.approval_id,
            args.max_cost_usd,
            args.worker_container,
            args.strategy,
            args.source_portfolio_id,
        )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
