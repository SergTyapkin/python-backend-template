import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from myapp.core.config import DatabaseSettings


class Database:
    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self.engine = create_async_engine(
            settings.url.get_secret_value(),
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_timeout=settings.pool_timeout,
            pool_pre_ping=True,
            hide_parameters=True,
            connect_args={"timeout": settings.pool_timeout, "command_timeout": 30},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def ready(self) -> bool:
        try:
            async with asyncio.timeout(self.settings.readiness_timeout):
                async with self.engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self.engine.dispose()
