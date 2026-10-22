from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError, model_validator

from myapp.auth.principal import Principal
from myapp.core.environment import environment_example
from myapp.core.exceptions import AppError
from myapp.modules.tasks.models import Task
from myapp.modules.tasks.resource import TaskPolicy
from myapp.resources import FieldAccess, FieldOverride, Resource, ResourceModel, api_field
from myapp.resources.schemas import generate_schema
from myapp.resources.service import Service

factory_calls: list[bool] = []


def generated_value() -> str:
    factory_calls.append(True)
    return "generated"


class Definition(ResourceModel):
    id: UUID = api_field(default_factory=uuid4, access=FieldAccess.READ_ONLY)
    title: str = api_field(min_length=1, max_length=20, access=FieldAccess.READ_WRITE)
    count: int = api_field(default=2, ge=1, le=5, access=FieldAccess.READ_WRITE)
    note: str | None = api_field(default=None, access=FieldAccess.READ_WRITE)
    automatic: str = api_field(default_factory=generated_value, access=FieldAccess.READ_WRITE)
    invitation: str = api_field(access=FieldAccess.CREATE_ONLY)
    secret: str = api_field(default="hidden")


def test_create_defaults_and_access():
    create = generate_schema(Definition, "create")
    read = generate_schema(Definition, "read")
    assert create.model_fields.keys() == {"title", "count", "note", "automatic", "invitation"}
    assert "id" in read.model_fields and "invitation" not in read.model_fields
    assert "secret" not in read.model_fields
    for values in (
        {},
        {"title": "x"},
        {"title": "x", "invitation": "v", "id": str(uuid4())},
        {"title": "x", "invitation": "v", "secret": "override"},
    ):
        with pytest.raises(ValidationError):
            create.model_validate(values)
    payload = create.model_validate({"title": "x", "invitation": "v"})
    assert payload.model_dump()["count"] == 2 and payload.model_dump()["automatic"] == "generated"
    assert payload.model_dump()["note"] is None


@pytest.mark.parametrize("values", [{"title": ""}, {"title": "a" * 21}, {"count": 0}, {"count": 6}])
def test_preserves_constraints(values):
    with pytest.raises(ValidationError):
        generate_schema(Definition, "patch").model_validate(values)


def test_patch_omission_null_and_factories():
    factory_calls.clear()
    patch = generate_schema(Definition, "patch")
    assert patch.model_validate({}).model_dump(exclude_unset=True) == {}
    assert factory_calls == []
    assert patch.model_validate({"note": None}).model_dump(exclude_unset=True) == {"note": None}
    for name in ("title", "count", "automatic", "id", "secret", "invitation", "unknown"):
        with pytest.raises(ValidationError):
            patch.model_validate({name: None})
    schema = patch.model_json_schema()
    assert not schema.get("required")
    assert schema["properties"]["title"]["type"] == "string"
    assert "default" not in schema["properties"]["title"]
    assert {item["type"] for item in schema["properties"]["note"]["anyOf"]} == {"null", "string"}


def test_operation_overrides_and_invalid_declarations():
    model = generate_schema(
        Definition,
        "create",
        {
            "invitation": FieldOverride(include=False),
            "title": FieldOverride(constraints={"max_length": 3}),
            "count": FieldOverride(required=True),
        },
    )
    with pytest.raises(ValidationError):
        model.model_validate({"title": "long", "count": 1})
    assert "count" in model.model_json_schema()["required"]
    for rules in (
        {"bad": FieldOverride()},
        {"secret": FieldOverride(include=True)},
        {"invitation": FieldOverride(include=False, required=True)},
        {"title": FieldOverride(required=False)},
        {"title": FieldOverride(constraints={"max_length": 200})},
        {"count": FieldOverride(constraints={"ge": 3})},
    ):
        with pytest.raises(ValueError):
            generate_schema(Definition, "create", rules)
    explicit = generate_schema(
        Definition, "read", {"secret": FieldOverride(include=True)}, allow_access_expansion=True
    )
    assert "secret" in explicit.model_fields
    with pytest.raises(ValueError):
        Resource(model=Task, path="/bad", operations={"put"}, policy=TaskPolicy())
    with pytest.raises(ValueError):
        Resource(model=Task, path="/bad/", operations={"list"}, policy=TaskPolicy())
    with pytest.raises(ValueError, match="table=True"):
        Resource(model=Definition, path="/bad", operations={"list"}, policy=TaskPolicy())
    with pytest.raises(ValueError):
        Resource(
            model=Task,
            path="/bad",
            operations={"list"},
            policy=TaskPolicy(),
            sort_fields={"id", "owner_id"},
        )


