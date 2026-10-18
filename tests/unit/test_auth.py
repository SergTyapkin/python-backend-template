import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from myapp.api.permissions import require_ownership, require_permissions, require_scopes
from myapp.auth.jwks import JWKSCache
from myapp.auth.oidc import TokenVerifier
from myapp.auth.principal import Principal
from myapp.core.config import AuthSettings
from myapp.core.exceptions import AppError


@pytest.fixture
def keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def jwk(key, kid="first"):
    return {
        **json.loads(RSAAlgorithm.to_jwk(key.public_key())),
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
    }


def token(key, **overrides):
    now = int(time.time())
    claims = {
        "sub": "subject",
        "iss": "https://sso.example",
        "aud": "api",
        "iat": now,
        "exp": now + 300,
        "nbf": now - 1,
        "scope": "read write",
        "permissions": ["edit"],
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "first"})


async def test_verification_and_invalid_tokens(keys):
    settings = AuthSettings(issuer="https://sso.example", audience="api", clock_skew=0)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200, json={"issuer": settings.issuer, "jwks_uri": "https://sso.example/keys"}
            )
        return httpx.Response(200, json={"keys": [jwk(keys[0])]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = TokenVerifier(settings, JWKSCache(settings, client))
        principal = await verifier.verify(token(keys[0]))
        assert principal.subject == "subject"
        assert principal.scopes == {"read", "write"}
        assert principal.permissions == {"edit"}
        for bad in (
            token(keys[1]),
            token(keys[0], exp=0),
            token(keys[0], aud="other"),
            token(keys[0], iss="https://evil.example"),
            token(keys[0], nbf=int(time.time()) + 1000),
            token(keys[0], sub=""),
            "not.a.token",
            jwt.encode({"sub": "s"}, "x" * 32, algorithm="HS256", headers={"kid": "first"}),
        ):
            with pytest.raises(AppError) as exc:
                await verifier.verify(bad)
            assert exc.value.status == 401
        assert len(calls) == 2  # Cached discovery/JWKS, even for invalid signatures.


async def test_rotation_and_throttling(keys):
    state = {"keys": [jwk(keys[0])]}
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=state)

    settings = AuthSettings(
        issuer="https://sso.example", audience="api", jwks_url="https://sso.example/keys"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cache = JWKSCache(settings, client)
        await cache.key("first", "RS256")
        state["keys"] = [jwk(keys[1], "rotated")]
        cache.last_refresh -= 6
        assert (await cache.key("rotated", "RS256")).key
        for _ in range(3):
            with pytest.raises(AppError):
                await cache.key("unknown", "RS256")
        assert len(calls) == 2
        cache.expires = 0
        cache.last_refresh -= 6
        await cache.key("rotated", "RS256")
        assert len(calls) == 3


async def test_unavailable_and_claim_allowlist(keys):
    settings = AuthSettings(
        issuer="https://sso.example",
        audience="api",
        jwks_url="https://sso.example/keys",
        expected_claims={"kind": "access"},
        allowed_claims=["tenant"],
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"keys": [jwk(keys[0])]}))
    ) as client:
        verifier = TokenVerifier(settings, JWKSCache(settings, client))
        with pytest.raises(AppError):
            await verifier.verify(token(keys[0], kind="id"))
        principal = await verifier.verify(
            token(keys[0], kind="access", tenant="t", email="private")
        )
        assert principal.claims == {"tenant": "t"}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        with pytest.raises(AppError) as exc:
            await TokenVerifier(settings, JWKSCache(settings, client)).verify(token(keys[0]))
        assert exc.value.status == 503


async def test_permissions_and_ownership():
    principal = Principal(
        subject="one",
        issuer="sso",
        scopes=frozenset({"read"}),
        roles=frozenset({"admin"}),
        permissions=frozenset({"edit"}),
    )
    assert await require_permissions("edit")(principal) == principal
    assert await require_scopes("read")(principal) == principal
    for dependency in (require_permissions("delete"), require_scopes("write")):
        with pytest.raises(AppError) as exc:
            await dependency(principal)
        assert exc.value.status == 403
    require_ownership(principal, "one")
    with pytest.raises(AppError):
        require_ownership(principal, "other")


@pytest.mark.parametrize("document", [{"keys": []}, {"keys": ["invalid"]}, {}, {"keys": None}])
async def test_malformed_jwks_fails_closed(document):
    settings = AuthSettings(
        issuer="https://sso.example", audience="api", jwks_url="https://sso.example/keys"
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=document))
    ) as client:
        with pytest.raises(AppError) as exc:
            await JWKSCache(settings, client).key("first", "RS256")
        assert exc.value.status == 503
