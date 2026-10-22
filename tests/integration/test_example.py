from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from myapp.audit.models import AuditLog
from myapp.main import create_app
from myapp.modules.auth.models import LoginSession
from myapp.modules.tasks.models import Task
from myapp.modules.tasks.resource import TaskPolicy
from myapp.modules.users.models import User
from myapp.resources import Resource
from myapp.resources.service import Service

pytestmark = pytest.mark.integration
ORIGIN = {"Origin": "http://localhost:3000"}
PASSWORD = "test-passphrase-" * 2


@pytest.fixture
async def example_app(database, pg_settings):
    app = create_app(pg_settings)
    async with LifespanManager(app):
        yield app


async def signed_client(app, username):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test", headers=ORIGIN)
    credentials = {"username": username, "password": PASSWORD}
    response = await client.post("/api/v1/auth/register", json=credentials)
    assert response.status_code == 201, response.text
    response = await client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


async def test_owner_crud_and_customization(example_app, database):
    alice = await signed_client(example_app, "alice")
    bob = await signed_client(example_app, "bob")
    try:
        response = await alice.post("/api/v1/tasks", json={"title": "  first  "})
        assert response.status_code == 201, response.text
        task = response.json()
        assert (
            task["title"] == "first"
        )  # TaskService overrides create, other operations stay generic.
        assert "owner_id" not in task
        assert task["created_at"].endswith("Z")
        path = "/api/v1/tasks/" + task["id"]
        assert (await bob.get("/api/v1/tasks")).json() == {
            "items": [],
            "total": 0,
            "limit": 20,
            "offset": 0,
        }
        for method, payload in (("GET", None), ("PATCH", {"title": "stolen"})):
            assert (await bob.request(method, path, json=payload)).status_code == 404
        assert (await alice.patch(path, json={"description": "changed"})).json()["title"] == "first"
        assert (await alice.patch(path, json={"description": None})).json()["description"] is None
        assert (await alice.patch(path, json={})).status_code == 200
        assert (await alice.patch(path, json={"title": None})).status_code == 422
        for forbidden in ("owner_id", "id", "created_at", "extra"):
            assert (
                await alice.patch(path, json={forbidden: str(UUID(task["id"]))})
            ).status_code == 422
        assert (
            await alice.post("/api/v1/tasks", json={"title": "x", "owner_id": task["id"]})
        ).status_code == 422
        conflict = await alice.post("/api/v1/tasks", json={"title": "first"})
        assert conflict.status_code == 409 and "SQL" not in conflict.text
        assert (await bob.post("/api/v1/tasks", json={"title": "first"})).status_code == 201
        own = (await alice.get("/api/v1/tasks?limit=1&sort=-title&title=first")).json()
        assert own["total"] == 1 and own["items"][0]["id"] == task["id"]
        assert (await alice.get("/api/v1/tasks?limit=101")).status_code == 422
        assert (await alice.get("/api/v1/tasks?sort=owner_id")).status_code == 422
        assert (await alice.get("/api/v1/tasks?owner_id=anything")).status_code == 422
        assert (await alice.delete(path)).status_code == 405
        async with database.sessions() as session:
            logs = list(await session.scalars(select(AuditLog)))
            assert logs and all("owner_id" not in log.changes for log in logs)
            assert len(list(await session.scalars(select(Task)))) == 2
    finally:
        await alice.aclose()
        await bob.aclose()


async def test_csrf_expiry_logout_and_hashes(example_app, database):
    client = await signed_client(example_app, "authuser")
    try:
        assert (await client.get("/api/v1/auth/me")).json()["username"] == "authuser"
        csrf = client.headers.pop("X-CSRF-Token")
        assert (await client.post("/api/v1/tasks", json={"title": "csrf"})).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert (
            await client.post(
                "/api/v1/tasks", json={"title": "csrf"}, headers={"Origin": "https://evil.example"}
            )
        ).status_code == 403
        async with database.sessions() as session, session.begin():
            row = (await session.scalars(select(LoginSession))).one()
            assert row.token_hash != client.cookies.get("session")
            user = (await session.scalars(select(User))).one()
            assert user.password_hash.startswith("$argon2id$")
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        logged_in = await client.post(
            "/api/v1/auth/login",
            json={"username": "authuser", "password": PASSWORD},
        )
        client.headers["X-CSRF-Token"] = logged_in.json()["csrf_token"]
        old_cookie = client.cookies.get("session")
        assert (await client.post("/api/v1/auth/logout")).status_code == 204
        client.cookies.set("session", old_cookie)
        assert (await client.get("/api/v1/auth/me")).status_code == 401
    finally:
        await client.aclose()


async def test_explicit_delete_and_transaction_rollback(example_app, database):
    class RejectService(Service):
        async def create(self, resource, session, principal, payload, settings):
            await super().create(resource, session, principal, payload, settings)
            from myapp.core.exceptions import AppError

            raise AppError(409, "REJECTED", "Rejected after flush")

    deletable = Resource(model=Task, path="/disposable", operations={"delete"}, policy=TaskPolicy())
    rollback = Resource(
        model=Task,
        path="/rollback",
        operations={"create"},
        policy=TaskPolicy(),
        service=RejectService(),
    )
    example_app.include_router(deletable.router)
    example_app.include_router(rollback.router)
    client = await signed_client(example_app, "deleter")
    try:
        task = (await client.post("/api/v1/tasks", json={"title": "delete"})).json()
        assert (await client.post("/rollback", json={"title": "rejected"})).status_code == 409
        async with database.sessions() as session:
            assert len(list(await session.scalars(select(Task)))) == 1
            assert len(list(await session.scalars(select(AuditLog)))) == 1
        response = await client.delete("/disposable/" + task["id"])
        assert response.status_code == 204 and response.content == b""
        assert "delete" in example_app.openapi()["paths"]["/disposable/{identifier}"]
    finally:
        await client.aclose()
