import importlib.util
from pathlib import Path
import pytest


@pytest.fixture
def web(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/smoke_demo_web.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("smoke_demo_web", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cookie(**changes):
    parts = {
        "name": "__Host-portfolio_session",
        "value": "a" * 43,
        "path": "Path=/",
        "secure": "Secure",
        "http": "HttpOnly",
        "site": "SameSite=Lax",
        "domain": "",
    }
    parts.update(changes)
    return f"{parts['name']}={parts['value']}; " + "; ".join(
        parts[k] for k in ["path", "secure", "http", "site", "domain"] if parts[k]
    )


def test_accepts_protected_cookie_without_printing_it(web):
    assert (
        web.secure_session_cookie([cookie()]) == "__Host-portfolio_session=" + "a" * 43
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "portfolio_session"},
        {"secure": ""},
        {"http": ""},
        {"site": "SameSite=None"},
        {"path": "Path=/auth"},
        {"domain": "Domain=example.ts.net"},
        {"value": "short"},
    ],
)
def test_rejects_weakened_cookie(web, changes):
    with pytest.raises(ValueError):
        web.secure_session_cookie([cookie(**changes)])


def test_bff_gate_accepts_real_logout_json_contract(web, tmp_path, monkeypatch):
    import json
    from email.message import Message
    from urllib.error import HTTPError
    from urllib.parse import urlsplit

    generated = tmp_path / "infra/local/.generated"
    generated.mkdir(parents=True)
    (generated / "accounts.json").write_text(
        json.dumps({"users": [{"username": "alice", "password": "fixture-only"}]})
    )
    monkeypatch.setattr(web, "ROOT", tmp_path)

    class Response:
        def __init__(self, status, body=None, headers=None):
            self.status = status
            self.body = body
            self.headers = headers or Message()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps(self.body).encode() if self.body is not None else b""

    class Opener:
        revoked = False

        def open(self, request, timeout):
            path = urlsplit(request.full_url).path
            if path == "/auth/login":
                headers = Message()
                headers.add_header("Set-Cookie", cookie())
                return Response(204, headers=headers)
            if path == "/auth/session":
                if self.revoked:
                    raise HTTPError(request.full_url, 401, "", Message(), None)
                return Response(
                    200, {"authenticated": True, "csrfToken": "fixture-csrf"}
                )
            if (
                path == "/api/v1/onboarding/portfolios"
                or request.get_header("Origin") == "https://invalid.example"
            ):
                raise HTTPError(request.full_url, 403, "", Message(), None)
            if path == "/api/v1/portfolios":
                return Response(200, [])
            if path == "/auth/logout":
                self.revoked = True
                return Response(
                    200,
                    {
                        "loggedOut": True,
                        "providerRevoked": True,
                        "delegationRevoked": True,
                    },
                )
            raise AssertionError(path)

    monkeypatch.setattr(web, "build_opener", lambda *args: Opener())
    web.check("https://demo.tail123.ts.net")
