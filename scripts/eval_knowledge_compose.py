"""One HTTP pass over the locked scenarios whose preconditions exist on the local Compose stack."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from eval_knowledge_status import (
    ROOT,
    counts,
    latency,
    load_split,
    rank_claim,
    source_hash,
)
from local_auth import login
from portfolio_contracts import canonical_hash, utcnow
from smoke_chat import CHAT, PORTFOLIO, STOPPED, SmokeFailure, get, request, require

WORKER = "portfolio-auth-demo-chat-worker-1"


def worker_read(code, payload=None):
    result = subprocess.run(
        ["docker", "exec", "-i", WORKER, "python", "-c", code],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
    )
    require(result.returncode == 0, "Compose read-only worker inspection failed")
    return json.loads(result.stdout)


def selected_cases(cases, paused):
    return [
        r
        for r in cases
        if (
            r["source"] == "knowledge"
            and len(r["messages"]) == 1
            and not r.get("as_of")
        )
        or (paused and r["id"] == "H02")
    ]


def real_turn(token, cid, pid, content, *, chat_base=CHAT):
    key = str(uuid4())
    start = time.perf_counter()
    for attempt in range(2):
        try:
            status, queued = request(
                "POST",
                chat_base + f"/api/v1/conversations/{cid}/messages",
                token=token,
                headers={"Idempotency-Key": key},
                body={
                    "client_message_id": key,
                    "content": content,
                    "portfolio_id": pid,
                },
            )
            break
        except SmokeFailure:
            # A lost HTTP response may already have queued the job. Reuse its exact key.
            if attempt:
                raise
    require(status == 202, f"Live Chat submit returned {status}")
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        job = get(chat_base, queued["status_url"], token)
        if job["status"] in STOPPED:
            break
        time.sleep(0.25)
    require(job["status"] in STOPPED, "Live Chat job exceeded deadline")
    messages = get(chat_base, f"/api/v1/conversations/{cid}/messages", token)
    msg = next((m for m in messages if m["id"] == job["result_message_id"]), {})
    return job, msg, (time.perf_counter() - start) * 1000


def run(output):
    require(not output.exists(), "Select a fresh receipt path for a new live cohort")
    config = worker_read("""
import hashlib,json,os,pathlib,chat_service.workflow as w
from portfolio_contracts import system_hybrid_managed, system_hybrid_enabled
h=hashlib.sha256()
for path in sorted(pathlib.Path(w.__file__).parent.glob("*.py")):
 h.update(path.name.encode()+bytes(1)+path.read_bytes()+bytes(1))
print(json.dumps({"chat_source_sha256":h.hexdigest(),
 "provider_off":os.environ.get("CHAT_LLM_ENABLED")!="1" and not os.environ.get("CHAT_PROVIDER_URL"),
 "embeddings_off":os.environ.get("CHAT_QUERY_EMBEDDINGS_ENABLED")!="1",
 "paused":system_hybrid_managed() and not system_hybrid_enabled()}))
