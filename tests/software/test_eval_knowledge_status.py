"""Frozen split integrity and metrics used for release decisions."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "scripts"))
from eval_knowledge_status import latency, load_split, rank_claim  # noqa: E402


def test_frozen_scenario_families_and_rubric():
    dev, _ = load_split("dev")
    heldout, _ = load_split("heldout")
    assert {r["family"] for r in dev}.isdisjoint(r["family"] for r in heldout)

    # The same short follow-up changes meaning when the user switches portfolios.
    def scenario(row):
        return tuple(row["messages"]), row.get("switch")

    assert {scenario(r) for r in dev}.isdisjoint(scenario(r) for r in heldout)
    assert sum(len(r["messages"]) > 1 for r in dev + heldout) >= 20
    assert all(
        r["allowed_statement"] and r["allowed_action"] and r["must_refuse"]
        for r in dev + heldout
    )
    topics = [r for r in heldout if r["source"] == "knowledge"]
    assert sum(bool(r["claims"]) for r in topics) >= 10
    assert sum(not r["claims"] for r in topics) >= 5


def test_metric_denominators_and_rank_cutoff():
    passages = [{"claim_id": str(i)} for i in range(6)]
    assert rank_claim(passages, ["1", "4"]) == 2
    assert rank_claim(passages, ["5"]) == 0
    assert latency([]) is None
    assert latency([1, 20]) == {"n": 2, "p50_ms": 10.5, "p95_ms": 20}


def test_compose_cohort_requires_real_preconditions():
    from eval_knowledge_compose import selected_cases

    heldout, _ = load_split("heldout")
    single = selected_cases(heldout, paused=False)
    assert len(single) == 16
    assert all(
        r["source"] == "knowledge" and len(r["messages"]) == 1 and "as_of" not in r
        for r in single
    )
    paused = selected_cases(heldout, paused=True)
    assert [r["id"] for r in paused if r not in single] == ["H02"]


def test_prospective_questions_are_separate_and_gradeable():
    previous, _ = load_split("heldout")
    development, _ = load_split("dev")
    previous.extend(development)
    for version in ("v3", "v4", "v5"):
        heldout, _ = load_split("heldout", version)
        assert len(heldout) == 40
        assert {r["family"] for r in heldout}.isdisjoint(r["family"] for r in previous)
        assert {r["messages"][-1] for r in heldout}.isdisjoint(
            r["messages"][-1] for r in previous
        )
        assert sum(bool(r["claims"]) for r in heldout) == 14
        assert sum(r["source"] == "knowledge" and not r["claims"] for r in heldout) == 5
        assert all(
            r["allowed_statement"] and r["must_refuse"] and r["allowed_action"]
            for r in heldout
        )
        previous.extend(heldout)


def test_comparison_joins_on_case_ids():
    from eval_knowledge_status import compare_conversations

    rows = [
        dict(
            id=k,
            source="knowledge",
            observed_source="knowledge",
            retrieved_claims=["a"],
            cited_claims=[],
        )
        for k in ("1", "2")
    ]
    base = dict(
        mode="conversation", dataset_sha256={"heldout": "x"}, as_of="fixed", rows=rows
    )
    changed = base | {"rows": [rows[1], rows[0] | {"cited_claims": ["a"]}]}
    diff = compare_conversations(base, changed)
    assert (
        diff[0]["after"]["cited_claims"] == ["a"]
        and diff[1]["after"]["cited_claims"] == []
    )


def test_benchmark_pairs_all_queries_and_separates_first_requests(monkeypatch):
    import benchmark_knowledge_arms as bench

    calls = []

    class Arm:
        def __init__(self, stack, url):
            self.url, self.samples = url, []

        def retrieve(self, args):
            self.samples.append(
                {
                    "ms": 2 if self.url == "new" else 1,
                    "server_ms": 0.5,
                    "phase": "warm" if self.samples else "first",
                }
            )
            calls.append((self.url, args))
            return {"corpus_id": "one", "corpus_hash": "immutable"}

    monkeypatch.setattr(bench, "LexicalAPI", Arm)
    report = bench.paired_benchmark("old", "new")
    assert report["queries_per_cycle"] == 36
    assert report["warm_p95_change_percent"] == 100
    assert report["latency"]["baseline"]["warm"]["ms"]["n"] == 429
    assert report["latency"]["candidate"]["first"]["ms"]["n"] == 3
    assert all(a[1] == b[1] and a[0] != b[0] for a, b in zip(calls[::2], calls[1::2]))
