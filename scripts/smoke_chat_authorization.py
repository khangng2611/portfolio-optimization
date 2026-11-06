"""Real localhost delegation authorization gate, separate from Chat lifecycle receipts.

Requires E2E_DISPOSABLE_STACK=1. Uses actual Keycloak JWTs and owner APIs only.
Creates Bob-owned disposable portfolios and one allocation intent; never accepts a
recommendation. Bob's enabled state is restored in finally. Credentials and opaque
grants remain in memory; this script writes no receipts or other files. The actual
five-minute grant expiry is observed within an overall six-minute deadline.
"""

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import httpx

from smoke_chat import select_real_universe

GENERATED = Path(__file__).resolve().parents[1] / "infra/local/.generated"
PORTFOLIO = "http://localhost:8001"
IDENTITY = "http://localhost:8080"
TOKEN = IDENTITY + "/realms/portfolio/protocol/openid-connect/token"
ADMIN = IDENTITY + "/admin/realms/portfolio"
ANSWERS = {
    "questionnaire_version": "risk-v1",
    "horizon_months": 60,
    "liquidity_need": "low",
    "loss_tolerance": "high",
    "experience": "experienced",
}
TOOLS = [
    "get_profile",
    "get_portfolio_summary",
    "request_allocation",
    "get_recommendation",
    "get_allocation_job",
]


class GateFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GateFailure(message)


def require_disposable_stack():
    require(
        os.environ.get("E2E_DISPOSABLE_STACK") == "1",
        "Set E2E_DISPOSABLE_STACK=1 only for the existing disposable local stack.",
    )


def select_expired_real(catalog):
    for item in catalog:
        try:
            expiry = datetime.fromisoformat(item["valid_until"].replace("Z", "+00:00"))
            if (
                item.get("status") == "EXPIRED"
                and item.get("reason_code") == "INPUT_EXPIRED"
                and item.get("data_origin") == "real"
                and item.get("demo") is False
                and expiry < datetime.now(timezone.utc)
            ):
                return item
        except (KeyError, TypeError, ValueError):
            continue
    raise GateFailure("No expired real input universe; this gate cannot fabricate one.")


@contextmanager
def temporarily_disabled(admin, subject):
    path = "/users/" + subject
    status, user = admin("GET", path)
    require(
        status == 200 and isinstance(user.get("enabled"), bool),
        "Cannot read Bob's original enabled state.",
    )
    original = user["enabled"]
    try:
        status, _ = admin("PUT", path, {"enabled": False})
        require(
            status == 204,
            "Cannot temporarily disable Bob for the active-account probe.",
        )
        yield
    finally:
        status, _ = admin("PUT", path, {"enabled": original})
        require(
            status == 204,
            "Bob enabled-state restoration failed; restore Bob before further tests.",
        )
        status, user = admin("GET", path)
        require(
            status == 200 and user.get("enabled") == original,
            "Bob enabled-state restoration could not be verified.",
        )


