"""Real local Chat → Portfolio → RabbitMQ → Quant API integration gate.

Creates one real-data risk-onboarded portfolio, one conversation and two turns.
Never accepts a recommendation. No SQL, mock transports or provider substitution.
Requires the existing disposable Keycloak portfolio-test client and Chat worker.
Run --verify-receipt after externally restarting the actual application processes.
For --provider-outage configure the real worker's provider outage externally first;
this script only checks TEMPLATE evidence, and never changes worker configuration.
Credentials stay in memory; the ignored receipt contains only IDs and hashes.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

GENERATED = Path(__file__).resolve().parents[1] / "infra/local/.generated"
CHAT = "http://localhost:8005"
PORTFOLIO = "http://localhost:8001"
MARKET = "http://localhost:8003"
QUANT = "http://localhost:8002"
IDENTITY = "http://localhost:8080/realms/portfolio/protocol/openid-connect/token"
SCOPES = "openid chat:read chat:write portfolio:read portfolio:write market:read"
STOPPED = {
    "SUCCEEDED",
    "WAITING_INPUT",
    "FAILED",
    "CANCELLED",
    "AUTHORIZATION_REQUIRED",
}


class SmokeFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def canonical_hash(value):
    # Exact wire-contract algorithm, including ensure_ascii=True.
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(method, url, *, token=None, body=None, form=None, headers=None, sse=False):
    headers = dict(headers or {})
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body, allow_nan=False).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if sse:
        headers["Accept"] = "text/event-stream"
    try:
        with build_opener(NoRedirect()).open(
            Request(url, data=data, headers=headers, method=method), timeout=10
        ) as response:
            if sse:
                require(
                    response.headers.get_content_type() == "text/event-stream",
                    "Chat events did not return SSE.",
                )
                value = parse_sse(response.read(2_000_001).decode("utf-8"))
            else:
                value = json.load(response)
            return response.status, value
    except HTTPError as error:
        # Never include raw dependency response bodies/URLs in reports.
        status = error.code
        error.close()
        return status, {}
    except (URLError, TimeoutError, ValueError, UnicodeError, OSError):
        raise SmokeFailure(
            "Local API unavailable or invalid response; check service health."
        ) from None


def get(base, path, token=None):
    status, value = request("GET", base + path, token=token)
    require(
        status == 200,
        f"API read failed ({status}); check local dependencies and scopes.",
    )
    return value


def credentials():
    accounts = json.loads((GENERATED / "accounts.json").read_text())
    settings = {}
    for name in ("smoke-settings.json", "settings.json"):
        path = GENERATED / name
        if path.exists():
            settings.update(json.loads(path.read_text()))
    env = GENERATED / ".env"
    if env.exists():
        settings.update(
            dict(
                line.split("=", 1)
                for line in env.read_text().splitlines()
                if line and not line.startswith("#") and "=" in line
            )
        )
    secret = settings.get("OIDC_TEST_CLIENT_SECRET") or settings.get(
        "TEST_CLIENT_SECRET"
    )
    require(
        isinstance(secret, str) and secret,
        "Existing local test-client secret unavailable.",
    )
    return accounts, secret


def login(username, accounts, secret):
    account = next((u for u in accounts["users"] if u["username"] == username), None)
    require(account is not None, "Required local test account unavailable.")
    status, data = request(
        "POST",
        IDENTITY,
        form={
            "grant_type": "password",
            "client_id": "portfolio-test",
            "client_secret": secret,
            "username": username,
            "password": account["password"],
            "scope": SCOPES,
        },
    )
    require(
        status == 200 and data.get("access_token"),
        f"Local Keycloak test login failed ({status}); check existing client/scopes.",
    )
    require(
        set(SCOPES.split()) <= set(data.get("scope", "").split()),
        "Keycloak did not grant all required Chat/Portfolio/Market scopes.",
    )
    return data["access_token"]


def select_real_universe(catalog):
    for item in catalog:
        try:
            current = datetime.fromisoformat(
                item["valid_until"].replace("Z", "+00:00")
            ) > datetime.now(timezone.utc)
            compatible = any(
                s.get("strategy") == "MVO"
                and s.get("available") is True
                and s.get("reason_code") == "READY"
                for s in item["strategies"]
            )
            if (
                item.get("status") == "READY"
                and item.get("reason_code") == "READY"
                and item.get("data_origin") == "real"
                and item.get("demo") is False
                and len(item.get("asset_ids", [])) >= 2
                and current
                and compatible
                and re.fullmatch(r"[a-f0-9]{64}", item.get("bundle_hash") or "")
                and item.get("snapshot_id")
            ):
                return item
        except (KeyError, ValueError, TypeError):
            continue
    raise SmokeFailure(
        "No current READY real-price MVO universe; publish fresh real inputs first."
    )


def assert_grounded(card, facts):
    digest = canonical_hash(facts)
    require(
        card.get("facts") == facts and card.get("facts_hash") == digest,
        "Chat full canonical facts/hash differ from Portfolio recommendation.",
    )


def assert_weights(facts):
    ids, raw = facts["asset_ids"], facts["weights"]
    require(
        isinstance(raw, list) and len(raw) == len(ids) and len(set(ids)) == len(ids),
        "Recommendation weights/asset order invalid.",
    )
    try:
        weights = [float(w) for w in raw]
    except (TypeError, ValueError, OverflowError):
        raise SmokeFailure("Recommendation weights invalid.") from None
    constraints = facts["constraints"]
    require(
        all(not isinstance(w, bool) for w in raw)
        and all(
            math.isfinite(w) and -1e-7 <= w <= constraints["max_position_weight"] + 1e-7
            for w in weights
        )
        and abs(sum(weights) - 1) <= 1e-7,
        "Recommendation weights violate sum/bounds.",
    )
    defensive = sum(
        w
        for asset, w in zip(ids, weights, strict=True)
        if asset in constraints.get("defensive_asset_ids", [])
    )
    require(
        defensive + 1e-7 >= constraints.get("min_defensive_weight", 0)
        and 1 - defensive <= constraints.get("max_non_defensive_weight", 1) + 1e-7,
        "Recommendation weights violate defensive constraints.",
    )


def parse_sse(raw):
    require(len(raw) <= 2_000_000, "SSE response exceeded evidence budget.")
    events = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        fields, data = {}, []
        for line in block.splitlines():
            if not line or line.startswith(":"):
                continue
            key, _, value = line.partition(":")
            value = value.removeprefix(" ")
            if key == "data":
                data.append(value)
            else:
                fields[key] = value
        if not data:
            continue
        require(
            fields.get("event") not in {"reset_required", "session_expired"},
            "SSE replay requires retained events and an active session.",
        )
        require(fields.get("id", "").isdigit(), "SSE event lacks persisted sequence.")
        events.append(
            {
                "id": int(fields["id"]),
                "event": fields.get("event", "message"),
                "data": json.loads("\n".join(data)),
            }
        )
    return events


def assert_replay(events, replay, after):
    require(
        events and [e["id"] for e in events] == list(range(1, len(events) + 1)),
        "Persisted SSE sequence is missing, repeated or nonmonotonic.",
    )
    require(
        replay == [e for e in events if e["id"] > after],
        "Last-Event-ID replay differs from persisted SSE suffix.",
    )


def events_for(job_id, token, after=0):
    status, events = request(
        "GET",
        CHAT + f"/api/v1/jobs/chat/{job_id}/events",
        token=token,
        headers={"Last-Event-ID": str(after)},
        sse=True,
    )
    require(status == 200, f"SSE read failed ({status}).")
    return events


def event_evidence(job, token):
    events = events_for(job["job_id"], token)
    after = max(1, len(events) // 2)
    assert_replay(events, events_for(job["job_id"], token, after), after)
    require(
        events[-1]["id"] == job["last_event_id"],
        "SSE terminal event count differs from job.",
    )
    return events, {
        "after": after,
        "events": [
            {"id": e["id"], "event": e["event"], "hash": canonical_hash(e)}
            for e in events
        ],
    }


def messages(cid, token):
    rows, offset = [], 0
    while True:
        page = get(
            CHAT,
            f"/api/v1/conversations/{cid}/messages?limit=100&offset={offset}",
            token,
        )
        require(isinstance(page, list), "Chat history response invalid.")
        rows.extend(page)
        if len(page) < 100:
            return rows
        offset += 100
        require(offset <= 1000, "Chat history exceeded smoke evidence budget.")


def history_evidence(rows):
    return {
        "count": len(rows),
        "hash": canonical_hash(rows),
        "messages": [
            {"id": m["id"], "role": m["role"], "hash": canonical_hash(m)} for m in rows
        ],
    }


def wait_job(job_id, token, expected, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = get(CHAT, f"/api/v1/jobs/chat/{job_id}", token)
        if state["status"] in STOPPED:
            require(
                state["status"] == expected,
                f"Chat worker did not reach {expected}; inspect persisted job status.",
            )
            return state
        time.sleep(0.5)
    raise SmokeFailure(f"Chat worker did not reach {expected} before timeout.")


def send(cid, token, body):
    return request(
        "POST",
        CHAT + f"/api/v1/conversations/{cid}/messages",
        token=token,
        body=body,
        headers={"Idempotency-Key": body["client_message_id"]},
    )


def send_idempotent(cid, token, body):
    # Genuine concurrent requests exercise the database serialization boundary.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(send, cid, token, body) for _ in range(2)]
        first, second = [f.result() for f in futures]
    require(
        first[0] == second[0] == 202 and first[1] == second[1],
        "Concurrent Chat retry changed the accepted receipt.",
    )
    require(
        send(cid, token, body | {"content": body["content"] + " changed"})[0] == 409,
        "Chat idempotency body conflict was not rejected.",
    )
    return first[1]


def assert_ownership(
    cid,
    job_ids,
    other,
    *,
    portfolio_id=None,
    recommendation_id=None,
    allocation_job_id=None,
):
    paths = [f"/api/v1/conversations/{cid}", f"/api/v1/conversations/{cid}/messages"]
    paths.extend(
        f"/api/v1/jobs/chat/{jid}{suffix}"
        for jid in job_ids
        for suffix in ("", "/events")
    )
    for path in paths:
        status, _ = request("GET", CHAT + path, token=other)
        require(
            status == 404,
            "Cross-user Chat conversation/history/job/SSE access was not hidden.",
        )
    portfolio_paths = []
    if portfolio_id:
        portfolio_paths.append(f"/api/v1/portfolios/{portfolio_id}")
    if recommendation_id:
        portfolio_paths.append(f"/api/v1/recommendations/{recommendation_id}")
    if allocation_job_id:
        portfolio_paths.append(f"/api/v1/jobs/portfolio/{allocation_job_id}")
    for path in portfolio_paths:
        require(
            request("GET", PORTFOLIO + path, token=other)[0] == 404,
            "Cross-user canonical Portfolio resource access was not hidden.",
        )


def assert_result(facts, portfolio, pins):
    assert_weights(facts)
    require(
        facts["portfolio_id"] == portfolio["id"]
        and facts["portfolio_version"] == portfolio["version"]
        and facts["policy_version_id"] == portfolio["policy_version_id"]
        and facts["risk_profile"] == portfolio["risk_profile"]
        and facts["capital_vnd"] == portfolio["capital_vnd"]
        and facts["constraints"] == portfolio["constraints"],
        "Canonical result lost confirmed portfolio/risk constraints.",
    )
    require(
        facts["strategy"] == facts["requested_strategy"] == "MVO"
        and facts["fallback_reason"] is None
        and facts["demo"] is False
        and facts["status"] == "optimal"
        and facts["asset_ids"] == pins["asset_ids"]
        and facts["bundle_hash"] == pins["bundle_hash"]
        and facts["data_snapshot_id"] == pins["snapshot_id"],
        "Canonical result differs from real MVO input pins.",
    )
    require(
        facts["core_version"] == "0.1.0"
        and facts.get("run_id")
        and re.fullmatch(r"[a-f0-9]{64}", facts.get("input_hash", "")),
        "Canonical result lacks numerical provenance.",
    )
    provenance = facts.get("inputs_provenance", {})
    require(
        provenance.get("data_origin") == "real"
        and provenance.get("snapshot_id") == pins["snapshot_id"]
        and all(
            re.fullmatch(r"[a-f0-9]{64}", provenance.get(k, ""))
            for k in ("snapshot_hash", "observation_hash")
        ),
        "Canonical result lacks verified real snapshot provenance.",
    )


def snapshot_evidence(facts, token):
    provenance = facts["inputs_provenance"]
    path = f"/api/v1/market/snapshots/{facts['data_snapshot_id']}"
    snapshot = get(MARKET, path, token)
    observations = get(MARKET, path + "/observations", token)
    manifest = {
        k: v
        for k, v in snapshot.items()
        if k not in {"id", "content_hash", "created_at"}
    }
    require(
        snapshot["data_origin"] == "real"
        and snapshot["content_hash"] == provenance["snapshot_hash"]
        and canonical_hash(manifest) == snapshot["content_hash"]
        and snapshot["observation_hash"] == provenance["observation_hash"]
        and canonical_hash({"observations": observations})
        == snapshot["observation_hash"]
        and len(observations) == snapshot["observation_count"]
        and all(row.get("data_origin") == "real" for row in observations),
        "Market snapshot/observations do not match canonical real provenance.",
    )
    return {
        "id": snapshot["id"],
        "content_hash": snapshot["content_hash"],
        "observation_hash": snapshot["observation_hash"],
        "observation_count": len(observations),
    }


def assert_outage(card, expected):
    if expected:
        require(
            card.get("explanation_status") == "TEMPLATE"
            and card.get("provider", {}).get("reason")
            in {"PROVIDER_UNAVAILABLE", "TIMEOUT"},
            "Provider outage not observed: require real worker TEMPLATE with unavailable/timeout reason.",
        )


def write_receipt(path, receipt):
    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                require(
                    not any(
                        part in key.lower()
                        for part in (
                            "token",
                            "secret",
                            "password",
                            "grant",
                            "authorization",
                        )
                    ),
                    "Refusing credential-bearing receipt field.",
                )
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(receipt)
    temporary = path.with_name(path.name + "." + str(uuid4()) + ".tmp")
    try:
        with open(
            temporary, "x", opener=lambda p, flags: os.open(p, flags, 0o600)
        ) as stream:
            json.dump(receipt, stream, indent=2, allow_nan=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_receipt(receipt, alice, bob, provider_outage=False):
    require(
        receipt.get("schema_version") == 1,
        "Chat receipt schema unsupported; run a fresh Chat gate.",
    )
    cid, pid, rid = (
        receipt["conversation_id"],
        receipt["portfolio_id"],
        receipt["recommendation_id"],
    )
    portfolio = get(PORTFOLIO, f"/api/v1/portfolios/{pid}", alice)
    require(
        canonical_hash(portfolio) == receipt["portfolio_hash"],
        "Saved portfolio/risk version changed.",
    )
    conv = get(CHAT, f"/api/v1/conversations/{cid}", alice)
    require(
        canonical_hash(conv) == receipt["conversation_hash"],
        "Saved conversation changed.",
    )
    rows = messages(cid, alice)
    require(
        history_evidence(rows) == receipt["history"],
        "Persisted Chat message history/hash changed.",
    )
    facts = get(PORTFOLIO, f"/api/v1/recommendations/{rid}", alice)
    require(
        canonical_hash(facts) == receipt["facts_hash"]
        and facts["input_hash"] == receipt["input_hash"],
        "Persisted canonical recommendation/input hash changed.",
    )
    assert_result(facts, portfolio, receipt["input_pins"])
    result = next(m for m in rows if m["id"] == receipt["result_message_id"])
    assert_grounded(result["structured"], facts)
    assert_outage(
        result["structured"], provider_outage or receipt["provider_outage_expected"]
    )
    card = next(m for m in rows if m["id"] == receipt["confirmation_message_id"])[
        "structured"
    ]
    require(
        card["confirmation_message_id"] == receipt["confirmation_message_id"]
        and canonical_hash(card["input"])
        == card["facts_hash"]
        == receipt["confirmation_input_hash"],
        "Persisted confirmation input/facts hash changed.",
    )
    for jid, evidence in receipt["chat_jobs"].items():
        state = get(CHAT, f"/api/v1/jobs/chat/{jid}", alice)
        require(
            state["status"] == evidence["status"]
            and state["result_message_id"] == evidence["result_message_id"],
            "Persisted Chat job/result changed.",
        )
        _, actual = event_evidence(state, alice)
        require(actual == evidence["sse"], "Persisted SSE sequence/hash changed.")
    allocation = get(
        PORTFOLIO, f"/api/v1/jobs/portfolio/{receipt['allocation_job_id']}", alice
    )
    require(
        allocation["status"] == "SUCCEEDED" and allocation["recommendation_id"] == rid,
        "Persisted allocation job/result binding changed.",
    )
    history = get(PORTFOLIO, f"/api/v1/portfolios/{pid}/recommendations", alice)
    require(
        len(history) == 1 and history[0] == facts,
        "Canonical recommendation history changed or duplicate allocation exists.",
    )
    require(
        snapshot_evidence(facts, alice) == receipt["market"],
        "Persisted Market evidence changed.",
    )
    assert_ownership(
        cid,
        receipt["chat_jobs"],
        bob,
        portfolio_id=pid,
        recommendation_id=rid,
        allocation_job_id=receipt["allocation_job_id"],
    )


def run(alice, bob, *, timeout, provider_outage):
    require(
        request("GET", CHAT + "/api/v1/conversations")[0] == 401,
        "Unauthenticated Chat access was not denied.",
    )
    for base in (CHAT, PORTFOLIO, MARKET, QUANT):
        get(base, "/health/ready")
    pins = select_real_universe(get(PORTFOLIO, "/api/v1/universes/readiness", alice))
    status, portfolio = request(
        "POST",
        PORTFOLIO + "/api/v1/onboarding/portfolios",
        token=alice,
        body={
            "name": "Chat live MVO " + str(uuid4())[:8],
            "capital_vnd": "100000000",
            "universe_id": pins["universe_id"],
            "answers": {
                "questionnaire_version": "risk-v1",
                "horizon_months": 60,
                "liquidity_need": "low",
                "loss_tolerance": "high",
                "experience": "experienced",
            },
        },
    )
    require(
        status == 201 and portfolio.get("risk_profile", {}).get("version_id"),
        f"Risk onboarding failed ({status}).",
    )
    pid = portfolio["id"]
    # Read the committed representation (notably DB Decimal scale) before pinning.
    portfolio = get(PORTFOLIO, f"/api/v1/portfolios/{pid}", alice)
    status, conversation = request(
        "POST",
        CHAT + "/api/v1/conversations",
        token=alice,
        body={"title": "Real MVO integration", "portfolio_id": pid},
    )
    require(status == 201, f"Chat conversation creation failed ({status}).")
    cid = conversation["id"]
    path = f"/api/v1/portfolios/{pid}/recommendations"
    require(
        get(PORTFOLIO, path, alice) == [],
        "New smoke portfolio unexpectedly has a proposal.",
    )
    initial = send_idempotent(
        cid,
        alice,
        {
            "content": "Tạo đề xuất phân bổ MVO cho danh mục này.",
            "client_message_id": str(uuid4()),
            "portfolio_id": pid,
            "intent": "allocation",
            "strategy": "MVO",
        },
    )
    first = wait_job(initial["job_id"], alice, "WAITING_INPUT", timeout)
    rows = messages(cid, alice)
    card_message = next(m for m in rows if m["id"] == first["result_message_id"])
    card = card_message["structured"]
    require(
        first["stage"] == "CONFIRMATION"
        and card["type"] == "confirmation"
        and card["confirmation_message_id"] == card_message["id"]
        and card["input"] == {"portfolio": portfolio, "strategy": "MVO"}
        and canonical_hash(card["input"]) == card["facts_hash"],
        "Worker confirmation card did not pin canonical inputs.",
    )
    require(
        get(PORTFOLIO, path, alice) == [] and first["recommendation_id"] is None,
        "Chat created a proposal before explicit confirmation.",
    )
    first_events, first_sse = event_evidence(first, alice)
    require(
        not any(
            e["data"].get("allocation_job_id") or e["event"] == "artifact_ready"
            for e in first_events
        ),
        "Chat submitted an allocation before confirmation.",
    )
    assert_ownership(cid, [first["job_id"]], bob, portfolio_id=pid)
    confirmed = send_idempotent(
        cid,
        alice,
        {
            "content": "Xác nhận tạo đề xuất MVO với đầu vào đã xem.",
            "client_message_id": str(uuid4()),
            "portfolio_id": pid,
            "confirmation": {
                "message_id": card["confirmation_message_id"],
                "facts_hash": card["facts_hash"],
            },
        },
    )
    final = wait_job(confirmed["job_id"], alice, "SUCCEEDED", timeout)
    final_events, final_sse = event_evidence(final, alice)
    dependency_ids = {
        e["data"]["allocation_job_id"]
        for e in final_events
        if e["data"].get("allocation_job_id")
    }
    require(
        len(dependency_ids) == 1 and final["recommendation_id"],
        "Chat SSE lacks the actual allocation dependency/result.",
    )
    allocation_job_id = dependency_ids.pop()
    allocation = get(PORTFOLIO, f"/api/v1/jobs/portfolio/{allocation_job_id}", alice)
    rid = final["recommendation_id"]
    require(
        allocation["status"] == "SUCCEEDED" and allocation["recommendation_id"] == rid,
        "Actual Portfolio/RabbitMQ/Quant allocation did not succeed.",
    )
    facts = get(PORTFOLIO, f"/api/v1/recommendations/{rid}", alice)
    assert_result(facts, portfolio, pins)
    rows = messages(cid, alice)
    result = next(m for m in rows if m["id"] == final["result_message_id"])
    require(
        result["structured"]["type"] == "recommendation"
        and result["structured"]["recommendation_id"] == rid,
        "Chat result artifact binding invalid.",
    )
    assert_grounded(result["structured"], facts)
    assert_outage(result["structured"], provider_outage)
    explanation = get(CHAT, f"/api/v1/recommendations/{rid}/explanation", alice)
    require(
        explanation == result,
        "Chat explanation API does not return canonical grounded message.",
    )
    receipt = {
        "schema_version": 1,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_id": pid,
        "portfolio_hash": canonical_hash(portfolio),
        "conversation_id": cid,
        "conversation_hash": canonical_hash(
            get(CHAT, f"/api/v1/conversations/{cid}", alice)
        ),
        "recommendation_id": rid,
        "allocation_job_id": allocation_job_id,
        "result_message_id": result["id"],
        "confirmation_message_id": card_message["id"],
        "confirmation_input_hash": card["facts_hash"],
        "input_hash": facts["input_hash"],
        "facts_hash": canonical_hash(facts),
        "history": history_evidence(rows),
        "input_pins": {
            k: pins[k]
            for k in ("universe_id", "asset_ids", "bundle_hash", "snapshot_id")
        },
        "market": snapshot_evidence(facts, alice),
        "provider_outage_expected": provider_outage,
        "explanation_status": result["structured"]["explanation_status"],
        "provider_reason": result["structured"]["provider"]["reason"],
        "chat_jobs": {
            state["job_id"]: {
                "status": state["status"],
                "result_message_id": state["result_message_id"],
                "sse": evidence,
            }
            for state, evidence in ((first, first_sse), (final, final_sse))
        },
    }
    verify_receipt(receipt, alice, bob, provider_outage)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-receipt",
        action="store_true",
        help="Read the saved resources/history/SSE after an external restart; no new API data",
    )
    parser.add_argument(
        "--provider-outage",
        action="store_true",
        help="Require genuine unavailable/timeout provider TEMPLATE evidence; configure worker externally",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Maximum seconds per Chat turn (default: 180)",
    )
    args = parser.parse_args()
    require(1 <= args.timeout <= 600, "Timeout must be between 1 and 600 seconds.")
    accounts, secret = credentials()
    alice, bob = login("alice", accounts, secret), login("bob", accounts, secret)
    path = GENERATED / "chat-api-receipt.json"
    if args.verify_receipt:
        verify_receipt(json.loads(path.read_text()), alice, bob, args.provider_outage)
        print(
            "PASS: same persisted Chat history/jobs/SSE, canonical real MVO facts/input hashes, Market provenance and ownership."
        )
    else:
        receipt = run(
            alice, bob, timeout=args.timeout, provider_outage=args.provider_outage
        )
        write_receipt(path, receipt)
        print(
            "PASS: real JWT, confirmed Chat MVO via Portfolio/RabbitMQ/Quant, idempotency, full facts, history, SSE replay and ownership; no target accepted."
        )


if __name__ == "__main__":
    try:
        main()
    except (
        SmokeFailure,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        StopIteration,
    ) as error:
        message = (
            str(error)
            if isinstance(error, SmokeFailure)
            else "Local receipt/configuration or API shape invalid; inspect services without exposing secrets."
        )
        raise SystemExit("FAIL: " + message) from None
