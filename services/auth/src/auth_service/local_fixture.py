"""Compose exec fixture. Accept input only from stdin and emit results to its pipe."""

import json
import os
import sys

import httpx

from .main import CLIENT_SECRET_ENV, sessions_from_env
from .models import Account

BASE = "http://127.0.0.1:8000/internal/v1/"


def run(action, body):
    if action == "set-enabled":
        with sessions_from_env().begin() as db:
            account = db.get(Account, body["subject"])
            if not account:
                return 404, {}
            account.enabled = body["enabled"] is True
        return 204, {}
    with httpx.Client(timeout=8, follow_redirects=False) as client:
        if action == "login":
            response = client.post(
                BASE + "login",
                json=body,
                headers={"Authorization": "Bearer " + os.environ["AUTH_WEB_SECRET"]},
            )
        elif action == "token":
            response = client.post(
                BASE + "token",
                data={
                    **body,
                    "grant_type": "client_credentials",
                    "client_secret": os.environ[CLIENT_SECRET_ENV[body["client_id"]]],
                },
            )
        elif action == "account":
            response = client.get(
                BASE + "accounts/" + body["subject"],
                headers={
                    "Authorization": "Bearer "
                    + os.environ["PORTFOLIO_ACCOUNT_READER_SECRET"]
                },
            )
        else:
            raise ValueError("Invalid fixture action")
    return response.status_code, response.json() if response.status_code == 200 else {}


if __name__ == "__main__":
    try:
        if sys.stdin.isatty() or sys.stdout.isatty():
            raise ValueError("Fixture requires pipes")
        print(json.dumps(run(sys.argv[1], json.load(sys.stdin))))
    except Exception:
        raise SystemExit("Local Auth fixture failed; details withheld.") from None
