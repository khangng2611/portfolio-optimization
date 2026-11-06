"""Local real-price Market→features→model→Quant→accepted-target gate.

Requires an explicit real input pack and reviewer for local artifact approval.
No research dataset writes or transactions. Receipts contain no credentials.
"""

import argparse
import csv
from datetime import timedelta
import fcntl
import hashlib
import io
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx

from portfolio_contracts import canonical_hash, utcnow
from portfolio_core import allocate
from quant_service.artifacts import ArtifactCatalog
from quant_service.ml import read_artifact
from quant_service.model_worker import train_candidate, approve_candidate
from quant_service.snapshot_publisher import MarketReader, publish_snapshot
from quant_service.snapshot_inputs import SnapshotPanel
from smoke_g2 import get, propose
from smoke_software import (
    GENERATED,
    MARKET,
    PORTFOLIO,
    IDENTITY,
    SmokeFailure,
    login,
    request,
    require,
)


def register_pack(directory):
    root = Path(directory).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    require(
        manifest["data_origin"] == "real"
        and manifest["source_unit"] == "thousand_VND/share"
        and manifest["price_basis"] == "provider_adjusted",
        "Explicit real stock unit/basis attestation required",
    )
    imported = []
    target = GENERATED / "datasets"
    for spec in manifest["files"]:
        path = (root / spec["file"]).resolve()
        require(path.is_relative_to(root), "Input path escapes price pack")
        raw = path.read_bytes()
        require(
            hashlib.sha256(raw).hexdigest() == spec["sha256"],
            "Raw provider file checksum mismatch",
        )
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        require(rows and len(rows) <= 5000, "Invalid price pack row count")
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "price", "symbol"])
        for row in rows:
            writer.writerow([row["time"][:10], row["close"], spec["asset_id"]])
        content = buffer.getvalue().encode()
        digest = hashlib.sha256(content).hexdigest()
        filename = f"real-{spec['asset_id']}-{digest[:16]}.csv"
        if not (target / filename).exists():
            with (target / filename).open("xb") as stream:
                stream.write(content)
            (target / filename).chmod(0o444)
        identity = f"REAL_{spec['asset_id']}_{digest[:16].upper()}"
        entry = {
            "path": filename,
            "sha256": digest,
            "asset_id": spec["asset_id"],
            "kind": "stock",
            "source_unit": manifest["source_unit"],
            "provider": f"vnstock-{manifest['library_version']}-{manifest['requested_provider']}",
            "price_column": "price",
            "price_type": "close",
            "data_origin": "real",
            "price_basis": manifest["price_basis"],
        }
        imported.append((identity, entry))
    with (target / ".catalog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        registry_file = target / "catalog.json"
        registry = json.loads(registry_file.read_text())
        for identity, entry in imported:
            require(
                identity not in registry or registry[identity] == entry,
                "Immutable dataset identity collision",
            )
            registry[identity] = entry
        temporary = target / f"catalog-{uuid4()}.tmp"
        temporary.write_text(json.dumps(registry, indent=2) + "\n")
        temporary.chmod(0o644)
        temporary.replace(registry_file)
    return manifest, imported


def verify(receipt, alice, bob):
    saved = get("/api/v1/recommendations/" + receipt["recommendation_id"], alice)
    require(
        saved["demo"] is False and saved["input_hash"] == receipt["input_hash"],
        "Real recommendation receipt mismatch",
    )
    require(
        saved["inputs_provenance"]["snapshot_hash"] == receipt["snapshot_hash"],
        "Snapshot provenance lost",
    )
    dashboard = get(f"/api/v1/portfolios/{receipt['portfolio_id']}/dashboard", alice)
    require(
        dashboard["accepted_target"]["id"] == receipt["target_id"],
        "Accepted real target changed",
    )
    require(
        dashboard["holdings_status"] == "NOT_TRACKED", "Target confused with execution"
    )
    require(
        request(
            "GET",
            PORTFOLIO + "/api/v1/recommendations/" + receipt["recommendation_id"],
            token=bob,
        )[0]
        == 404,
        "Ownership violation",
    )
    catalog = ArtifactCatalog(GENERATED / "bundles")
    from portfolio_contracts import ReadyInput

    numerical = catalog.load(
        ReadyInput.model_validate(receipt["pinned_inputs"]), "BL_ML"
    )
    numerical.pop("inference_provenance", None)
    weights = allocate(
        numerical | {"strategy": "BL_ML", "constraints": saved["constraints"]}
    )["weights"]
    require(
        max(abs(float(a) - b) for a, b in zip(saved["weights"], weights)) < 1e-10,
        "Real serving/core parity failed",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory")
    parser.add_argument("--reviewer")
    parser.add_argument("--universe-id", default="VN_EQUITY_REAL")
    parser.add_argument("--verify-receipt", action="store_true")
    args = parser.parse_args()
    accounts = json.loads((GENERATED / "accounts.json").read_text())
    settings = dict(
        line.split("=", 1)
        for line in (GENERATED / ".env").read_text().splitlines()
        if line and not line.startswith("#")
    )
    alice, bob = login("alice", accounts, settings), login("bob", accounts, settings)
    receipt_file = GENERATED / "market-quant-receipt.json"
    if args.verify_receipt:
        verify(json.loads(receipt_file.read_text()), alice, bob)
        print(
            "PASS: same real-price snapshot/model/recommendation/target and one-step parity after restart."
        )
        return
    require(
        bool(args.source_directory and args.reviewer),
        "Source pack and explicit reviewer required",
    )
    manifest, imports = register_pack(args.source_directory)
    operator = login("data-operator", accounts, settings)
    for identity, _ in imports:
        status, job = request(
            "POST",
            MARKET + "/api/v1/market/ingestions",
            token=operator,
            body={"dataset_id": identity},
            headers={"Idempotency-Key": identity},
        )
        require(status == 202, f"Real ingestion failed ({status})")
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            status, state = request("GET", MARKET + job["status_url"], token=operator)
            require(status == 200, "Cannot read ingestion job")
            if state["status"] == "SUCCEEDED":
                break
            require(state["status"] != "FAILED", "Real price ingestion failed")
            time.sleep(0.5)
        require(state["status"] == "SUCCEEDED", "Real ingestion timed out")
    status, snapshot = request(
        "POST",
        MARKET + "/api/v1/market/snapshots",
        token=operator,
        body={
            "asset_ids": [e["asset_id"] for _, e in imports],
            "start_date": max(f["first_date"] for f in manifest["files"]),
            "end_date": min(f["last_date"] for f in manifest["files"]),
            "as_of_date": utcnow().date().isoformat(),
            "max_age_days": 14,
        },
    )
    require(
        status == 201 and snapshot["data_origin"] == "real",
        f"Real snapshot failed ({status})",
    )
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        token = client.post(
            IDENTITY,
            data={
                "grant_type": "client_credentials",
                "client_id": "quant-publisher",
                "client_secret": settings["MARKET_READER_CLIENT_SECRET"],
                "scope": "market:snapshot:read",
            },
        )
        token.raise_for_status()
        source, rows = MarketReader(
            "http://localhost:8003", token.json()["access_token"], client=client
        ).load(snapshot["id"], snapshot["content_hash"])
    panel = SnapshotPanel(source, rows, expected_hash=snapshot["content_hash"])
    directory = GENERATED / "bundles"
    training = panel.training_data(panel.dates[-1] - timedelta(days=20))
    candidate = train_candidate(directory, training)
    approved = approve_candidate(directory, candidate, reviewer=args.reviewer)
    artifact = publish_snapshot(
        directory,
        source,
        rows,
        expected_hash=snapshot["content_hash"],
        universe_id=args.universe_id,
        model=approved,
    )
    catalog = ArtifactCatalog(directory)
    pin = catalog.ready(args.universe_id, "BL_ML")
    status, portfolio = request(
        "POST",
        PORTFOLIO + "/api/v1/onboarding/portfolios",
        token=alice,
        body={
            "name": "Market → Quant real-price verification",
            "capital_vnd": "100000000",
            "universe_id": args.universe_id,
            "answers": {
                "questionnaire_version": "risk-v1",
                "horizon_months": 36,
                "liquidity_need": "low",
                "loss_tolerance": "medium",
                "experience": "experienced",
            },
        },
    )
    require(status == 201, "Could not create real universe portfolio")
    proposal = propose(portfolio["id"], alice, "BL_ML")
    status, target = request(
        "POST",
        PORTFOLIO + f"/api/v1/recommendations/{proposal['id']}/accept",
        token=alice,
        body={},
        headers={"If-Match": '"1"'},
    )
    require(status == 200, "Could not accept real-data target")
    model = json.loads(read_artifact(directory, approved))
    receipt = {
        "verified_at": utcnow().isoformat(),
        "portfolio_id": portfolio["id"],
        "recommendation_id": proposal["id"],
        "target_id": target["id"],
        "snapshot_id": snapshot["id"],
        "snapshot_hash": snapshot["content_hash"],
        "input_hash": proposal["input_hash"],
        "pinned_inputs": pin.model_dump(mode="json"),
        "artifact": artifact,
        "approved_model": approved,
        "training_event_cutoff": training["training_cutoff"],
        "training_knowledge_cutoff": training["knowledge_cutoff"],
        "model_validation": model["validation"],
        "source_pack_hash": canonical_hash(manifest),
        "raw_source_files": manifest["files"],
        "universe_id": args.universe_id,
        "data_as_of": proposal["as_of_date"],
        "synthetic": False,
    }
    verify(receipt, alice, bob)
    receipt_file.write_text(json.dumps(receipt, indent=2) + "\n")
    receipt_file.chmod(0o600)
    print(
        f"PASS: real {', '.join(pin.asset_ids)} through {pin.as_of_date}; Market snapshot → features → approved XGBoost → BL_ML → accepted target; parity < 1e-10."
    )


if __name__ == "__main__":
    try:
        main()
    except SmokeFailure as exc:
        raise SystemExit("FAIL: " + str(exc)) from None
