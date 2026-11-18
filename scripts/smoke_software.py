"""Exercise the disposable Compose stack using real identity, DBs and broker.

Credentials and tokens are never printed; a token-free receipt supports restart checks.
"""

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from local_auth import GENERATED, login
PORTFOLIO = "http://localhost:8001"
MARKET = "http://localhost:8003"


class SmokeFailure(Exception):
    pass


def request(method, url, *, token=None, body=None, form=None, headers=None):
    headers = dict(headers or {})
    data = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urlopen(
            Request(url, data=data, headers=headers, method=method), timeout=8
        ) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        # Error bodies may contain upstream details; assertions use status only.
        return error.code, {}
    except (URLError, TimeoutError, ValueError) as error:
        raise SmokeFailure(
            f"Local stack unavailable ({type(error).__name__}); check Compose health."
        ) from None


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def verify_market_receipt(receipt, operator, other):
    saved = receipt.get("market")
    require(
        saved is not None,
        "Receipt predates the Market milestone; run a fresh smoke test.",
    )
    status, _ = request(
        "GET", MARKET + "/api/v1/jobs/market/" + saved["job_id"], token=other
    )
    require(status == 404, "Market cross-owner job access was not denied.")
    status, job = request(
        "GET", MARKET + "/api/v1/jobs/market/" + saved["job_id"], token=operator
    )
    require(
        status == 200 and job["status"] == "SUCCEEDED",
        "Persisted Market ingestion job unavailable.",
    )
    status, manifest = request(
        "GET",
        MARKET + "/api/v1/market/snapshots/" + saved["snapshot_id"],
        token=operator,
    )
    require(
        status == 200
        and manifest["content_hash"] == saved["content_hash"]
        and manifest["observation_hash"] == saved["observation_hash"],
        "Persisted Market snapshot does not match receipt.",
    )
    status, observations = request(
        "GET",
        MARKET + "/api/v1/market/snapshots/" + saved["snapshot_id"] + "/observations",
        token=operator,
    )
    require(
        status == 200 and len(observations) == manifest["observation_count"],
        "Persisted snapshot observations unavailable.",
    )


