import os
from service_auth import TokenVerifier
from service_observability import configure
from .api import create_app
from .runtime import sessions_from_env
from .tools import Tools


def app_factory():
    configure("chat-api")
    return create_app(
        sessions=sessions_from_env(),
        verifier=TokenVerifier(
            os.environ["OIDC_ISSUER"], "chat-api", os.environ["OIDC_JWKS_URL"]
        ),
        tools=Tools(),
    )
