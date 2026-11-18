import json
import re
import secrets
from hashlib import sha256
from string import punctuation
from time import time
from urllib.parse import parse_qs
from uuid import UUID

import jwt
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from .models import Account, RefreshSession

ACCESS_SECONDS = 300
SESSION_SECONDS = 8 * 60 * 60
ROLE_SCOPES = {
    "investor": (),
    "researcher": (),
    "data-operator": (
        "market:write",
        "quant:publish",
        "ml:read",
        "ml:train",
        "knowledge:read",
        "knowledge:write",
    ),
    "model-reviewer": ("ml:read", "ml:review"),
    "system-admin": (),
}
BASE_SCOPES = (
    "portfolio:read",
    "portfolio:write",
    "chat:read",
    "chat:write",
    "market:read",
)
SERVICE_SCOPES = {
    "portfolio-service": {"quant:resolve": "quant-api"},
    "quant-publisher": {"market:snapshot:read": "market-api"},
    "ml-worker": {"market:snapshot:read": "market-api"},
    "quant-ml-reader": {"ml:model:read": "ml-api"},
    "chat-service": {
        "chat:delegate": "portfolio-api",
        "market:chat:read": "market-api",
        "knowledge:retrieve": "knowledge-api",
    },
}
INVALID_LOGIN = "Thông tin đăng nhập không hợp lệ."
# Match JavaScript trim so a spelling has the same Redis rate-limit bucket and DB lookup.
USERNAME_WHITESPACE = (
    " \t\n\r\v\f\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005"
    "\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


def password_hash(password: str) -> str:
    return Argon2id(
        salt=secrets.token_bytes(16),
        length=32,
        iterations=2,
        lanes=1,
        memory_cost=19456,
    ).derive_phc_encoded(password.encode())


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def matches(value: str, expected: str) -> bool:
    return secrets.compare_digest(value.encode(), expected.encode())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    username: str = Field(max_length=128)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize(cls, value):
        value = value.strip(USERNAME_WHITESPACE)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{3,32}", value):
            raise ValueError("Invalid username")
        return value.lower()


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("password")
    @classmethod
    def require_punctuation(cls, value):
        if not any(character in punctuation for character in value):
            raise ValueError("Password requires ASCII punctuation")
        return value

    @field_validator("name")
    @classmethod
    def display_name(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Invalid display name")
        return value.strip()


class SessionId(StrictModel):
    sessionId: UUID


class Refresh(SessionId):
    refreshToken: str = Field(pattern=r"^[a-zA-Z0-9_-]{43}$")


def create_app(sessions, issuer, key, web_secret, reader_secret, client_secrets):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    public_key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    kid = digest(public_key["n"])[:32]
    dummy_hash = password_hash(secrets.token_urlsafe(24))

    def auth_header(expected, supplied):
        if not supplied or not matches(supplied, f"Bearer {expected}"):
            raise HTTPException(401, "Invalid service credential")

    def web(authorization: str | None = Header(default=None)):
        auth_header(web_secret, authorization)

    def reader(authorization: str | None = Header(default=None)):
        auth_header(reader_secret, authorization)

    def sign(subject, client_id, roles, scopes, audiences, expires_at=None):
        now = int(time())
        expires = (
            min(now + ACCESS_SECONDS, expires_at)
            if expires_at
            else now + ACCESS_SECONDS
        )
        token = jwt.encode(
            {
                "iss": issuer,
                "sub": subject,
                "iat": now,
                "exp": expires,
                "aud": sorted(set(audiences)),
                "realm_access": {"roles": roles},
                "scope": " ".join(scopes),
                "azp": client_id,
            },
            key,
            algorithm="RS256",
            headers={"kid": kid},
        )
        return token, expires

    def user_tokens(db, user, session):
        refresh_token = secrets.token_urlsafe(32)
        session.token_hash = digest(refresh_token)
        db.flush()
        scopes = BASE_SCOPES + ROLE_SCOPES[user.role]
        token, expires = sign(
            user.id,
            "portfolio-web",
            [user.role],
            scopes,
            [f"{scope.split(':', 1)[0]}-api" for scope in scopes],
            session.expires_at,
        )
        return {
            "accessToken": token,
            "refreshToken": refresh_token,
            "accessExpiresAt": expires * 1000,
            "sessionId": session.id,
            "sessionExpiresAt": session.expires_at * 1000,
            "user": {"sub": user.id, "name": user.name, "roles": [user.role]},
        }

    @app.exception_handler(RequestValidationError)
    def invalid_body(_request, _error):
        return JSONResponse({"detail": "Thông tin tài khoản không hợp lệ."}, 422)

    @app.exception_handler(SQLAlchemyError)
    def database_error(_request, _error):
        return JSONResponse({"detail": "Authentication service unavailable"}, 503)

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/ready")
    def ready():
        with sessions() as db:
            db.scalar(select(Account.id).limit(1))
            db.scalar(select(RefreshSession.id).limit(1))
        return {"status": "ready"}

    @app.get("/.well-known/jwks.json")
    def jwks():
        return {"keys": [{**public_key, "kid": kid, "alg": "RS256", "use": "sig"}]}

    @app.post("/internal/v1/register", status_code=201, dependencies=[Depends(web)])
    def register(body: Registration):
        try:
            with sessions.begin() as db:
                db.add(
                    Account(
                        username=body.username,
                        name=body.name,
                        password_hash=password_hash(body.password),
                        role="investor",
                    )
                )
        except IntegrityError:
            raise HTTPException(409, "Tên đăng nhập đã được sử dụng.") from None
        return {}

    @app.post("/internal/v1/login", dependencies=[Depends(web)])
    def login(body: Credentials):
        with sessions.begin() as db:
            user = db.scalar(select(Account).where(Account.username == body.username))
            try:
                Argon2id.verify_phc_encoded(
                    body.password.encode(), user.password_hash if user else dummy_hash
                )
            except InvalidKey:
                raise HTTPException(401, INVALID_LOGIN) from None
            if not user or not user.enabled or user.role not in ROLE_SCOPES:
                raise HTTPException(401, INVALID_LOGIN)
            now = int(time())
            db.execute(
                delete(RefreshSession).where(
                    RefreshSession.account_id == user.id,
                    RefreshSession.expires_at <= now,
                )
            )
            session = RefreshSession(
                account_id=user.id, expires_at=now + SESSION_SECONDS
            )
            db.add(session)
            return user_tokens(db, user, session)

    @app.post("/internal/v1/refresh", dependencies=[Depends(web)])
    def refresh(body: Refresh):
        with sessions.begin() as db:
            session = db.scalar(
                select(RefreshSession)
                .where(RefreshSession.id == str(body.sessionId))
                .with_for_update()
            )
            if (
                not session
                or session.expires_at <= int(time())
                or not matches(session.token_hash, digest(body.refreshToken))
            ):
                raise HTTPException(401, INVALID_LOGIN)
            user = db.get(Account, session.account_id)
            if not user or not user.enabled or user.role not in ROLE_SCOPES:
                raise HTTPException(401, INVALID_LOGIN)
            return user_tokens(db, user, session)

    @app.post("/internal/v1/revoke", status_code=204, dependencies=[Depends(web)])
    def revoke(body: SessionId):
        with sessions.begin() as db:
            db.execute(
                delete(RefreshSession).where(RefreshSession.id == str(body.sessionId))
            )
        return Response(status_code=204)

    @app.get("/internal/v1/accounts/{subject}", dependencies=[Depends(reader)])
    def account_active(subject: UUID):
        with sessions() as db:
            user = db.get(Account, str(subject))
            return {"active": bool(user and user.enabled and user.role in ROLE_SCOPES)}

    @app.post("/internal/v1/token")
    async def client_token(request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 4096:
                raise HTTPException(413, "Request too large")
            raw.extend(chunk)
        if (
            request.headers.get("content-type", "").split(";")[0]
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(415, "Form required")
        try:
            form = parse_qs(raw.decode("ascii"), max_num_fields=4)
        except ValueError:
            raise HTTPException(400, "Invalid token request") from None
        if form.get("grant_type") != ["client_credentials"]:
            raise HTTPException(400, "Invalid grant type")
        client_id = form.get("client_id", [""])[0]
        expected = client_secrets.get(client_id)
        if not expected or not matches(form.get("client_secret", [""])[0], expected):
            raise HTTPException(401, "Invalid service credential")
        policy = SERVICE_SCOPES[client_id]
        scopes = form.get("scope", [" ".join(policy)])[0].split()
        if not scopes or not set(scopes) <= policy.keys():
            raise HTTPException(403, "Scope not permitted")
        token, _ = sign(
            client_id, client_id, [], scopes, [policy[scope] for scope in scopes]
        )
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": ACCESS_SECONDS,
        }

    return app
