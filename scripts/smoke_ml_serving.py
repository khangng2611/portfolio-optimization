"""Publish an explicit synthetic ML demo, then verify real serving/core parity.

Run only against the disposable local stack. Training occurs in this process,
never in the HTTP API/optimizer consumer. Preserve all old artifacts and secrets.
"""

import argparse
import hashlib
import fcntl
import json
from datetime import timedelta
from uuid import uuid4

from portfolio_contracts import utcnow
from portfolio_core import allocate
from quant_service.artifacts import ArtifactCatalog
from quant_service.model_worker import approve_candidate, train_candidate
from smoke_g2 import propose
from smoke_software import GENERATED, PORTFOLIO, SmokeFailure, login, request, require


def publish_demo():
    root = GENERATED / "bundles"
    now = utcnow()
    catalog_file = root / "catalog.json"
    previous = ArtifactCatalog(root, allow_demo=True)
    ready = previous.ready("DEMO", "MVO")
    numerical = previous.load(ready, "MVO")
    # The synthetic BL prior uses an explicit equal-weight market portfolio.
    numerical = numerical | {
        "market_weights": [1 / len(numerical["asset_ids"])]
        * len(numerical["asset_ids"])
    }
    start = now.date() - timedelta(days=60)
    candidate = train_candidate(
        root,
        {
            "schema_version": 1,
            "horizon_sessions": 1,
            "return_unit": "daily_simple_fraction",
            "asset_ids": numerical["asset_ids"],
            "feature_names": ["synthetic_momentum", "synthetic_volatility"],
            "feature_schema_version": "synthetic-v1",
            "snapshot_id": "synthetic-training-only",
            "demo": True,
            "training_cutoff": (start + timedelta(days=30)).isoformat(),
            "features": [[i / 100, (i % 3 + 1) / 100] for i in range(24)],
            "targets": [i / 10000 for i in range(24)],
            "feature_dates": [
                (start + timedelta(days=i)).isoformat() for i in range(24)
            ],
            "label_available_dates": [
                (start + timedelta(days=i + 1)).isoformat() for i in range(24)
            ],
        },
    )
    approved = approve_candidate(
        root, candidate, reviewer="local-synthetic-demo-reviewer"
    )
    identity = "ml-demo-" + str(uuid4())
    value = {
        "schema_version": 1,
        "bundle_id": identity,
        "universe_id": "DEMO",
        "snapshot_id": "synthetic-" + identity,
        "model_bundle_id": approved["sha256"],
        "model_status": "APPROVED",
        "as_of_date": now.date().isoformat(),
        "valid_until": (now + timedelta(days=7)).isoformat(),
        "demo": True,
        "strategies": ["EW", "MVO", "BL_ML"],
        "numerical": numerical,
        "ml_inference": {
            "manifest": approved,
            "feature_schema_version": "synthetic-v1",
            "feature_names": ["synthetic_momentum", "synthetic_volatility"],
            "asset_ids": numerical["asset_ids"],
            "feature_date": now.date().isoformat(),
            "rows": [[(i + 1) / 100, 0.02] for i in range(len(numerical["asset_ids"]))],
        },
    }
    content = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    filename = identity + ".json"
    with (root / filename).open("xb") as stream:
        stream.write(content)
    # Validate every artifact/model before atomically publishing the serving index.
    from quant_service.ml import infer

    infer(root, value, allow_demo=True)
    with (root / ".catalog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        catalog = json.loads(catalog_file.read_text())
        catalog["bundles"].insert(
            0, {"file": filename, "sha256": hashlib.sha256(content).hexdigest()}
        )
        temporary = root / f"catalog-{uuid4()}.tmp"
        temporary.write_text(json.dumps(catalog, indent=2) + "\n")
        temporary.replace(catalog_file)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish-demo",
        action="store_true",
        help="Explicitly train/approve/publish synthetic local artifacts",
    )
    parser.add_argument("--verify-receipt", action="store_true")
    args = parser.parse_args()
    require(
        not (args.publish_demo and args.verify_receipt),
        "Choose publish or receipt verification",
    )
    if args.publish_demo:
        publish_demo()
    accounts = json.loads((GENERATED / "accounts.json").read_text())
    settings = dict(
        line.split("=", 1)
        for line in (GENERATED / ".env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    alice = login("alice", accounts, settings)
    receipt_file = GENERATED / "ml-serving-receipt.json"
    if args.verify_receipt:
        receipt = json.loads(receipt_file.read_text())
        status, proposal = request(
            "GET",
            PORTFOLIO + "/api/v1/recommendations/" + receipt["recommendation_id"],
            token=alice,
        )
        require(
            status == 200 and proposal["input_hash"] == receipt["input_hash"],
            "Persisted ML recommendation changed",
        )
        require(
            proposal["diagnostics"]["inference"]["model_manifest_hash"]
            == receipt["model_manifest_hash"],
            "Model provenance changed",
        )
        print(
            "PASS: same persisted BL_ML recommendation and approved-model provenance after restart."
        )
        return
    status, portfolio = request(
        "POST",
        PORTFOLIO + "/api/v1/portfolios",
        token=alice,
        body={
            "name": "Synthetic ML parity",
            "capital_vnd": "100000000",
            "max_position_weight": 0.5,
        },
    )
    require(status == 201, "Could not create parity portfolio")
    proposal = propose(portfolio["id"], alice, "BL_ML")
    catalog = ArtifactCatalog(GENERATED / "bundles", allow_demo=True)
    numerical = catalog.load(catalog.ready("DEMO", "BL_ML"), "BL_ML")
    numerical.pop("inference_provenance", None)
    expected = allocate(
        numerical | {"strategy": "BL_ML", "constraints": proposal["constraints"]}
    )
    difference = max(
        abs(float(a) - b) for a, b in zip(proposal["weights"], expected["weights"])
    )
    require(
        difference < 1e-10 and proposal["demo"] is True,
        "Serving/core same-step parity failed",
    )
    receipt = {
        "recommendation_id": proposal["id"],
        "input_hash": proposal["input_hash"],
        "model_manifest_hash": proposal["diagnostics"]["inference"][
            "model_manifest_hash"
        ],
        "max_weight_difference": difference,
        "synthetic": True,
    }
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt_file.chmod(0o600)
    print(
        f"PASS: synthetic native XGBoost → BL_ML via RabbitMQ → recommendation; same-step core parity max |Δw|={difference:.3g}."
    )


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as exc:
        raise SystemExit("FAIL: " + str(exc)) from None
