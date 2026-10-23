# Local software stack

This Compose project is **local development only**: it explicitly permits HTTP,
uses disposable generated accounts and mounts a synthetic numerical bundle. It
does not configure production identity, market data, trained ML models or TLS.
All published ports bind to `127.0.0.1`.

From the repository root:

```sh
python3 infra/local/bootstrap.py --enable-test-client
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml config --quiet
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml build
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml up -d --wait
```

Open [the web application](http://localhost:3000). Disposable `alice` and `bob`
investor credentials, plus accounts for the other four human roles, are in
`infra/local/.generated/accounts.json` under `users`, with fields `username`,
`password` and `roles`. Read that ignored file locally; do not paste its contents
into logs, screenshots or commits. The bootstrap preserves existing secrets.
`secrets.json` is the source of truth for generated credentials; `.env` is derived
from it. Keep both with the corresponding Docker volumes.

`--enable-test-client` is optional and must be supplied **before the first realm
import** to use real-JWT integration tests. It creates the confidential
`portfolio-test` client with a password grant only in the disposable local realm.
Its secret is `OIDC_TEST_CLIENT_SECRET` in the ignored `.env`. The normal
`portfolio-web` client always disables password and implicit grants and requires
S256 PKCE for the authorization code flow. Existing realms are never overwritten
by a later import, so enabling this flag after initial startup does not change
the database's realm configuration.

| Component | Local address |
| --- | --- |
| Browser BFF | <http://localhost:3000> |
| Keycloak | <http://localhost:8080> |
| Portfolio API | <http://localhost:8001> |
| Quant API | <http://localhost:8002> |
| PostgreSQL | `localhost:5433` |
| RabbitMQ AMQP / management | `localhost:5673` / <http://localhost:15673> |
| Redis | `localhost:6380` |

The Keycloak admin username is `local-admin`; RabbitMQ and PostgreSQL bootstrap
admin usernames are `local_admin`. Admin passwords are in the ignored `.env`.
Application containers receive only their own runtime database credentials.
Each database has a separate non-login owner, a migrator allowed to assume that
owner, and a runtime role with DML and sequence use only. `PUBLIC` database and
schema privileges are revoked. There are no cross-database application grants.
Keycloak's one-shot `identity-migrate` service imports the realm and migrates its
schema; normal Keycloak startup validates it with a restricted runtime role.
Alembic migrations for the two backend services run in separate init containers.

RabbitMQ's `portfolio` vhost has predeclared direct exchanges
`portfolio.commands`, `portfolio.events` and `portfolio.dead`. The
`quant.optimize.v1` and `portfolio.results.v1` queues, and their `.dead` queues,
are durable quorum queues. Each worker has its own publisher or consumer user:
publishers can write only the owner's exchange, consumers can read only their
own queue, and no runtime user can declare topology. A delivery limit of three
and an at-least-once dead-letter policy bound transient delivery attempts.

The `DEMO` universe uses three fictional assets and predetermined means and
covariance, supporting only EW and MVO. It expires after one day. Refresh is an
explicit action that preserves secrets and old bundles, writes a new immutable
bundle ID, then changes the hash-pinned catalog:

```sh
python3 infra/local/bootstrap.py --refresh-demo
docker compose --env-file infra/local/.generated/.env -f infra/local/compose.yaml restart quant-api quant-consume
```

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
check live database isolation, broker ACLs and normal-web password-grant denial:

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
