import os
import threading
import time
from datetime import date

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from service_observability import inject_headers, span
from portfolio_contracts import ModelUnavailable, utcnow


class StaleInput(Exception):
    def __init__(self, detail):
        self.detail = detail
        super().__init__(detail["message"])


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

    def catalog(self):
        return self._read("/internal/v1/assets/catalog", {})

    def selection_ready(self, body):
        return self._read("/internal/v1/inputs/selection-ready", {}, body=body)

    def verify_selection(self, pin, context, proof, deadline, *, constraints, strategy):
        remaining = (deadline - utcnow()).total_seconds()
        if remaining <= 0:
            return False
        return self._read("/internal/v1/inputs/verify-selection", {}, body={
            "inputs": pin, "selection_context": context, "selection_proof": proof,
            "constraints": constraints, "strategy": strategy,
        }, timeout=min(15, remaining)).get("valid") is True

    def universes(self):
        return self._read("/internal/v1/inputs/universes", {})

    def readiness(self, universe_id=None):
        return self._read(
            "/internal/v1/inputs/readiness",
            {"universe_id": universe_id} if universe_id is not None else {},
        )

    def _read(self, path, params, *, body=None, timeout=3):
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
            request = httpx.get if body is None else httpx.post
            response = request(
                os.environ["QUANT_API_URL"] + path,
                **({"params": params} if body is None else {"json": body}),
                headers=inject_headers({"Authorization": f"Bearer {token}"}),
                timeout=timeout,
            )
            if response.status_code == 409:
                try:
                    detail = response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                if isinstance(detail, dict) and detail.get("code") in {
                    "VFF_STALE", "GOLD_STALE"
                }:
                    data = detail.get("details")
                    try:
                        observation = date.fromisoformat(data["observation_date"])
                    except (ValueError, TypeError, KeyError):
                        observation = None
                    if (
                        isinstance(data, dict)
                        and data.get("asset_id") == detail["code"].removesuffix("_STALE")
                        and observation is not None
                        and str(observation) == data["observation_date"]
                        and type(data.get("age_days")) is int
                        and data["age_days"] > 7
                        and type(data.get("max_age_days")) is int
                        and data["max_age_days"] == 7
                        and isinstance(detail.get("message"), str)
                        and 0 < len(detail["message"]) <= 1000
                    ):
                        raise StaleInput({
                            "code": detail["code"],
                            "message": detail["message"],
                            "details": {
                                key: data[key] for key in (
                                    "asset_id", "observation_date", "age_days", "max_age_days"
                                )
                            },
                        })
                if (
                    isinstance(detail, dict)
                    and detail.get("code") == "MODEL_UNAVAILABLE"
                ):
                    raise ModelUnavailable("No compatible approved model")
            response.raise_for_status()
            return response.json()


class IdentityStatus:
    """Read current account status when a Chat tool uses a delegation grant."""

    def __call__(self, issuer, subject):
        from uuid import UUID

        try:
            subject = str(UUID(subject))
            if issuer != os.environ["OIDC_ISSUER"]:
                return False
            response = httpx.get(
                os.environ["AUTH_ACCOUNT_STATUS_URL"] + "/" + subject,
                headers={"Authorization": "Bearer " + os.environ["AUTH_ACCOUNT_READER_SECRET"]},
                timeout=3,
                follow_redirects=False,
            )
            response.raise_for_status()
            return response.json().get("active") is True
        except (httpx.HTTPError, ValueError, KeyError, AttributeError, TypeError):
            return False
