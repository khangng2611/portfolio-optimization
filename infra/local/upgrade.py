#!/usr/bin/env python3
"""Add the Market milestone to a healthy disposable local stack without resetting it.

Run bootstrap.py first, then this script from the software virtual environment.
Only local endpoints and the fixed portfolio-software Compose project are used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import httpx

try:
    from .bootstrap import make_rabbit_definitions, make_realm
except ImportError:
    from bootstrap import make_rabbit_definitions, make_realm

ROOT = Path(__file__).resolve().parent
REALM = "/admin/realms/portfolio"


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


def reconcile_identity(
    client: httpx.Client, values: dict[str, str], test_client: bool
) -> None:
    desired = make_realm(values, [], test_client)

    def get(path: str, **kwargs):
        response = client.get(REALM + path, **kwargs)
        response.raise_for_status()
        return response.json()

    def post(path: str, representation: dict):
        response = client.post(REALM + path, json=representation)
        response.raise_for_status()

    scopes = {scope["name"]: scope for scope in get("/client-scopes")}
    for scope in desired["clientScopes"]:
        if (
            scope["name"] in ("basic", "market:read", "market:write")
            and scope["name"] not in scopes
        ):
            post("/client-scopes", scope)
    scopes = {scope["name"]: scope for scope in get("/client-scopes")}
    for wanted in desired["clients"]:
        name = wanted["clientId"]
        if name not in (
            "market-api",
            "portfolio-test",
            "portfolio-web",
            "portfolio-service",
        ):
            continue
        existing = get("/clients", params={"clientId": name})
        if not existing:
            post("/clients", wanted)
            existing = get("/clients", params={"clientId": name})
        if len(existing) != 1:
            raise RuntimeError("Expected one local identity client")
        if name == "market-api":
            continue
        identity = existing[0]["id"]
        defaults = get(f"/clients/{identity}/default-client-scopes")
        attached = {scope["name"] for scope in defaults}
        required_scopes = (
            ("basic", "market:read", "market:write")
            if name == "portfolio-test"
            else ("basic",)
        )
        for scope_name in required_scopes:
            if scope_name not in attached:
                response = client.put(
                    f"{REALM}/clients/{identity}/default-client-scopes/{scopes[scope_name]['id']}"
                )
                response.raise_for_status()
        if name != "portfolio-test":
            continue
        mappers = get(f"/clients/{identity}/protocol-mappers/models")
        if not any(
            mapper.get("config", {}).get("included.client.audience") == "market-api"
            for mapper in mappers
        ):
            mapper = next(
                mapper
                for mapper in wanted["protocolMappers"]
                if mapper["name"] == "audience-market-api"
            )
            post(f"/clients/{identity}/protocol-mappers/models", mapper)


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


def upgrade_identity(values: dict[str, str], test_client: bool) -> None:
    with httpx.Client(base_url="http://localhost:8080", timeout=15) as client:
        response = client.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "local-admin",
                "password": values["KEYCLOAK_ADMIN_PASSWORD"],
            },
        )
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        reconcile_identity(client, values, test_client)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        values = json.loads((ROOT / ".generated/secrets.json").read_text())
        settings = json.loads((ROOT / ".generated/settings.json").read_text())
        for name, operation in (
            ("database", upgrade_databases),
            ("broker", lambda: upgrade_broker(values)),
            (
                "identity",
                lambda: upgrade_identity(values, bool(settings["test_client"])),
            ),
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
