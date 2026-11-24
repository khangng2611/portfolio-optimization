"""Frozen synthetic explanation eval; never calls a provider in offline mode."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from portfolio_contracts import canonical_hash
from portfolio_contracts.explanation import (
    OptimizationExplanationEvidence,
    RecommendationEvidence,
)
from chat_service.explanation import (
    build_claims,
    default_ids,
    render_claims,
    validate_plan,
    detail_requested,
)
from chat_service.provider import render

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests/fixtures/knowledge/eval-allocation-explanation-vi-v1.jsonl"
CONCISE_CASES = CASES.with_name("eval-allocation-explanation-vi-v2.jsonl")
FACTS = ROOT / "tests/fixtures/knowledge/allocation-explanation-facts-v1.json"


def frozen(path):
    raw = path.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest()
        != path.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError("Frozen fixture changed; create a new version")
    return raw


def evaluate(cases=CASES):
    cases = Path(cases)
    dataset = [json.loads(row) for row in frozen(cases).splitlines()]
    production_rendering = cases.name == CONCISE_CASES.name
    base = json.loads(frozen(FACTS))
    if (
        len(dataset) < 24
        or len({row["id"] for row in dataset}) != len(dataset)
        or not base["synthetic"]
    ):
        raise ValueError("Invalid synthetic evaluation dataset")
    rows = []
    for case in dataset:
        facts = deepcopy(base["facts"])
        values = deepcopy(base["quant"])
        variant = case.get("variant", "")
        if "positive" in variant:
            for view in values["views"]:
                if view["source_kind"] == "ML":
                    view["raw_mean_return"] = abs(view["raw_mean_return"])
                    if view["applied_q_daily"] is not None:
                        view["applied_q_daily"] = abs(view["applied_q_daily"])
        if variant.startswith("partial"):
            values["status"] = "PARTIAL"
        quant = OptimizationExplanationEvidence(**values).seal()
        evidence = RecommendationEvidence(
            recommendation_id=facts["id"],
            run_id=facts["run_id"],
            facts_hash=canonical_hash(facts),
            status="PARTIAL" if case["category"] == "legacy" else values["status"],
            quant=None if case["category"] == "legacy" else quant,
            limitations=["NOT_RETAINED"] if case["category"] == "legacy" else [],
        ).seal()
        rejected, text, ids, references = False, "", [], []
        baseline = render(facts)
        concise = production_rendering and not detail_requested(case["question"])
        if case["category"] == "hash":
            facts["weights"][0] = "0.9"
        elif case["category"] == "resource":
            evidence["recommendation_id"] = "another-recommendation"
            evidence["evidence_hash"] = canonical_hash(
                {k: v for k, v in evidence.items() if k != "evidence_hash"}
            )
        try:
            claims = build_claims(facts, evidence)
            ids = default_ids(claims, case["question"])
            if case["category"] == "claim_injection":
                validate_plan(
                    dict(
                        facts_hash=canonical_hash(facts),
                        evidence_hash=evidence["evidence_hash"],
                        selected_claim_ids=["buy_now_99_percent"],
                    ),
                    facts,
                    evidence,
                    claims,
                )
            text = render_claims(claims, ids, concise=concise)
            references = [ref for c in claims if c.id in ids for ref in c.refs]
        except ValueError:
            rejected = True
        wanted_reject = case["topic"] == "reject"
        relevance = not rejected and all(
            s.casefold() in text.casefold() for s in case["contains"]
        )
        relevance = relevance and not any(
            s.casefold() in text.casefold() for s in case.get("excludes", [])
        )
        brief = len(text.split()) <= case.get("max_words", float("inf"))
        passed = rejected if wanted_reject else relevance and brief
        if case["category"] == "injection":
            passed = passed and "99%" not in text and "mua ngay" not in text.casefold()
        rows.append(
            dict(
                id=case["id"],
                category=case["category"],
                passed=passed,
                rejected=rejected,
                baseline_relevance=None
                if wanted_reject
                else all(s.casefold() in baseline.casefold() for s in case["contains"]),
                grounded_relevance=None if wanted_reject else relevance,
                selected_claim_ids=ids,
                references=references,
                text=text,
                concise_case=case.get("concise", False),
                concise_rendering=concise,
                word_budget_passed=brief,
                words=len(text.split()),
                before_words=len(case.get("before_text", "").split()),
            )
        )

    def score(key):
        values = [r[key] for r in rows if r[key] is not None]
        return dict(
            passed=sum(values), total=len(values), rate=sum(values) / len(values)
        )

    concise_rows = [row for row in rows if row["concise_case"]]
    return dict(
        dataset=Path(cases).name,
        dataset_hash=hashlib.sha256(Path(cases).read_bytes()).hexdigest(),
        synthetic=True,
        total=len(rows),
        passed=sum(r["passed"] for r in rows),
        baseline_relevance=score("baseline_relevance"),
        grounded_relevance=score("grounded_relevance"),
        rubric="Frozen topic/phrase assertions plus hash/ID/claim rejection; human relevance review remains separate.",
        provider_calls=0,
        usage_usd="0",
        retrieval_hit_at_5="N/A",
        live_integration="NOT RUN",
        rows=rows,
        concision=dict(
            total=len(concise_rows),
            passed=sum(row["passed"] for row in concise_rows),
            before_words=sum(row["before_words"] for row in concise_rows),
            after_words=sum(row["words"] for row in concise_rows),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["offline", "live", "verify"], default="offline"
    )
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output/allocation-explanation/eval-offline.json",
    )
    parser.add_argument("--approval-id")
    parser.add_argument("--max-cost-usd")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.mode == "offline":
        report = evaluate(args.cases)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False
            )
        )
        raise SystemExit(0 if report["passed"] == report["total"] else 1)
    from smoke_allocation_explanation import run, verify_receipt, preflight

    if args.receipt is None:
        parser.error("live/verify requires --receipt")
    if args.mode == "verify":
        print(json.dumps(verify_receipt(args.receipt)))
    elif args.dry_run:
        print(json.dumps(preflight("openai", args.approval_id, args.max_cost_usd)))
    else:
        # Live evidence comes from real API resources, never the synthetic fixture.
        print(
            json.dumps(run(args.receipt, "openai", args.approval_id, args.max_cost_usd))
        )


if __name__ == "__main__":
    main()
