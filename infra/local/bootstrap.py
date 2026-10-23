#!/usr/bin/env python3
"""Create disposable localhost-only configuration. Existing secrets are never rotated."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / ".generated"
ROLES = ["investor", "researcher", "data-operator", "model-reviewer", "system-admin"]
LEGACY_SECRET_NAMES = [
    "POSTGRES_PASSWORD",
    "IDENTITY_MIGRATOR_PASSWORD",
    "IDENTITY_RUNTIME_PASSWORD",
    "PORTFOLIO_MIGRATOR_PASSWORD",
    "PORTFOLIO_RUNTIME_PASSWORD",
    "QUANT_MIGRATOR_PASSWORD",
    "QUANT_RUNTIME_PASSWORD",
    "KEYCLOAK_ADMIN_PASSWORD",
    "OIDC_CLIENT_SECRET",
    "QUANT_CLIENT_SECRET",
    "TEST_CLIENT_SECRET",
    "REDIS_PASSWORD",
    "RABBITMQ_ADMIN_PASSWORD",
    "PORTFOLIO_PUBLISHER_PASSWORD",
    "PORTFOLIO_CONSUMER_PASSWORD",
    "QUANT_PUBLISHER_PASSWORD",
    "QUANT_CONSUMER_PASSWORD",
]
MARKET_SECRET_NAMES = [
    "MARKET_MIGRATOR_PASSWORD",
    "MARKET_RUNTIME_PASSWORD",
    "MARKET_PUBLISHER_PASSWORD",
    "MARKET_CONSUMER_PASSWORD",
]
SECRET_NAMES = LEGACY_SECRET_NAMES + MARKET_SECRET_NAMES


def write_private(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    path.chmod(0o600)


def json_text(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def create_secrets() -> dict[str, str]:
    path = GENERATED / "secrets.json"
    if path.exists():
        values = json.loads(path.read_text())
        missing = set(LEGACY_SECRET_NAMES + ["SESSION_ENCRYPTION_KEY"]) - values.keys()
        if missing:
            raise SystemExit(
                "Existing secrets are incomplete; restore secrets.json rather than silently rotating credentials."
            )
        additions = set(MARKET_SECRET_NAMES) - values.keys()
        if additions:
            values.update({name: secrets.token_hex(32) for name in sorted(additions)})
            write_private(path, json_text(values))
        return values
    values = {name: secrets.token_hex(32) for name in SECRET_NAMES}
    values["SESSION_ENCRYPTION_KEY"] = base64.b64encode(
        secrets.token_bytes(32)
    ).decode()
    write_private(path, json_text(values))
    return values


def create_accounts() -> list[dict[str, str]]:
    path = GENERATED / "accounts.json"
    if path.exists():
        stored = json.loads(path.read_text())
        accounts = stored["users"] if isinstance(stored, dict) else stored
        for account in accounts:
            account["roles"] = account.get("roles") or [account.pop("role")]
    else:
        accounts = [
            {
                "username": "alice",
                "roles": ["investor"],
                "password": secrets.token_urlsafe(24),
            },
            {
                "username": "bob",
                "roles": ["investor"],
                "password": secrets.token_urlsafe(24),
            },
        ] + [
            {"username": role, "roles": [role], "password": secrets.token_urlsafe(24)}
            for role in ROLES[1:]
        ]
    write_private(path, json_text({"users": accounts}))
    return accounts


def make_database_sql(values: dict[str, str]) -> str:
    lines = [
        "-- Generated disposable local credentials. Never commit this file.",
        "REVOKE ALL ON DATABASE postgres FROM PUBLIC;",
        "REVOKE ALL ON DATABASE template1 FROM PUBLIC;",
    ]
    for name in ("identity", "portfolio", "quant", "market"):
        owner, migrator, runtime, database = [
            f"{name}_{suffix}" for suffix in ("owner", "migrator", "runtime", "db")
        ]
        lines += [
            f"SELECT 'CREATE ROLE {owner} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{owner}') \\gexec",
            f"SELECT 'CREATE ROLE {migrator} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD ''{values[name.upper() + '_MIGRATOR_PASSWORD']}''' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{migrator}') \\gexec",
            f"SELECT 'CREATE ROLE {runtime} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD ''{values[name.upper() + '_RUNTIME_PASSWORD']}''' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{runtime}') \\gexec",
            f"GRANT {owner} TO {migrator};",
            f"SELECT 'CREATE DATABASE {database} OWNER {owner}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{database}') \\gexec",
            f"REVOKE ALL ON DATABASE {database} FROM PUBLIC;",
            f"GRANT CONNECT ON DATABASE {database} TO {migrator}, {runtime};",
            f"ALTER ROLE {migrator} IN DATABASE {database} SET role = '{owner}';",
            f"\\connect {database}",
            "REVOKE ALL ON SCHEMA public FROM PUBLIC;",
            f"ALTER SCHEMA public OWNER TO {owner};",
            f"GRANT USAGE ON SCHEMA public TO {runtime};",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {runtime};",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {runtime};",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner} IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;",
            "\\connect postgres",
        ]
    return "\n".join(lines) + "\n"


def audience_mapper(audience: str) -> dict:
    return {
        "name": f"audience-{audience}",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-audience-mapper",
        "consentRequired": False,
        "config": {
            "included.client.audience": audience,
            "id.token.claim": "false",
            "access.token.claim": "true",
        },
    }


def make_realm(
    values: dict[str, str], accounts: list[dict[str, str]], test_client: bool
) -> dict:
    roles_mapper = {
        "name": "realm-roles",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-realm-role-mapper",
        "consentRequired": False,
        "config": {
            "multivalued": "true",
            "claim.name": "realm_access.roles",
            "jsonType.label": "String",
            "id.token.claim": "true",
            "access.token.claim": "true",
        },
    }
    scopes = [
        {
            "name": "basic",
            "protocol": "openid-connect",
            "attributes": {"include.in.token.scope": "false"},
            "protocolMappers": [
                {
                    "name": "subject",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-sub-mapper",
                    "consentRequired": False,
                    "config": {
                        "access.token.claim": "true",
                        "introspection.token.claim": "true",
                        "lightweight.claim": "true",
                    },
                }
            ],
        },
        {
            "name": "profile",
            "protocol": "openid-connect",
            "attributes": {"include.in.token.scope": "true"},
            "protocolMappers": [
                {
                    "name": "username",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-usermodel-property-mapper",
                    "config": {
                        "user.attribute": "username",
                        "claim.name": "preferred_username",
                        "jsonType.label": "String",
                        "id.token.claim": "true",
                        "access.token.claim": "true",
                        "userinfo.token.claim": "true",
                    },
                }
            ],
        },
        {
            "name": "email",
            "protocol": "openid-connect",
            "attributes": {"include.in.token.scope": "true"},
            "protocolMappers": [
                {
                    "name": "email",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-usermodel-property-mapper",
                    "config": {
                        "user.attribute": "email",
                        "claim.name": "email",
                        "jsonType.label": "String",
                        "id.token.claim": "true",
                        "access.token.claim": "true",
                        "userinfo.token.claim": "true",
                    },
                }
            ],
        },
        {
            "name": "roles",
            "protocol": "openid-connect",
            "attributes": {"include.in.token.scope": "false"},
            "protocolMappers": [roles_mapper],
        },
    ] + [
        {
            "name": name,
            "protocol": "openid-connect",
            "attributes": {"include.in.token.scope": "true"},
            "protocolMappers": [],
        }
        for name in [
            "portfolio:read",
            "portfolio:write",
            "quant:resolve",
            "market:read",
            "market:write",
        ]
    ]
    web = {
        "clientId": "portfolio-web",
        "name": "Local browser BFF",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "secret": values["OIDC_CLIENT_SECRET"],
        "standardFlowEnabled": True,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "redirectUris": ["http://localhost:3000/auth/callback"],
        "webOrigins": ["http://localhost:3000"],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "post.logout.redirect.uris": "http://localhost:3000/*",
        },
        "defaultClientScopes": [
            "basic",
            "profile",
            "email",
            "roles",
            "portfolio:read",
            "portfolio:write",
        ],
        "optionalClientScopes": [],
        "protocolMappers": [audience_mapper("portfolio-api")],
    }
    service = {
        "clientId": "portfolio-service",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "secret": values["QUANT_CLIENT_SECRET"],
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": True,
        "defaultClientScopes": ["basic", "quant:resolve"],
        "optionalClientScopes": [],
        "protocolMappers": [audience_mapper("quant-api")],
    }
    clients = [web, service] + [
        {
            "clientId": name,
            "enabled": True,
            "protocol": "openid-connect",
            "bearerOnly": True,
        }
        for name in ["portfolio-api", "quant-api", "market-api"]
    ]
    if test_client:
        clients.append(
            {
                "clientId": "portfolio-test",
                "name": "DEV ONLY integration password grant",
                "description": "Disposable local tests only. Never import this client into a deployed realm.",
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "secret": values["TEST_CLIENT_SECRET"],
                "standardFlowEnabled": False,
                "implicitFlowEnabled": False,
                "directAccessGrantsEnabled": True,
                "serviceAccountsEnabled": False,
                "defaultClientScopes": [
                    "basic",
                    "profile",
                    "email",
                    "roles",
                    "portfolio:read",
                    "portfolio:write",
                    "market:read",
                    "market:write",
                ],
                "optionalClientScopes": [],
                "protocolMappers": [
                    audience_mapper("portfolio-api"),
                    audience_mapper("market-api"),
                ],
            }
        )
    return {
        "realm": "portfolio",
        "enabled": True,
        "displayName": "Portfolio — local development",
        "sslRequired": "none",
        "registrationAllowed": False,
        "resetPasswordAllowed": False,
        "rememberMe": False,
        "loginWithEmailAllowed": True,
        "duplicateEmailsAllowed": False,
        "bruteForceProtected": True,
        "accessTokenLifespan": 300,
        "ssoSessionIdleTimeout": 1800,
        "ssoSessionMaxLifespan": 28800,
        "revokeRefreshToken": True,
        "refreshTokenMaxReuse": 0,
        "roles": {"realm": [{"name": role} for role in ROLES]},
        "clientScopes": scopes,
        "clients": clients,
        "users": [
            {
                "username": account["username"],
                "enabled": True,
                "emailVerified": True,
                "email": account["username"] + "@example.invalid",
                "firstName": account["username"],
                "lastName": "Local",
                "requiredActions": [],
                "realmRoles": account["roles"],
                "credentials": [
                    {
                        "type": "password",
                        "value": account["password"],
                        "temporary": False,
                    }
                ],
            }
            for account in accounts
        ],
    }


def rabbit_password_hash(password: str) -> str:
    salt = secrets.token_bytes(4)
    return base64.b64encode(
        salt + hashlib.sha256(salt + password.encode()).digest()
    ).decode()


def make_rabbit_definitions(values: dict[str, str]) -> dict:
    users = [("local_admin", "RABBITMQ_ADMIN_PASSWORD", ["administrator"])] + [
        (name, name.upper() + "_PASSWORD", [])
        for name in [
            "portfolio_publisher",
            "portfolio_consumer",
            "quant_publisher",
            "quant_consumer",
            "market_publisher",
            "market_consumer",
        ]
    ]
    permissions = [
        {
            "user": "local_admin",
            "vhost": "portfolio",
            "configure": ".*",
            "write": ".*",
            "read": ".*",
        }
    ]
    for name, exchange, queue in [
        ("portfolio", "portfolio.commands", "portfolio.results.v1"),
        ("quant", "portfolio.events", "quant.optimize.v1"),
        ("market", "market.commands", "market.ingest.v1"),
    ]:
        permissions += [
            {
                "user": name + "_publisher",
                "vhost": "portfolio",
                "configure": "^$",
                "write": "^" + exchange.replace(".", "\\.") + "$",
                "read": "^$",
            },
            {
                "user": name + "_consumer",
                "vhost": "portfolio",
                "configure": "^$",
                "write": "^$",
                "read": "^" + queue.replace(".", "\\.") + "$",
            },
        ]
    queues, bindings = [], []
    for name, exchange in [
        ("quant.optimize.v1", "portfolio.commands"),
        ("portfolio.results.v1", "portfolio.events"),
        ("market.ingest.v1", "market.commands"),
    ]:
        queues.extend(
            [
                {
                    "name": name,
                    "vhost": "portfolio",
                    "durable": True,
                    "auto_delete": False,
                    "arguments": {
                        "x-queue-type": "quorum",
                        "x-delivery-limit": 3,
                        "x-dead-letter-exchange": "portfolio.dead",
                    },
                },
                {
                    "name": name + ".dead",
                    "vhost": "portfolio",
                    "durable": True,
                    "auto_delete": False,
                    "arguments": {"x-queue-type": "quorum"},
                },
            ]
        )
        bindings.extend(
            [
                {
                    "source": exchange,
                    "vhost": "portfolio",
                    "destination": name,
                    "destination_type": "queue",
                    "routing_key": name,
                    "arguments": {},
                },
                {
                    "source": "portfolio.dead",
                    "vhost": "portfolio",
                    "destination": name + ".dead",
                    "destination_type": "queue",
                    "routing_key": name,
                    "arguments": {},
                },
            ]
        )
    return {
        "users": [
            {
                "name": user,
                "password_hash": rabbit_password_hash(values[key]),
                "hashing_algorithm": "rabbit_password_hashing_sha256",
                "tags": tags,
            }
            for user, key, tags in users
        ],
        "vhosts": [{"name": "portfolio"}],
        "permissions": permissions,
        "exchanges": [
            {
                "name": name,
                "vhost": "portfolio",
                "type": "direct",
                "durable": True,
                "auto_delete": False,
                "internal": False,
                "arguments": {},
            }
            for name in [
                "portfolio.commands",
                "portfolio.events",
                "portfolio.dead",
                "market.commands",
            ]
        ],
        "queues": queues,
        "bindings": bindings,
        "policies": [
            {
                "vhost": "portfolio",
                "name": "durable-dead-lettering",
                "pattern": "^(quant\\.optimize\\.v1|portfolio\\.results\\.v1|market\\.ingest\\.v1)$",
                "apply-to": "quorum_queues",
                "definition": {
                    "dead-letter-strategy": "at-least-once",
                    "overflow": "reject-publish",
                },
                "priority": 1,
            }
        ],
    }


def create_bundle(refresh: bool) -> None:
    directory = GENERATED / "bundles"
    directory.mkdir(exist_ok=True)
    catalog = directory / "catalog.json"
    if catalog.exists() and not refresh:
        return
    now = datetime.now(timezone.utc)
    # Refresh makes a new immutable identity; it never overwrites a prior snapshot.
    bundle_id = "demo-" + now.strftime("%Y%m%dT%H%M%S%fZ") if refresh else "demo-v1"
    bundle = {
        "schema_version": 1,
        "bundle_id": bundle_id,
        "universe_id": "DEMO",
        "snapshot_id": "synthetic-" + bundle_id,
        "model_bundle_id": None,
        "model_status": None,
        "as_of_date": now.date().isoformat(),
        "valid_until": (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "demo": True,
        "strategies": ["EW", "MVO"],
        "numerical": {
            "asset_ids": ["AAA", "BBB", "VFF"],
            "mean_returns": [0.001, 0.0005, 0.0001],
            "covariance": [[0.0004, 0, 0], [0, 0.0003, 0], [0, 0, 0.00005]],
        },
    }
    content = json_text(bundle)
    artifact = directory / (bundle_id + ".json")
    if artifact.exists():
        raise SystemExit("Immutable bundle already exists. Refusing to overwrite it.")
    artifact.write_text(content)
    artifact.chmod(0o444)
    previous = json.loads(catalog.read_text())["bundles"] if catalog.exists() else []
    pending_catalog = directory / (".catalog-" + secrets.token_hex(8) + ".tmp")
    pending_catalog.write_text(
        json_text(
            {
                "bundles": [
                    {
                        "file": artifact.name,
                        "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    }
                ]
                + previous
            }
        )
    )
    # Keep old, still-valid identities available to jobs already accepted and
    # switch readers atomically to the newest-first catalog.
    pending_catalog.chmod(0o644)
    pending_catalog.replace(catalog)


def create_market_dataset(refresh: bool) -> None:
    """Register a hash-pinned synthetic CSV; refreshing never edits the prior file."""
    directory = GENERATED / "datasets"
    directory.mkdir(exist_ok=True)
    catalog = directory / "catalog.json"
    if catalog.exists() and not refresh:
        return
    now = datetime.now(timezone.utc)
    identity = now.strftime("%Y%m%dT%H%M%S%fZ") if refresh else "v1"
    artifact = directory / ("demo-stock-" + identity + ".csv")
    if artifact.exists():
        raise SystemExit(
            "Immutable Market dataset already exists. Refusing to overwrite it."
        )
    content = (
        "date,price,symbol,published_at\n"
        + f"{(now - timedelta(days=1)).date().isoformat()},10000,DEMO_STOCK,{(now - timedelta(days=1)).isoformat()}\n"
        + f"{now.date().isoformat()},10100,DEMO_STOCK,{now.isoformat()}\n"
    )
    artifact.write_text(content)
    artifact.chmod(0o444)
    entries = json.loads(catalog.read_text()) if catalog.exists() else {}
    entries["DEMO_STOCK"] = {
        "path": artifact.name,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "asset_id": "DEMO_STOCK",
        "kind": "stock",
        "source_unit": "VND/share",
        "provider": "synthetic-local",
        "price_column": "price",
    }
    pending = directory / (".catalog-" + secrets.token_hex(8) + ".tmp")
    pending.write_text(json_text(entries))
    pending.chmod(0o644)
    pending.replace(catalog)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enable-test-client",
        action="store_true",
        help="Include DEV ONLY password-grant client; run upgrade.py for an existing realm",
    )
    parser.add_argument(
        "--refresh-demo",
        action="store_true",
        help="Publish new immutable synthetic bundle and Market CSV catalogs; preserve secrets",
    )
    args = parser.parse_args()
    os.umask(0o077)
    GENERATED.mkdir(exist_ok=True)
    GENERATED.chmod(0o700)
    values = create_secrets()
    accounts = create_accounts()
    settings_path = GENERATED / "settings.json"
    settings = (
        json.loads(settings_path.read_text())
        if settings_path.exists()
        else {"test_client": False}
    )
    settings["test_client"] = settings["test_client"] or args.enable_test_client
    write_private(settings_path, json_text(settings))
    environment = dict(values, OIDC_TEST_CLIENT_SECRET=values["TEST_CLIENT_SECRET"])
    write_private(
        GENERATED / ".env",
        "# GENERATED; local development only. Do not commit.\n"
        + "\n".join(f"{key}={value}" for key, value in environment.items())
        + "\n",
    )
    write_private(
        GENERATED / "postgres" / "10-databases.sql", make_database_sql(values)
    )
    write_private(
        GENERATED / "keycloak" / "portfolio-realm.json",
        json_text(make_realm(values, accounts, settings["test_client"])),
    )
    write_private(
        GENERATED / "rabbitmq" / "definitions.json",
        json_text(make_rabbit_definitions(values)),
    )
    write_private(
        GENERATED / "redis" / "redis.conf",
        f"bind 0.0.0.0\nprotected-mode yes\nport 6379\nrequirepass {values['REDIS_PASSWORD']}\nappendonly yes\nappendfsync everysec\ndir /data\n",
    )
    create_bundle(args.refresh_demo)
    create_market_dataset(args.refresh_demo)
    # Bind-mounted generated config must be readable by each container's non-root uid.
    # The parent directory stays mode 0700 and never enters any build context.
    for directory in [
        "postgres",
        "keycloak",
        "rabbitmq",
        "redis",
        "bundles",
        "datasets",
    ]:
        (GENERATED / directory).chmod(0o755)
        for path in (GENERATED / directory).iterdir():
            if (
                path.is_file()
                and path.name != "catalog.json"
                and directory not in ("bundles", "datasets")
            ):
                path.chmod(0o644)
    print(
        "Local configuration ready; existing secrets preserved. Credentials: infra/local/.generated/accounts.json (not printed)."
    )
    print(
        "Synthetic DEMO inputs expire after one day. Explicit refresh: python3 infra/local/bootstrap.py --refresh-demo"
    )
    if settings["test_client"]:
        print(
            "DEV ONLY portfolio-test password grant enabled in generated realm import."
        )


if __name__ == "__main__":
    main()