""")
    require(
        config["provider_off"] and config["embeddings_off"],
        "Live eval requires disabled provider and embeddings",
    )
    require(
        config["chat_source_sha256"] == source_hash(),
        "Worker code differs from the selected local snapshot",
    )
    token = login("alice")
    owned = get(PORTFOLIO, "/api/v1/portfolios", token)
    require(owned, "Seeded owner requires an existing portfolio")
    pid = owned[0]["id"]
    readiness = get(PORTFOLIO, f"/api/v1/portfolios/{pid}/readiness", token)
    cases, digest = load_split("heldout")
    cohort = selected_cases(
        cases, config["paused"] and readiness.get("reason_code") == "SYSTEM_PAUSED"
    )
    report = {
        "mode": "compose_chat_http",
        "dataset_sha256": digest,
        **config,
        "worker_image": subprocess.check_output(
            ["docker", "inspect", "--format", "{{.Image}}", WORKER], text=True
        ).strip(),
        "started_at": utcnow().isoformat(),
        "cutoff": "real worker job time",
        "rows": [],
        "skipped_ids": [r["id"] for r in cases if r not in cohort],
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    save()
    job_ids = []
    for case in cohort:
        status, conv = request(
            "POST",
            CHAT + "/api/v1/conversations",
            token=token,
            body={"title": "RAG quality eval " + case["id"], "portfolio_id": pid},
        )
        require(status == 201, f"Live Chat session creation returned {status}")
        for prompt in case["messages"]:
            job, msg, ms = real_turn(token, conv["id"], pid, prompt)
            job_ids.append(job["job_id"])
            require(not job["provider_usage"], "Unexpected live provider invocation")
        card = msg.get("structured") or {}
        evidence = card.get("knowledge") or {}
        cited = evidence.get("citations", [])
        row = {
            "id": case["id"],
            "job_hash": canonical_hash(job["job_id"]),
            "job_status": job["status"],
            "source_code": card.get("type"),
            "ms": ms,
            "error_code": job.get("error"),
            "source_match": card.get("type")
            == ("knowledge" if case["source"] == "knowledge" else "allocation_status"),
        }
        if case["source"] == "knowledge":
            row.update(
                corpus_hash=evidence.get("corpus_hash"),
                evidence_hash=evidence.get("evidence_hash"),
                intact_evidence=bool(evidence)
                and evidence.get("evidence_hash")
                == canonical_hash(
                    {k: v for k, v in evidence.items() if k != "evidence_hash"}
                ),
            )
            if case["claims"]:
                row["citation_hit"] = bool(rank_claim(cited, case["claims"]))
                row["answer_quotes_claim"] = any(
                    c["claim_id"] in case["claims"]
                    and c["text"] in msg.get("content", "")
                    for c in cited
                )
            else:
                row["abstained"] = (
                    row["source_match"]
                    and evidence.get("status") == "MISSING"
                    and not cited
                    and bool(evidence.get("corpus_hash"))
                    and evidence.get("reason") in ("NO_EVIDENCE", "MATCH")
                )
        else:
            row["reason_code"] = card.get("reason_code")
            row["status_authority"] = (
                row["reason_code"] == "SYSTEM_PAUSED"
                and card.get("source") == "portfolio_readiness"
                and card.get("portfolio_id") == pid
                and bool(card.get("checked_at"))
            )
        report["rows"].append(row)
        save()
    audit = worker_read(
        """
import json,sys
from sqlalchemy import select,func
from chat_service.models import Job,ProviderInvocation,ToolCall
from chat_service.runtime import sessions_from_env
ids=json.load(sys.stdin)
with sessions_from_env()() as s:
 jobs=s.scalars(select(Job).where(Job.id.in_(ids))).all()
 tools=s.execute(select(ToolCall.tool,func.count()).where(ToolCall.job_id.in_(ids)).group_by(ToolCall.tool)).all()
 print(json.dumps({"jobs":len(jobs),"dependencies":sum(bool(j.dependency_id) for j in jobs),
 "recommendation_links":sum(bool(j.recommendation_id) for j in jobs),
 "provider_invocations":s.scalar(select(func.count()).select_from(ProviderInvocation).where(ProviderInvocation.job_id.in_(ids))),
 "tools":dict(tools)}))
""",
        job_ids,
    )
    require(audit["jobs"] == len(job_ids), "Live audit missed an eval job")
    rows = report["rows"]
    report.update(
        audit=audit,
        finished_at=utcnow().isoformat(),
        quality={
            k: counts(rows, k)
            for k in (
                "source_match",
                "status_authority",
                "citation_hit",
                "answer_quotes_claim",
                "abstained",
                "intact_evidence",
            )
        },
        source_counts=dict(Counter(r["source_code"] for r in rows)),
        latency_ms=latency([r["ms"] for r in rows]),
    )
    save()
    print(
        json.dumps(
            {
                "quality": report["quality"],
                "audit": audit,
                "latency_ms": report["latency_ms"],
            }
        )
    )
    require(
        not (
            audit["dependencies"]
            or audit["recommendation_links"]
            or audit["provider_invocations"]
            or audit["tools"].get("request_allocation")
        ),
        "Unexpected live mutation or invocation",
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run", action="store_true", required=True)
    cli.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/rag-status-20261123/v2-live-compose-b2.json",
    )
    run(cli.parse_args().output)
