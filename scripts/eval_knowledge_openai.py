"""Evaluate finite RAG answers via the real owner APIs. Default is a zero-call dry run."""

import argparse
import fcntl
from hashlib import sha256
from decimal import Decimal
import json
import os
from pathlib import Path

import httpx
import time
from uuid import uuid4

from accept_knowledge_paid import save_receipt
from chat_service.knowledge import knowledge_answer
from eval_knowledge_status import latency, load_split, source_hash
from eval_knowledge_compose import real_turn
from knowledge_eval_stack import api_url, docker, owner_stack, wait_ready
from knowledge_service.corpus import load_manifest
from local_auth import claims as token_claims, login
from portfolio_contracts import canonical_hash
from smoke_allocation_explanation import ledger
from smoke_chat import get, request, require

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "services/knowledge/corpus/candidate-20261123"
APPROVAL = "rag-quality-v3-20261123"
LIMIT = 10
CAP = Decimal("0.04")
RESERVATION = Decimal("0.0017")
PROTOCOLS = {
    "clauses2-v5": ("rag-clauses2-v5-20261124", 48, Decimal("0.16")),
    "clauses2-v6": ("rag-clauses2-v6-20261124", 92, Decimal("0.28")),
    "clauses-v5": ("rag-clauses-v5-20261124", 48, Decimal("0.16")),
    "clauses-v6": ("rag-clauses-v6-20261124", 92, Decimal("0.28")),
    "rewrite-v6": ("rag-rewrite-v6-20261124", 100, Decimal("0.30")),
    "combined-v6": ("rag-combined-v6-20261124", 92, Decimal("0.28")),
    "contrast-v3": (APPROVAL, LIMIT, CAP),
    "heldout-v4": ("rag-quality-v4-20261123", 48, Decimal("0.16")),
    "heldout-v5": ("rag-quality-v5-20261123", 48, Decimal("0.16")),
    "hybrid-v5": ("rag-embeddings-v5-20261123", 0, Decimal("0.025")),
}
ROUND_CEILING = Decimal("0.10")


def round_ceiling(protocol):
    if protocol.startswith(("clauses-", "clauses2-", "rewrite-", "combined-")):
        return Decimal("1.25")
    return Decimal("0.20") if protocol.endswith("-v5") else ROUND_CEILING


# The second question of each pair is sent in the same conversation.
CASES = [
    ("EW-definition", "EW là gì?", "ew-definition", "SUPPORTED", "EW"),
    ("EW-followup", "Vậy nó có nhược điểm gì?", "ew-limit", "SUPPORTED", "EW"),
    (
        "EW-limit",
        "Chia đều tỷ trọng có bảo đảm lợi nhuận không?",
        "ew-limit",
        "SUPPORTED",
        "EW",
    ),
    ("ML-definition", "Views ML là gì?", "ml-views-definition", "SUPPORTED", "ML"),
    (
        "ML-limit",
        "Views ML có chắc chắn đúng không?",
        "ml-views-limit",
        "SUPPORTED",
        "ML",
    ),
    (
        "NAV",
        "Độ mới NAV VFF được tính từ ngày nào?",
        ("freshness-window", "vff-nav-availability"),
        "SUPPORTED",
        "NAV",
    ),
    (
        "unsupported",
        "Khái niệm lượng tử rối trong vật lý là gì?",
        None,
        "MISSING",
        "other",
    ),
    (
        "partial",
        "EW là gì? Giá quỹ ngày mai chính xác bao nhiêu đồng?",
        "ew-definition",
        "PARTIAL",
        "partial",
    ),
    ("status", "Bây giờ tạo được chưa?", None, "SYSTEM_PAUSED", "status"),
]


