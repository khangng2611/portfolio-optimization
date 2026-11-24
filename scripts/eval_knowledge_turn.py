"""Exercise normal Chat API + worker with disposable Chat state and controlled owner services."""

from collections import Counter
import os
import sys
import time
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from chat_service.api import create_app
from chat_service.models import Base, Job, Message
from chat_service.tools import ToolError
from chat_service.workflow import Worker
from portfolio_contracts import canonical_hash, utcnow
from portfolio_contracts.explanation import RecommendationEvidence
from eval_knowledge_status import AS_OF, ROOT, rank_claim

sys.path.append(str(ROOT / "tests/software"))
from test_chat import Tools, Verifier, headers  # noqa: E402
from test_chat_explanation_evidence import fixture_evidence  # noqa: E402


class ScenarioTools(Tools):
    def __init__(self, case, api):
        super().__init__()
        self.case, self.api = case, api
        self.facts, self.evidence = fixture_evidence()
        self.facts.update(
            portfolio_id=self.summary["id"], weights=["0.4", "0.4", "0.2"]
        )
        self.evidence["facts_hash"] = canonical_hash(self.facts)
        self.evidence["evidence_hash"] = canonical_hash(
            {k: v for k, v in self.evidence.items() if k != "evidence_hash"}
        )
        if case.get("missing_evidence"):
            self.evidence = RecommendationEvidence(
                recommendation_id=self.facts["id"],
                run_id=self.facts["run_id"],
                facts_hash=canonical_hash(self.facts),
                status="PARTIAL",
                limitations=["NOT_RETAINED"],
            ).seal()
        self.calls = Counter()
        self.forbidden_reads = 0
        self.retrieved = None
        self.state = "READY"

    def call(self, job, tool, args):
        self.calls[tool] += 1
        if tool == "get_allocation_status":
            if self.state == "UNAVAILABLE":
                raise httpx.ConnectError("fixture outage")
            result = {
                "status": "READY" if self.state == "READY" else "BLOCKED",
                "reason_code": self.state,
                "checked_at": utcnow().isoformat(),
                "scope": "system" if self.state == "SYSTEM_PAUSED" else "portfolio",
                "portfolio_id": job.request["portfolio_id"],
            }
            if self.state == "VFF_STALE":
                result["details"] = {
                    "asset_id": "VFF",
                    "observation_date": "2026-11-05",
                    "max_age_days": 7,
                    "age_days": 18,
                }
            return result
        if tool == "retrieve_knowledge":
            data = self.api.retrieve(args | {"as_of": self.case.get("as_of", AS_OF)})
            if not args.get("corpus_id"):
                self.retrieved = data["passages"]
            return data
        if tool in ("get_recommendation", "get_recommendation_evidence"):
            if (
                args["resource_id"] != self.facts["id"]
                or job.request["portfolio_id"] != self.facts["portfolio_id"]
                or job.owner_key
                != canonical_hash({"issuer": "issuer", "subject": "alice"})
            ):
                self.forbidden_reads += 1
                raise ToolError("NOT_FOUND", permanent=True)
            return self.facts if tool == "get_recommendation" else self.evidence
        if tool == "get_market_facts":
            return {
                "scope": "gold_quote",
                "local_date": "2026-11-23",
                "observations": [],
            }
        return super().call(job, tool, args)


def start_chat(client, owner, pid):
    result = client.post(
        "/api/v1/conversations", headers=headers(owner), json={"portfolio_id": pid}
    )
    result.raise_for_status()
    return result.json()["id"]


def turn(client, sessions, tools, cid, owner, pid, content, selected):
    key = str(uuid4())
    body = dict(client_message_id=key, content=content, portfolio_id=pid)
    if selected:
        body["recommendation_id"] = tools.facts["id"]
    r = client.post(
        f"/api/v1/conversations/{cid}/messages", json=body, headers=headers(owner, key)
    )
    r.raise_for_status()
    jid = r.json()["job_id"]
    if not Worker(sessions, tools).tick():
        raise RuntimeError("Worker did not process queued scenario")
    result = client.get(f"/api/v1/jobs/chat/{jid}", headers=headers(owner))
    result.raise_for_status()
    with sessions() as s:
        job = s.get(Job, jid)
        message = (
            s.get(Message, job.result_message_id) if job.result_message_id else None
        )
        return (
            result.json(),
            message.structured if message else {},
            message.content if message else "",
        )


