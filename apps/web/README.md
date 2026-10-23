# Portfolio Web / BFF

Vietnamese Next.js application and Node.js BFF. Browser cookies contain only opaque random identifiers; access/refresh tokens remain in AES-256-GCM encrypted Redis records. This milestone creates demo portfolios and asynchronous MVO recommendations with prepared numerical inputs. It does not implement live ML inference, risk onboarding, or trading.

## Run

Node.js 22.12+ is required. From `apps/web`:

```sh
npm ci
cp .env.example .env.local
# Set the real Keycloak client secret and a random SESSION_ENCRYPTION_KEY.
npm run dev
```

The local stack and its bootstrap script are in `infra/local`. For a container, use `apps/web` as the build context (`docker build -t portfolio-web apps/web` from the repository root). Inject secrets at runtime, never as `NEXT_PUBLIC_*` variables or build arguments.

## Environment contract

| Variable | Meaning |
| --- | --- |
| `APP_ORIGIN` | Exact public origin, e.g. `http://localhost:3000`; never inferred from request Host headers. HTTPS required except explicit localhost mode. |
| `OIDC_ISSUER` | Exact public Keycloak issuer, local `http://localhost:8080/realms/portfolio`. Tokens and discovery must use this value. |
| `OIDC_INTERNAL_ORIGIN` | Optional origin, e.g. `http://keycloak:8080`, used only for the server's discovery/token/JWKS/revocation network requests. Public metadata and issuer validation stay unchanged. |
| `OIDC_CLIENT_ID` | Confidential authorization-code client, default `portfolio-web`. |
| `OIDC_CLIENT_SECRET` | Required secret provisioned in Keycloak. |
| `OIDC_AUDIENCE` | Required access-token audience, default `portfolio-api`. |
| `OIDC_SCOPE` | Default `openid profile email portfolio:read portfolio:write`; provision matching scopes in Keycloak. |
| `REDIS_URL` | Required dedicated session Redis URL; Docker `redis://redis:6379/0`, production `rediss://...` with credentials. |
| `SESSION_ENCRYPTION_KEY` | Required base64-encoded 32 random bytes (`openssl rand -base64 32`). Rotating invalidates existing sessions. |
| `SESSION_TTL_SECONDS` | Absolute session lifetime, default 28800; 60–86400. Cookie, Redis TTL and server expiry are all bounded. |
| `PORTFOLIO_API_URL` | Fixed backend origin, e.g. `http://portfolio-api:8000`; no path, credentials or query. |
| `ALLOW_INSECURE_HTTP` | Set exactly `true` only for local HTTP Keycloak and localhost browser access. Otherwise secure cookies and HTTPS OIDC are required. |
| `OTEL_TRACES_ENABLED` | Set exactly `true` to enable manual BFF tracing; default disabled. |
| `OTEL_SERVICE_NAME` | Trace process resource name, local `web-bff`. |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | OTLP HTTP endpoint, local container `http://jaeger:4318/v1/traces`. |
| `TRACE_VIEWER_URL` | Trusted server-configured Jaeger base, local `http://localhost:16686`; never taken from caller input or build-time public env. |

Keycloak must allow exactly `${APP_ORIGIN}/auth/callback`, require PKCE S256, enable standard flow, disable implicit/direct grants, and map audience `portfolio-api` and `realm_access.roles` into RS256 access tokens. Five supported application roles are investor, researcher, data-operator, model-reviewer, system-admin. Backend services remain authoritative for scope, RBAC and record ownership.

## Routes and session behavior