def cohort(protocol):
    if protocol == "contrast-v3":
        return CASES, [], None
    heldout, digest = load_split("heldout", protocol.rsplit("-", 1)[1])
    cases = []
    skipped = []
    for case in heldout:
        if (
            case["source"] != "knowledge"
            or case.get("as_of")
            or case.get("switch")
            or case.get("state")
            or case.get("owner_switch")
        ):
            skipped.append(case["id"])
            continue
        cases.append(
            (
                case["id"],
                case["messages"],
                case["claims"],
                case.get("expected_coverage", "SUPPORTED" if case["claims"] else "MISSING"),
                case["id"],
            )
        )
    require(cases, "No eligible knowledge turns in locked fixture")
    return cases, skipped, digest


def reserve_protocol(directory, approval, bound, output, *, ceiling=ROUND_CEILING):
    # Reservations must outlive a test DB. Lock both tranches under the same round ceiling.
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "round.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        reserved = Decimal(0)
        for marker in directory.glob("*.json"):
            amount = Decimal(json.loads(marker.read_text())["max_reserved_usd"])
            if not amount.is_finite() or amount <= 0:
                raise ValueError("Invalid prior budget reservation")
            reserved += amount
        if not bound.is_finite() or bound <= 0 or reserved + bound > ceiling:
            raise ValueError("Round reservation ceiling exceeded")
        with (directory / (approval + ".json")).open("x") as f:
            os.fchmod(f.fileno(), 0o600)
            json.dump(
                {"max_reserved_usd": str(bound), "packet": str(output.resolve())}, f
            )
            f.flush()
            os.fsync(f.fileno())


def dry_run(protocol="contrast-v3"):
    _, limit, cap = PROTOCOLS[protocol]
    cases, skipped, digest = cohort(protocol)
    plan = {
        "protocol": protocol,
        "semantic_flag": protocol != "contrast-v3",
        "fixture_sha256": digest,
        "skipped_ids": skipped,
        "round_reservation_ceiling_usd": str(round_ceiling(protocol)),
        "provider": "OpenAI",
        "model": "gpt-6-luna",
        "user_limit_usd": "10.00",
        "configured_budget_usd": str(cap),
        "text_call_limit": limit,
        "case_count": len(cases),
        "max_reserved_usd": str(limit * RESERVATION),
        "max_input_bytes_per_request": 12000,
        "max_output_tokens_per_request": 384,
        "embedding_calls": 0,
        "provider_calls": 0,
        "price_source": "https://developers.openai.com/api/docs/models/gpt-6-luna",
    }
    if protocol in {"hybrid-v5", "combined-v6"}:
        # The owner ledgers each allow 20% of the configured cap for embeddings.
        reservation = Decimal("0.00016")
        slots = min(50, int(cap * Decimal("0.2") / reservation))
        plan.update(
            model="gpt-6-luna + text-embedding-3-small" if limit else "text-embedding-3-small",
            semantic_flag=bool(limit),
            max_input_bytes_per_request=12000 if limit else 8000,
            max_output_tokens_per_request=384 if limit else 0,
            input_embedding_limit=slots,
            query_embedding_limit=slots,
            max_reserved_usd=str(limit * RESERVATION + 2 * slots * reservation),
            price_source="https://developers.openai.com/api/docs/models/text-embedding-3-small",
        )
    return plan


def index_candidate(api, corpus_path=CORPUS, *, embeddings=False):
    token = login("data-operator")
    submission = load_manifest(corpus_path).model_dump(mode="json")
    headers = {"Idempotency-Key": str(uuid4())}
    code, job = request(
        "POST",
        api + "/api/v1/knowledge/indexing-jobs",
        token=token,
        body=submission,
        headers=headers,
    )
    require(code == 202, "Isolated candidate submission failed")
    for _ in range(720 if embeddings else 100):
        status = get(api, "/api/v1/knowledge/indexing-jobs/" + job["id"], token)
        if status["status"] in {"READY", "FAILED"}:
            break
        time.sleep(0.25)
    require(status["status"] == "READY", "Isolated indexing failed")
    corpus = next(
        c
        for c in get(api, "/api/v1/knowledge/corpora", token)
        if c["id"] == job["corpus_id"]
    )
    require(
        not corpus["active"]
        and corpus["chunks"] > 0
        and corpus["embedded_chunks"] == (corpus["chunks"] if embeddings else 0),
        "Expected complete embedding coverage for the selected mode",
    )
    code, _ = request(
        "POST",
        api + "/api/v1/knowledge/corpora/" + corpus["id"] + "/activate",
        token=token,
        body={"reason": "Isolated quality evaluation"},
        headers={"Idempotency-Key": str(uuid4()), "If-Match": f'"{corpus["version"]}"'},
    )
    require(code == 200, "Cannot activate in isolated database")
    return corpus


