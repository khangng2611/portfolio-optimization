#!/usr/bin/env python3
"""Validate a staging env file without connecting or displaying expanded secrets."""

from __future__ import annotations

import argparse
import base64
import binascii
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

SERVICES = ("PORTFOLIO", "QUANT", "MARKET")
REQUIRED = (
    "WEB_IMAGE",
    "PORTFOLIO_IMAGE",
    "QUANT_IMAGE",
    "MARKET_IMAGE",
    "APP_ORIGIN",
    "OIDC_ISSUER",
    "OIDC_JWKS_URL",
    "OIDC_TOKEN_URL",
    "OIDC_INTERNAL_ORIGIN",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "QUANT_CLIENT_SECRET",
    "SESSION_ENCRYPTION_KEY",
    "REDIS_URL",
    "BUNDLE_DIRECTORY",
    "DATASET_DIRECTORY",
    "TLS_CA_DIRECTORY",
) + tuple(
    service + suffix
    for service in SERVICES
    for suffix in (
        "_DATABASE_URL",
        "_MIGRATION_DATABASE_URL",
        "_PUBLISHER_BROKER_URL",
        "_CONSUMER_BROKER_URL",
    )
)


def validate(values: dict[str, str], allow_example: bool = False) -> None:
    for key in ("ALLOW_INSECURE_HTTP", "ALLOW_DEMO_INPUTS"):
        if values.get(key, "false").lower() != "false":
            raise ValueError(f"{key} must remain disabled in staging")
    if values.get("OIDC_CLIENT_ID") == "portfolio-test":
        raise ValueError("OIDC_CLIENT_ID must be a deployed confidential BFF client")
    for key in REQUIRED:
        value = values.get(key, "")
        if not value or (not allow_example and "CHANGE_ME" in value):
            raise ValueError(f"{key} is required with a real staging value")
    for key in ("WEB_IMAGE", "PORTFOLIO_IMAGE", "QUANT_IMAGE", "MARKET_IMAGE"):
        value = values[key]
        pinned_digest = bool(re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", value))
        image_name, separator, tag = value.rsplit("/", 1)[-1].partition(":")
        if not pinned_digest and (
            not image_name
            or not separator
            or not tag
            or tag in ("latest", "local")
            or re.search(r"\s", tag)
        ):
            raise ValueError(f"{key} requires an explicit release tag or sha256 digest")
    for key in (
        "APP_ORIGIN",
        "OIDC_ISSUER",
        "OIDC_JWKS_URL",
        "OIDC_TOKEN_URL",
        "OIDC_INTERNAL_ORIGIN",
    ):
        url = urlsplit(values[key])
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(f"{key} requires an HTTPS endpoint")
        if key in ("APP_ORIGIN", "OIDC_INTERNAL_ORIGIN") and url.path not in ("", "/"):
            raise ValueError(f"{key} must be an HTTPS origin")
    redis = urlsplit(values["REDIS_URL"])
    if redis.scheme != "rediss" or not redis.hostname or not redis.password:
        raise ValueError("REDIS_URL requires TLS and a runtime credential")
    database_ids = set()
    broker_users = set()
    for service in SERVICES:
        urls = []
        for suffix in ("_DATABASE_URL", "_MIGRATION_DATABASE_URL"):
            key = service + suffix
            url = urlsplit(values[key])
            query = parse_qs(url.query)
            if (
                url.scheme != "postgresql+psycopg"
                or not url.hostname
                or not url.username
                or not url.password
                or url.path in ("", "/")
                or query.get("sslmode") != ["verify-full"]
            ):
                raise ValueError(f"{key} requires a credential and sslmode=verify-full")
            urls.append(url)
        runtime, migrator = urls
        if (runtime.hostname, runtime.port, runtime.path) != (
            migrator.hostname,
            migrator.port,
            migrator.path,
        ) or runtime.username == migrator.username:
            raise ValueError(
                f"{service}_DATABASE_URL must share only its own database with a separate migrator identity"
            )
        database_id = (runtime.hostname, runtime.port or 5432, runtime.path)
        if database_id in database_ids:
            raise ValueError(f"{service}_DATABASE_URL must have its own database")
        database_ids.add(database_id)
        for suffix in ("_PUBLISHER_BROKER_URL", "_CONSUMER_BROKER_URL"):
            key = service + suffix
            url = urlsplit(values[key])
            if (
                url.scheme != "amqps"
                or not url.hostname
                or not url.username
                or not url.password
                or url.path in ("", "/")
                or url.query
            ):
                raise ValueError(
                    f"{key} requires AMQPS and a dedicated runtime credential"
                )
            if url.username in broker_users:
                raise ValueError(f"{key} requires a distinct broker identity")
            broker_users.add(url.username)
    try:
        key_bytes = base64.b64decode(values["SESSION_ENCRYPTION_KEY"], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("SESSION_ENCRYPTION_KEY must encode 32 random bytes") from None
    if len(key_bytes) != 32 or (not allow_example and key_bytes == bytes(32)):
        raise ValueError("SESSION_ENCRYPTION_KEY must encode 32 random bytes")
    for key in ("BUNDLE_DIRECTORY", "DATASET_DIRECTORY", "TLS_CA_DIRECTORY"):
        if not Path(values[key]).is_absolute():
            raise ValueError(f"{key} must be an absolute host path")


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
            raise ValueError("Invalid env-file assignment")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument(
        "--allow-example",
        action="store_true",
        help="Only validate disposable placeholders for CI; never authorizes deployment",
    )
    args = parser.parse_args()
    try:
        validate(read_env(args.env_file), allow_example=args.allow_example)
    except (ValueError, OSError):
        raise SystemExit(
            "Invalid staging configuration. Check required endpoints, secrets, image versions and separate identities; values were not printed."
        ) from None
    print("Staging template configuration validated; no services were deployed.")


if __name__ == "__main__":
    main()
