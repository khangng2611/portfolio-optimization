"""JWT authentication primitives. Business authorization remains in each owner."""

from dataclasses import dataclass

import jwt


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str
    roles: frozenset[str]
    scopes: frozenset[str]


class TokenVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str):
        self.issuer = issuer
        self.audience = audience
        self.keys = jwt.PyJWKClient(
            jwks_url, cache_jwk_set=True, lifespan=300, timeout=3
        )

    def verify(self, token: str) -> Principal:
        try:
            if (
                not token
                or len(token) > 16384
                or jwt.get_unverified_header(token).get("alg") != "RS256"
            ):
                raise AuthError("Invalid access token")
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            )
            roles = claims.get("realm_access", {}).get("roles", [])
            scope = claims.get("scope", "")
            if (
                not isinstance(claims["sub"], str)
                or not claims["sub"]
                or not isinstance(roles, list)
                or not all(isinstance(role, str) for role in roles)
                or not isinstance(scope, str)
            ):
                raise AuthError("Invalid access token claims")
            return Principal(
                self.issuer, claims["sub"], frozenset(roles), frozenset(scope.split())
            )
        except (jwt.PyJWTError, ValueError, TypeError, AttributeError, OSError) as exc:
            raise AuthError("Access token could not be verified") from exc
