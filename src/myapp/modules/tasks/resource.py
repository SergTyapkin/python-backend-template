from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from myapp.auth.principal import Principal
from myapp.core.config import Settings
from myapp.modules.tasks.models import Task
from myapp.resources import Resource
from myapp.resources.policy import Policy
from myapp.resources.service import Service


class TaskPolicy(Policy):
    async def authorize(self, operation: str, principal: Principal) -> None:
        UUID(principal.subject)

    def scope(self, statement: Select, model: type[Any], principal: Principal) -> Select:
        return statement.where(model.owner_id == UUID(principal.subject))

    def server_values(self, principal: Principal) -> dict[str, Any]:
        return {"owner_id": UUID(principal.subject)}


class TaskService(Service):
    """A single-operation customization: trim a validated title before storing it."""

    async def create(
        self,
        resource: Resource,
        session: AsyncSession,
        principal: Principal,
        payload: BaseModel,
        settings: Settings,
    ) -> BaseModel:
        payload = payload.model_copy(update={"title": payload.model_dump()["title"].strip()})
        return await super().create(resource, session, principal, payload, settings)


tasks = Resource(
    model=Task,
    path="/tasks",
    operations={"list", "retrieve", "create", "patch"},
    policy=TaskPolicy(),
    service=TaskService(),
    sort_fields={"id", "created_at", "title"},
    filter_fields={"title"},
)
