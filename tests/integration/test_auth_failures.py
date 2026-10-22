import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from myapp.main import create_app
from myapp.modules.auth.models import LoginSession

pytestmark = pytest.mark.integration


async def test_rejected_authentication_and_session_bound_csrf(database, pg_settings):
    app = create_app(pg_settings)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            credentials = {"username": "securityuser", "password": "long-test-password-12345"}
            assert (await client.post("/api/v1/auth/register", json=credentials)).status_code == 403
            client.headers["Origin"] = "http://localhost:3000"
            assert (
                await client.post(
                    "/api/v1/auth/register",
                    json={"username": "invalid spaces", "password": "short"},
                )
            ).status_code == 422
            assert (await client.post("/api/v1/auth/register", json=credentials)).status_code == 201
            assert (await client.post("/api/v1/auth/register", json=credentials)).status_code == 409
            assert (
                await client.post(
                    "/api/v1/auth/login", json={**credentials, "password": "wrong-password-12345"}
                )
            ).status_code == 401
            async with database.sessions() as session:
                assert not list(await session.scalars(select(LoginSession)))
            first = await client.post("/api/v1/auth/login", json=credentials)
            client.headers["X-CSRF-Token"] = first.json()["csrf_token"]
            second = await client.post("/api/v1/auth/login", json=credentials)
            assert (await client.post("/api/v1/tasks", json={"title": "csrf"})).status_code == 403
            client.headers["X-CSRF-Token"] = second.json()["csrf_token"]
            assert (await client.post("/api/v1/tasks", json={"title": "csrf"})).status_code == 201
