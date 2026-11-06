"""Local G2 acceptance gate using real JWTs, broker/solver and persistent targets.

Creates synthetic demo portfolios/proposals, never trades or resets infrastructure.
The receipt contains IDs/hashes only; --verify-receipt creates no business records.
"""

import argparse
import hashlib
import json
import time
from uuid import uuid4

from smoke_software import GENERATED, PORTFOLIO, SmokeFailure, login, request, require


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def get(path, token):
    status, body = request("GET", PORTFOLIO + path, token=token)
    require(status == 200, f"Read failed ({status}): {path}")
    return body


def propose(pid, token, strategy="MVO", *, fallback=False):
    status, body = request(
        "POST",
        f"{PORTFOLIO}/api/v1/portfolios/{pid}/recommendations",
        token=token,
        body={
            "strategy": strategy,
            **({"fallback_strategy": "EW"} if fallback else {}),
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    require(status == 202, f"Proposal enqueue failed ({status})")
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        state = get(body["status_url"], token)
        if state["status"] == "SUCCEEDED":
            return get("/api/v1/recommendations/" + state["recommendation_id"], token)
        require(
            state["status"] != "FAILED",
            f"Proposal failed ({(state.get('error') or {}).get('code')})",
        )
        time.sleep(0.5)
    raise SmokeFailure("Proposal did not complete within 70 seconds")


def verify(receipt, alice, bob):
    pid, rid = receipt["portfolio_id"], receipt["recommendation_id"]
    dashboard = get(f"/api/v1/portfolios/{pid}/dashboard", alice)
    target = dashboard["accepted_target"]
    require(
        target["id"] == receipt["target_id"]
        and canonical_hash(target["allocation"]) == receipt["allocation_hash"],
        "Target receipt mismatch",
    )
    require(
        dashboard["holdings_status"] == "NOT_TRACKED",
        "Accepted target confused with holdings",
    )
    require(
        any(
            t["id"] == target["id"]
            for t in get(f"/api/v1/portfolios/{pid}/targets", alice)
        ),
        "Target history lost",
    )
    for path in [
        f"/api/v1/portfolios/{pid}/dashboard",
        f"/api/v1/portfolios/{pid}/targets",
    ]:
        require(
            request("GET", PORTFOLIO + path, token=bob)[0] == 404,
            "Cross-owner read allowed",
        )
    status, replay = request(
        "POST",
        f"{PORTFOLIO}/api/v1/recommendations/{rid}/accept",
        token=alice,
        body={},
        headers={"If-Match": '"1"'},
    )
    require(status == 200 and replay == target, "Accept retry changed the target")
    require(
        request(
            "POST",
            f"{PORTFOLIO}/api/v1/recommendations/{rid}/accept",
            token=bob,
            body={},
            headers={"If-Match": '"1"'},
        )[0]
        == 404,
        "Cross-owner accept allowed",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-receipt", action="store_true")
    args = parser.parse_args()
    accounts = json.loads((GENERATED / "accounts.json").read_text())
    settings = dict(
        line.split("=", 1)
        for line in (GENERATED / ".env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    alice, bob = login("alice", accounts, settings), login("bob", accounts, settings)
    receipt_file = GENERATED / "g2-receipt.json"
    if args.verify_receipt:
        verify(json.loads(receipt_file.read_text()), alice, bob)
        print(
            "PASS: same G2 target/allocation/history/ownership and idempotent accept after restart."
        )
        return
    status, portfolio = request(
        "POST",
        PORTFOLIO + "/api/v1/onboarding/portfolios",
        token=alice,
        body={
            "name": "G2 local acceptance",
            "capital_vnd": "100000000",
            "universe_id": "DEMO",
            "answers": {
                "questionnaire_version": "risk-v1",
                "horizon_months": 36,
                "liquidity_need": "low",
                "loss_tolerance": "medium",
                "experience": "experienced",
            },
        },
    )
    require(
        status == 201
        and portfolio["risk_profile"]["profile"] == "balanced"
        and portfolio["policy_version_id"]
        == f"risk-policy-v1:balanced:{portfolio['risk_profile']['version_id']}",
        f"Onboarding failed ({status})",
    )
    pid = portfolio["id"]
    proposal = propose(pid, alice)
    second = propose(pid, alice)
    require(
        proposal["policy_version_id"] == portfolio["policy_version_id"],
        "Policy provenance missing",
    )
    rid = proposal["id"]
    status, _ = request(
        "POST", f"{PORTFOLIO}/api/v1/recommendations/{rid}/accept", token=alice, body={}
    )
    require(status == 428, "Accept without version precondition allowed")
    status, target = request(
        "POST",
        f"{PORTFOLIO}/api/v1/recommendations/{rid}/accept",
        token=alice,
        body={},
        headers={"If-Match": '"1"'},
    )
    require(
        status == 200 and target["portfolio_version"] == 2, f"Accept failed ({status})"
    )
    require(
        request(
            "POST",
            f"{PORTFOLIO}/api/v1/recommendations/{second['id']}/accept",
            token=alice,
            body={},
            headers={"If-Match": '"2"'},
        )[0]
        == 409,
        "Stale proposal accepted",
    )
    fallback = propose(pid, alice, "BL_ML", fallback=True)
    require(
        fallback["requested_strategy"] == "BL_ML"
        and fallback["strategy"] in {"EW", "BL_ML"},
        "Strategy provenance missing",
    )
    if fallback["strategy"] == "EW":
        require(
            fallback["fallback_reason"] == "MODEL_UNAVAILABLE",
            "Fallback reason missing",
        )
    receipt = {
        "portfolio_id": pid,
        "recommendation_id": rid,
        "target_id": target["id"],
        "allocation_hash": canonical_hash(target["allocation"]),
        "effective_ml_strategy": fallback["strategy"],
    }
    verify(receipt, alice, bob)
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt_file.chmod(0o600)
    print(
        f"PASS: onboarding → {proposal['strategy']} via broker → accept target → dashboard; stale/owner/retry gates; BL_ML effective={fallback['strategy']}."
    )


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as exc:
        raise SystemExit("FAIL: " + str(exc)) from None
