#!/usr/bin/env python3
"""Check a clean private-demo release and its rendered Compose configuration."""

import argparse
import json
import os
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(command):
    try:
        return subprocess.run(
            command, cwd=ROOT, check=True, capture_output=True, text=True, timeout=60,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        # Compose diagnostics can expand credentials from the generated environment.
        raise ValueError("Command failed; check Git/Docker and the generated config locally.") from None


def check_release(release):
    commit = run(["git", "rev-parse", "HEAD"])
    expected = run(["git", "rev-parse", "--verify", "--end-of-options", release + "^{commit}"])
    if commit != expected:
        raise ValueError("HEAD does not match the requested release.")
    if run(["git", "status", "--porcelain", "--untracked-files=all"]):
        raise ValueError("Release checkout must be clean, including untracked files.")
    return commit


def validate_origin(origin):
    if origin != "http://localhost:3000" and not re.fullmatch(
        r"https://(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+ts\.net", origin,
    ):
        raise ValueError("Expected a localhost origin or HTTPS Tailscale Funnel origin.")


def validate_compose(config, *, origin="http://localhost:3000"):
    validate_origin(origin)
    if config["name"] != "portfolio-auth-demo":
        raise ValueError("Use the portfolio-auth-demo project required by the smoke scripts.")
    services = config["services"]
    web = services["web"]["environment"]
    if web["APP_ORIGIN"] != origin:
        raise ValueError("APP_ORIGIN must match the requested demo origin.")
    if web["ALLOW_INSECURE_HTTP"] != "true":
        raise ValueError("The demo requires the existing HTTP configuration for internal Auth.")
    for service in services.values():
        if service.get("network_mode"):
            raise ValueError("Explicit network_mode bypasses the private Compose network.")
        for port in service.get("ports", []):
            if port.get("host_ip") not in ("127.0.0.1", "::1"):
                raise ValueError("Every published port must bind explicitly to loopback.")
        environment = service.get("environment", {})
        for key in (
            "OPENAI_API_KEY", "CHAT_LLM_PROVIDER", "CHAT_PROVIDER_URL", "CHAT_PROVIDER_KEY",
            "KNOWLEDGE_PAID_APPROVAL", "KNOWLEDGE_BUDGET_USD",
        ):
            if environment.get(key):
                raise ValueError("External provider configuration is outside this demo release.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True, help="Expected commit or immutable tag")
    parser.add_argument("--funnel-origin", help="Expected HTTPS origin on ts.net")
    args = parser.parse_args()
    if args.funnel_origin:
        validate_origin(args.funnel_origin)
        if not args.funnel_origin.startswith("https://"):
            raise ValueError("Funnel origin requires HTTPS.")
        os.environ["DEMO_PUBLIC_ORIGIN"] = args.funnel_origin
    commit = check_release(args.release)
    command = [
        "docker", "compose", "--env-file", str(ROOT / "infra/local/.generated/.env"),
        "-f", str(ROOT / "infra/local/compose.yaml"),
    ]
    if args.funnel_origin:
        command += ["-f", str(ROOT / "infra/public/compose.funnel.yaml")]
    config = json.loads(run(command + ["config", "--format", "json"]))
    validate_compose(config, origin=args.funnel_origin or "http://localhost:3000")
    print(f"PASS: clean release {commit}, loopback-only Compose, provider configuration absent.")
    print("Next: verify running services, application flows and the SSH boundary on the VPS.")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit("FAIL: " + str(error)) from None
    except (KeyError, TypeError):
        raise SystemExit("FAIL: private demo checks failed; inspect the checkout and Compose configuration locally.") from None
