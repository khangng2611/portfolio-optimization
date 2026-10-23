import os
import threading
import time

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from service_observability import inject_headers, span


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
        with span("quant.inputs.resolve", attributes={"strategy": strategy}):
            response = httpx.get(
                os.environ["QUANT_API_URL"] + "/internal/v1/inputs/ready",
                params={"universe_id": universe_id, "strategy": strategy},
                headers=inject_headers({"Authorization": f"Bearer {token}"}),
                timeout=3,
            )
            response.raise_for_status()
            return response.json()