async def test_full_state_validation_after_partial_patch():
    class Range(ResourceModel):
        low: int = api_field(access=FieldAccess.READ_WRITE)
        high: int = api_field(access=FieldAccess.READ_WRITE)

        @model_validator(mode="after")
        def ordered(self):
            if self.low > self.high:
                raise ValueError("invalid range")
            return self

    class FakeResource:
        model = Range

    resource: Any = FakeResource()
    patch = generate_schema(Range, "patch").model_validate({"low": 10})
    row = Range(low=1, high=5)

    class MemoryService(Service):
        async def get(self, *args, **kwargs):
            return row

    from unittest.mock import AsyncMock

    from myapp.core.config import Settings

    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await MemoryService().patch(
            resource,
            session,
            Principal(subject="test", issuer="test"),
            uuid4(),
            patch,
            Settings.model_construct(),
        )
    assert exc.value.status == 422
    assert row.low == 1 and row.high == 5
    session.flush.assert_not_called()


def test_disabled_operations_stable_names_and_new_field(app):
    schema = app.openapi()
    assert "delete" not in schema["paths"]["/api/v1/tasks/{identifier}"]
    assert schema["paths"]["/api/v1/tasks"]["post"]["operationId"] == "tasks_create"
    assert {"TaskCreate", "TaskPatch", "TaskRead", "TaskList"} <= schema["components"][
        "schemas"
    ].keys()
    assert "owner_id" not in schema["components"]["schemas"]["TaskRead"]["properties"]

    class Extended(Definition):
        new_field: int = api_field(default=1, access=FieldAccess.READ_WRITE)

    for operation in ("create", "patch", "read"):
        assert "new_field" in generate_schema(Extended, operation).model_json_schema()["properties"]


async def test_custom_handler_replaces_route_and_custom_schema(app, client):
    async def custom(identifier: UUID) -> dict:
        return {"id": str(identifier)}

    class CustomRead(BaseModel):
        id: UUID

    resource = Resource(
        model=Task,
        path="/custom",
        operations={"retrieve"},
        policy=TaskPolicy(),
        schemas={"read": CustomRead},
        handlers={"retrieve": custom},
        principal_dependency=lambda: __import__(
            "myapp.auth.principal", fromlist=["Principal"]
        ).Principal(subject=str(uuid4()), issuer="test"),
    )
    assert len(resource.router.routes) == 1
    from starlette.routing import Route

    route = resource.router.routes[0]
    assert isinstance(route, Route)
    assert route.endpoint is custom
    app.include_router(resource.router)
    identifier = uuid4()
    response = await client.get(f"/custom/{identifier}")
    assert response.status_code == 200 and response.json() == {"id": str(identifier)}


async def test_custom_handler_still_requires_policy(app, client):
    from myapp.resources.policy import Policy

    async def forbidden_handler(identifier: UUID):
        raise AssertionError("Policy must run before custom handler")

    resource = Resource(
        model=Task,
        path="/denied",
        operations={"retrieve"},
        policy=Policy(),
        handlers={"retrieve": forbidden_handler},
        principal_dependency=lambda: Principal(subject=str(uuid4()), issuer="test"),
    )
    app.include_router(resource.router)
    assert (await client.get(f"/denied/{uuid4()}")).status_code == 403


def test_generated_env_is_current():
    from pathlib import Path

    assert Path(".env.example").read_text(encoding="utf-8") == environment_example()
