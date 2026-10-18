import asyncio

import jwt

from myapp.auth.jwks import JWKSCache
from myapp.auth.principal import Principal
from myapp.core.config import AuthSettings
from myapp.core.exceptions import AppError


def string_set(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(value.split())
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return frozenset(value)
    raise ValueError("invalid claim type")


class TokenVerifier:
    def __init__(self, settings: AuthSettings, cache: JWKSCache):
        self.settings, self.cache = settings, cache

    async def verify(self, token: str) -> Principal:
        if not self.settings.configured:
            raise AppError(503, "SSO_NOT_CONFIGURED", "Authentication unavailable")
        try:
            if len(token) > 16384:
                raise ValueError("oversized token")
            header = jwt.get_unverified_header(token)
            algorithm, kid = header.get("alg"), header.get("kid")
            if algorithm not in self.settings.algorithms or not isinstance(kid, str) or not kid:
                raise ValueError("untrusted header")
            if header.get("crit"):
                raise ValueError("unsupported critical headers")
            key = await self.cache.key(kid, algorithm)
            claims = await asyncio.to_thread(
                jwt.decode,
                token,
                key.key,
                algorithms=self.settings.algorithms,
                issuer=self.settings.issuer,
                audience=self.settings.audience,
                leeway=self.settings.clock_skew,
                options={
                    "require": list(
                        set(self.settings.required_claims) | {"sub", "iss", "aud", "exp", "iat"}
                    )
                },
            )
            if not isinstance(claims["sub"], str) or not claims["sub"]:
                raise ValueError("subject required")
            if any(claims.get(k) != v for k, v in self.settings.expected_claims.items()):
                raise ValueError("claim mismatch")
            return Principal(
                subject=claims["sub"],
                issuer=claims["iss"],
                scopes=string_set(claims.get("scope", "")),
                roles=string_set(claims.get("roles", [])),
                permissions=string_set(claims.get("permissions", [])),
                claims={k: claims[k] for k in self.settings.allowed_claims if k in claims},
            )
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise AppError(401, "INVALID_TOKEN", "Invalid access token") from exc
