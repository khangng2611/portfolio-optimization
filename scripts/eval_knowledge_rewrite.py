"""Paired Vietnamese fixture-adapter eval on a dedicated local Chat/Knowledge stack."""

import argparse
from functools import partial
import hashlib
import json
from pathlib import Path
from select import select
import subprocess
from uuid import uuid4

from portfolio_contracts import canonical_hash
from local_auth import login
from smoke_chat import CHAT, get, request, require

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/fixtures/knowledge/eval-vi-rewrite-v1.jsonl"
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    str(ROOT / "infra/local/.generated/.env"),
    "-f",
    str(ROOT / "infra/local/compose.yaml"),
    "-f",
    str(ROOT / "infra/local/compose.tracing.yaml"),
]

# Only the text rewriter is substituted. The actual worker, grants, HTTP tools,
# owner databases and persisted Chat message are exercised in both arms.
TICK = """
import json
import os
import sys
from sqlalchemy import select
from chat_service.models import Job
from chat_service.queue import TERMINAL
from chat_service.runtime import sessions_from_env
from chat_service.tools import Tools
from chat_service.workflow import Worker

assert not os.environ.get('OPENAI_API_KEY') and not os.environ.get('KNOWLEDGE_PAID_APPROVAL')
sessions = sessions_from_env()
def tick(job_id, adapter_input):
    with sessions() as db:
        pending = db.scalars(select(Job.id).where(Job.status.not_in(TERMINAL))).all()
    assert pending == ([job_id] if job_id else []), 'Dedicated eval stack must have no other pending jobs'
    if job_id is None:
        return {}

    calls = []
    def adapter(question, topic):
        calls.append(True)
        expected_topic = adapter_input.get('topic_prefix')
        if question == adapter_input['question'] and (
            (topic is None and expected_topic is None)
            or (expected_topic and topic and topic.startswith(expected_topic))
        ):
            return adapter_input.get('rewrite')
        return None

    assert Worker(sessions, Tools(), query_rewriter=adapter if adapter_input else None).tick()
    with sessions() as db:
        job = db.get(Job, job_id)
        assert job.status == 'SUCCEEDED'
        passages = (job.knowledge_checkpoint or {}).get('passages', [])
        return {'adapter_calls': len(calls), 'candidates': {
            p['chunk_id']: p['claim_id'] for p in passages
        }}

for line in sys.stdin:
    print(json.dumps(tick(*json.loads(line))), flush=True)
"""


def tick_process(process, job_id=None, adapter_input=None):
    process.stdin.write(json.dumps([job_id, adapter_input]) + "\n")
    process.stdin.flush()
    ready, _, _ = select([process.stdout], [], [], 40)
    require(ready, "Local worker probe timed out")
    line = process.stdout.readline()
    require(
        line,
        "Local worker probe failed; require an idle zero-provider stack and current Chat image",
    )
    return json.loads(line)


def published(token, conversation_id, job_id):
    job = get(CHAT, f"/api/v1/jobs/chat/{job_id}", token)
    require(
        job["status"] == "SUCCEEDED" and not job["provider_usage"],
        "Expected successful zero-provider turn",
    )
    messages = get(CHAT, f"/api/v1/conversations/{conversation_id}/messages", token)
    message = next(m for m in messages if m["id"] == job["result_message_id"])
    card = message["structured"]
    require(card["type"] == "knowledge", "Expected Knowledge card")
    evidence = card["knowledge"]
    require(
        evidence["mode"] == "LEXICAL"
        and evidence["evidence_hash"]
        == canonical_hash(
            {key: value for key, value in evidence.items() if key != "evidence_hash"}
        ),
        "Evidence integrity failed",
    )
    return message["id"], evidence


def submit(tick, token, conversation_id, question, adapter_input=None):
    key = str(uuid4())
    status, response = request(
        "POST",
        CHAT + f"/api/v1/conversations/{conversation_id}/messages",
        token=token,
        body={"content": question, "intent": "knowledge", "client_message_id": key},
        headers={"Idempotency-Key": key},
    )
    require(status == 202, "Chat rejected eval turn")
    job_id = response["job_id"]
    probe = tick(job_id, adapter_input)
    message_id, evidence = published(token, conversation_id, job_id)
    return (
        probe,
        evidence,
        {
            "conversation_id": conversation_id,
            "job_id": job_id,
            "message_id": message_id,
            "evidence_hash": evidence["evidence_hash"],
        },
    )


