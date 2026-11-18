import importlib.util
from pathlib import Path
import pytest


def runner():
    path = Path(__file__).resolve().parents[2] / "scripts/accept_knowledge_paid.py"
    assert path.exists()
    spec = importlib.util.spec_from_file_location("paid_acceptance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paid_preflight_is_offline_zero_by_default_and_caps_requests():
    report = runner().dry_run("0")
    assert report["allowed_to_execute"] is False
    assert (
        report["embedding_request_cap"] == 100 and report["dialogue_request_cap"] == 20
    )
    assert report["provider_calls"] == 0
    assert runner().dry_run("1")["maximum_reserved_usd"] <= 1
    for value in ("NaN", "-1", "2"):
        with pytest.raises(ValueError):
            runner().dry_run(value)


def test_usage_keeps_uncertain_reservations_separate():
    path = Path(__file__).resolve().parents[2] / "scripts/knowledge_usage.py"
    spec = importlib.util.spec_from_file_location("knowledge_usage", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = module.summarize(
        [
            {"purpose": "query_embedding", "reserved_usd": "0.00016", "details": None},
            {
                "purpose": "query_embedding",
                "reserved_usd": "0.00016",
                "details": {"input_tokens": 20, "estimated_cost_usd": "0.0000004"},
            },
        ]
    )
    assert out["query_embedding"] == {
        "reservations": 2,
        "uncertain_reservations": 1,
        "input_tokens": 20,
        "output_tokens": 0,
        "reserved_usd": "0.00032",
        "estimated_usd": "4E-7",
    }


def test_paid_case_acceptance_rejects_transport_only_and_wrong_answers():
    m = runner()
    case = {
        "id": "A01",
        "expected_intent": "knowledge",
        "expected_abstention": False,
        "allowed_claim_ids": ["ew-definition"],
    }
    corpus = {"id": "corpus", "hash": "a" * 64, "chunks": 24, "embedded_chunks": 24}
    from portfolio_contracts import canonical_hash

    evidence = {
        "mode": "HYBRID",
        "status": "VERIFIED_REFERENCES",
        "corpus_id": "corpus",
        "corpus_hash": "a" * 64,
        "citations": [{"claim_id": "ew-definition", "chunk_id": "chunk"}],
        "retrieved_chunk_ids": ["chunk"],
        "selected_chunk_ids": ["chunk"],
        "selection_reason": "VALID_REFERENCES",
    }
    evidence["evidence_hash"] = canonical_hash(evidence)
    message = {"structured": {"type": "knowledge", "knowledge": evidence}}
    job = {
        "recommendation_id": None,
        "provider_usage": [
            {"purpose": "query_embedding", "reason": "VERIFIED", "input_tokens": 20},
            {
                "purpose": "explanation",
                "reason": "VERIFIED",
                "input_tokens": 20,
                "output_tokens": 10,
            },
        ],
    }
    assert m.assess_case(case, message, job, corpus)["passed"]
    assert not m.assess_case(
        case, message, job | {"provider_usage": job["provider_usage"][:1]}, corpus
    )["passed"]
    missing = dict(evidence, status="MISSING", citations=[], selected_chunk_ids=[])
    missing["evidence_hash"] = canonical_hash(
        {k: v for k, v in missing.items() if k != "evidence_hash"}
    )
    assert not m.assess_case(
        case, {"structured": {"type": "knowledge", "knowledge": missing}}, job, corpus
    )["passed"]
    assert not m.assess_case(
        case | {"expected_abstention": True}, message, job, corpus
    )["passed"]
    assert not m.embedding_corpus_ready(corpus | {"embedded_chunks": 0})


def test_paid_partial_run_checkpoints_keys_and_never_replaces_uncertain_work(tmp_path):
    m = runner()
    cases = [{"id": "A01", "messages": ["EW là gì?"]}]
    corpus = {"id": "corpus", "hash": "a" * 64, "chunks": 24, "embedded_chunks": 24}
    planned = m.plan_run(None, "new-approval", "0.01", cases, corpus)
    original = planned["cases"]["A01"]["client_message_id"]
    planned["conversation_state"] = "CREATING"
    planned["cases"]["A01"]["state"] = "POSTING"
    path = tmp_path / "receipt.json"
    m.save_receipt(path, planned)
    import json

    resumed = m.plan_run(
        json.loads(path.read_text()), "new-approval", "0.01", cases, corpus
    )
    assert resumed["cases"]["A01"]["client_message_id"] == original
    assert resumed["conversation_state"] == "CREATING"
    with pytest.raises(ValueError):
        m.plan_run(resumed, "different-approval", "0.01", cases, corpus)


def test_paid_driver_replays_same_key_after_lost_post_and_verify_is_read_only(
    tmp_path, monkeypatch
):
    """Injected unit owner transport only; this is not provider/browser evidence."""
    import sys
    import json
    from types import SimpleNamespace
    from portfolio_contracts import canonical_hash

    m = runner()
    monkeypatch.setattr(m, "worker_budget_preflight", lambda *a: None)
    monkeypatch.setenv("KNOWLEDGE_PAID_APPROVAL", "new-test-approval")
    monkeypatch.setenv("KNOWLEDGE_BUDGET_USD", "0.01")
    monkeypatch.setenv("KNOWLEDGE_PRICE_REVIEWED", "2026-11-07")
    corpus = {
        "id": "corpus",
        "hash": "a" * 64,
        "active": True,
        "chunks": 1,
        "embedded_chunks": 1,
    }
    case = {
        "id": "A01",
        "messages": ["EW là gì?"],
        "expected_intent": "knowledge",
        "expected_abstention": False,
        "allowed_claim_ids": ["ew-definition"],
    }
    data = tmp_path / "cases.jsonl"
    data.with_suffix(".sha256").write_text("f" * 64)
    evidence = {
        "mode": "HYBRID",
        "status": "VERIFIED_REFERENCES",
        "corpus_id": "corpus",
        "corpus_hash": "a" * 64,
        "citations": [{"claim_id": "ew-definition", "chunk_id": "chunk"}],
        "retrieved_chunk_ids": ["chunk"],
        "selected_chunk_ids": ["chunk"],
    }
    evidence["evidence_hash"] = canonical_hash(evidence)
    message = {
        "id": "message",
        "structured": {"type": "knowledge", "knowledge": evidence},
    }
    job = {
        "status": "SUCCEEDED",
        "job_id": "job",
        "recommendation_id": None,
        "result_message_id": "message",
        "provider_usage": [
            {"purpose": "query_embedding", "reason": "VERIFIED", "input_tokens": 20},
            {
                "purpose": "explanation",
                "reason": "VERIFIED",
                "input_tokens": 20,
                "output_tokens": 10,
            },
        ],
    }
    sent = []
    lost = [True]

    def request(method, url, **kw):
        if method == "GET":
            return 200, [corpus]
        if url.endswith("/conversations"):
            return 201, {"id": "conversation"}
        sent.append(kw["body"]["client_message_id"])
        if lost.pop() if lost else False:
            raise RuntimeError("unit lost response")
        return 202, {"job_id": "job"}

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    fake = SimpleNamespace(
        CHAT="http://chat",
        GENERATED=tmp_path,
        credentials=lambda: ({}, "unit-secret"),
        login=lambda *a: "unit-token",
        request=request,
        get=lambda base, path, token: [message] if path.endswith("/messages") else job,
        require=require,
    )
    monkeypatch.setitem(sys.modules, "smoke_chat", fake)
    monkeypatch.setitem(
        sys.modules,
        "smoke_knowledge",
        SimpleNamespace(tokens=lambda: ("operator", "machine"), API="http://knowledge"),
    )
    monkeypatch.setitem(
        sys.modules,
        "eval_knowledge",
        SimpleNamespace(load_cases=lambda: [case], DATA=data),
    )
    path = tmp_path / "receipt.json"
    with pytest.raises(RuntimeError):
        m.execute("0.01", "new-test-approval", receipt_path=path)
    old = json.loads(path.read_text())
    assert (
        old["cases"]["A01"]["state"] == "POSTING"
        and old["conversation_id"] == "conversation"
    )
    m.execute("0.01", "new-test-approval", receipt_path=path)
    assert len(sent) == 2 and len(set(sent)) == 1
    monkeypatch.delenv("KNOWLEDGE_PAID_APPROVAL")
    monkeypatch.delenv("KNOWLEDGE_BUDGET_USD")
    m.execute("0.01", "new-test-approval", verify=True, receipt_path=path)
    assert len(sent) == 2


def test_paid_cli_dry_run_is_executable_without_budget_or_key():
    import subprocess
    import sys
    import json

    path = Path(__file__).resolve().parents[2] / "scripts/accept_knowledge_paid.py"
    r = subprocess.run(
        [sys.executable, str(path), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r.returncode == 0
    value = json.loads(r.stdout)
    assert value["budget_usd"] == "0" and value["provider_calls"] == 0
