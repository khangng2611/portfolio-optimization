import os
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from sqlalchemy import text

from service_auth import AuthError, TokenVerifier
from .runtime import catalog_from_env, sessions_from_env


def create_app(*, sessions, verifier, catalog):
    app = FastAPI(title="Quant Serving", version="0.1.0")

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def health():
        try:
            with sessions() as session:
                session.execute(text("SELECT 1 FROM numerical_run LIMIT 1"))
        except Exception:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ready"}

    @app.get("/internal/v1/inputs/ready")
    def ready(
        universe_id: str,
        strategy: Literal["EW", "MVO", "BL_ML"],
        authorization: str | None = Header(default=None),
    ):
        try:
            if not authorization or not authorization.startswith("Bearer "):
                raise AuthError()
            identity = verifier.verify(authorization[7:])
        except AuthError:
            raise HTTPException(401, "Service identity required") from None
        if "quant:resolve" not in identity.scopes:
            raise HTTPException(403, "Missing quant:resolve scope")
        try:
            return catalog.ready(universe_id, strategy).model_dump(mode="json")
        except ValueError:
            raise HTTPException(503, "Compatible verified input unavailable") from None

    return app


def app_factory():
    return create_app(
        sessions=sessions_from_env(),
        verifier=TokenVerifier(
            os.environ["OIDC_ISSUER"], "quant-api", os.environ["OIDC_JWKS_URL"]
        ),
        catalog=catalog_from_env(),
    )
