import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect, select, text
from sqlalchemy.pool import AsyncAdaptedQueuePool

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

pytestmark = pytest.mark.integration


async def test_migration_schema_and_readiness(database, pg_settings):
    assert await database.ready()
    load_models()
    async with database.engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
        assert set(tables) == {"audit_log", "alembic_version", "app_user", "login_session", "task"}
        assert set(Base.metadata.tables) == {"audit_log", "app_user", "login_session", "task"}
        assert await connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
    env = {**os.environ, "APP_DATABASE__URL": pg_settings.database.url.get_secret_value()}

    def check_migrations():
        with patch.dict(os.environ, env):
            command.check(Config("alembic.ini"))

    await asyncio.to_thread(check_migrations)


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


async def test_pool_concurrency_and_cancellation(pg_settings, migrated_schema):
    settings = pg_settings.database.model_copy(update={"pool_size": 2, "max_overflow": 1})
    database = Database(settings)
    pool = cast(AsyncAdaptedQueuePool, database.engine.pool)
    sessions = []
    maximum = 0

    async def worker():
        nonlocal maximum
        async with database.sessions() as session, session.begin():
            sessions.append(session)
            await session.execute(text("SELECT 1"))
            maximum = max(maximum, pool.checkedout())
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(asyncio.gather(*(worker() for _ in range(8))), timeout=10)
        assert len({id(session) for session in sessions}) == 8
        assert maximum == 3
        assert pool.checkedout() == 0
        acquired = asyncio.Event()

        async def cancelled_transaction():
            async with database.sessions() as session, session.begin():
                await session.execute(text("SELECT 1"))
                acquired.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(cancelled_transaction())
        await asyncio.wait_for(acquired.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pool.checkedout() == 0
        assert await database.ready()
    finally:
        await database.close()
    assert pool.checkedin() == 0


async def test_pagination_stable_order_empty_page_and_query_count(database):
    class AuditRead(Schema):
        entity_id: str

    async with database.sessions() as session, session.begin():
        for index in range(5):
            session.add(
                AuditLog(
                    action="update",
                    entity_type="fixture",
                    entity_id=str(index),
                    changes={},
                    timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )

    statements = []

    def track_query(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(database.engine.sync_engine, "before_cursor_execute", track_query)
    try:
        async with database.sessions() as session:
            statement = sorted_statement(
                select(AuditLog), "timestamp", {"timestamp": AuditLog.timestamp}
            ).order_by(AuditLog.id)
            first = await paginate(session, statement, Pagination(limit=2), AuditRead)
            assert len(statements) == 2  # COUNT + bounded ORM SELECT, no per-row queries.
            statements.clear()
            again = await paginate(session, statement, Pagination(limit=2), AuditRead)
            assert first.items == again.items and first.has_next
            assert len(statements) == 2
            empty = await paginate(session, statement, Pagination(limit=2, offset=100), AuditRead)
            assert empty.total == 5 and empty.items == [] and not empty.has_next
    finally:
        event.remove(database.engine.sync_engine, "before_cursor_execute", track_query)
