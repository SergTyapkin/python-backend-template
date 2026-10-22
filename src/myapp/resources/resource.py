from collections.abc import Callable
from typing import Any, get_args
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import JSON, inspect
from sqlalchemy.exc import NoInspectionAvailable

from myapp.resources.fields import ResourceModel
from myapp.resources.policy import Policy
from myapp.resources.schemas import ACCESS, FieldOverride, Operation, access_of, generate_schema
from myapp.resources.service import Service


class Resource:
    def __init__(
        self,
        *,
        model: type[ResourceModel],
        path: str,
        operations: set[str],
        policy: Policy,
        service: Service | None = None,
        overrides: dict[Operation, dict[str, FieldOverride]] | None = None,
        schemas: dict[Operation, type[BaseModel]] | None = None,
        allow_access_expansion: bool = False,
        sort_fields: set[str] | None = None,
        filter_fields: set[str] | None = None,
        handlers: dict[str, Callable[..., Any]] | None = None,
        principal_dependency: Callable[..., Any] | None = None,
    ):
        if not operations or operations - {"list", "retrieve", "create", "patch", "delete"}:
            raise ValueError("Resource operations must be explicitly chosen")
        if not path.startswith("/") or "{" in path or path.endswith("/"):
            raise ValueError("Resource path must be a static non-trailing-slash path")
        try:
            mapper = inspect(model)
        except NoInspectionAvailable as exc:
            raise ValueError("Resource model must declare table=True") from exc
        if mapper is None:
            raise ValueError("Resource model must be a SQLModel table")
        if len(mapper.primary_key) != 1 or mapper.primary_key[0].name != "id":
            raise ValueError("Resources require one primary key named id")
        self.id_column = mapper.primary_key[0]
        if model.model_fields["id"].annotation is not UUID:
            raise ValueError("Resources currently support UUID identifiers only")
        for column in mapper.columns:
            name = mapper.get_property_by_column(column).key
            annotation = model.model_fields[name].annotation
            if (
                not column.nullable
                and type(None) in get_args(annotation)
                and not isinstance(column.type, JSON)
            ):
                raise ValueError(f"{name}: nullable API type conflicts with NOT NULL column")
        self.model, self.path, self.operations, self.policy = model, path, operations, policy
        self.name = path.strip("/").replace("/", "_").replace("-", "_")
        self.service = service or Service()
        self.handlers, self.principal_dependency = handlers or {}, principal_dependency
        if self.handlers.keys() - operations:
            raise ValueError("Custom handlers must replace enabled operations")
        rules, custom = overrides or {}, schemas or {}
        if rules.keys() & custom.keys():
            raise ValueError("Choose either generated overrides or a custom schema per operation")
        if rules.keys() - {"create", "patch", "read"} or custom.keys() - {
            "create",
            "patch",
            "read",
        }:
            raise ValueError("Unknown schema operation")
        for operation, schema in custom.items():
            for name in schema.model_fields.keys() & model.model_fields.keys():
                if (
                    access_of(model.model_fields[name]) not in ACCESS[operation]
                    and not allow_access_expansion
                ):
                    raise ValueError(
                        f"Explicit allow_access_expansion required for {operation}.{name}"
                    )
        self.create_schema = custom.get("create") or generate_schema(
            model, "create", rules.get("create"), allow_access_expansion=allow_access_expansion
        )
        self.patch_schema = custom.get("patch") or generate_schema(
            model, "patch", rules.get("patch"), allow_access_expansion=allow_access_expansion
        )
        self.read_schema = custom.get("read") or generate_schema(
            model, "read", rules.get("read"), allow_access_expansion=allow_access_expansion
        )
        self.sort_fields = sort_fields if sort_fields is not None else {"id"}
        self.filter_fields = filter_fields or set()
        allowed = self.read_schema.model_fields.keys() & model.model_fields.keys()
        if (
            self.sort_fields - (allowed | {"id"})
            or self.filter_fields - allowed
            or "id" not in self.sort_fields
        ):
            raise ValueError(
                "Sort/filter allowlists must contain only readable model fields; id sorts"
            )
        for operation, schema in (
            ("create", self.create_schema),
            ("patch", self.patch_schema),
            ("read", self.read_schema),
        ):
            if schema.model_fields.keys() - model.model_fields.keys():
                if getattr(type(self.service), operation) is getattr(Service, operation):
                    raise ValueError(f"Custom {operation} fields require a service override")
        from myapp.resources.router import build_router

        self.router = build_router(self)
