import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from service_auth import AuthError, TokenVerifier


@pytest.fixture
def signing():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = TokenVerifier(
        "https://identity/realms/portfolio", "portfolio-api", "https://identity/keys"
    )
    verifier.keys = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
    )
    claims = {
        "iss": verifier.issuer,
        "aud": "portfolio-api",
        "sub": "user-a",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "scope": "portfolio:read portfolio:write",
        "realm_access": {"roles": ["investor"]},
    }
    return key, verifier, claims


def test_valid_identity_roles_and_scopes(signing):
    key, verifier, claims = signing
    principal = verifier.verify(jwt.encode(claims, key, algorithm="RS256"))
    assert principal.subject == "user-a"
    assert principal.roles == frozenset({"investor"})
    assert principal.scopes == frozenset({"portfolio:read", "portfolio:write"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "other-api"},
        {"iss": "https://attacker"},
        {"exp": 1},
        {"sub": ""},
        {"realm_access": {"roles": "system-admin"}},
    ],
)
def test_rejects_invalid_claims(signing, overrides):
    key, verifier, claims = signing
    with pytest.raises(AuthError):
        verifier.verify(jwt.encode(claims | overrides, key, algorithm="RS256"))


def test_rejects_forged_signature(signing):
    _, verifier, claims = signing
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        verifier.verify(jwt.encode(claims, attacker, algorithm="RS256"))


def test_rejects_unsigned_and_missing_expiry(signing):
    key, verifier, claims = signing
    with pytest.raises(AuthError):
        verifier.verify(jwt.encode(claims, key="", algorithm="none"))
    del claims["exp"]
    with pytest.raises(AuthError):
        verifier.verify(jwt.encode(claims, key, algorithm="RS256"))
