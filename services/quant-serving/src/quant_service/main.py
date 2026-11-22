import os
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from service_auth import AuthError, TokenVerifier
from portfolio_contracts import ModelUnavailable, Constraints, ReadyInput, StrictModel
from portfolio_contracts.selection import SelectionContext, SelectionProof
from portfolio_contracts.selection import CandidateSet
from service_observability import configure, install_http_tracing
from .publication_api import install_publication_api, CredentialModelResolver
from .runtime import catalog_from_env, sessions_from_env
from .full import FullDataUnavailable


class SelectionReadyRequest(CandidateSet):
    strategy: Literal["EW", "MVO", "BL_ML"] = "BL_ML"
    constraints: Constraints | None = None
    portfolio_version: int | None = None
    revision_id: str | None = None
    candidate_hash: str | None = None


class VerifySelectionRequest(StrictModel):
    inputs: ReadyInput
    selection_context: SelectionContext
    selection_proof: SelectionProof
    constraints: Constraints
    strategy: Literal["EW", "MVO", "BL_ML", "HYBRID"]


def create_app(*, sessions, verifier, catalog, model_resolver=None):
    app = FastAPI(title="Quant Serving", version="0.1.0")
    install_http_tracing(app)
    bearer = HTTPBearer(auto_error=False)
    install_publication_api(
        app,
        sessions=sessions,
        verifier=verifier,
        bearer=bearer,
        model_resolver=model_resolver,
    )

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

    def resolver_identity(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        try:
            if credentials is None:
                raise AuthError()
            identity = verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(401, "Service identity required") from None
        if "quant:resolve" not in identity.scopes:
            raise HTTPException(403, "Missing quant:resolve scope")
        return identity

    @app.post("/internal/v1/inputs/verify-selection")
    def verify_selection(
        body: VerifySelectionRequest, identity=Depends(resolver_identity)
    ):
        from types import SimpleNamespace
        from .selection import recompute_selection

        command = SimpleNamespace(
            inputs=body.inputs,
            selection_context=body.selection_context,
            constraints=body.constraints,
            strategy=body.strategy,
            deadline=body.selection_context.valid_until,
            decision_context=None,
            input_hash=body.selection_proof.input_hash,
        )
        try:
            actual = recompute_selection(catalog.selection_catalog, command)[3]
            return {"valid": actual == body.selection_proof}
        except (ValueError, KeyError, TypeError, OSError):
            return {"valid": False}

    @app.post("/internal/v1/inputs/selection-ready")
    def selection_ready(
        body: SelectionReadyRequest, identity=Depends(resolver_identity)
    ):
        from .selection_ready import prepare_selection

        try:
            return prepare_selection(
                catalog.selection_catalog, body.model_dump(mode="json")
            ).model_dump(mode="json")
        except (ValueError, KeyError, TypeError, OSError):
            raise HTTPException(409, {"code": "INPUT_INVALID"}) from None

    @app.get("/internal/v1/assets/catalog")
    def assets(identity=Depends(resolver_identity)):
        from .asset_catalog import asset_catalog

        return asset_catalog(catalog)

    @app.get("/internal/v1/inputs/universes")
    def universes(identity=Depends(resolver_identity)):
        try:
            return catalog.universes()
        except ValueError:
            raise HTTPException(503, "Verified catalog unavailable") from None

    @app.get("/internal/v1/inputs/ready")
    def ready(
        universe_id: str,
        strategy: Literal["EW", "MVO", "BL_ML"],
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        try:
            if credentials is None:
                raise AuthError()
            identity = verifier.verify(credentials.credentials)
        except AuthError:
            raise HTTPException(401, "Service identity required") from None
        if "quant:resolve" not in identity.scopes:
            raise HTTPException(403, "Missing quant:resolve scope")
        try:
            return catalog.ready(universe_id, strategy).model_dump(mode="json")
        except FullDataUnavailable as exc:
            raise HTTPException(
                409, {"code": exc.code, "message": str(exc), "details": exc.details}
            ) from None
        except ModelUnavailable:
            raise HTTPException(409, {"code": "MODEL_UNAVAILABLE"}) from None
        except ValueError:
            raise HTTPException(503, "Compatible verified input unavailable") from None

    @app.get("/internal/v1/inputs/readiness")
    def readiness(
        universe_id: str | None = Query(default=None, pattern=r"^[A-Z0-9_-]{1,64}$"),
        identity=Depends(resolver_identity),
    ):
        try:
            return catalog.readiness(universe_id)
        except (ValueError, KeyError, TypeError, OSError):
            raise HTTPException(503, "Verified catalog unavailable") from None

    return app


def app_factory():
    configure("quant-api")
    return create_app(
        sessions=sessions_from_env(),
        verifier=TokenVerifier(
            os.environ["OIDC_ISSUER"], "quant-api", os.environ["OIDC_JWKS_URL"]
        ),
        catalog=catalog_from_env(),
        model_resolver=CredentialModelResolver()
        if os.environ.get("ML_API_URL")
        else None,
    )
