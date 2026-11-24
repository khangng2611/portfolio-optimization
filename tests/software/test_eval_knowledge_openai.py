from pathlib import Path
import sys

from portfolio_contracts import canonical_hash

sys.path.append(str(Path(__file__).resolve().parents[2] / "scripts"))
from eval_knowledge_openai import assess, dry_run


def test_paid_plan_fits_local_and_approved_ceiling():
    from decimal import Decimal

    plan = dry_run()
    assert plan["provider_calls"] == plan["embedding_calls"] == 0
    assert (
        Decimal(plan["max_reserved_usd"])
        <= Decimal(plan["configured_budget_usd"])
        <= Decimal(plan["user_limit_usd"])
    )


def test_correct_quote_plus_unsupported_sentence_fails_paid_quality_check():
    from hashlib import sha256

    text = "Chia đều không bảo đảm lợi nhuận."
    c = {
        "claim_id": "ew-limit",
        "text": text,
        "text_hash": sha256(text.encode()).hexdigest(),
    }
    ev = {
        "mode": "LEXICAL",
        "corpus_hash": "a" * 64,
        "coverage": "SUPPORTED",
        "citations": [c],
    }
    ev["evidence_hash"] = canonical_hash(ev)
    msg = {"content": text, "structured": {"type": "knowledge", "knowledge": ev}}
    corpus = {"hash": "a" * 64}
    assert assess(msg, "ew-limit", "SUPPORTED", corpus)
    assert not assess(
        msg | {"content": text + " Mức lãi cố định là 10%."},
        "ew-limit",
        "SUPPORTED",
        corpus,
    )


def test_durable_budget_blocks_new_db_or_concurrent_second_protocol(tmp_path):
    from decimal import Decimal
    from concurrent.futures import ThreadPoolExecutor
    from eval_knowledge_openai import reserve_protocol

    reserve_protocol(tmp_path, "a", Decimal("0.0170"), tmp_path / "first")

    def competing_packet(n):
        try:
            reserve_protocol(tmp_path, "b", Decimal("0.0816"), tmp_path / f"second-{n}")
        except (ValueError, FileExistsError):
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(competing_packet, [1, 2])) == 1
    import pytest

    with pytest.raises(ValueError):
        reserve_protocol(tmp_path, "c", Decimal("0.05"), tmp_path / "third")


def test_paid_cohort_uses_real_cutoff_and_keeps_turn_order(monkeypatch):
    import eval_knowledge_openai as harness

    row = {
        "id": "ok",
        "source": "knowledge",
        "messages": ["trước", "sau"],
        "claims": ["claim-id"],
    }
    rows = [
        row,
        row | {"id": "historical", "as_of": "2000-01-01"},
        row | {"id": "portfolio", "switch": True},
    ]
    monkeypatch.setattr(harness, "load_split", lambda split, version: (rows, "frozen"))
    cases, skipped, revision = harness.cohort("heldout-v4")
    assert cases == [("ok", ["trước", "sau"], ["claim-id"], "SUPPORTED", "ok")]
    assert skipped == ["historical", "portfolio"] and revision == "frozen"


def test_third_frozen_tranche_preserves_earlier_reservations(monkeypatch, tmp_path):
    from decimal import Decimal
    import pytest
    import eval_knowledge_openai as harness

    monkeypatch.setattr(harness, "cohort", lambda _: ([{}], [], "fixture-sha"))
    plan = harness.dry_run("heldout-v5")
    assert plan["semantic_flag"] and plan["provider_calls"] == 0
    ceiling = Decimal(plan["round_reservation_ceiling_usd"])
    assert ceiling == Decimal("0.20")
    for approval, bound in [("v3", "0.0170"), ("v4", "0.0816"), ("v5", "0.0816")]:
        harness.reserve_protocol(
            tmp_path, approval, Decimal(bound), tmp_path / approval, ceiling=ceiling
        )
    with pytest.raises(ValueError):
        harness.reserve_protocol(
            tmp_path, "over", Decimal("0.02"), tmp_path / "again", ceiling=ceiling
        )


def test_ambiguous_submit_retries_same_chat_message_key(monkeypatch):
    import eval_knowledge_compose as compose
    from smoke_chat import SmokeFailure

    submitted = []

    def flaky(method, url, **kwargs):
        submitted.append(kwargs)
        if len(submitted) == 1:
            raise SmokeFailure("test lost response")
        return 202, {"status_url": "/job"}

    monkeypatch.setattr(compose, "request", flaky)
    monkeypatch.setattr(
        compose,
        "get",
        lambda base, path, token: (
            {"status": "SUCCEEDED", "result_message_id": "m"}
            if path == "/job"
            else [{"id": "m"}]
        ),
    )
    compose.real_turn("token", "conversation", None, "EW là gì?")
    assert len(submitted) == 2 and submitted[0] == submitted[1]
    assert (
        submitted[0]["headers"]["Idempotency-Key"]
        == submitted[1]["body"]["client_message_id"]
    )


def test_hybrid_protocol_has_zero_text_and_independent_owner_reservations(monkeypatch):
    from decimal import Decimal
    import eval_knowledge_openai as harness

    monkeypatch.setattr(harness, "cohort", lambda _: ([{}], [], "fixture-sha"))
    plan = harness.dry_run("hybrid-v5")
    assert plan["input_embedding_limit"] == plan["query_embedding_limit"] == 31
    assert plan["text_call_limit"] == plan["provider_calls"] == 0
    assert plan["model"] == "text-embedding-3-small"
    assert Decimal(plan["max_reserved_usd"]) == Decimal(".00992")
    assert Decimal(".1802") + Decimal(plan["max_reserved_usd"]) <= Decimal(
        plan["round_reservation_ceiling_usd"]
    )


def test_saved_proposal_paid_run_reserves_once_across_output_files(tmp_path):
    import pytest
    from eval_proposal_followup import reserve_paid_turns
    reserve_paid_turns(tmp_path, tmp_path / "one", 7)
    with pytest.raises(FileExistsError):
        reserve_paid_turns(tmp_path, tmp_path / "two", 7)


def test_recorded_source_hash_depends_on_mounted_chat_source(tmp_path):
    from eval_knowledge_status import source_hash
    module = tmp_path / "workflow.py"
    module.write_text("x = 1")
    old = source_hash(tmp_path)
    module.write_text("x = 2")
    assert old != source_hash(tmp_path)


def test_combined_dry_run_reserves_text_and_two_embedding_ledgers():
    from decimal import Decimal
    plan = dry_run("combined-v6")
    expected = Decimal("0.0017") * plan["text_call_limit"] + Decimal("0.00016") * (
        plan["input_embedding_limit"] + plan["query_embedding_limit"]
    )
    assert plan["case_count"] == 40 and plan["semantic_flag"] and plan["provider_calls"] == 0
    assert expected == Decimal(plan["max_reserved_usd"]) < Decimal(plan["configured_budget_usd"])
