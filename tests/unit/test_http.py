import asyncio
from typing import Annotated
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends
from openapi_spec_validator import validate
from starlette.routing import Route

from myapp.api.pagination import Pagination
from myapp.api.permissions import require_permissions
from myapp.auth.dependencies import get_current_principal
from myapp.core.exceptions import AppError


async def test_infrastructure_only(client):
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    assert (await client.get("/version")).json()["gitSha"] == "unknown"
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await client.get(path)).status_code == 200
    contract = (await client.get("/openapi.json")).json()
    validate(contract)
    assert set(contract["paths"]) == {"/health/live", "/health/ready", "/version"}
    assert all("put" not in operations for operations in contract["paths"].values())


def test_only_declared_public_routes(app):
    paths = set(app.openapi()["paths"]) | {
        route.path for route in app.routes if isinstance(route, Route)
    }
    assert paths == {
        "/health/live",
        "/health/ready",
        "/version",
        "/docs",
        "/redoc",
        "/openapi.json",
    }


async def test_readiness(app, client):
    app.state.database.ready = AsyncMock(return_value=True)
    assert (await client.get("/health/ready")).status_code == 200
    app.state.database.ready = AsyncMock(return_value=False)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    assert "database" not in response.text.lower()
    assert (await client.get("/health/live")).status_code == 200


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500])
async def test_errors(app, client, status):
    @app.get("/test/error")
    async def fail():
        raise AppError(status, "SAFE_ERROR", "Safe message")

    response = await client.get("/test/error", headers={"X-Request-ID": "test-123"})
    assert response.status_code == status
    assert response.json() == {
        "code": "SAFE_ERROR",
        "message": "Safe message",
        "details": None,
        "requestId": "test-123",
    }
    assert response.headers["x-request-id"] == "test-123"


async def test_validation_and_unhandled(app, client):
    @app.get("/test/params")
    async def params(query: Annotated[Pagination, Depends()]):
        return query

    @app.get("/test/crash")
    async def crash():
        raise RuntimeError("private-token")

    assert (await client.get("/test/params?limit=999")).status_code == 422
    response = await client.get("/test/crash")
    assert response.status_code == 500
    assert "private-token" not in response.text
    assert response.json()["requestId"] == response.headers["x-request-id"]


async def test_closed_without_sso(app, client):
    @app.get("/test/secure", dependencies=[Depends(get_current_principal)])
    async def secure():
        return {"ok": True}

    assert (await client.get("/test/secure")).status_code == 401
    assert (await client.get("/test/secure", headers={"X-User-ID": "admin"})).status_code == 401
    assert (
        await client.get("/test/secure", headers={"Authorization": "Bearer token"})
    ).status_code == 503


async def test_limits_and_timeout(app, client):
    app.state.settings.max_request_bytes = 1024
    app.state.settings.request_timeout = 0.02

    @app.post("/test/slow")
    async def slow():
        await asyncio.sleep(1)
        return {}

    assert (await client.post("/test/slow", content=b"a" * 1025)).status_code == 413
    assert (await client.post("/test/slow")).status_code == 504


async def test_permission_dependency(app, client):
    from myapp.auth.principal import Principal

    @app.get("/test/permission", dependencies=[Depends(require_permissions("write"))])
    async def permission():
        return {}

    app.dependency_overrides[get_current_principal] = lambda: Principal(subject="a", issuer="sso")
    assert (await client.get("/test/permission")).status_code == 403
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        subject="a", issuer="sso", permissions=frozenset({"write"})
    )
    assert (await client.get("/test/permission")).status_code == 200
