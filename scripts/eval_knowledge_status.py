"""Frozen v2 scenario evaluation. Report codes and counters without logging questions or portfolios."""

from collections import Counter
from contextlib import ExitStack
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import time
from urllib.parse import urlsplit

import httpx
from chat_service.workflow import intent_of
from portfolio_contracts import utcnow

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/knowledge"
AS_OF = "2026-11-23T16:00:00+00:00"
SOURCES = {
    "explain": "proposal",
    "allocation": "action",
    "gold_quote": "market",
    "allocation_status": "status",
    "current_status": "status",
    "previous_status": "status",
}


def load_split(split, version="v2"):
    path = FIXTURES / f"eval-vi-{version}-{split}.jsonl"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Frozen scenario file changed")
    cases = [json.loads(line) for line in raw.splitlines()]
    if (
        len(cases) != {"dev": 20, "heldout": 40}[split]
        or len({c["id"] for c in cases}) != len(cases)
        or any(c["split"] != split for c in cases)
    ):
        raise ValueError("Invalid frozen split")
    return cases, digest


def latency(values):
    if not values:
        return None
    return {
        "n": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(sorted(values)[math.ceil(0.95 * len(values)) - 1], 3),
    }


def timing(rows):
    return {
        phase: latency([row["ms"] for row in rows if row["phase"] == phase])
        for phase in ("first", "warm")
    }


def flow_latency(rows):
    # First exposure to this flow in the process, not a cold database.
    return {
        "first": latency([r["ms"] for r in rows[:1]]),
        "warm": latency([r["ms"] for r in rows[1:]]),
    }


def counts(rows, key):
    scores = [r[key] for r in rows if r.get(key) is not None]
    return {"passed": sum(scores), "total": len(scores)}


def rank_claim(passages, claims):
    return next(
        (i for i, p in enumerate(passages[:5], 1) if p["claim_id"] in claims), 0
    )


class LexicalAPI:
    def __init__(self, stack, url):
        parts = urlsplit(url)
        if (
            parts.scheme != "http"
            or parts.hostname not in ("localhost", "127.0.0.1")
            or parts.username
            or parts.password
            or parts.path not in ("", "/")
        ):
            raise ValueError("Use a loopback Knowledge API")
        if parts.port == 8006:
            from local_auth import service_token

            token = service_token("chat-service", "knowledge:retrieve")
        else:
            # The isolated service uses its own test verifier, never a Compose token.
            token = os.environ["EVAL_KNOWLEDGE_FIXTURE_TOKEN"]
        self.client = stack.enter_context(
            httpx.Client(
                base_url=url,
                timeout=5,
                trust_env=False,
                headers={"Authorization": "Bearer " + token},
            )
        )
        self.corpus = None
        self.samples = []

    def retrieve(self, args):
        start = time.perf_counter()
        response = self.client.post("/internal/v1/knowledge/retrieve", json=args)
        ms = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        data = response.json()
        if data["mode"] != "LEXICAL" or not data["corpus_hash"]:
            raise RuntimeError("A serving lexical corpus is required")
        corpus = {
            k: data[k]
            for k in (
                "corpus_hash",
                "corpus_version",
                "retrieval_version",
                "index_version",
            )
        }
        if self.corpus and self.corpus != corpus:
            raise RuntimeError("Corpus changed during evaluation")
        self.corpus = corpus
        timing_header = response.headers.get("Server-Timing", "").removeprefix(
            "retrieval;dur="
        )
        self.samples.append(
            {
                "ms": ms,
                "server_ms": float(timing_header) if timing_header else None,
                "phase": "warm" if self.samples else "first",
            }
        )
        return data


