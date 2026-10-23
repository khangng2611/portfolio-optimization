# Identity/BFF và Portfolio Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for integration and superpowers:dispatching-parallel-agents for isolated frontend/core work. Steps use checkbox tracking.

**Goal:** Implement login/session/RBAC/ownership and an asynchronous Portfolio recommendation API backed by a separately deployed Quant worker.

**Architecture:** Next.js BFF authenticates against Keycloak and keeps tokens in encrypted Redis sessions. Portfolio owns users, portfolios, jobs and recommendations in its own PostgreSQL database. Quant owns numerical runs in another database; commands/results travel through RabbitMQ with transactional outbox/inbox deduplication. Quant calls an installable numerical package using server-controlled immutable input artifacts.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLAlchemy/Alembic, PostgreSQL, Kombu/RabbitMQ, PyJWT, Next.js/TypeScript, openid-client, Redis, Keycloak, Docker Compose.

**Spec:** `docs/TECHNICAL_SPECIFICATION_PHASE_2.md` sections 3, 5, 6, 7 and 14; `docs/superpowers/specs/2026-09-26-software-foundation-design.md`.

## Global constraints

- User approved implementation after clarifying Identity/BFF and Portfolio/Quant boundaries. Proceed without another design approval cycle.
- Work additively in current feature checkout; preserve existing untracked research documents and tracked numerical source. No publishing, deployment to cloud, or paid infrastructure.
- No standalone Auth or Allocation microservice. No cross-service ORM imports or database reads.
- Roles: investor, researcher, data-operator, model-reviewer, system-admin. Every private record is owner-scoped, including for admins.
- Browser holds opaque HttpOnly session cookie. Tokens remain encrypted server-side. OIDC state/nonce/PKCE, Origin/CSRF checks, session expiry and locked refresh are required.
- Do not advertise legacy ranking_absolute parity without evidence. Initially supported numerical strategies and input provenance must be explicit. Unavailable model/data or unsupported strategy fails closed.
- Full autonomous crawling/training/model promotion and Chat/RAG remain separate milestones; this implementation provides the auth and recommendation flow requested in the last clarification.

## Review focus

- Cross-user IDs and forged owner fields must never expose or mutate another user's record.
- Invalid issuer/audience/signature/expiry, missing scope, and unavailable session/JWKS dependencies fail closed.
- Duplicate commands/results, a process crash after commit, and a broker outage must not create duplicate recommendations or lose accepted jobs.
- Missing, stale, incompatible artifacts and nonfinite/infeasible numerical inputs must fail explicitly, never silently become an equal-weight success.
- Model/config provenance and personalized constraints must survive the BFF, job, Quant result and persisted response unchanged.

### Task 1: Shared wire contracts and Python service packaging

Files: `packages/contracts/`, `packages/service-auth/`, `services/portfolio/pyproject.toml`, `services/quant-serving/pyproject.toml`, `tests/software/`.

Interfaces: versioned `OptimizeCommand` and `OptimizeResult`; `Principal(issuer, subject, roles)`; `TokenVerifier.verify(token) -> Principal`; no client-provided owner.

- [x] Write/run failing schema and JWT tests: reject malformed IDs, nonfinite numbers, wrong signature/audience/issuer/expired JWT, missing authentication; accept valid Keycloak role claims.
- [x] Implement strict Pydantic contracts and RS256/JWKS verification with bounded cache/network timeout.
- [x] Verify package imports and all authentication tests.

### Task 2: Keycloak BFF and web entry point

Files: `apps/web/` only. Interfaces: BFF `GET /auth/login`, `/auth/callback`, `/auth/session`, `POST /auth/logout`; fixed allowlisted `/api/v1/...` proxy to Portfolio. Portfolio base URL configured server-side; role claims use realm_access.roles and audience portfolio-api.

- [x] Write/run tests for OIDC state/session handling, secure cookies, CSRF/origin checks, fixed proxy routing, refresh concurrency and logout.
- [x] Implement Next.js UI and BFF with Redis-backed encrypted sessions and standards-based OIDC library.
- [x] Run tests, typecheck and production build. Provide local environment variables and Dockerfile.

### Task 3: Installable deterministic numerical package

Files: `packages/portfolio-core/` only. Interface: `allocate(request: dict) -> dict` with ordered asset_ids, mean_returns, covariance, market_weights, optional P/Q/confidences and explicit constraints. Result has ordered weights, solver status and diagnostics; only documented supported strategies accepted.

