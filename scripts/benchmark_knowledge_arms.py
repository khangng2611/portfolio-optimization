"""Paired HTTP timings against two rankers sharing the exact same active corpus and chunk IDs."""

import argparse
from contextlib import ExitStack
import json
from pathlib import Path

from eval_knowledge_status import AS_OF, LexicalAPI, latency, load_split


def paired_benchmark(baseline_url, candidate_url, suites=("v2", "v3")):
    cases = []
    digests = {}
    for version in suites:
        scenarios, digests[version] = load_split("heldout", version)
        cases.extend(r for r in scenarios if r["source"] == "knowledge")
    samples = []
    corpus = {}
    for wave in range(3):
        with ExitStack() as stack:
            clients = {
                "baseline": LexicalAPI(stack, baseline_url),
                "candidate": LexicalAPI(stack, candidate_url),
            }
            for cycle in range(4):
                for i, case in enumerate(cases):
                    order = list(clients)
                    if (wave + cycle + i) % 2:
                        order.reverse()
                    args = {
                        "query": case["messages"][-1],
                        "as_of": case.get("as_of", AS_OF),
                    }
                    for arm in order:
                        client = clients[arm]
                        data = client.retrieve(args)
                        identity = data["corpus_id"], data["corpus_hash"]
                        if (
                            corpus.setdefault(arm, identity) != identity
                            or len(set(corpus.values())) != 1
                        ):
                            raise ValueError(
                                "Matched benchmark requires one identical active corpus ID/hash"
                            )
                        samples.append(
                            dict(
                                id=case["id"],
                                wave=wave + 1,
                                cycle=cycle + 1,
                                arm=arm,
                                **client.samples[-1],
                            )
                        )
    report = {}
    for arm in ("baseline", "candidate"):
        rows = [s for s in samples if s["arm"] == arm]

        def summary(selected):
            return {
                key: latency([s[key] for s in selected if s[key] is not None])
                for key in ("ms", "server_ms")
            }

        report[arm] = {
            phase: summary([s for s in rows if s["phase"] == phase])
            for phase in ("first", "warm")
        }
        report[arm]["warm_by_wave"] = [
            summary([s for s in rows if s["phase"] == "warm" and s["wave"] == w])
            for w in (1, 2, 3)
        ]
    base = report["baseline"]["warm"]["ms"]["p95_ms"]
    candidate = report["candidate"]["warm"]["ms"]["p95_ms"]
    return {
        "as_of": AS_OF,
        "dataset_sha256": digests,
        "corpus": corpus["baseline"],
        "queries_per_cycle": len(cases),
        "cycles_per_wave": 4,
        "waves": 3,
        "transport": "HTTP loopback; alternating order on each matched question",
        "baseline_url": baseline_url,
        "candidate_url": candidate_url,
        "latency": report,
        "warm_p95_change_percent": 100 * (candidate / base - 1),
        "samples": samples,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--baseline-url", required=True)
    cli.add_argument("--candidate-url", required=True)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument(
        "--suites", nargs="+", choices=["v2", "v3", "v4", "v5", "v6"], default=["v2", "v3"]
    )
    args = cli.parse_args()
    report = paired_benchmark(args.baseline_url, args.candidate_url, args.suites)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}))
