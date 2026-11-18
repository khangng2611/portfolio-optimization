"""Use the private local issuer from host smoke scripts without a public token port."""

import base64
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "infra/local/.generated"


def auth_request(action, body, *, generated=GENERATED):
    if action == "set-enabled" and os.environ.get("E2E_DISPOSABLE_STACK") != "1":
        raise RuntimeError("Account fixtures require E2E_DISPOSABLE_STACK=1.")
    try:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-p",
                "portfolio-auth-demo",
                "--env-file",
                str(generated / ".env"),
                "-f",
                str(ROOT / "infra/local/compose.yaml"),
                "exec",
                "-T",
                "auth-api",
                "python",
                "-m",
                "auth_service.local_fixture",
                action,
            ],
            input=json.dumps(body),
            text=True,
            capture_output=True,
            check=True,
            timeout=20,
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise RuntimeError("Local Auth unavailable; check the demo stack.") from None


def login(username, *, generated=GENERATED):
    accounts = json.loads((generated / "accounts.json").read_text())["users"]
    account = next((user for user in accounts if user["username"] == username), None)
    if account is None:
        raise RuntimeError("Required seeded account unavailable.")
    status, response = auth_request(
        "login",
        {"username": username, "password": account["password"]},
        generated=generated,
    )
    if status != 200:
        raise RuntimeError(f"Local account login failed ({status}).")
    return response["accessToken"]


def service_token(client_id, scope=None):
    body = {"client_id": client_id}
    if scope is not None:
        body["scope"] = scope
    status, response = auth_request("token", body)
    if status != 200:
        raise RuntimeError(f"Local service token request failed ({status}).")
    return response["access_token"]


def claims(token):
    # Used by local probes for issued claims, alongside actual API signature checks.
    segment = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