def assess(message, claim, expected, corpus, mode="LEXICAL"):
    card = message.get("structured") or {}
    if expected == "SYSTEM_PAUSED":
        return (
            card.get("type") == "allocation_status"
            and card.get("reason_code") == expected
        )
    ev = card.get("knowledge") or {}
    citations = ev.get("citations", [])
    if (
        card.get("type") != "knowledge"
        or ev.get("mode") != mode
        or message.get("content") != knowledge_answer(ev)
        or any(
            sha256(c["text"].encode()).hexdigest() != c["text_hash"] for c in citations
        )
        or (
            ev.get("evidence_hash")
            != canonical_hash({k: v for k, v in ev.items() if k != "evidence_hash"})
            or ev.get("corpus_hash") != corpus["hash"]
            or ev.get("coverage") != expected
        )
    ):
        return False
    if expected == "MISSING":
        return not citations and ev.get("status") == "MISSING"
    missing_parts = [p["question"] for p in ev.get("clause_evidence", []) if p["chunk_id"] is None]
    if expected == "PARTIAL" and "phần còn lại" not in message["content"] and not (
        missing_parts and all(p in message["content"] for p in missing_parts)
    ):
        return False
    allowed = (claim,) if isinstance(claim, str) else claim
    return bool(citations) and all(
        c["claim_id"] in allowed and c["text"] in message["content"] for c in citations
    )


def index_ledger(container):
    """Read only cost/provenance of the isolated worker, omitting the vector itself."""
    return json.loads(
        docker(
            "exec",
            "-i",
            container,
            "python",
            "-",
            data="""
import json
from sqlalchemy import select
from knowledge_service.models import EmbeddingInvocation
from knowledge_service.runtime import sessions_from_env
with sessions_from_env()() as db:
    rows = db.scalars(select(EmbeddingInvocation).order_by(EmbeddingInvocation.content_key))
    print(json.dumps([dict(content_key=r.content_key, budget_id=r.budget_id, reserved_usd=r.reserved_usd,
        dimension=len((r.output or {}).get("embedding", [])), usage=r.details or {}) for r in rows]))
""",
        )
    )


