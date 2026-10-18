from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from myapp.core.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.sessions() as session:
        # Commit before dependency exits; handlers use scope='function' to commit before response.
        async with session.begin():
            yield session


Session = Annotated[AsyncSession, Depends(get_session, scope="function")]