def source_hash(src=None):
    src = src or Path(inspect.getsourcefile(intent_of)).parent
    digest = hashlib.sha256()
    for path in sorted(src.glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def evaluate_scenarios(mode, split, url, run, version="v2", review_output=None):
    groups = (
        (["heldout"] if version in ("v3", "v4", "v5", "v6") else ["dev", "heldout"])
        if split == "all"
        else [split]
    )
    packet = [] if review_output is not None else None
    cases, digests, rows = [], {}, []
    for group in groups:
        scenarios, digests[group] = load_split(group, version)
        cases.extend(scenarios)
    with ExitStack() as stack:
        api = LexicalAPI(stack, url) if mode != "offline" else None
        if mode == "conversation":
            from eval_knowledge_turn import dialogue
        for case in cases:
            text = case["messages"][-1]
            started = time.perf_counter()
            intent = intent_of({"content": text})
            row = dict(
                id=case["id"], split=case["split"], source=case["source"], intent=intent
            )
            if mode == "conversation":
                row.update(dialogue(case, api, packet))
            elif mode == "lexical":
                if case["source"] != "knowledge":
                    continue
                result = api.retrieve(
                    {"query": text, "as_of": case.get("as_of", AS_OF)}
                )
                row["retrieved_claims"] = [p["claim_id"] for p in result["passages"]]
                rank = rank_claim(result["passages"], case["claims"])
                if case["claims"]:
                    row.update(
                        rank=rank,
                        hit=bool(rank),
                        route_and_hit=bool(rank and intent == "knowledge"),
                    )
                else:
                    row["empty_retrieval"] = not result["passages"]
                row.update(api.samples[-1])
            else:
                source = SOURCES.get(intent, intent)
                row.update(
                    observed_source=source, source_match=source == case["source"]
                )
            row.setdefault("ms", (time.perf_counter() - started) * 1000)
            row.setdefault("phase", "warm" if rows else "first")
            rows.append(row)
    metrics = [
        "source_match",
        "status_match",
        "status_authority",
        "status_read_only",
        "hit",
        "route_and_hit",
        "empty_retrieval",
        "abstained",
        "pinned",
        "citation_hit",
        "answer_quotes_claim",
        "intact_evidence",
        "safe_actions",
    ]

    def measure(selected):
        result = {
            m: counts(selected, m) for m in metrics if any(m in r for r in selected)
        }
        ranks = [r["rank"] for r in selected if "rank" in r]
        if ranks:
            result["mrr_at_5"] = sum(1 / k for k in ranks if k) / len(ranks)
        return result

    if review_output is not None:
        review_output.parent.mkdir(parents=True, exist_ok=True)
        with review_output.open("x", encoding="utf-8") as f:
            review_output.chmod(0o600)
            json.dump(
                {
                    "synthetic_fixtures_only": True,
                    "dataset_sha256": digests,
                    "chat_source_sha256": source_hash(),
                    "corpus": api.corpus,
                    "cases": packet,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    return {
        "version": version,
        "run": run,
        "at": utcnow().isoformat(),
        "dataset_sha256": digests,
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "chat_source_sha256": source_hash(),
        "mode": mode,
        "endpoint": url if api else None,
        "as_of": AS_OF,
        "corpus": api.corpus if api else None,
        "retrieval": "HTTP lexical, no embeddings, server top 5" if api else None,
        "provider_mode": "off",
        "provider_calls": sum(r.get("provider_calls", 0) for r in rows),
        "estimated_usd": 0,
        "breakdown": {g: measure([r for r in rows if r["split"] == g]) for g in groups},
        "by_source": {
            g: {
                s: measure([r for r in rows if r["source"] == s and r["split"] == g])
                for s in sorted({r["source"] for r in rows if r["split"] == g})
            }
            for g in groups
        },
        "latency": timing(rows),
        "latency_by_source": {
            s: flow_latency([r for r in rows if r["source"] == s])
            for s in sorted({r["source"] for r in rows})
        },
        "lexical_http_latency": timing(api.samples) if api else None,
        "lexical_server_latency": timing(
            [
                dict(s, ms=s["server_ms"])
                for s in api.samples
                if s["server_ms"] is not None
            ]
        )
        if api
        else None,
        "tool_counts": dict(
            sum((Counter(r.get("tools", {})) for r in rows), Counter())
        ),
        "latency_scope": "First measured request in fresh client/process; per-flow first = first occurrence of that source. Server cache not reset. Warm = subsequent observations.",
        "human_review": "PENDING",
        "rows": rows,
    }


def compare_conversations(before, after):
    """Compare the same cases without emitting question, answer or portfolio data."""
    if (
        before["mode"] != "conversation"
        or after["mode"] != "conversation"
        or before["dataset_sha256"] != after["dataset_sha256"]
        or before["as_of"] != after["as_of"]
    ):
        raise ValueError("Use two conversation reports with identical cases and cutoff")
    rows = {}
    for key, report in (("before", before), ("after", after)):
        for row in report["rows"]:
            out = rows.setdefault(
                row["id"], {"id": row["id"], "expected_source": row["source"]}
            )
            if key in out or out["expected_source"] != row["source"]:
                raise ValueError("Duplicate case or changed label")
            out[key] = {
                k: row.get(k)
                for k in (
                    "observed_source",
                    "retrieved_claims",
                    "cited_claims",
                    "source_match",
                    "route_and_hit",
                    "answer_quotes_claim",
                    "abstained",
                    "status_match",
                    "safe_actions",
                )
            }
    if not all("before" in row and "after" in row for row in rows.values()):
        raise ValueError("Reports must cover the same cases")
    return list(rows.values())


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(
        description="Compare per-case source, retrieved claims and cited claims."
    )
    for arg in ("before", "after", "output"):
        cli.add_argument(arg, type=Path)
    args = cli.parse_args()
    diff = compare_conversations(
        json.loads(args.before.read_text()), json.loads(args.after.read_text())
    )
    args.output.write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n")