- `GET /auth/login`: random server-stored state, nonce, PKCE verifier and five-minute transaction cookie; redirect to public issuer.
- `GET /auth/callback`: consumes transaction once, validates state/nonce/code, verifies RS256 access token issuer/audience/expiry, rotates application session.
- `GET /auth/session`: returns `{authenticated:true,user:{sub,name,roles},csrfToken}` only. Responses disable caching.
- `POST /auth/logout`: requires exact Origin and `X-CSRF-Token`; deletes Redis session before provider revocation. Clears cookies; reports `providerRevoked:false` if Keycloak cannot confirm revocation. This closes the application session; the separate Identity browser SSO cookie may remain.
- `/api/v1/portfolios` GET/POST, `/api/v1/portfolios/{uuid}` GET/PATCH, `/api/v1/portfolios/{uuid}/recommendations` GET/POST, `/api/v1/recommendations/{uuid}` GET, `/api/v1/jobs/portfolio/{uuid}` GET: fixed allowlist to Portfolio. No internal/admin or arbitrary upstream URL routes.
- List routes allow integer `limit`/`offset` query parameters only. Mutations require JSON, exact Origin, session CSRF token and at most 64 KiB body; recommendation creation additionally requires `Idempotency-Key` (8–128 URL-safe characters). Version preconditions (`If-Match`) and backend version tags (`ETag`) pass through for owner-scoped PATCH. Cookies, caller Authorization, identity headers, upstream redirects and Set-Cookie are never forwarded.
- `GET /health/live` is process liveness, not a claim that dependencies are healthy.

HTTPS cookies are `__Host-portfolio_session` and `__Host-portfolio_login`, with Secure, HttpOnly, SameSite=Lax and Path=/. Local HTTP has explicitly unprefixed, non-Secure cookies. Tokens refresh under Redis NX locks; Lua checks the current lock owner and session existence before storing rotated tokens, preventing expired lock holders or concurrent logout from resurrecting sessions. Redis failures fail closed without queuing requests. Established clients reconnect with a capped delay (at most 2.1 seconds); initial connection setup has a four-second deadline. If Redis restarts without saved sessions, old cookies remain invalid and users must sign in again. Protect Redis with authentication/TLS and no eviction; only trusted BFF instances should access it. Provider revocation failure does not restore a deleted session.

The first UI flow uses universe `DEMO`, risk aversion 1.5, maximum position 0.6 and capital entered by the user. Each recommendation submission gets an idempotency UUID, then polls the owner-scoped job and reads the persisted recommendation. Results include backend provenance without claiming parity with legacy ML workflows.

## Verification

Job/result UI links use persisted `job_trace_id`/`job_trace_url`. `X-Trace-ID`
belongs to the current HTTP request, so polling has its own trace. Only manual
`portfolio-bff` spans with route templates/status are exported; automatic
Next/auth spans are filtered before batching. See [local tracing guide](../../docs/software/TRACING.md).

```sh
npm test
npm run typecheck
npm run build
```

Tests cover encrypted records/tampering, secure cookies, one-time login state, CSRF/origin, proxy allowlists/header isolation/redirect rejection, concurrent refresh, expiry, unavailable Redis and logout races. OIDC tests use the real openid-client/Jose libraries against a deterministic issuer transport with actual RSA-signed tokens, including forged signatures, nonce/state, issuer, audience and expiry rejection. When `redis-server` is on PATH (or set `REDIS_TEST_BINARY`), the suite also runs an isolated nonpersistent Redis process, stops/restarts it, and checks failure during outage, invalidation of lost sessions and successful reauthentication on the same BFF. This test is skipped if the binary is unavailable. A complete Keycloak/Redis/browser stack is a separate integration gate; see the local stack verification record.

This is a runnable foundation, not production certification: deployment still needs TLS ingress, secret rotation, dependency/image scanning, centralized rate limits, operational observability, administrative MFA policy and staging load/security checks. Next's static page CSP permits inline hydration; private mutations remain CSRF protected and the application never renders untrusted HTML.

Library references: [openid-client](https://github.com/panva/openid-client), [Next.js security advisories](https://github.com/vercel/next.js/security/advisories), [Keycloak OIDC](https://www.keycloak.org/securing-apps/oidc-layers).
