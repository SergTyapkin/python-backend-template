import asyncio
import os
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import inspect, select, text

from myapp.api.pagination import Pagination, paginate, sorted_statement
from myapp.api.responses import Schema
from myapp.audit.context import actor_id, request_id
from myapp.audit.models import AuditLog
from myapp.audit.service import record_audit
from myapp.core.config import AuditSettings
from myapp.core.exceptions import AppError
from myapp.db.base import Base, load_models
from myapp.db.session import Database
from myapp.jobs.cli import cleanup_audit
from tests.settings import IsolatedSettings

pytestmark = pytest.mark.integration


@pytest.fixture
def pg_settings():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test")
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        pytest.fail("Integration database name must end in _test; schema is rebuilt")
    settings = IsolatedSettings(environment="test")
    settings.database.url = SecretStr(url)
    return settings


@pytest.fixture
async def database(pg_settings):
    env = {
        **os.environ,
        "APP_DATABASE__URL": pg_settings.database.url.get_secret_value(),
        "APP_ENVIRONMENT": "test",
    }
    # Exercise actual Alembic on an empty schema, not metadata.create_all().
    await asyncio.to_thread(
        subprocess.run, ["uv", "run", "alembic", "downgrade", "base"], env=env, check=True
    )
    await asyncio.to_thread(
        subprocess.run, ["uv", "run", "alembic", "upgrade", "head"], env=env, check=True
    )
    database = Database(pg_settings.database)
    yield database
    await database.close()


async def test_migration_schema_and_readiness(database, pg_settings):
    assert await database.ready()
    load_models()
    async with database.engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
        assert set(tables) == {"audit_log", "alembic_version"}
        assert set(Base.metadata.tables) == {"audit_log"}
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
    env = {**os.environ, "APP_DATABASE__URL": pg_settings.database.url.get_secret_value()}
    result = await asyncio.to_thread(
        subprocess.run, ["uv", "run", "alembic", "check"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


async def test_atomic_audit_pagination_and_cleanup(database, pg_settings):
    actor = actor_id.set("subject")
    request = request_id.set("request")
    try:
        async with database.sessions() as session:
            with pytest.raises(RuntimeError):
                async with session.begin():
                    await record_audit(
                        session,
                        AuditSettings(),
                        action="create",
                        entity_type="fixture",
                        entity_id="rolled-back",
                        changes={"name": "value"},
                    )
                    raise RuntimeError("force rollback")
            async with session.begin():
                assert not list(await session.scalars(select(AuditLog)))
                await record_audit(
                    session,
                    AuditSettings(),
                    action="update",
                    entity_type="fixture",
                    entity_id="committed",
                    changes={"password": "secret", "name": "v"},
                )
            async with session.begin():
                row = (await session.scalars(select(AuditLog))).one()
                assert row.actor_id == "subject" and row.request_id == "request"
                assert row.changes == {"name": "v"}
                assert row.timestamp.tzinfo is not None

                class AuditRead(Schema):
                    entity_id: str

                statement = sorted_statement(
                    select(AuditLog), "timestamp", {"timestamp": AuditLog.timestamp}
                )
                page = await paginate(session, statement, Pagination(limit=1), AuditRead)
                assert page.total == 1 and page.items[0].entity_id == "committed"
                with pytest.raises(AppError):
                    sorted_statement(statement, "timestamp; DROP TABLE audit_log", {})
                row.timestamp = datetime.now(UTC) - timedelta(days=100)
        assert await cleanup_audit(pg_settings) == 1
    finally:
        actor_id.reset(actor)
        request_id.reset(request)


async def test_session_dependency_commits_before_response(database, pg_settings):
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from myapp.core.dependencies import Session
    from myapp.core.exceptions import AppError
    from myapp.main import create_app

    app = create_app(pg_settings)

    @app.post("/test/commit")
    async def commit(session: Session):
        await record_audit(
            session,
            pg_settings.audit,
            action="create",
            entity_type="fixture",
            entity_id="http-commit",
            changes={},
        )
        return {"ok": True}

    @app.post("/test/rollback")
    async def rollback(session: Session):
        await record_audit(
            session,
            pg_settings.audit,
            action="create",
            entity_type="fixture",
            entity_id="http-rollback",
            changes={},
        )
        raise AppError(409, "CONFLICT", "Operation rejected")

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health/ready")).status_code == 200
            assert (await client.post("/test/commit")).status_code == 200
            assert (await client.post("/test/rollback")).status_code == 409
            async with database.sessions() as session:
                assert list(await session.scalars(select(AuditLog.entity_id))) == ["http-commit"]