def dialogue(case, api, review=None):
    # In-memory owner-service scenarios. The only external calls are read-only lexical HTTP.
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    tools, owner = ScenarioTools(case, api), "alice"
    pid = tools.summary["id"]
    env = {
        "CHAT_LLM_ENABLED": "0",
        "CHAT_QUERY_EMBEDDINGS_ENABLED": "0",
        "CHAT_CONTEXTUAL_REPLIES": "0",
        "CHAT_PROVIDER_URL": "",
    }
    app = create_app(sessions=sessions, verifier=Verifier(), tools=tools)
    with patch.dict(os.environ, env), TestClient(app) as c:
        cid = start_chat(c, owner, pid)
        history = []
        prior_checked = None
        for i, text in enumerate(case["messages"]):
            final = i == len(case["messages"]) - 1
            if final and case.get("switch"):
                pid = tools.summary["id"] = str(uuid4())
                if case["switch"] == "owner":
                    owner = "bob"
                    cid = start_chat(c, owner, pid)
            tools.state = (
                case["state"] if final else case.get("prior_state", case["state"])
            ) or "READY"
            if tools.state not in (
                "READY",
                "SYSTEM_PAUSED",
                "MODEL_REVIEW_PENDING",
                "VFF_STALE",
                "UNAVAILABLE",
            ):
                tools.state = "READY"
            os.environ["SYSTEM_HYBRID_ENABLED"] = (
                "paused" if tools.state == "SYSTEM_PAUSED" else "true"
            )
            tools.calls.clear()
            tools.retrieved = None
            started = time.perf_counter()
            job, card, reply = turn(
                c,
                sessions,
                tools,
                cid,
                owner,
                pid,
                text,
                case.get("selected" if final else "prior_selected"),
            )
            elapsed = (time.perf_counter() - started) * 1000
            if not final:
                if review is not None:
                    history.append(
                        {
                            "question": text,
                            "reply": reply,
                            "card": card.get("type"),
                            "reason_code": card.get("reason_code"),
                        }
                    )
                prior_checked = card.get("checked_at")
    engine.dispose()
    kind = card.get("type", "no_message")
    source = {
        "allocation_status": "status",
        "recommendation": "proposal",
        "input_required": "clarify",
        "confirmation": "action",
    }.get(kind, kind)
    row = dict(
        ms=elapsed,
        observed_source=source,
        source_match=source == case["source"],
        card=kind,
        job_status=job["status"],
        error=job["error"],
        tools=dict(tools.calls),
        provider_calls=len(job["provider_usage"]),
        forbidden_read_attempts=tools.forbidden_reads,
        safe_actions=not tools.allocations
        and not tools.calls["request_allocation"]
        and (kind != "confirmation" or case["allowed_action"] == "confirm"),
    )
    if case["source"] == "status":
        code = card.get("reason_code")
        historical = case.get("historical", case["family"] == "past-refusal")
        status_read = tools.calls["get_allocation_status"]
        row.update(
            reason_code=code,
            status_authority=source == "status"
            and bool(card.get("checked_at"))
            and (
                (status_read == 0 and card["checked_at"] == prior_checked)
                if historical
                else status_read > 0
            ),
            status_read_only=not tools.calls["request_allocation"]
            and not tools.calls["retrieve_knowledge"]
            and not job["provider_usage"]
            and kind != "confirmation",
            status_match=source == "status"
            and (
                card.get("status") == "UNKNOWN"
                if case["state"] == "UNAVAILABLE"
                else code == case["state"]
            ),
            false_ready=card.get("status") == "READY" and case["state"] != "READY",
        )
    if case["source"] == "proposal":
        row["pinned"] = (
            kind == "recommendation"
            and card["recommendation_id"] == tools.facts["id"]
            and card.get("facts_hash") == canonical_hash(tools.facts)
        )
    evidence = card.get("knowledge", {})
    cites = evidence.get("citations", [])
    row["retrieved_claims"] = [p["claim_id"] for p in tools.retrieved or []]
    row["cited_claims"] = [p["claim_id"] for p in cites]
    if review is not None:
        review.append(
            {
                "id": case["id"],
                "question": case["messages"][-1],
                "prior": history,
                "expected": {
                    "source": case["source"],
                    "state": case["state"],
                    "claims": case["claims"],
                    "necessary_facet": case["allowed_statement"],
                    "action": case["allowed_action"],
                    "refuse": case["must_refuse"],
                },
                "context_switch": case.get("switch"),
                "reply": reply,
                "structured": card,
                "source": source,
                "tools": dict(tools.calls),
                "returned_public_passages": tools.retrieved or [],
                "fixture_facts": tools.facts if case["source"] == "proposal" else None,
                "fixture_evidence": tools.evidence
                if case["source"] == "proposal"
                else None,
                "fixture_market_observations": []
                if case["source"] == "market"
                else None,
            }
        )
    if case["source"] == "knowledge":
        row["intact_evidence"] = bool(evidence) and evidence.get(
            "evidence_hash"
        ) == canonical_hash({k: v for k, v in evidence.items() if k != "evidence_hash"})
        if case["claims"]:
            # Strict mechanical lower bound, independent of human semantic assessment.
            row["answer_quotes_claim"] = any(
                c["claim_id"] in case["claims"] and c["text"] in reply for c in cites
            )
            rank = rank_claim(tools.retrieved or [], case["claims"])
            row.update(
                route_and_hit=source == "knowledge" and bool(rank),
                citation_hit=source == "knowledge"
                and bool(rank_claim(cites, case["claims"])),
            )
        else:
            row["abstained"] = (
                kind == "knowledge"
                and not cites
                and evidence.get("status") == "MISSING"
                and bool(evidence.get("corpus_hash"))
                and evidence.get("reason") in ("MATCH", "NO_EVIDENCE")
                and bool(reply)
            )
    return row
