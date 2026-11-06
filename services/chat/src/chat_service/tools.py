"""Scoped HTTP adapter; opaque grants live only in the Chat database/headers."""

import os
import threading
import time
import httpx


class ToolError(Exception):
    def __init__(self, code, *, permanent=False):
        self.code, self.permanent = code, permanent
        super().__init__(code)


class Tools:
    def __init__(self):
        self.lock = threading.Lock()
        self.token, self.expires = None, 0

    def service_headers(self):
        with self.lock:
            if self.expires <= time.monotonic():
                r = httpx.post(
                    os.environ["OIDC_TOKEN_URL"],
                    data={
                        "grant_type": "client_credentials",
                        "client_id": "chat-service",
                        "client_secret": os.environ["CHAT_CLIENT_SECRET"],
                        "scope": "chat:delegate market:chat:read",
                    },
                    timeout=3,
                )
                r.raise_for_status()
                data = r.json()
                self.token, self.expires = (
                    data["access_token"],
                    time.monotonic() + max(0, data["expires_in"] - 30),
                )
            return {"Authorization": "Bearer " + self.token}

    @staticmethod
    def checked(r):
        if r.status_code in (401, 403):
            raise ToolError("AUTHORIZATION_REQUIRED", permanent=True)
        if r.status_code == 404:
            raise ToolError("RESOURCE_UNAVAILABLE", permanent=True)
        if r.status_code in (409, 412, 422):
            raise ToolError("STALE_OR_INVALID_INPUT", permanent=True)
        r.raise_for_status()
        return r.json()

    def grant(
        self,
        token,
        conversation_id,
        job_id,
        portfolio_id,
        authorization_id=None,
        allow_mutation=False,
    ):
        headers = {
            "Authorization": "Bearer " + token,
            "X-Service-Authorization": self.service_headers()["Authorization"],
        }
        permitted = [
            "get_profile",
            "get_portfolio_summary",
            "get_recommendation",
            "get_allocation_job",
        ]
        if allow_mutation:
            permitted.append("request_allocation")
        return self.checked(
            httpx.post(
                os.environ["PORTFOLIO_API_URL"] + "/internal/v1/delegation-grants",
                headers=headers,
                json={
                    "conversation_id": conversation_id,
                    "job_id": job_id,
                    "authorization_id": authorization_id,
                    "portfolio_id": portfolio_id,
                    "tools": permitted,
                },
                timeout=4,
            )
        )

    def call(self, job, tool, args):
        headers = self.service_headers() | {
            "X-Delegation-Grant": job.grant_id,
            "X-Chat-Job": job.id,
            "X-Chat-Conversation": job.conversation_id,
        }
        if tool == "get_market_facts":
            return self.checked(
                httpx.get(
                    os.environ["MARKET_API_URL"] + "/internal/v1/chat/market-facts",
                    headers=self.service_headers(),
                    params=args,
                    timeout=3,
                )
            )
        return self.checked(
            httpx.post(
                os.environ["PORTFOLIO_API_URL"] + "/internal/v1/chat-tools/" + tool,
                headers=headers,
                json=args,
                timeout=4,
            )
        )

    def read_recommendation(self, token, rid):
        return self.checked(
            httpx.get(
                os.environ["PORTFOLIO_API_URL"] + "/api/v1/recommendations/" + rid,
                headers={"Authorization": "Bearer " + token},
                timeout=3,
            )
        )
