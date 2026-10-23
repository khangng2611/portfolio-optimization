import os

from service_auth import TokenVerifier
from .api import create_app
from .runtime import QuantResolver, sessions_from_env


def app_factory():
    return create_app(
        sessions=sessions_from_env(),
        verifier=TokenVerifier(
            os.environ["OIDC_ISSUER"], "portfolio-api", os.environ["OIDC_JWKS_URL"]
        ),
        resolver=QuantResolver(),
    )
