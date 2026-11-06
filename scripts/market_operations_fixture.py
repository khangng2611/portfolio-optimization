#!/usr/bin/env python3
"""Prepare bounded, explicitly disposable Market Operations browser inventory.

Reuses verified bytes and provenance from existing REAL stock sources. It never
downloads, edits prices, changes research data, credentials, SQL or bundle files.
New catalog aliases exercise registration even when originals are already pinned.
The sole invalid source is clearly synthetic and must be quarantined by Market.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "infra/local/.generated"


def prepare():
    if os.environ.get("E2E_DISPOSABLE_STACK") != "1":
        raise ValueError(
            "Set E2E_DISPOSABLE_STACK=1 for the disposable localhost stack"
        )
    if not (GENERATED / "accounts.json").is_file():
        raise ValueError("Bootstrap the disposable localhost stack first")
    directory = GENERATED / "datasets"
    catalog = directory / "catalog.json"
    run_id = uuid4().hex[:12].upper()
    with (directory / ".catalog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = json.loads(catalog.read_text())
        selected = {}
        # Prefer original imports, avoiding aliases from previous browser runs.
        for identity, spec in sorted(entries.items()):
            if not identity.startswith("REAL_") or spec.get("data_origin") != "real":
                continue
            if (
                spec.get("kind") != "stock"
                or spec.get("price_basis") != "provider_adjusted"
            ):
                continue
            asset = spec.get("asset_id", "")
            if not re.fullmatch(r"[A-Z0-9_-]{1,32}", asset) or asset in selected:
                continue
            source = (directory / spec["path"]).resolve()
            if not source.is_relative_to(directory.resolve()):
                raise ValueError(
                    "Trusted real source escapes disposable datasets directory"
                )
            raw = source.read_bytes()
            if (
                len(raw) > 4 * 1024 * 1024
                or hashlib.sha256(raw).hexdigest() != spec["sha256"]
            ):
                raise ValueError(
                    "Existing real source checksum does not match its inventory pin"
                )
            rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
            dates = sorted({date.fromisoformat(row["date"]) for row in rows})
            if not 61 <= len(dates) <= 5000:
                continue
            alias = f"OPS_REAL_{asset}_{run_id}"
            selected[asset] = {
                "dataset_id": alias,
                "original_dataset_id": identity,
                "sha256": spec["sha256"],
                "asset_id": asset,
                "provider": spec["provider"],
                "start_date": dates[0].isoformat(),
                "end_date": dates[-1].isoformat(),
                "row_count": len(rows),
                "data_origin": "real",
                "price_basis": "provider_adjusted",
            }
            entries[alias] = dict(spec)
            if len(selected) == 3:
                break
        if len(selected) != 3:
            raise ValueError(
                "Three existing real, adjusted, SHA-pinned stock sources with 61 sessions are required"
            )
        today = datetime.now(timezone.utc).date()
        start = max(item["start_date"] for item in selected.values())
        end = min(item["end_date"] for item in selected.values())
        age = (today - date.fromisoformat(end)).days
        if not 0 <= age <= 14:
            raise ValueError(
                "Existing real sources are stale; provide a new attested real source pack"
            )
        invalid_id = "OPS_SYNTHETIC_BAD_" + run_id
        invalid_asset = "OPS_SYNTHETIC_" + run_id
        # Negative price is rejected before any observation revision is written.
        content = f"date,price,symbol\n{end},-1,{invalid_asset}\n".encode()
        name = invalid_id.lower() + ".csv"
        artifact = directory / name
        with artifact.open("xb") as stream:
            stream.write(content)
        artifact.chmod(0o444)
        bad_hash = hashlib.sha256(content).hexdigest()
        entries[invalid_id] = {
            "path": name,
            "sha256": bad_hash,
            "asset_id": invalid_asset,
            "kind": "stock",
            "source_unit": "VND/share",
            "provider": "synthetic-disposable-browser-quality-fixture",
            "price_column": "price",
            "price_type": "close",
            "data_origin": "synthetic",
            "price_basis": "raw_close",
        }
        temporary = directory / (".ops-catalog-" + run_id + ".tmp")
        temporary.write_text(json.dumps(entries, indent=2) + "\n")
        temporary.chmod(0o644)
        temporary.replace(catalog)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "sources": list(selected.values()),
        "asset_ids": list(selected),
        "start_date": start,
        "end_date": end,
        "as_of_date": today.isoformat(),
        "max_age_days": 14,
        "universe_id": "VN_EQUITY_REAL",
        "invalid": {
            "dataset_id": invalid_id,
            "sha256": bad_hash,
            "asset_id": invalid_asset,
        },
    }
    receipt = GENERATED / "market-operations-fixture.json"
    temporary = GENERATED / (".ops-fixture-" + run_id + ".tmp")
    with open(
        temporary, "x", opener=lambda path, flags: os.open(path, flags, 0o600)
    ) as stream:
        stream.write(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(receipt)
    print(
        "Prepared three unchanged real-price aliases and one synthetic quarantine source"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare"])
    parser.add_argument("--disposable", required=True, action="store_true")
    parser.parse_args()
    try:
        prepare()
    except (ValueError, OSError, KeyError, TypeError):
        raise SystemExit(
            "Disposable Market Operations fixture preparation failed; inspect source inventory locally"
        ) from None


if __name__ == "__main__":
    main()