def measure(tick, token, cases, adapter):
    rows = []
    for case in cases:
        code, conv = request(
            "POST",
            CHAT + "/api/v1/conversations",
            token=token,
            body={"title": "Vietnamese rewrite eval " + case["id"]},
        )
        require(code == 201, "Could not create eval conversation")
        if case.get("previous"):
            _, seed, _ = submit(tick, token, conv["id"], case["previous"])
            require(seed["citations"], "Follow-up seed has no cited topic")
        adapter_input = (
            {k: case[k] for k in ("question", "rewrite", "topic_prefix") if k in case}
            if adapter
            else None
        )
        probe, evidence, receipt = submit(
            tick, token, conv["id"], case["question"], adapter_input
        )
        retrieved = [
            probe["candidates"][cid] for cid in evidence["retrieved_chunk_ids"]
        ]
        require(
            evidence["corpus_id"]
            and all(
                probe["candidates"].get(p["chunk_id"]) == p["claim_id"]
                and p["chunk_id"] in evidence["retrieved_chunk_ids"]
                for p in evidence["citations"]
            ),
            "Citation is outside the pinned retrieval candidates",
        )
        cited = [p["claim_id"] for p in evidence["citations"]]
        expected = set(case["allowed_claim_ids"])
        rows.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "hit_at_5": bool(expected.intersection(retrieved))
                if expected
                else None,
                "cited_hit": bool(expected.intersection(cited)) if expected else None,
                "abstained": not retrieved and not cited if not expected else None,
                "retrieved": retrieved,
                "cited": cited,
                "adapter_calls": probe["adapter_calls"],
                "rewrite_used": "rewritten_query_hash" in evidence,
                "corpus": [
                    evidence["corpus_id"],
                    evidence["corpus_hash"],
                    evidence["retrieval_version"],
                ],
                "receipt": receipt,
            }
        )
    return rows


def scores(rows):
    return {
        metric: {
            "passed": sum(row[metric] is True for row in rows),
            "total": sum(row[metric] is not None for row in rows),
        }
        for metric in ("hit_at_5", "cited_hit", "abstained")
    }


def evaluate(authenticate):
    raw = CASES.read_bytes()
    cases = [json.loads(line) for line in raw.splitlines()]
    require(
        len(cases) == 10 and len({case["id"] for case in cases}) == 10,
        "Invalid eval fixture",
    )
    workers = subprocess.check_output(
        COMPOSE + ["ps", "-q", "--status", "running", "chat-worker"], text=True
    ).splitlines()
    require(len(workers) == 1, "Expected exactly one running local Chat worker")
    worker_id = workers[0]
    with subprocess.Popen(
        COMPOSE + ["exec", "-T", "chat-api", "python", "-u", "-c", TICK],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    ) as process:
        tick = partial(tick_process, process)
        try:
            tick()
            try:
                subprocess.run(["docker", "stop", worker_id], check=True, timeout=40)
                arms = {
                    "lexical": measure(tick, authenticate(), cases, False),
                    "fixture_rewrite": measure(tick, authenticate(), cases, True),
                }
            finally:
                subprocess.run(["docker", "start", worker_id], check=True, timeout=40)
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    require(
        len({tuple(r["corpus"]) for rows in arms.values() for r in rows}) == 1,
        "Corpus or retrieval version changed during comparison",
    )
    return {
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "adapter": "fixture-provided query strings; model quality not measured",
        "provider_usage": {"calls": 0},
        "arms": {
            name: {"scores": scores(rows), "rows": rows} for name, rows in arms.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/knowledge-rag/eval-rewrite-vi.json",
    )
    parser.add_argument("--verify-report", action="store_true")
    args = parser.parse_args()

    def authenticate():
        return login("alice")

    if args.verify_report:
        token = authenticate()
        report = json.loads(args.output.read_text())
        count = 0
        for arm in report["arms"].values():
            for row in arm["rows"]:
                receipt = row["receipt"]
                mid, ev = published(
                    token, receipt["conversation_id"], receipt["job_id"]
                )
                require(
                    mid == receipt["message_id"]
                    and ev["evidence_hash"] == receipt["evidence_hash"],
                    "Saved Chat message or evidence changed",
                )
                count += 1
        print(f"PASS: {count} saved Chat message/evidence receipts; provider calls=0")
        return
    report = evaluate(authenticate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    args.output.chmod(0o600)
    print(
        json.dumps(
            {name: data["scores"] for name, data in report["arms"].items()}, indent=2
        )
    )


if __name__ == "__main__":
    main()
