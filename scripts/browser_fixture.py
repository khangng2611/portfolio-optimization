#!/usr/bin/env python3
"""Explicit LOCAL disposable browser fixtures, never an HTTP test bypass.

Creates only synthetic DEMO artifacts (no network/market downloads). Catalog
updates are atomic and immutable old bundles stay available to accepted jobs.
Session expiry deletes one named session through the local Redis service;
the opaque cookie is read only from stdin and is never printed or put in argv.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "infra/local/.generated"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["ready", "expired", "expire-session"])
    parser.add_argument("--disposable", required=True, action="store_true")
    args = parser.parse_args()
    if not (GENERATED / "accounts.json").is_file():
        raise SystemExit("Bootstrap the localhost disposable stack first")
    if args.action == "expire-session":
        session_id = sys.stdin.read().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", session_id):
            raise SystemExit("Invalid opaque local session identifier")
        # The redis service already has REDISCLI_AUTH in its private environment.
        # -x appends the exact key from stdin; neither ID nor password enters argv.
        result = subprocess.run(
            ["docker", "compose", "--env-file", str(GENERATED / ".env"),
             "-f", str(ROOT / "infra/local/compose.yaml"), "exec", "-T",
             "redis", "redis-cli", "--raw", "-x", "DEL"],
            input="session:" + session_id, text=True, capture_output=True, cwd=ROOT,
        )
        if result.returncode or result.stdout.strip() != "1":
            raise SystemExit("Local session expiry failed (details withheld)")
        print("Expired one disposable BFF session")
        return
    directory = GENERATED / "bundles"
    directory.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    expired = args.action == "expired"
    identity = "browser-demo-" + str(uuid4())
    bundle = {
        "schema_version": 1, "bundle_id": identity, "universe_id": "DEMO",
        "snapshot_id": "synthetic-" + identity, "model_bundle_id": None,
        "model_status": None,
        "as_of_date": (now - timedelta(days=2 if expired else 0)).date().isoformat(),
        "valid_until": (now + timedelta(days=-1 if expired else 1)).isoformat(),
        "demo": True, "strategies": ["EW", "MVO"],
        "numerical": {
            "asset_ids": ["AAA", "BBB", "VFF"],
            "mean_returns": [0.001, 0.0005, 0.0001],
            "covariance": [[0.0004, 0, 0], [0, 0.0003, 0], [0, 0, 0.00005]],
        },
    }
    content = (json.dumps(bundle, indent=2) + "\n").encode()
    artifact = directory / (identity + ".json")
    with artifact.open("xb") as stream:
        stream.write(content)
    artifact.chmod(0o444)
    catalog = directory / "catalog.json"
    with (directory / ".catalog.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        entries = json.loads(catalog.read_text())["bundles"] if catalog.exists() else []
        entry = {"file": artifact.name, "sha256": hashlib.sha256(content).hexdigest(),
                 "universe_id": "DEMO", "bundle_id": identity, "demo": True}
        pending = directory / (".browser-catalog-" + str(uuid4()) + ".tmp")
        pending.write_text(json.dumps({"bundles": [entry] + entries}, indent=2) + "\n")
        pending.chmod(0o644)
        pending.replace(catalog)
    print("Registered immutable synthetic DEMO: " + args.action)


if __name__ == "__main__":
    main()
