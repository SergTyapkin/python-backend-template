from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Select, SQLColumnExpression, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from myapp.api.responses import Schema
from myapp.core.exceptions import AppError


class Pagination(Schema):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=1000000)


class Page[T](Schema):
    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_next(self) -> bool:
        return self.offset + len(self.items) < self.total


def sorted_statement(
    statement: Select, sort: str, allowed: Mapping[str, SQLColumnExpression[Any]]
) -> Select:
    field = sort.removeprefix("-")
    if field not in allowed:
        raise AppError(422, "INVALID_SORT", "Unsupported sort field")
    column = allowed[field]
    return statement.order_by(column.desc() if sort.startswith("-") else column.asc())


async def paginate[T: BaseModel](
    session: AsyncSession, statement: Select, params: Pagination, schema: type[T]
) -> Page[T]:
    # Callers apply typed filters and stable ordering (including a unique tie-breaker) first.
    total = await session.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    rows = await session.scalars(statement.limit(params.limit).offset(params.offset))
    return Page[T](
        items=[schema.model_validate(row) for row in rows],
        total=total or 0,
        limit=params.limit,
        offset=params.offset,
    )