def run(output, paid, protocol="contrast-v3", source_root=ROOT):
    approval, limit, cap = PROTOCOLS[protocol]
    embeddings = protocol in {"hybrid-v5", "combined-v6"}
    flags = []
    if protocol.startswith(("clauses-", "clauses2-", "rewrite-", "combined-")):
        flags.append("CHAT_KNOWLEDGE_CLAUSES")
    if protocol == "rewrite-v6":
        flags.append("CHAT_KNOWLEDGE_REWRITE")
    if embeddings and not paid:
        raise ValueError(
            "For a zero-cost comparison use --protocol heldout-v5 --offline"
        )
    cases, skipped, digest = cohort(protocol)
    if embeddings:
        manifest = load_manifest(source_root / CORPUS.relative_to(ROOT))
        chunk_count = sum(len(doc.claims) for doc in manifest.documents)
        limits = dry_run(protocol)
        require(
            chunk_count <= limits["input_embedding_limit"]
            and sum(len(row[1]) if isinstance(row[1], list) else 1 for row in cases) <= limits["query_embedding_limit"],
            "Fixture exceeds reserved embedding capacity",
        )
    if ROOT / "output" not in output.resolve().parents:
        raise ValueError("Use an ignored output directory for the review packet")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never spend again on a stale or interrupted packet.
    with output.open("x") as f:
        os.chmod(f.fileno(), 0o600)
        json.dump({"status": "OPENING"}, f)
    packet = {
        "status": "STARTED",
        "mode": "embeddings" if embeddings else "openai" if paid else "offline",
        "limits": dry_run(protocol),
        "skipped_ids": skipped,
        "fixture_sha256": digest,
        "chat_sha256": source_hash(source_root / "services/chat/src/chat_service"),
        "cases": [],
    }
    save_receipt(output, packet)
    if paid:
        reserve_protocol(
            ROOT / "output/rag-quality-v3/paid-approvals",
            approval,
            Decimal(packet["limits"]["max_reserved_usd"]),
            output,
            ceiling=round_ceiling(protocol),
        )
    users_token = login("alice")
    with owner_stack(
        paid=paid,
        approval=approval if paid else "",
        cap=cap if paid else 0,
        limit=limit if paid else 0,
        semantic=packet["limits"]["semantic_flag"],
        source_root=source_root,
        embeddings=embeddings,
        chat_flags=flags,
    ) as (chat, knowledge, worker):
        require(
            docker(
                "exec",
                worker,
                "python",
                "-c",
                "import os; print(os.environ.get('CHAT_KNOWLEDGE_SEMANTIC_SELECTION'))",
            )
            == ("1" if packet["limits"]["semantic_flag"] else "0"),
            "Wrong selector mode",
        )
        initial = ledger(worker)
        cfg = initial["config"]
        require(
            not initial["rows"]
            and cfg["enabled"] == paid
            and cfg["embeddings_enabled"] == embeddings,
            "Expected a fresh scoped language-model ledger",
        )
        if paid:
            require(
                cfg["has_key"]
                and cfg["model"] == "gpt-6-luna"
                and cfg["approval"] == approval
                and Decimal(cfg["budget"]) == cap
                and cfg["calls_limit"] == cfg["daily_limit"] == limit,
                "Could not enforce approved run limits",
            )
        knowledge_worker = worker.removesuffix("chat-worker") + "knowledge-worker"
        if embeddings:
            require(not index_ledger(knowledge_worker), "Expected a fresh index ledger")
        try:
            corpus = index_candidate(
                knowledge, source_root / CORPUS.relative_to(ROOT), embeddings=embeddings
            )
        finally:
            if embeddings:
                packet["index_invocations"] = index_ledger(knowledge_worker)
                save_receipt(output, packet)
        packet["corpus"] = {
            k: corpus[k] for k in ("id", "name", "hash", "chunks", "embedded_chunks")
        }
        if embeddings:
            require(
                len(packet["index_invocations"]) == corpus["chunks"]
                and all(
                    r["budget_id"] == approval
                    and r["dimension"] == 1536
                    and r["usage"].get("reason") == "VERIFIED"
                    for r in packet["index_invocations"]
                ),
                "Index must have a verified real vector for every source",
            )
        chats = {}
        for label, turns, claim, coverage, group in cases:
            if time.time() + 75 >= token_claims(users_token)["exp"]:
                users_token = login("alice")
            turns = [turns] if isinstance(turns, str) else turns
            question = turns[-1]
            if group not in chats:
                code, c = request(
                    "POST",
                    chat + "/api/v1/conversations",
                    token=users_token,
                    body={"title": "RAG QA"},
                )
                require(code == 201, "Chat creation failed")
                chats[group] = c["id"]
            cid = chats[group]
            for prefix in turns[:-1]:
                prefix_job, _, _ = real_turn(
                    users_token, cid, None, prefix, chat_base=chat
                )
                require(
                    prefix_job["status"] == "SUCCEEDED"
                    and not prefix_job.get("recommendation_id"),
                    "Unexpected setup turn",
                )
            job, msg, elapsed = real_turn(
                users_token, cid, None, question, chat_base=chat
            )
            card = msg.get("structured") or {}
            ev = card.get("knowledge") or {}
            packet["cases"].append(
                dict(
                    id=label,
                    question=question,
                    history=turns[:-1],
                    expected_claim=claim,
                    expected_coverage=coverage,
                    conversation_id=cid,
                    job_id=job["job_id"],
                    message_hash=canonical_hash(msg),
                    job_status=job["status"],
                    answer=msg.get("content", ""),
                    passed=assess(
                        msg,
                        claim,
                        coverage,
                        corpus,
                        "HYBRID" if embeddings else "LEXICAL",
                    ),
                    source=card.get("type"),
                    citations=ev.get("citations", []),
                    evidence=ev,
                    evidence_hash=ev.get("evidence_hash"),
                    latency_ms=round(elapsed),
                    actual_coverage=ev.get("coverage"),
                    selection=ev.get("status"),
                    reason=ev.get("selection_reason"),
                    usage=job.get("provider_usage", []),
                )
            )
            save_receipt(output, packet)
            require(
                not job.get("dependency_id") and not job.get("recommendation_id"),
                "Unexpected allocation path",
            )
        rows = ledger(worker)["rows"]
        require(
            sum(r["purpose"] != "query_embedding" for r in rows) <= limit
            and sum(r["purpose"] == "query_embedding" for r in rows) <= packet["limits"].get("query_embedding_limit", 0)
            and all(
                r["budget_id"] == approval
                and (r["purpose"] in {"intent", "explanation"} or
                     (r["purpose"] == "query_rewrite" and "CHAT_KNOWLEDGE_REWRITE" in flags) or
                     (r["purpose"] == "query_embedding" and embeddings))
                for r in rows
            ),
            "Unexpected provider invocation",
        )
        selections = json.loads(
            docker(
                "exec",
                "-i",
                worker,
                "python",
                "-",
                data="""
import json
from sqlalchemy import select
from chat_service.models import Job, ProviderInvocation, ToolCall
from chat_service.runtime import sessions_from_env
with sessions_from_env()() as session:
    output = {}
    for job in session.scalars(select(Job)):
        passages = (job.knowledge_checkpoint or {}).get('passages', [])
        claims = {p['chunk_id']:p['claim_id'] for p in passages}
        row = session.get(ProviderInvocation, (job.id, 'explanation'))
        plan = (row.output or {}) if row else {}
        candidate_text = {p['chunk_id']: p['text'] for p in passages}
        supports = [dict(chunk_id=r['chunk_id'],claim_id=claims.get(r['chunk_id']),quote=r['quote'],
                         matched=bool(r['quote']) and r['quote'] in candidate_text.get(r['chunk_id'],'')) for r in plan.get('supports', plan.get('parts', [])) if r.get('chunk_id')]
        ids = plan.get('selected_chunk_ids', [r['chunk_id'] for r in supports])
        tools = list(session.scalars(select(ToolCall.tool).where(ToolCall.job_id == job.id)))
        output[job.id] = dict(retrieved_claims=list(claims.values()), provider_supports=supports, provider_claims=[claims.get(i) for i in ids], tools=tools, allocation_requested=bool(job.dependency_id) or 'request_allocation' in tools)
print(json.dumps(output))
""",
            )
        )
        for case in packet["cases"]:
            case.update(selections[case["job_id"]])
            case["rewrite_attempted"] = any(
                r["purpose"] == "query_rewrite" and r["job_id"] == case["job_id"] for r in rows
            )
            require(
                not case["allocation_requested"], "Read-only case attempted allocation"
            )
            if case["id"] == "status":
                require(
                    not case["usage"] and "retrieve_knowledge" not in case["tools"],
                    "Status read called a provider or Knowledge",
                )
        packet["end_to_end_latency"] = latency([r["latency_ms"] for r in packet["cases"]])
        if protocol.endswith("-v6"):
            fixtures, _ = load_split("heldout", "v6")
            challenges = {f["id"] for f in fixtures if f.get("rewrite_challenge")}
            answerable = [r for r in packet["cases"] if r["expected_claim"]]
            packet["retrieval_and_citation"] = {
                group: {
                    "n": len(subset),
                    "hit_at_5": sum(bool(set(r["expected_claim"]) & set(r["retrieved_claims"][:5])) for r in subset),
                    "final_citation_hit": sum(any(
                        c["claim_id"] in r["expected_claim"] and c["text"] in r["answer"] and
                        sha256(c["text"].encode()).hexdigest() == c["text_hash"] for c in r["citations"]
                    ) for r in subset),
                }
                for group, subset in (
                    ("answerable", answerable), ("hard", [r for r in answerable if r["id"] in challenges]),
                    ("rewrite_attempted_answerable", [r for r in answerable if r["rewrite_attempted"]]),
                )
            }
        packet["purposes"] = {purpose: sum(r["purpose"] == purpose for r in rows) for purpose in sorted({r["purpose"] for r in rows})}
        packet["usage"] = {
            "calls": len(rows),
            "uncertain": sum("input_tokens" not in r["usage"] for r in rows),
            "input_tokens": sum(r["usage"].get("input_tokens", 0) for r in rows),
            "output_tokens": sum(r["usage"].get("output_tokens", 0) for r in rows),
            "estimated_usd": str(
                sum(
                    (
                        Decimal(str(r["usage"].get("estimated_cost_usd", 0)))
                        for r in rows
                    ),
                    Decimal(0),
                )
            ),
            "reserved_usd": str(
                sum((Decimal(r["reserved_usd"]) for r in rows), Decimal(0))
            ),
        }
        if embeddings:
            indexing = packet["index_invocations"]
            packet["index_usage"] = {
                "calls": len(indexing),
                "input_tokens": sum(r["usage"]["input_tokens"] for r in indexing),
                "estimated_usd": str(
                    sum(Decimal(r["usage"]["estimated_cost_usd"]) for r in indexing)
                ),
                "reserved_usd": str(sum(Decimal(r["reserved_usd"]) for r in indexing)),
            }
        packet["status"] = "ANSWERED"
        save_receipt(output, packet)
        if paid:
            # Reopen the same jobs after restart. Only the ephemeral Chat services are affected.
            api = worker.removesuffix("-worker") + "-api"
            docker("restart", api, worker)
            chat = api_url(api)
            wait_ready(lambda: httpx.get(chat + "/health/ready", timeout=2).is_success)
            users_token = login("alice")
            for case in packet["cases"]:
                state = get(chat, "/api/v1/jobs/chat/" + case["job_id"], users_token)
                messages = get(
                    chat,
                    f"/api/v1/conversations/{case['conversation_id']}/messages",
                    users_token,
                )
                persisted = next(
                    m for m in messages if m["id"] == state["result_message_id"]
                )
                require(
                    canonical_hash(persisted) == case["message_hash"]
                    and state["provider_usage"] == case["usage"],
                    "Original RAG message or usage changed",
                )
            require(
                ledger(worker)["rows"] == rows,
                "Original reservations changed after restart",
            )
            if embeddings:
                require(
                    index_ledger(knowledge_worker) == packet["index_invocations"],
                    "Original index receipts changed",
                )
            packet["same_receipts_after_restart"] = len(packet["cases"])
        packet["status"] = "COMPLETE"
        save_receipt(output, packet)
        return {
            "mode": packet["mode"],
            "passed": sum(r["passed"] for r in packet["cases"]),
            "total": len(cases),
            "usage": packet["usage"],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--offline", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--protocol", choices=PROTOCOLS, default="contrast-v3")
    parser.add_argument("--approval-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.execute and args.approval_id != PROTOCOLS[args.protocol][0]:
        parser.error("Supply the new run-specific approval ID.")
    if (args.offline or args.execute) and not args.output:
        parser.error("--output is required for a fresh immutable packet.")
    print(
        json.dumps(
            run(args.output, args.execute, args.protocol, args.source_root.resolve())
            if args.offline or args.execute
            else dry_run(args.protocol),
            indent=2,
        )
    )