def market_smoke(operator, investor):
    registry = json.loads((GENERATED / "datasets/catalog.json").read_text())
    spec = registry["DEMO_STOCK"]
    dataset_id = "DEMO_STOCK_" + spec["sha256"][:32].upper()
    require(registry.get(dataset_id) == spec, "Refresh DEMO with the current bootstrap first.")
    with (GENERATED / "datasets" / spec["path"]).open() as stream:
        dates = [row["date"] for row in csv.DictReader(stream)]
    body = {"dataset_id": dataset_id}
    status, _ = request(
        "POST",
        MARKET + "/api/v1/market/ingestions",
        token=investor,
        body=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    require(status == 403, "Investor must not enqueue Market ingestion.")
    key = {"Idempotency-Key": str(uuid4())}
    status, accepted = request(
        "POST",
        MARKET + "/api/v1/market/ingestions",
        token=operator,
        body=body,
        headers=key,
    )
    require(status == 202, f"Market ingestion enqueue failed ({status}).")
    status, replay = request(
        "POST",
        MARKET + "/api/v1/market/ingestions",
        token=operator,
        body=body,
        headers=key,
    )
    require(
        status == 202 and replay == accepted, "Market idempotent replay changed job."
    )
    deadline, state = time.monotonic() + 45, {}
    while time.monotonic() < deadline:
        status, state = request("GET", MARKET + accepted["status_url"], token=operator)
        require(status == 200, "Market job polling failed.")
        if state["status"] != "QUEUED":
            break
        time.sleep(0.5)
    require(
        state.get("status") == "SUCCEEDED",
        "Market broker ingestion failed; inspect job/worker status.",
    )
    status, snapshot = request(
        "POST",
        MARKET + "/api/v1/market/snapshots",
        token=operator,
        body={
            "asset_ids": [spec["asset_id"]],
            "start_date": min(dates),
            "end_date": max(dates),
            "as_of_date": datetime.now(timezone.utc).date().isoformat(),
            "max_age_days": 7,
        },
    )
    require(
        status == 201, f"Market snapshot failed ({status}); refresh stale demo imports."
    )
    return {
        "job_id": accepted["job_id"],
        "snapshot_id": snapshot["id"],
        "content_hash": snapshot["content_hash"],
        "observation_hash": snapshot["observation_hash"],
    }


def verify_receipt(receipt, alice, bob, operator):
    for path in (
        "/api/v1/portfolios/" + receipt["portfolio_id"],
        "/api/v1/jobs/portfolio/" + receipt["job_id"],
        "/api/v1/recommendations/" + receipt["recommendation_id"],
    ):
        status, _ = request("GET", PORTFOLIO + path, token=bob)
        require(status == 404, "Cross-owner access was not denied.")
    status, saved = request(
        "GET",
        PORTFOLIO + "/api/v1/recommendations/" + receipt["recommendation_id"],
        token=alice,
    )
    require(
        status == 200 and saved["input_hash"] == receipt["input_hash"],
        "Persisted recommendation does not match the receipt.",
    )
    weights = [float(weight) for weight in saved["weights"]]
    require(
        abs(sum(weights) - 1) < 1e-7 and max(weights) <= 0.5000001,
        "Final weights violate constraints.",
    )
    require(
        saved["strategy"] == "MVO"
        and saved["status"] == "optimal"
        and saved["demo"] is True,
        "Unexpected result metadata.",
    )
    require(
        saved["core_version"] == "0.1.0"
        and len(saved["bundle_hash"]) == 64
        and saved["data_snapshot_id"],
        "Missing provenance.",
    )
    status, history = request(
        "GET",
        PORTFOLIO
        + "/api/v1/portfolios/"
        + receipt["portfolio_id"]
        + "/recommendations",
        token=alice,
    )
    require(
        status == 200
        and any(item["id"] == receipt["recommendation_id"] for item in history),
        "Recommendation history missing.",
    )
    verify_market_receipt(receipt, operator, bob)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-receipt",
        action="store_true",
        help="Re-read the prior result after a container restart; create nothing",
    )
    args = parser.parse_args()
    alice, bob = login("alice"), login("bob")
    operator = login("data-operator")
    receipt_path = GENERATED / "smoke-receipt.json"
    if args.verify_receipt:
        verify_receipt(json.loads(receipt_path.read_text()), alice, bob, operator)
        print(
            "PASS: persisted recommendation, Market job/snapshot, provenance, history and ownership after restart."
        )
        return
    status, _ = request("GET", PORTFOLIO + "/api/v1/portfolios")
    require(status == 401, "Unauthenticated API access was not denied.")
    status, portfolio = request(
        "POST",
        PORTFOLIO + "/api/v1/portfolios",
        token=alice,
        body={
            "name": "Compose smoke " + str(uuid4())[:8],
            "capital_vnd": "1000000",
            "universe_id": "DEMO",
            "max_position_weight": 0.5,
        },
    )
    require(status == 201, f"Portfolio creation failed ({status}).")
    path = PORTFOLIO + "/api/v1/portfolios/" + portfolio["id"] + "/recommendations"
    key = {"Idempotency-Key": str(uuid4())}
    status, accepted = request(
        "POST", path, token=alice, body={"strategy": "MVO"}, headers=key
    )
    require(
        status == 202,
        f"Recommendation enqueue failed ({status}); check bundle freshness and service identity.",
    )
    status, replay = request(
        "POST", path, token=alice, body={"strategy": "MVO"}, headers=key
    )
    require(
        status == 202 and replay == accepted, "Idempotent retry created another job."
    )
    status, _ = request("POST", path, token=alice, body={"strategy": "EW"}, headers=key)
    require(status == 409, "Conflicting idempotency key was accepted.")
    deadline = time.monotonic() + 65
    state = {}
    while time.monotonic() < deadline:
        status, state = request("GET", PORTFOLIO + accepted["status_url"], token=alice)
        require(status == 200, f"Job read failed ({status}).")
        if state["status"] != "QUEUED":
            break
        time.sleep(0.5)
    require(
        state.get("status") == "SUCCEEDED",
        "Asynchronous computation did not succeed; inspect local worker/job status.",
    )
    status, saved = request(
        "GET",
        PORTFOLIO + "/api/v1/recommendations/" + state["recommendation_id"],
        token=alice,
    )
    require(status == 200, "Saved recommendation was unavailable.")
    receipt = {
        "schema_version": 2,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_id": portfolio["id"],
        "job_id": accepted["job_id"],
        "recommendation_id": state["recommendation_id"],
        "input_hash": saved["input_hash"],
        "market": market_smoke(operator, alice),
    }
    verify_receipt(receipt, alice, bob, operator)
    status, _ = request(
        "POST",
        path,
        token=alice,
        body={"strategy": "BL_ML"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    require(status == 503, "Demo without approved ML model must reject BL_ML.")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt_path.chmod(0o600)
    print(
        "PASS: real Auth, async MVO + Market ingestion/snapshot, idempotency, provenance, history, ownership and missing-model rejection."
    )


if __name__ == "__main__":
    try:
        main()
    except (SmokeFailure, OSError, KeyError, StopIteration) as error:
        message = (
            str(error)
            if isinstance(error, SmokeFailure)
            else type(error).__name__ + "; check local bootstrap files."
        )
        raise SystemExit("FAIL: " + message) from None
