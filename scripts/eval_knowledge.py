"""Frozen Vietnamese eval. Offline intent and real lexical retrieval are distinct reports."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
from chat_service.workflow import intent_of
from portfolio_contracts import utcnow

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests/fixtures/knowledge/eval-vi-v1.jsonl"


def load_cases():
    raw = DATA.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != DATA.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("Frozen eval changed; require a new dataset version")
    cases = [json.loads(line) for line in raw.decode().splitlines()]
    if len(cases) != 60 or len({c["id"] for c in cases}) != 60:
        raise ValueError("Invalid eval fixture")
    return cases


def summarize(rows):
    count = sum(r["passed"] for r in rows)
    return {
        "passed": count,
        "total": len(rows),
        "rate": count / len(rows) if rows else None,
    }


def evaluate(mode="offline", split="all"):
    cases = [c for c in load_cases() if split == "all" or c["split"] == split]
    rows = []
    latencies = []
    server_latencies = []
    token = None
    if mode == "lexical":
        try:
            from smoke_knowledge import tokens, API
            from smoke_chat import require
        except ImportError:
            from scripts.smoke_knowledge import tokens, API
            from scripts.smoke_chat import require
        _, token = tokens()
    for case in cases:
        predicted = intent_of({"content": case["messages"][-1]})
        row = {
            "id": case["id"],
            "split": case["split"],
            "category": case["category"],
            "intent": {
                "passed": predicted == case["expected_intent"],
                "predicted": predicted,
            },
            "retrieval": None,
            "abstention": None,
            "skip": None,
        }
        if mode == "lexical" and (
            case["category"] in ("answerable", "no_evidence")
            or case["requires"] == "historical_cutoff"
        ):
            body = {
                "query": case["messages"][-1],
                "as_of": "2000-01-01T00:00:00+00:00"
                if case["requires"] == "historical_cutoff"
                else utcnow().isoformat(),
            }
            import httpx

            start = time.perf_counter()
            response = httpx.post(
                API + "/internal/v1/knowledge/retrieve",
                headers={"Authorization": "Bearer " + token},
                json=body,
                timeout=5,
                follow_redirects=False,
            )
            status = response.status_code
            data = response.json()
            latencies.append((time.perf_counter() - start) * 1000)
            timing = response.headers.get("Server-Timing", "")
            if timing.startswith("retrieval;dur="):
                server_latencies.append(float(timing.split("=", 1)[1]))
            require(
                status == 200 and data["mode"] == "LEXICAL",
                "Lexical eval requires real lexical API",
            )
            ids = {p["claim_id"] for p in data["passages"]}
            if case["category"] == "answerable":
                row["retrieval"] = {
                    "passed": bool(ids & set(case["allowed_claim_ids"])),
                    "retrieved_claim_ids": sorted(ids),
                }
            if case["expected_abstention"]:
                row["abstention"] = {"passed": not ids}
        elif mode == "lexical":
            row["skip"] = (
                case["requires"]
                or "Requires conversation/security harness; retrieval alone cannot certify it"
            )
        rows.append(row)
    breakdown = {}
    for group in ("dev", "heldout"):
        selected = [r for r in rows if r["split"] == group]
        breakdown[group] = {
            metric: summarize([r[metric] for r in selected if r[metric] is not None])
            for metric in ("intent", "retrieval", "abstention")
        }
    return {
        "mode": mode,
        "dataset_sha256": DATA.with_suffix(".sha256").read_text().strip(),
        "at": utcnow().isoformat(),
        "breakdown": breakdown,
        "categories": {
            k: sum(r["category"] == k for r in rows)
            for k in sorted({r["category"] for r in rows})
        },
        "latency_http_ms": {
            "p50": statistics.median(latencies),
            "p95": sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)],
        }
        if latencies
        else None,
        "latency_server_ms": {
            "samples": len(server_latencies),
            "p50": statistics.median(server_latencies),
            "p95": sorted(server_latencies)[
                max(0, int(len(server_latencies) * 0.95) - 1)
            ],
        }
        if server_latencies
        else None,
        "provider_usage": {
            "ingestion_calls": 0,
            "query_embedding_calls": 0,
            "dialogue_calls": 0,
            "actual_tokens": 0,
            "estimated_usd": "0",
        },
        "release_gate": "NOT_ACCEPTED: conversation safety, human support review and paid hybrid evaluated separately",
        "rows": rows,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--mode", choices=["offline", "lexical", "conversation"], default="offline"
    )
    p.add_argument("--version", choices=["v1", "v2", "v3", "v4", "v5", "v6"], default="v1")
    p.add_argument("--run", type=int, default=1)
    p.add_argument("--knowledge-url", default="http://localhost:8006")
    p.add_argument("--split", choices=["all", "dev", "heldout"], default="all")
    p.add_argument(
        "--output", type=Path, default=ROOT / "output/knowledge-rag/eval.json"
    )
    p.add_argument(
        "--review-output",
        type=Path,
        help="Separate private synthetic conversation packet",
    )
    a = p.parse_args()
    if a.review_output and (
        a.mode != "conversation" or a.review_output.resolve() == a.output.resolve()
    ):
        p.error("Review packets require conversation mode and a separate output file")
    if a.version in ("v3", "v4", "v5", "v6") and a.split == "dev":
        p.error("Prospective suites contain the heldout split only")
    if a.version in ("v2", "v3", "v4", "v5", "v6"):
        from eval_knowledge_status import evaluate_scenarios

        report = evaluate_scenarios(
            a.mode, a.split, a.knowledge_url, a.run, a.version, a.review_output
        )
    elif a.mode == "conversation":
        p.error("conversation requires --version v2 through v6")
    else:
        report = evaluate(a.mode, a.split)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("rows", "categories", "by_source", "latency_by_source")
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
