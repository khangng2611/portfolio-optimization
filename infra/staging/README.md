# Staging deployment template

This standalone Compose template runs the BFF and Portfolio, Quant and Market
migrations/APIs/workers against separately provisioned PostgreSQL, RabbitMQ,
Redis and Keycloak. It contains no infrastructure containers, realm import,
demo accounts, password-grant test client, generated credentials or demo bundles.
It is a deployment template, and has not been deployed or exercised with real
staging dependencies.

Before deployment, an operator must provision these resources:

1. Three separate application databases: `portfolio_db`, `quant_db`, `market_db`.
   Each has a non-login owner, a login migrator able to assume only that owner,
   and a distinct runtime with only its own CONNECT, schema USAGE, table DML and
   sequence privileges. Revoke PUBLIC database/schema privileges. Set default
   table/sequence privileges for the owner before migrations. A separately
   managed Keycloak installation owns its own identity database. Do not pass
   database administrator credentials to these containers.
2. A durable RabbitMQ `portfolio` vhost with direct exchanges `portfolio.commands`,
   `portfolio.events`, `market.commands`, `portfolio.dead`; durable quorum queues
   `quant.optimize.v1`, `portfolio.results.v1`, `market.ingest.v1` and each `.dead`
   queue. Bind each command/result queue by its own name to its exchange, and
   each `.dead` queue by the source queue name to `portfolio.dead`. Source queues
   require `x-delivery-limit=3`, `x-dead-letter-exchange=portfolio.dead`, with an
   at-least-once dead-letter policy and overflow `reject-publish`.
   Publisher users write only their exchange; consumer users read only their
   queue. Every runtime user has no configure permission and no opposite
   operation permission. The corresponding local topology is documented in
   [the local stack](../local/README.md); provision staging through your
   infrastructure management process, never by importing local credentials.
3. An HTTPS Keycloak realm with the agreed human roles and scopes
   `portfolio:read`, `portfolio:write`, `quant:resolve`, `market:read`, `market:write`.
   The confidential BFF client uses authorization code + S256 PKCE, explicit
   HTTPS callback/web origins and only Portfolio scopes/audience. Disable
   direct/password and implicit grants. The confidential Portfolio service client
   uses client credentials with `quant:resolve` and audience `quant-api`.
   Register bearer API audiences `portfolio-api`, `quant-api`, `market-api`;
   attach the default `basic` scope with the Subject (`sub`) mapper to every
   token-issuing client, including service accounts, so API ownership identity
   validation succeeds. Access tokens without `sub` are rejected.
   provision a separately controlled operator client with Market scope/audience
   as appropriate. Do not create the disposable `portfolio-test` client or local
   demo users. Validate issuer, JWKS, roles and granted scopes with real staging
   identities before exposing access.
4. TLS endpoints for PostgreSQL (`sslmode=verify-full`), RabbitMQ (`amqps`) and
   Redis (`rediss`), individual runtime credentials, and a trusted CA bundle
   `ca.pem` in the host CA directory. The bundle must include the trust chains
   required by Keycloak and these dependencies. Containers mount it read-only;
   PostgreSQL, Python HTTPS, broker hostname verification and Node TLS use it.
5. Read-only approved Quant bundle catalog/artifacts and registered Market CSV
   dataset catalog/artifacts. Quant has demo inputs disabled. Market CSV entries
   are hash-pinned and server-registered; the Market snapshot workflow is not
   automatically connected to Quant bundle construction. Ensure files/directories
   are readable by service UID 10001.
6. A host reverse proxy that serves the BFF and any intentionally exposed API
   routes over HTTPS. Published ports bind to localhost for this proxy; HTTP on
   the private Compose network is confined to that host. This template does not
   install TLS certificates, configure a proxy, define multi-host encryption,
   create an identity realm or promise production availability.

Use a protected env file outside Git, with mode 0600 or equivalent secret-manager
injection. Replace every example endpoint, credential and image with the real
staging values. URL-encode reserved characters in database/broker/Redis passwords.
`SESSION_ENCRYPTION_KEY` encodes 32 random bytes in base64. Supply explicit release
image tags or SHA-256 digests; `latest` and `local` are rejected by the validator.
Do not copy ignored local `.generated` files into staging.

From the repository root, after preparing `/secure/portfolio-staging.env`:

```sh
python3 infra/staging/validate.py --env-file /secure/portfolio-staging.env
docker compose --env-file /secure/portfolio-staging.env -f infra/staging/compose.yaml config --quiet
```

These commands validate without contacting dependencies or deploying. The
validator rejects missing values, local HTTP/demo bypasses, insecure external
URLs, a shared application database, a shared migrator/runtime login, duplicate
broker logins, test BFF clients and unversioned images. It does not verify live
ACLs, existing realm settings, certificate chains or image contents. Missing
Compose variables fail through required interpolation too. Always use
`config --quiet`; expanded configuration contains credentials.

Once the concrete configuration and infrastructure are reviewed by the operator,
`docker compose ... pull` and `docker compose ... up -d --wait` use this template
and run each service's migrations before its runtime processes. No deployment
has been performed as part of adding these files. Back up databases and review
migration changes before a real upgrade. Retry and health behavior do not replace
monitoring, managed dependency resilience, backups or rollback planning.

CI uses the following disposable values only to check template syntax:

```sh
python3 infra/staging/validate.py --env-file infra/staging/.env.example --allow-example
docker compose --env-file infra/staging/.env.example -f infra/staging/compose.yaml config --quiet
```

`--allow-example` permits sentinel secrets solely for offline validation. It
never starts a service and is not an approval to deploy the example. The real
validation command rejects those placeholders.

Protocol references: [Keycloak administration REST API](https://www.keycloak.org/docs-api/latest/rest-api/index.html),
[RabbitMQ definition import](https://www.rabbitmq.com/docs/definitions),
[RabbitMQ quorum dead-lettering](https://www.rabbitmq.com/docs/quorum-queues).
