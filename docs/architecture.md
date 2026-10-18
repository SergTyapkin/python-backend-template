# Архитектура и расширение

Router занимается HTTP, service — бизнес-операцией, model — схемой БД, DTO — контрактом.
Repository нужен только для сложного повторяемого доступа к данным.
В `modules/` нет бизнес-примеров: весь пример ниже существует только в документации.

## Модель, DTO и PATCH

```python
from uuid import UUID, uuid4
from pydantic import Field
from sqlalchemy.orm import Mapped, mapped_column
from myapp.db.base import Base
from myapp.api.responses import Schema


class Resource(Base):
    __tablename__ = "resources"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column()
    description: Mapped[str | None] = mapped_column()


class ResourceCreate(Schema):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)


class ResourcePatch(Schema):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)


class ResourceRead(Schema):
    id: UUID
    title: str
    description: str | None
```

Добавьте импорт Resource в `load_models`, сгенерируйте и проверьте миграцию.
Для дат используйте `DateTime(timezone=True)` и Pydantic `AwareDatetime`, UTC.
UUID/даты сериализуются Pydantic в строки/ISO 8601; nullable — явно через `| None`.

```python
from myapp.core.exceptions import AppError
from myapp.audit.service import record_audit


async def patch_resource(session, settings, resource, payload):
    values = payload.model_dump(exclude_unset=True)
    if "title" in values and values["title"] is None:
        raise AppError(422, "VALIDATION_ERROR", "Title cannot be null")
    changes = {}
    for field, value in values.items():
        before = getattr(resource, field)
        if before != value:
            changes[field] = {"before": before, "after": value}
            setattr(resource, field, value)
    if changes:
        await record_audit(
            session,
            settings.audit,
            action="update",
            entity_type="resource",
            entity_id=str(resource.id),
            changes=changes,
        )
    await session.flush()
    return ResourceRead.model_validate(resource)
```

`Session` из core.dependencies открывает транзакцию с function scope: ошибка commit
не должна появляться после отправки 200. Весь service, включая audit, использует одну сессию.
Для отдельной команды используйте `async with session.begin()` явно.
Для конкурентного изменения используйте row lock или optimistic versioning;
иначе чтение перед PATCH допускает lost updates. Защищайте уникальность constraints,
переводите известные IntegrityError в 409 внутри service с корректным rollback/savepoint.

## Router и permissions

```python
from fastapi import APIRouter, Depends
from myapp.core.dependencies import Session
from myapp.auth.dependencies import CurrentPrincipal
from myapp.api.permissions import require_permissions, require_ownership

router = APIRouter(
    prefix="/resources", dependencies=[Depends(require_permissions("resource:edit"))]
)


@router.patch("/{resource_id}", response_model=ResourceRead)
async def update(
    resource_id: UUID, payload: ResourcePatch, session: Session, principal: CurrentPrincipal
):
    # Service loads row with the desired concurrency policy, checks existence/ownership,
    # then applies patch and audit. Inject Settings through get_settings as well.
    return await service.update(session, principal, resource_id, payload)
```

Подключите router явно в api_router. Для read/create/delete заведите отдельные permissions.
SSO глобальные роли не заменяют resource ownership/tenant checks в service.
Для multi-tenant данных добавляйте tenant predicate уже в SQL, а не после пагинации.

## Списки и фильтры

Принимайте `Pagination` через query model `Annotated[Pagination, Query()]`.
Дополнительные фильтры — типизированные DTO конкретного модуля.
Не передавайте пользовательские строки в SQL как имена колонок:

```python
statement = select(Resource).where(Resource.title.ilike(bound_pattern))
statement = sorted_statement(statement, sort, {"title": Resource.title, "id": Resource.id})
statement = statement.order_by(Resource.id)
page = await paginate(session, statement, pagination, ResourceRead)
```

COUNT и page query могут видеть разные snapshots при конкурентных записях (READ COMMITTED).
Для строгого snapshot используйте подходящий isolation level. JOIN с дублями требует
правильного distinct/grouping до передачи statement в paginate.

## Внешний сервис (только пример документации)

```python
class DeliveryClient:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def send(self, payload):
        try:
            response = await self.http.post("/messages", json=payload, timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError(503, "DELIVERY_UNAVAILABLE", "Delivery unavailable") from exc
```

В lifespan создайте AsyncClient(base_url=..., timeout=5), сохраните клиент в app.state
и закройте при shutdown. Dependency возвращает его service через Depends.
В тесте передайте MockTransport или fake; не обращайтесь к реальному провайдеру.
Не повторяйте state-changing запросы без idempotency key. Секреты — SecretStr/env,
ответ провайдера и exception message не попадают в публичную ошибку/лог.

## Периодическая задача

Добавьте `async def` в jobs/, зарегистрируйте явную команду в jobs/cli.py.
Команда создаёт/закрывает ресурсы сама, использует короткие транзакции и ограниченные batches.
Внешний scheduler запускает `uv run project-job <name>`. Для singleton jobs применяйте
DB advisory lock либо гарантию scheduler; для audit cleanup используется SKIP LOCKED.
BackgroundTasks подходит только для коротких best-effort действий; durable delivery требует
отдельной очереди/outbox. Retention audit-cleanup согласуйте с требованиями хранения проекта.

## Проверка новой сущности

Тесты должны покрывать DTO/null/aliases, permissions/ownership/tenant isolation,
успешный CRUD, conflict, transaction rollback вместе с audit, pagination/filter/sort.
Завершите `alembic check`, экспортом/валидацией OpenAPI и обновлением frontend types.
