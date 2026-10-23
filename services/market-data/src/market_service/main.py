import os

from service_auth import TokenVerifier
from service_observability import configure
from .api import create_app
from .runtime import provider_from_env, sessions_from_env


def app_factory():
    configure("market-api")
    return create_app(
        sessions=sessions_from_env(),
        verifier=TokenVerifier(
            os.environ["OIDC_ISSUER"], "market-api", os.environ["OIDC_JWKS_URL"]
        ),
        provider=provider_from_env(),
    )
