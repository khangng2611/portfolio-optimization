# Local software stack

This Compose project is **local development only**: it explicitly permits HTTP,
uses disposable generated accounts and mounts a synthetic numerical bundle. It
does not configure production identity, live upstream market crawling, trained ML models or TLS.
Market CSV ingestion uses a synthetic, server-registered dataset.
All published ports bind to `127.0.0.1`.

From the repository root, use the setup entry point for either a new or existing
local stack:

```sh
python3 scripts/setup_software.py up --enable-test-client
```

It prepares the isolated software environment, generates local config, builds
images, starts dependency services, applies the additive upgrade, then starts the
full stack. See the [Vietnamese setup and API guide](../../docs/software/SETUP_AND_API_TESTING.md)
for prerequisites and flags. The manual upgrade commands below assume that the
software virtual environment is already installed.

Open [the web application](http://localhost:3000). Disposable `alice` and `bob`
investor credentials, plus accounts for the other four human roles, are in
`infra/local/.generated/accounts.json` under `users`, with fields `username`,
`password` and `roles`. Read that ignored file locally; do not paste its contents
into logs, screenshots or commits. The bootstrap preserves existing secrets.
`secrets.json` is the source of truth for generated credentials; `.env` is derived
from it. Keep both with the corresponding Docker volumes.

`--enable-test-client` is optional and creates the client on the first realm
import, or through the additive upgrade below, to use real-JWT integration tests.
It creates the confidential
`portfolio-test` client with a password grant only in the disposable local realm.
Its secret is `OIDC_TEST_CLIENT_SECRET` in the ignored `.env`. The normal
`portfolio-web` client always disables password and implicit grants and requires
S256 PKCE for the authorization code flow. Existing realms are never overwritten
by a later import. On an existing stack, run the upgrade command below after
enabling the flag; bootstrap alone changes only generated configuration.

| Component | Local address |
| --- | --- |
| Browser BFF | <http://localhost:3000> |
| Keycloak | <http://localhost:8080> |
| Portfolio API | <http://localhost:8001> |
| Quant API | <http://localhost:8002> |
| Market Data API / Swagger | <http://localhost:8003> / <http://localhost:8003/docs> |
| PostgreSQL | `localhost:5433` |
| RabbitMQ AMQP / management | `localhost:5673` / <http://localhost:15673> |
| Redis | `localhost:6380` |
| Jaeger UI (optional tracing overlay) | <http://localhost:16686> |

The Keycloak admin username is `local-admin`; RabbitMQ and PostgreSQL bootstrap
admin usernames are `local_admin`. Admin passwords are in the ignored `.env`.
Application containers receive only their own runtime database credentials.
Each database has a separate non-login owner, a migrator allowed to assume that
owner, and a runtime role with DML and sequence use only. `PUBLIC` database and
schema privileges are revoked. There are no cross-database application grants.
Keycloak's one-shot `identity-migrate` service imports the realm and migrates its
schema; normal Keycloak startup validates it with a restricted runtime role.
Alembic migrations for Portfolio, Quant and Market run in separate init containers.
Market owns `market_db`, its revisions, jobs and immutable snapshots.

RabbitMQ's `portfolio` vhost has predeclared direct exchanges
`portfolio.commands`, `portfolio.events`, `market.commands` and `portfolio.dead`.
The `quant.optimize.v1`, `portfolio.results.v1` and `market.ingest.v1` queues, and their `.dead` queues,
are durable quorum queues. Each worker has its own publisher or consumer user:
publishers can write only the owner's exchange, consumers can read only their
own queue, and no runtime user can declare topology. A delivery limit of three
and an at-least-once dead-letter policy bound transient delivery attempts.
`market_publisher` writes only `market.commands`; `market_consumer` reads only
`market.ingest.v1`. Neither can declare queues or access another owner's resources.

The `DEMO` universe uses three fictional assets and predetermined means and
covariance, supporting only EW and MVO. It expires after one day. Refresh is an
explicit action that preserves secrets and old bundles, writes a new immutable
bundle ID, then changes the hash-pinned catalog:

```sh
python3 infra/local/bootstrap.py --refresh-demo
```

The same refresh writes a new immutable CSV with yesterday/today synthetic prices
and replaces `.generated/datasets/catalog.json` with its SHA-256-pinned registration
for `DEMO_STOCK` (stock, VND/share, provider `synthetic-local`). Prior CSVs remain
unchanged. Both adapters reread catalogs for each request, so a catalog refresh
needs no process restart. Market jobs record the accepted dataset hash and reject
changed registrations rather than silently ingesting different input.

The test client receives Market read/write scopes and `market-api` audience in
addition to Portfolio access. The normal BFF client keeps only its Portfolio
scopes/audience. Market ingestion also checks role `data-operator`; granting a
scope alone does not authorize an investor to ingest data.

## Optional local tracing

Enable the OpenTelemetry/Jaeger overlay explicitly:

```sh
python3 scripts/setup_software.py up --enable-test-client --tracing
python3 scripts/setup_software.py check --tracing
python3 scripts/setup_software.py verify --live --tracing
```

Pass `--tracing` on each command; it is not stored with credentials. The base
stack keeps tracing disabled. The overlay adds Jaeger all-in-one with in-memory
storage and 100% sampling, loopback-only UI `16686` and OTLP HTTP `4318`.
Each BFF/API/dispatch/consume process has a separate service name. Existing
database, broker and identity settings remain in the base Compose file.
Collector restart clears traces while application data stays in owner databases.

For direct Compose operations, append `-f infra/local/compose.tracing.yaml` after
the base file in **every** build/up/config/stop command. Use `config --quiet` to
avoid expanded credentials. Do not reset volumes to enable or disable tracing.
See [the tracing guide](../../docs/software/TRACING.md) for manual startup,
dispatcher-restart smoke, job trace vs HTTP poll trace, JSON console logs and the
limits of local collection. Only new instrumented jobs have a real timeline.

## Upgrade an existing local stack

Keep the existing ignored `.generated` directory and its matching volumes.
Bootstrap appends only the four newly introduced Market credentials and never
replaces an existing password/session key. A missing previously required credential
still fails and asks you to restore the matching `secrets.json`. Do not delete
volumes or rotate a config file to get past this failure.

From the repository root, with the software virtual environment installed:

```sh
python3 infra/local/bootstrap.py --enable-test-client
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml config --quiet
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml up -d postgres rabbitmq redis keycloak --wait
.venv-software/bin/python infra/local/upgrade.py
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml build
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml up -d --wait
```

`upgrade.py` uses fixed localhost endpoints and the named local Compose project.
It applies conditional PostgreSQL role/database creation and privileges to an
already initialized volume, imports only Market broker accounts/topology and
extends the dead-letter policy, then adds missing Market scopes/audience to the
imported Keycloak realm. When `--enable-test-client` is recorded in settings, it
creates a missing local test client or adds its Market scope/audience. It preserves
existing realm users, passwords, BFF configuration and existing client secrets.
The process can be repeated; a component failure stops with a redacted error and
can be retried after the dependencies recover. It never clears database records,
queues, sessions or volumes. It needs `httpx` from the software environment.

PostgreSQL's entrypoint init scripts and Keycloak's first import do not rerun on
existing storage. This command is required before starting the new Market
migration/API/workers on a stack created before this milestone. It is a local
upgrade utility, and must never be pointed at staging or production. For the
external-dependency deployment template, see [staging](../staging/README.md).

Generated configuration is excluded from Docker build contexts. Bootstrap files below
the mode-0700 `.generated` directory are readable through their specific read-only
container mounts. No generated passwords or tokens should be printed by test
scripts. `docker compose config` without `--quiet` expands secrets; avoid logging
that output.

To stop containers while retaining accounts, sessions, queues and database data:

```sh
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml down
```

With the software test virtual environment installed and the stack healthy,
check live database isolation, broker ACLs, normal-web password-grant denial and
the enabled test client's Market audience/scopes/operator role:

```sh
.venv-software/bin/python infra/local/verify_boundaries.py
```

This check creates and removes temporary tables, never consumes business messages,
and does not print credentials or tokens. In a restricted agent sandbox, it needs
permission to connect to these localhost ports.

The named volumes belong to project `portfolio-software`. Deleting them resets
stored application data; changing generated passwords alone does not rotate
credentials already installed in PostgreSQL, RabbitMQ or Keycloak.

Pinned upstream sources: [Keycloak containers and realm import](https://www.keycloak.org/server/containers),
[Keycloak JPA migration options](https://www.keycloak.org/server/all-provider-config),
[RabbitMQ definitions](https://www.rabbitmq.com/docs/definitions),
[RabbitMQ quorum queues](https://www.rabbitmq.com/docs/quorum-queues),
[PostgreSQL Docker image](https://hub.docker.com/_/postgres),
[Redis 8.2 releases](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/release-notes/redisce/redisos-8.2-release-notes/).
