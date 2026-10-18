import asyncio
import time
from typing import Any

import httpx
import jwt

from myapp.core.config import AuthSettings
from myapp.core.exceptions import AppError


class JWKSCache:
    def __init__(self, settings: AuthSettings, client: httpx.AsyncClient):
        self.settings, self.client = settings, client
        self.keys: list[dict[str, Any]] = []
        self.expires = 0.0
        self.last_refresh = float("-inf")
        self.uri = settings.jwks_url
        self.lock = asyncio.Lock()

    async def _refresh(self) -> None:
        if not self.uri:
            response = await self.client.get(
                self.settings.issuer.rstrip("/") + "/.well-known/openid-configuration"
            )
            response.raise_for_status()
            discovery = response.json()
            if discovery.get("issuer") != self.settings.issuer:
                raise ValueError("discovery issuer mismatch")
            uri = discovery["jwks_uri"]
            if not isinstance(uri, str) or not uri.startswith("https://"):
                raise ValueError("HTTPS JWKS required")
            self.uri = uri
        response = await self.client.get(self.uri)
        response.raise_for_status()
        keys = response.json()["keys"]
        if not isinstance(keys, list) or not keys or len(keys) > 100:
            raise ValueError("invalid JWKS")
        if any(not isinstance(key, dict) for key in keys):
            raise ValueError("invalid JWK")
        self.keys = keys
        self.expires = time.monotonic() + self.settings.cache_ttl

    async def key(self, kid: str, algorithm: str) -> jwt.PyJWK:
        try:
            async with self.lock:
                now = time.monotonic()
                found = any(k.get("kid") == kid for k in self.keys)
                # Unknown kid triggers a refresh, throttled per worker against random-kid floods.
                if now >= self.expires or (not found and now - self.last_refresh >= 5):
                    if now - self.last_refresh < 5:
                        raise AppError(503, "SSO_UNAVAILABLE", "Identity provider unavailable")
                    self.last_refresh = now
                    await self._refresh()
                candidates = [
                    k
                    for k in self.keys
                    if k.get("kid") == kid
                    and k.get("use", "sig") == "sig"
                    and "verify" in k.get("key_ops", ["verify"])
                    and k.get("alg", algorithm) == algorithm
                ]
                if len(candidates) != 1:
                    raise AppError(401, "INVALID_TOKEN", "Invalid access token")
                return jwt.PyJWK.from_dict(candidates[0], algorithm=algorithm)
        except AppError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError) as exc:
            raise AppError(503, "SSO_UNAVAILABLE", "Identity provider unavailable") from exc
