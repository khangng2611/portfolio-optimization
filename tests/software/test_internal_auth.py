import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_service.api import create_app, password_hash
from auth_service.models import Account, Base

ISSUER = "http://auth-api:8000"
WEB = {"Authorization": "Bearer browser-secret"}
READER = {"Authorization": "Bearer reader-secret"}
CREDENTIALS = {
    "username": "  New_User ",
    "password": " pass word 123! ",
    "name": "New User",
}


@pytest.fixture
def auth():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app = create_app(
        sessions,
        ISSUER,
        key,
        "browser-secret",
        "reader-secret",
        {"portfolio-service": "quant-secret", "chat-service": "chat-secret"},
    )
    with TestClient(app) as client:
        yield client, sessions


def test_registration_login_rotation_and_revoke(auth):
    client, sessions = auth
    assert client.post("/internal/v1/register", json=CREDENTIALS).status_code == 401
    assert (
        client.post(
            "/internal/v1/register",
            headers=WEB,
            json={**CREDENTIALS, "role": "system-admin"},
        ).status_code
        == 422
    )
    assert (
        client.post("/internal/v1/register", headers=WEB, json=CREDENTIALS).status_code
        == 201
    )
    assert (
        client.post(
            "/internal/v1/register",
            headers=WEB,
            json={**CREDENTIALS, "username": "NEW_USER"},
        ).status_code
        == 409
    )
    with sessions() as db:
        user = db.scalar(select(Account))
        assert user.username == "new_user"
        assert user.password_hash.startswith("$argon2id$")
    login = {key: CREDENTIALS[key] for key in ("username", "password")}
    assert (
        client.post(
            "/internal/v1/login",
            headers=WEB,
            json={**login, "password": login["password"].strip()},
        ).status_code
        == 401
    )
    result = client.post("/internal/v1/login", headers=WEB, json=login)
    assert result.status_code == 200
    session = result.json()
    jwk = jwt.PyJWK.from_dict(client.get("/.well-known/jwks.json").json()["keys"][0])
    claims = jwt.decode(
        session["accessToken"],
        jwk.key,
        algorithms=["RS256"],
        issuer=ISSUER,
        audience="portfolio-api",
    )
    assert claims["realm_access"]["roles"] == ["investor"]
    assert "ml:review" not in claims["scope"].split()
    assert claims["exp"] - claims["iat"] == 300
    active = f"/internal/v1/accounts/{claims['sub']}"
    assert client.get(active, headers=WEB).status_code == 401
    assert client.get(active, headers=READER).json() == {"active": True}
    refresh = {key: session[key] for key in ("sessionId", "refreshToken")}
    rotated = client.post("/internal/v1/refresh", headers=WEB, json=refresh).json()
    assert rotated["sessionId"] == session["sessionId"]
    assert rotated["refreshToken"] != session["refreshToken"]
    assert (
        client.post("/internal/v1/refresh", headers=WEB, json=refresh).status_code
        == 401
    )
    assert (
        client.post(
            "/internal/v1/revoke", headers=WEB, json={"sessionId": session["sessionId"]}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/internal/v1/refresh",
            headers=WEB,
            json={**refresh, "refreshToken": rotated["refreshToken"]},
        ).status_code
        == 401
    )


def test_registration_password_requires_six_characters_and_punctuation(auth):
    client, _ = auth
    for invalid in ("abcd!", "abcdef", "abcde ", "🔒🔒🔒🔒!", "a" * 128 + "!"):
        result = client.post(
            "/internal/v1/register",
            headers=WEB,
            json={**CREDENTIALS, "password": invalid},
        )
        assert result.status_code == 422

    for credentials in (
        {"username": "short_pass", "password": "abcde!"},
        {"username": "long_pass", "password": "🔒" * 127 + "!"},
    ):
        registered = client.post(
            "/internal/v1/register", headers=WEB, json={**CREDENTIALS, **credentials}
        )
        assert registered.status_code == 201
        logged_in = client.post("/internal/v1/login", headers=WEB, json=credentials)
        assert logged_in.status_code == 200


def test_existing_password_without_punctuation_still_works(auth):
    client, sessions = auth
    credentials = {"username": "existing_user", "password": "oldpassword123"}
    with sessions.begin() as db:
        db.add(
            Account(
                username=credentials["username"],
                name="Existing User",
                role="investor",
                password_hash=password_hash(credentials["password"]),
            )
        )
    assert client.post("/internal/v1/login", headers=WEB, json=credentials).status_code == 200


def test_invalid_name_and_disabled_account_fail_closed(auth):
    client, sessions = auth
    bad = {**CREDENTIALS, "name": "Invalid\x00name"}
    assert (
        client.post("/internal/v1/register", headers=WEB, json=bad).status_code == 422
    )
    assert (
        client.post("/internal/v1/register", headers=WEB, json=CREDENTIALS).status_code
        == 201
    )
    credentials = {key: CREDENTIALS[key] for key in ("username", "password")}
    session = client.post("/internal/v1/login", headers=WEB, json=credentials).json()
    with sessions.begin() as db:
        user = db.scalar(select(Account))
        user.enabled = False
    assert (
        client.post("/internal/v1/login", headers=WEB, json=credentials).status_code
        == 401
    )
    assert (
        client.post(
            "/internal/v1/refresh",
            headers=WEB,
            json={key: session[key] for key in ("sessionId", "refreshToken")},
        ).status_code
        == 401
    )
    assert client.get(
        "/internal/v1/accounts/" + session["user"]["sub"], headers=READER
    ).json() == {"active": False}


def test_machine_tokens_cannot_escalate(auth):
    client, _ = auth
    body = {
        "grant_type": "client_credentials",
        "client_id": "portfolio-service",
        "client_secret": "quant-secret",
    }
    assert (
        client.post(
            "/internal/v1/token", data={**body, "scope": "market:write"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/internal/v1/token", data={**body, "client_secret": "wrong"}
        ).status_code
        == 401
    )
    response = client.post(
        "/internal/v1/token", data={**body, "scope": "quant:resolve"}
    )
    assert response.status_code == 200
    key = jwt.PyJWK.from_dict(
        client.get("/.well-known/jwks.json").json()["keys"][0]
    ).key
    token = response.json()["access_token"]
    claims = jwt.decode(
        token, key, algorithms=["RS256"], issuer=ISSUER, audience="quant-api"
    )
    assert claims["realm_access"]["roles"] == []
    assert claims["azp"] == "portfolio-service"
    assert claims["scope"] == "quant:resolve"
    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            token, key, algorithms=["RS256"], issuer=ISSUER, audience="portfolio-api"
        )
