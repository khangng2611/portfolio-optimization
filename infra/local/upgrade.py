#!/usr/bin/env python3
"""Add owner services to a healthy disposable local stack without resetting it.

Run bootstrap.py first, then this script from the software virtual environment.
Only local endpoints and the fixed portfolio-auth-demo Compose project are used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import httpx

try:
    from .bootstrap import make_rabbit_definitions
except ImportError:
    from bootstrap import make_rabbit_definitions

ROOT = Path(__file__).resolve().parent


def market_broker_definitions(values: dict[str, str]) -> dict:
    """Import only new Market resources; leave existing credentials/queues intact."""
    definitions = make_rabbit_definitions(values)
    for section in ("users", "exchanges", "queues"):
        definitions[section] = [
            item for item in definitions[section] if item["name"].startswith("market")
        ]
    definitions["permissions"] = [
        item
        for item in definitions["permissions"]
        if item["user"].startswith("market_")
    ]
    definitions["bindings"] = [
        item
        for item in definitions["bindings"]
        if item["destination"].startswith("market.")
    ]
    # The existing named policy is extended to Market without changing old queues.
    return definitions


def upgrade_databases() -> None:
    command = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".generated/.env"),
        "-f",
        str(ROOT / "compose.yaml"),
        "exec",
        "-T",
        "postgres",
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "local_admin",
        "-d",
        "postgres",
    ]
    # Never log psql stderr: an SQL error can include a generated password literal.
    with (ROOT / ".generated/postgres/10-databases.sql").open() as source:
        result = subprocess.run(
            command, stdin=source, capture_output=True, timeout=60, check=False
        )
    if result.returncode:
        raise RuntimeError("Local database provisioning failed; no volumes were reset")


def upgrade_knowledge_database():
    command = [
        "docker",
        "compose",
        "--env-file",
        str(ROOT / ".generated/.env"),
        "-f",
        str(ROOT / "compose.yaml"),
        "exec",
        "-T",
        "knowledge-postgres",
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "knowledge_admin",
        "-d",
        "postgres",
    ]
    with (ROOT / ".generated/knowledge-postgres/10-databases.sql").open() as source:
        result = subprocess.run(
            command, stdin=source, capture_output=True, timeout=60, check=False
        )
    if result.returncode:
        raise RuntimeError(
            "Knowledge database provisioning failed; existing volumes preserved"
        )


def upgrade_broker(values: dict[str, str]) -> None:
    with httpx.Client(
        base_url="http://127.0.0.1:15673",
        auth=("local_admin", values["RABBITMQ_ADMIN_PASSWORD"]),
        timeout=15,
    ) as client:
        response = client.post(
            "/api/definitions", json=market_broker_definitions(values)
        )
        response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        values = json.loads((ROOT / ".generated/secrets.json").read_text())
        for name, operation in (
            ("database", upgrade_databases),
            ("knowledge database", upgrade_knowledge_database),
            ("broker", lambda: upgrade_broker(values)),
        ):
            try:
                operation()
            except (
                httpx.HTTPError,
                RuntimeError,
                subprocess.SubprocessError,
                OSError,
                KeyError,
            ):
                raise SystemExit(
                    f"Local {name} upgrade failed. Start the dependency services and retry; credentials were not printed."
                ) from None
            print(
                f"Local {name} configuration reconciled; existing data and credentials preserved."
            )
    except FileNotFoundError:
        raise SystemExit("Run infra/local/bootstrap.py before upgrade.py.") from None


if __name__ == "__main__":
    main()
