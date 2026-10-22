from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from myapp.audit.service import record_audit
from myapp.auth.principal import Principal
from myapp.core.config import Settings
from myapp.core.exceptions import AppError
from myapp.resources.fields import FieldAccess
from myapp.resources.schemas import access_of

if TYPE_CHECKING:
    from myapp.resources.resource import Resource


class Service:
    """Transactions belong to the request Session dependency; services never commit."""

    async def flush(self, session: AsyncSession) -> None:
        try:
            await session.flush()
        except IntegrityError as exc:
            raise AppError(409, "CONFLICT", "Data integrity conflict") from exc

    def read(self, resource: Resource, row: Any) -> BaseModel:
        names = resource.read_schema.model_fields.keys()
        if names - resource.model.model_fields.keys():
            raise AppError(
                500, "CUSTOM_READ_REQUIRED", "Custom fields require an explicit serializer"
            )
        if set(names) & inspect(row).unloaded:
            raise AppError(500, "UNLOADED_FIELD", "Read fields must be explicitly loaded")
        return resource.read_schema.model_validate({name: getattr(row, name) for name in names})

    async def get(
        self,
        resource: Resource,
        session: AsyncSession,
        principal: Principal,
        identifier: UUID,
        *,
        lock: bool = False,
    ) -> Any:
        statement = resource.policy.scope(select(resource.model), resource.model, principal)
        statement = statement.where(resource.id_column == identifier)
        if lock:
            statement = statement.with_for_update()
        row = await session.scalar(statement)
        if row is None:
            raise AppError(404, "NOT_FOUND", "Resource not found")
        return row

    async def list(
        self,
        resource: Resource,
        session: AsyncSession,
        principal: Principal,
        limit: int,
        offset: int,
        sort: str | None,
        filters: dict[str, Any],
    ) -> dict:
        statement = resource.policy.scope(select(resource.model), resource.model, principal)
        for name, value in filters.items():
            statement = statement.where(getattr(resource.model, name) == value)
        field = (sort or "id").removeprefix("-")
        if field not in resource.sort_fields:
            raise AppError(422, "INVALID_SORT", "Unsupported sort field")
        column = getattr(resource.model, field)
        statement = statement.order_by(
            column.desc() if sort and sort.startswith("-") else column.asc(), resource.id_column
        )
        total = await session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = await session.scalars(statement.limit(limit).offset(offset))
        return {
            "items": [self.read(resource, row) for row in rows],
            "total": total or 0,
            "limit": limit,
            "offset": offset,
        }

    async def validate_state(self, resource: Resource, values: dict[str, Any]) -> Any:
        try:
            return resource.model.model_validate(values)
        except ValidationError as exc:
            raise AppError(422, "VALIDATION_ERROR", "Invalid resulting state") from exc

    async def audit(
        self,
        resource: Resource,
        session: AsyncSession,
        settings: Settings,
        row: Any,
        action: str,
        changes: dict[str, Any],
    ) -> None:
        # Only declaration-approved public fields are audit candidates; never dump all columns.
        public = {
            name
            for name, info in resource.model.model_fields.items()
            if access_of(info) in {FieldAccess.READ_ONLY, FieldAccess.READ_WRITE}
        }
        await record_audit(
            session,
            settings.audit,
            action=action,
            entity_type=str(resource.model.__tablename__),
            entity_id=str(row.id),
            changes={name: value for name, value in changes.items() if name in public},
        )

    async def create(
        self,
        resource: Resource,
        session: AsyncSession,
        principal: Principal,
        payload: BaseModel,
        settings: Settings,
    ) -> BaseModel:
        values = {**payload.model_dump(), **resource.policy.server_values(principal)}
        row = await self.validate_state(resource, values)
        session.add(row)
        await self.flush(session)
        await self.audit(resource, session, settings, row, "create", payload.model_dump())
        return self.read(resource, row)

    async def patch(
        self,
        resource: Resource,
        session: AsyncSession,
        principal: Principal,
        identifier: UUID,
        payload: BaseModel,
        settings: Settings,
    ) -> BaseModel:
        row = await self.get(resource, session, principal, identifier, lock=True)
        updates = payload.model_dump(exclude_unset=True)
        values = {name: getattr(row, name) for name in resource.model.model_fields}
        await self.validate_state(resource, {**values, **updates})
        changes = {
            name: {"before": values[name], "after": value}
            for name, value in updates.items()
            if values[name] != value
        }
        for name, value in updates.items():
            setattr(row, name, value)
        await self.flush(session)
        if changes:
            await self.audit(resource, session, settings, row, "update", changes)
        return self.read(resource, row)

    async def delete(
        self,
        resource: Resource,
        session: AsyncSession,
        principal: Principal,
        identifier: UUID,
        settings: Settings,
    ) -> None:
        row = await self.get(resource, session, principal, identifier, lock=True)
        await self.audit(resource, session, settings, row, "delete", {})
        await session.delete(row)
        await self.flush(session)