class Gate:
    def __init__(self, client):
        self.client = client
        self.deadline = time.monotonic() + 360
        self.values = json.loads((GENERATED / "secrets.json").read_text())
        self.accounts = json.loads((GENERATED / "accounts.json").read_text())["users"]
        self.cached = {}
        self.checks = []
        self.statuses = Counter()

    def request(
        self,
        method,
        url,
        *,
        token=None,
        body=None,
        form=None,
        headers=None,
        cleanup=False,
    ):
        remaining = self.deadline - time.monotonic()
        require(
            cleanup or remaining > 0,
            "Authorization gate exceeded its 360-second deadline.",
        )
        safe_headers = dict(headers or {})
        if token:
            safe_headers["Authorization"] = "Bearer " + token
        try:
            response = self.client.request(
                method,
                url,
                headers=safe_headers,
                json=body,
                data=form,
                timeout=10 if cleanup else min(10, remaining),
            )
            return response.status_code, response.json() if response.content else {}
        except (httpx.HTTPError, ValueError, TypeError):
            raise GateFailure(
                "A local dependency was unavailable or returned invalid JSON; no credentials printed."
            ) from None

    def expect(self, label, expected, response):
        status, value = response
        self.statuses[str(status)] += 1
        allowed = (expected,) if isinstance(expected, int) else expected
        require(
            status in allowed, f"{label}: expected HTTP {allowed}, observed {status}."
        )
        self.checks.append(label)
        return value

    def login(self, username):
        user = next(
            (user for user in self.accounts if user["username"] == username), None
        )
        require(user is not None, "Required existing local test account is missing.")
        status, data = self.request(
            "POST",
            TOKEN,
            form={
                "grant_type": "password",
                "client_id": "portfolio-test",
                "client_secret": self.values["TEST_CLIENT_SECRET"],
                "username": username,
                "password": user["password"],
                "scope": "openid portfolio:read portfolio:write chat:read chat:write",
            },
        )
        require(
            status == 200 and data.get("access_token"),
            "Existing local test-client login failed.",
        )
        return data["access_token"]

    def machine(self):
        return self.cached_token(
            "chat",
            TOKEN,
            {
                "grant_type": "client_credentials",
                "client_id": "chat-service",
                "client_secret": self.values["CHAT_CLIENT_SECRET"],
                "scope": "chat:delegate market:chat:read",
            },
        )

    def cached_token(self, name, url, form):
        token, until = self.cached.get(name, (None, 0))
        if until <= time.monotonic():
            status, data = self.request("POST", url, form=form, cleanup=name == "admin")
            require(
                status == 200 and data.get("access_token"),
                "Existing local machine/admin identity login failed.",
            )
            token = data["access_token"]
            self.cached[name] = (
                token,
                time.monotonic() + max(0, data["expires_in"] - 30),
            )
        return token

    def admin(self, method, path, body=None):
        token = self.cached_token(
            "admin",
            IDENTITY + "/realms/master/protocol/openid-connect/token",
            {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "local-admin",
                "password": self.values["KEYCLOAK_ADMIN_PASSWORD"],
            },
        )
        return self.request(method, ADMIN + path, token=token, body=body, cleanup=True)

    def onboard(self, token, universe, suffix):
        value = self.expect(
            "onboard_" + suffix,
            201,
            self.request(
                "POST",
                PORTFOLIO + "/api/v1/onboarding/portfolios",
                token=token,
                body={
                    "name": "Delegation gate " + suffix + " " + uuid4().hex[:8],
                    "capital_vnd": "100000000",
                    "universe_id": universe,
                    "answers": ANSWERS,
                },
            ),
        )
        return self.expect(
            "read_" + suffix,
            200,
            self.request(
                "GET", PORTFOLIO + "/api/v1/portfolios/" + value["id"], token=token
            ),
        )

    def grant_body(self, portfolio, tools=None):
        return {
            "conversation_id": str(uuid4()),
            "job_id": str(uuid4()),
            "portfolio_id": portfolio["id"],
            "tools": TOOLS if tools is None else tools,
        }

    def issue(self, user, body, actor=None):
        return self.request(
            "POST",
            PORTFOLIO + "/internal/v1/delegation-grants",
            token=user,
            body=body,
            headers={"X-Service-Authorization": "Bearer " + (actor or self.machine())},
        )

    def invoke(
        self,
        grant,
        tool="get_portfolio_summary",
        body=None,
        *,
        actor=None,
        bindings=None,
    ):
        headers = {
            "X-Delegation-Grant": grant["grant_id"],
            "X-Chat-Job": grant["job_id"],
            "X-Chat-Conversation": grant["conversation_id"],
        } | (bindings or {})
        return self.request(
            "POST",
            PORTFOLIO + "/internal/v1/chat-tools/" + tool,
            token=actor or self.machine(),
            body=body or {},
            headers=headers,
        )

    @staticmethod
    def pins(portfolio):
        return {
            "portfolio_id": portfolio["id"],
            "strategy": "MVO",
            "expected_version": portfolio["version"],
            "expected_policy_version": portfolio["policy_version_id"],
        }

    def run(self):
        bob, other = self.login("bob"), self.login("researcher")
        catalog = self.expect(
            "owner_readiness_catalog",
            200,
            self.request("GET", PORTFOLIO + "/api/v1/universes/readiness", token=bob),
        )
        ready, expired = select_real_universe(catalog), select_expired_real(catalog)
        first = self.onboard(bob, ready["universe_id"], "primary")
        second = self.onboard(bob, ready["universe_id"], "other_resource")
        stale_data = self.onboard(bob, expired["universe_id"], "expired_data")
        body = self.grant_body(first)
        self.expect("missing_user_identity", 401, self.issue(None, body))
        self.expect(
            "missing_actor_identity",
            401,
            self.request(
                "POST",
                PORTFOLIO + "/internal/v1/delegation-grants",
                token=bob,
                body=body,
            ),
        )
        self.expect("human_is_not_chat_actor", 403, self.issue(bob, body, actor=bob))
        self.expect("machine_is_not_user", 403, self.issue(self.machine(), body))
        self.expect("cross_user_portfolio", 404, self.issue(other, body))
        self.expect(
            "unknown_tool_at_issue",
            422,
            self.issue(bob, self.grant_body(first, ["accept_target"])),
        )
        grant = self.expect("dual_identity_issue", 200, self.issue(bob, body))
        replay = self.expect("issue_idempotent", 200, self.issue(bob, body))
        require(replay == grant, "Grant replay changed opaque identity or expiry.")
        self.expect(
            "issue_body_conflict",
            409,
            self.issue(bob, body | {"tools": ["get_profile"]}),
        )
        summary = self.expect("bound_summary", 200, self.invoke(grant))
        require(
            summary == first,
            "Delegated summary differs from the canonical owner resource.",
        )
        self.expect("invocation_wrong_actor", 403, self.invoke(grant, actor=bob))
        self.expect(
            "invocation_wrong_job",
            403,
            self.invoke(grant, bindings={"X-Chat-Job": str(uuid4())}),
        )
        self.expect(
            "invocation_wrong_conversation",
            403,
            self.invoke(grant, bindings={"X-Chat-Conversation": str(uuid4())}),
        )
        self.expect(
            "invocation_wrong_portfolio",
            403,
            self.invoke(grant, body={"portfolio_id": second["id"]}),
        )
        self.expect(
            "unknown_opaque_reference",
            403,
            self.invoke(grant | {"grant_id": str(uuid4())}),
        )
        self.expect(
            "mutation_outside_allowlist", 404, self.invoke(grant, "accept_target")
        )
        limited = self.expect(
            "read_only_issue",
            200,
            self.issue(bob, self.grant_body(first, ["get_profile"])),
        )
        self.expect("tool_not_in_grant", 403, self.invoke(limited))
        before = self.pins(first)
        allocated = self.expect(
            "explicit_pinned_allocation",
            200,
            self.invoke(grant, "request_allocation", before),
        )
        require(
            allocated.get("job_id"), "Owner did not return a durable allocation job."
        )
        self.expect(
            "allocation_job_is_readable",
            200,
            self.invoke(
                grant, "get_allocation_job", {"resource_id": allocated["job_id"]}
            ),
        )
        other_resource = self.expect(
            "other_resource_issue", 200, self.issue(bob, self.grant_body(second))
        )
        self.expect(
            "actual_job_wrong_portfolio",
            404,
            self.invoke(
                other_resource,
                "get_allocation_job",
                {"resource_id": allocated["job_id"]},
            ),
        )
        self.expect(
            "allocation_body_conflict",
            409,
            self.invoke(grant, "request_allocation", before | {"strategy": "EW"}),
        )
        first = self.expect(
            "edit_portfolio",
            200,
            self.request(
                "PATCH",
                PORTFOLIO + "/api/v1/portfolios/" + first["id"],
                token=bob,
                body={"capital_vnd": "110000000"},
                headers={"If-Match": f'"{first["version"]}"'},
            ),
        )
        recovered = self.expect(
            "reconcile_after_edit",
            200,
            self.invoke(grant, "request_allocation", before),
        )
        require(
            recovered == allocated,
            "Owner replay lost its durable allocation receipt after an edit.",
        )
        new_intent = self.expect(
            "new_intent_issue", 200, self.issue(bob, self.grant_body(first))
        )
        self.expect(
            "stale_portfolio_pins",
            409,
            self.invoke(new_intent, "request_allocation", before),
        )
        self.expect(
            "confirm_new_risk_revision",
            201,
            self.request(
                "POST",
                PORTFOLIO + f"/api/v1/portfolios/{first['id']}/risk-assessments",
                token=bob,
                body={
                    "answers": ANSWERS | {"horizon_months": 24, "loss_tolerance": "low"}
                },
                headers={
                    "If-Match": f'"{first["version"]}"',
                    "Idempotency-Key": "auth-risk-" + uuid4().hex,
                },
            ),
        )
        first = self.expect(
            "read_new_risk_revision",
            200,
            self.request(
                "GET", PORTFOLIO + "/api/v1/portfolios/" + first["id"], token=bob
            ),
        )
        require(
            first["policy_version_id"] != before["expected_policy_version"],
            "Actual risk revision did not change its policy pin.",
        )
        self.expect(
            "stale_risk_policy_pin",
            409,
            self.invoke(
                new_intent,
                "request_allocation",
                self.pins(first)
                | {"expected_policy_version": before["expected_policy_version"]},
            ),
        )
        readiness = self.expect(
            "expired_owner_readiness",
            200,
            self.request(
                "GET",
                PORTFOLIO + f"/api/v1/portfolios/{stale_data['id']}/readiness",
                token=bob,
            ),
        )
        require(
            readiness.get("status") == "EXPIRED"
            and readiness.get("data_origin") == "real",
            "Expired fixture is not currently expired at the Portfolio owner.",
        )
        expired_grant = self.expect(
            "expired_data_intent_issue",
            200,
            self.issue(bob, self.grant_body(stale_data)),
        )
        rejected = self.expect(
            "expired_data_rejected",
            (409, 503),
            self.invoke(expired_grant, "request_allocation", self.pins(stale_data)),
        )
        require(
            not rejected.get("job_id"),
            "Expired input unexpectedly returned an accepted allocation.",
        )
        status, users = self.admin("GET", "/users?username=bob&exact=true")
        require(
            status == 200 and len(users) == 1,
            "Could not locate exactly one existing Bob identity.",
        )
        with temporarily_disabled(self.admin, users[0]["id"]):
            self.expect("disabled_owner_rejected", 403, self.invoke(grant))
        self.expect("restored_owner_allowed", 200, self.invoke(grant))
        self.expect(
            "revoke_bob_only",
            200,
            self.request(
                "POST",
                PORTFOLIO + "/api/v1/chat/delegations/revoke",
                token=bob,
                body={},
            ),
        )
        self.expect("revoked_reference_rejected", 403, self.invoke(grant))
        expiry_grant = self.expect(
            "expiry_probe_issue",
            200,
            self.issue(bob, self.grant_body(first, ["get_portfolio_summary"])),
        )
        self.expect("expiry_probe_initially_valid", 200, self.invoke(expiry_grant))
        expires = datetime.fromisoformat(
            expiry_grant["expires_at"].replace("Z", "+00:00")
        )
        require(
            250 < (expires - datetime.now(timezone.utc)).total_seconds() <= 301,
            "Actual grant TTL differs from the expected five-minute expiry.",
        )
        print(
            json.dumps(
                {
                    "phase": "waiting_for_actual_expiry",
                    "completed_checks": len(self.checks),
                    "probe_http_status_counts": dict(self.statuses),
                }
            ),
            flush=True,
        )
        while (expires - datetime.now(timezone.utc)).total_seconds() > -2:
            remaining = self.deadline - time.monotonic()
            require(
                remaining > 0,
                "Authorization gate exceeded its 360-second deadline before real expiry.",
            )
            time.sleep(
                min(
                    15,
                    remaining,
                    max(
                        0.01, (expires - datetime.now(timezone.utc)).total_seconds() + 2
                    ),
                )
            )
        self.expect(
            "actually_expired_reference_rejected", 403, self.invoke(expiry_grant)
        )
        print(
            json.dumps(
                {
                    "result": "PASS",
                    "checks": len(self.checks),
                    "probe_http_status_counts": dict(self.statuses),
                    "elapsed_seconds": round(
                        360 - (self.deadline - time.monotonic()), 2
                    ),
                    "account_state_restored": True,
                    "targets_accepted": 0,
                    "receipt_files_written": 0,
                }
            ),
            flush=True,
        )


def main():
    require_disposable_stack()
    with httpx.Client(follow_redirects=False) as client:
        Gate(client).run()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # No traceback or HTTP exception text: either could expose opaque references.
        message = (
            str(error)
            if isinstance(error, GateFailure)
            else "Authorization gate failed; no credentials or opaque references printed."
        )
        raise SystemExit("FAIL: " + message) from None
