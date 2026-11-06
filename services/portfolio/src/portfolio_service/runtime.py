import os
import threading
import time

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from service_observability import inject_headers, span
from portfolio_contracts import ModelUnavailable


def sessions_from_env():
    return sessionmaker(
        create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True),
        expire_on_commit=False,
    )


class QuantResolver:
    def __init__(self):
        self.lock = threading.Lock()
        self.token, self.expires = None, 0

    def ready(self, universe_id, strategy):
        return self._read(
            "/internal/v1/inputs/ready",
            {"universe_id": universe_id, "strategy": strategy},
        )

    def universes(self):
        return self._read("/internal/v1/inputs/universes", {})

    def readiness(self, universe_id=None):
        return self._read(
            "/internal/v1/inputs/readiness",
            {"universe_id": universe_id} if universe_id is not None else {},
        )

    def _read(self, path, params):
        with self.lock:
            if self.expires <= time.monotonic():
                response = httpx.post(
                    os.environ["OIDC_TOKEN_URL"],
                    data={
                        "grant_type": "client_credentials",
                        "client_id": "portfolio-service",
                        "client_secret": os.environ["QUANT_CLIENT_SECRET"],
                        "scope": "quant:resolve",
                    },
                    timeout=3,
                )
                response.raise_for_status()
                data = response.json()
                self.token, self.expires = (
                    data["access_token"],
                    time.monotonic() + max(0, data["expires_in"] - 30),
                )
            token = self.token
        with span(
            "quant.inputs.resolve",
            attributes={"strategy": params.get("strategy", "catalog")},
        ):
            response = httpx.get(
                os.environ["QUANT_API_URL"] + path,
                params=params,
                headers=inject_headers({"Authorization": f"Bearer {token}"}),
                timeout=3,
            )
            if response.status_code == 409:
                try:
                    detail = response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                if (
                    isinstance(detail, dict)
                    and detail.get("code") == "MODEL_UNAVAILABLE"
                ):
                    raise ModelUnavailable("No compatible approved model")
            response.raise_for_status()
            return response.json()


class IdentityStatus:
    """Current account/role check using a read-only Keycloak service identity.

    A dependency outage fails closed. No user token or grant is sent to Identity.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.token, self.expires = None, 0

    def __call__(self, issuer, subject):
        from uuid import UUID

        try:
            UUID(subject)
            if issuer != os.environ["OIDC_ISSUER"]:
                return False
            with self.lock:
                if self.expires <= time.monotonic():
                    r = httpx.post(
                        os.environ["OIDC_TOKEN_URL"],
                        data={
                            "grant_type": "client_credentials",
                            "client_id": "portfolio-account-reader",
                            "client_secret": os.environ["OIDC_ACCOUNT_READER_SECRET"],
                        },
                        timeout=3,
                    )
                    r.raise_for_status()
                    data = r.json()
                    self.token, self.expires = (
                        data["access_token"],
                        time.monotonic() + max(0, data["expires_in"] - 30),
                    )
                headers = {"Authorization": "Bearer " + self.token}
            base = (
                os.environ["OIDC_TOKEN_URL"].split("/realms/")[0]
                + "/admin/realms/portfolio/users/"
                + subject
            )
            r = httpx.get(base, headers=headers, timeout=3)
            r.raise_for_status()
            if not r.json().get("enabled"):
                return False
            r = httpx.get(
                base + "/role-mappings/realm/composite", headers=headers, timeout=3
            )
            r.raise_for_status()
            human = {
                "investor",
                "researcher",
                "data-operator",
                "model-reviewer",
                "system-admin",
            }
            return bool(human.intersection(role["name"] for role in r.json()))
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False
