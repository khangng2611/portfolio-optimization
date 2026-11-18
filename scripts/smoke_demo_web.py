"""Check the real HTTPS-profile BFF from the trusted VPS, without logging cookies."""

import argparse
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from check_private_demo import validate_origin

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3000"


def secure_session_cookie(headers):
    cookies = SimpleCookie()
    for header in headers:
        cookies.load(header)
    cookie = cookies.get("__Host-portfolio_session")
    if (
        not cookie
        or not cookie["secure"]
        or not cookie["httponly"]
        or cookie["path"] != "/"
        or cookie["domain"]
        or cookie["samesite"].lower() != "lax"
    ):
        raise ValueError("HTTPS session cookie protections are missing")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", cookie.value):
        raise ValueError("Invalid opaque session cookie")
    return "__Host-portfolio_session=" + cookie.value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(origin):
    validate_origin(origin)
    if not origin.startswith("https://"):
        raise ValueError("Public demo requires HTTPS")
    accounts = json.loads((ROOT / "infra/local/.generated/accounts.json").read_text())[
        "users"
    ]
    alice = next(a for a in accounts if a["username"] == "alice")
    opener = build_opener(NoRedirect())

    def request(method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = {"Origin": origin, "Content-Type": "application/json", **(headers or {})}
        try:
            with opener.open(
                Request(BASE + path, data=data, headers=h, method=method), timeout=15
            ) as r:
                raw = r.read(1024 * 1024)
                return (
                    r.status,
                    json.loads(raw) if raw else {},
                    r.headers.get_all("Set-Cookie", []),
                )
        except HTTPError as error:
            return error.code, {}, []

    status, _, cookies = request(
        "POST",
        "/auth/login",
        {"username": alice["username"], "password": alice["password"]},
    )
    if status != 204:
        raise ValueError("BFF login did not succeed")
    cookie = secure_session_cookie(cookies)
    status, session, _ = request("GET", "/auth/session", headers={"Cookie": cookie})
    if status != 200 or session.get("authenticated") is not True:
        raise ValueError("BFF session unavailable")
    auth = {"Cookie": cookie, "X-CSRF-Token": session["csrfToken"]}
    status, _, _ = request(
        "POST", "/api/v1/onboarding/portfolios", {}, headers={"Cookie": cookie}
    )
    if status != 403:
        raise ValueError("Missing CSRF was not rejected")
    status, _, _ = request(
        "POST", "/auth/logout", headers={**auth, "Origin": "https://invalid.example"}
    )
    if status != 403:
        raise ValueError("Cross-origin mutation was not rejected")
    status, _, _ = request("GET", "/api/v1/portfolios", headers=auth)
    if status != 200:
        raise ValueError("BFF owner-scoped API unavailable")
    status, logged_out, _ = request("POST", "/auth/logout", headers=auth)
    if status != 200 or not all(
        logged_out.get(key) is True
        for key in ("loggedOut", "providerRevoked", "delegationRevoked")
    ):
        raise ValueError("BFF logout failed")
    status, _, _ = request("GET", "/auth/session", headers={"Cookie": cookie})
    if status != 401:
        raise ValueError("Revoked BFF session remained usable")
    print(
        "PASS: BFF login, Secure/HttpOnly/SameSite cookies, CSRF, origin, owner API and logout."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    try:
        check(args.origin)
    except Exception:
        raise SystemExit(
            "FAIL: public-profile BFF check failed; no cookie/credential details printed."
        ) from None
