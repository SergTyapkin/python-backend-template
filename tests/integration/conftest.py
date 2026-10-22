import os
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import delete

from myapp.audit.models import AuditLog
from myapp.db.session import Database
from myapp.modules.auth.models import LoginSession
from myapp.modules.tasks.models import Task
from myapp.modules.users.models import User
from tests.settings import IsolatedSettings


@pytest.fixture(scope="session")
def pg_settings():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test")
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        pytest.fail("Integration database name must end in _test; schema is rebuilt")
    settings = IsolatedSettings(environment="test")
    settings.database.url = SecretStr(url)
    return settings


@pytest.fixture(scope="session")
def migrated_schema(pg_settings):
    env = {
        **os.environ,
        "APP_DATABASE__URL": pg_settings.database.url.get_secret_value(),
        "APP_ENVIRONMENT": "test",
    }
    # Exercise real migrations once per run; data is isolated before each test below.
    with patch.dict(os.environ, env):
        config = Config("alembic.ini")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        command.upgrade(config, "head")  # Applying head again must be idempotent.


@pytest.fixture
async def database(pg_settings, migrated_schema):
    database = Database(pg_settings.database)
    try:
        async with database.sessions() as session, session.begin():
            await session.execute(delete(AuditLog))
            await session.execute(delete(Task))
            await session.execute(delete(LoginSession))
            await session.execute(delete(User))
        yield database
    finally:
        await database.close()