- [x] Write/run failures for covariance/input shapes, infeasibility, final cap violations, missing ML views, and a hand-derived/small golden numerical result.
- [x] Implement explicit config, BL posterior and constrained optimization without importing repo-root modules; no implicit model training or mutable global configuration.
- [x] Verify core wheel can run outside repo root and numerical tests pass. Record exact legacy parity limits.

### Task 4: Portfolio database, API and transactional workflow

Files: `services/portfolio/src/portfolio_service/`, migrations, tests. Interfaces: owner-scoped portfolio create/read/update; `POST /api/v1/portfolios/{id}/recommendations` returns 202 with job ID/status URL, `GET /api/v1/jobs/portfolio/{id}`, `GET /api/v1/recommendations/{id}`. Require Idempotency-Key for job creation. Store issuer+sub mapping, portfolio version, frozen inputs/hash and outbox in one transaction.

- [x] Write/run failing API tests for cross-user reads/writes, validation, idempotency conflict/replay, and result correlation.
- [x] Implement routes/application/domain/models, explicit migrations, ready input resolver, job+outbox transaction and result consumer with inbox dedupe.
- [x] Verify API behavior and migrations against disposable SQLite databases; recreated API instances read persisted state. PostgreSQL runtime validation is tracked separately below.

### Task 5: Quant artifact resolver and durable workers

Files: `services/quant-serving/src/quant_service/`, migrations, tests; owner-specific broker workers in each service. Quant resolves immutable server-controlled prepared bundles; authenticated internal resolver gives Portfolio version/hash/cutoff before enqueue. Bundle contract explicitly distinguishes demo/precomputed inputs from live ML inference.

- [x] Write/run failures for tampered/stale bundle, unsupported strategy, duplicate command, duplicate result, and infeasible personalized constraints.
- [x] Implement numerical worker using installed core, persisted Quant run/result outbox, durable publisher confirms and bounded consumer retry/dead-letter behavior. No training inside HTTP request.
- [x] Verify command/result handler roundtrip and duplicate delivery produces one persisted recommendation; numerical failures become FAILED jobs. Real broker gate remains below.

### Task 6: Local stack, contracts, CI and integration verification

Files: `infra/local/`, `.github/workflows/software.yml`, `docs/software/README.md`, run scripts, OpenAPI/event exports.

- [x] Compose PostgreSQL with separate databases/runtime roles, Keycloak realm/clients/five roles, RabbitMQ and Redis, Web, Portfolio API/workers, Quant API/workers. Bind infrastructure ports to localhost; configure explicit images/versions and healthchecks.
- [x] Generate disposable local secrets/accounts through an explicit bootstrap script; no committed production credentials. Supply a clearly labeled deterministic demo bundle for end-to-end development.
- [x] Run Python suites, frontend tests/typecheck/build and Compose validation; provide real identity/DB/broker smoke scripts and CI gate.
- [ ] Run full real OIDC and PostgreSQL/RabbitMQ integration, browser sign-in and container-restart persistence verification. Blocked by host Docker storage I/O failure after disk filled; not represented as passing.
- [x] Review implementation, fix important findings, record remaining scientific/live-data limitations and exact startup commands. Keep changes reviewable in working tree; do not commit unrelated files.

## Execution ledger

- Baseline: no application test suite or service metadata. Existing CLI smoke passed in prior turn. Docker CLI installed but daemon was stopped; checking startup separately.
- Ruling: latest user request explicitly authorizes implementation of clarified auth and recommendation boundaries; no repeat approval gate. This plan scopes numerical integration honestly rather than claiming the entire Phase 1 audit, scheduled ML platform, or production release is complete.
- Final local checks: 84 Python tests, 21 web tests (including actual Redis restart and connection-leak tests), Ruff, TypeScript and production Next build passed. Exported five HTTP/event schemas. SQLite migrations and external core-wheel installation passed.
- Review fixes: recommendation history, versioned PATCH/ETag through BFF, strict strategy/status/core-version/nonfinite result rejection, Redis reconnect and initial discovery cleanup. Result completion holds Portfolio lock; owner quota uses PostgreSQL NO KEY UPDATE to allow foreign-key KEY SHARE checks. Actual PostgreSQL concurrency remains in the unrun integration gate.
- Added regression coverage for uncertain broker acknowledgement retaining the same outbox event, job deadline failure, and demo refresh preserving already-pinned bundles. Catalog replacement is atomic.
- Docker infrastructure images pulled and Postgres/RabbitMQ/Redis initially became healthy; BuildKit and overlay2 then failed with I/O errors when Data volume reached 100% (about 220 MiB free). No volumes or user files were deleted. Free capacity and a normal Docker restart are needed before the remaining integration checks; GitHub CI was authored but not executed here.
