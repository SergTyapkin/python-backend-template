# mypy: disable-error-code=valid-type
# Dynamic Pydantic types are runtime annotations; mypy checks the surrounding factory code.
from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field, create_model

from myapp.api.responses import Schema
from myapp.auth.principal import Principal
from myapp.core.dependencies import Session

if TYPE_CHECKING:
    from myapp.resources.resource import Resource


def build_router(resource: Resource) -> APIRouter:
    from myapp.modules.auth.dependencies import current_principal

    dependency = resource.principal_dependency or current_principal

    principal_type: Any = Annotated[Principal, Depends(dependency)]
    create_type: Any = resource.create_schema
    patch_type: Any = resource.patch_schema
    page = create_model(
        f"{resource.model.__name__}List",
        __base__=Schema,
        items=(list[resource.read_schema], ...),  # type: ignore[name-defined]
        total=(int, ...),
        limit=(int, ...),
        offset=(int, ...),
    )
    router = APIRouter(prefix=resource.path, tags=[resource.model.__name__])

    sort_values = tuple(
        sorted(resource.sort_fields | {"-" + name for name in resource.sort_fields})
    )
    sort_type: Any = Literal[sort_values]
    query_fields: dict[str, Any] = {
        "limit": (int, Field(default=20, ge=1, le=100)),
        "offset": (int, Field(default=0, ge=0, le=1000000)),
        "sort": (sort_type | None, None),
    }
    for name in sorted(resource.filter_fields):
        info = resource.model.model_fields[name]
        # Put metadata outside the nullable union so FastAPI sees a hashable base annotation.
        base_annotation: Any = info.annotation
        annotation: Any = Annotated[(base_annotation | None, *info.metadata)]
        query_fields[name] = (annotation, None)
    query_schema = create_model(f"{resource.model.__name__}Query", __base__=Schema, **query_fields)
    query_type: Any = Annotated[query_schema, Query()]

    async def list_rows(session: Session, principal: principal_type, parameters: query_type) -> Any:
        values = parameters.model_dump()
        filters = {
            name: values[name] for name in resource.filter_fields if values[name] is not None
        }
        return await resource.service.list(
            resource, session, principal, values["limit"], values["offset"], values["sort"], filters
        )

    async def retrieve(identifier: UUID, session: Session, principal: principal_type) -> Any:
        return resource.service.read(
            resource, await resource.service.get(resource, session, principal, identifier)
        )

    async def create(
        payload: create_type,
        request: Request,
        session: Session,
        principal: principal_type,
    ) -> Any:
        return await resource.service.create(
            resource, session, principal, payload, request.app.state.settings
        )

    async def patch(
        identifier: UUID,
        payload: patch_type,
        request: Request,
        session: Session,
        principal: principal_type,
    ) -> Any:
        return await resource.service.patch(
            resource, session, principal, identifier, payload, request.app.state.settings
        )

    async def delete(
        identifier: UUID, request: Request, session: Session, principal: principal_type
    ) -> Response:
        await resource.service.delete(
            resource, session, principal, identifier, request.app.state.settings
        )
        return Response(status_code=204)

    definitions = {
        "list": ("", "GET", list_rows, page, 200),
        "retrieve": ("/{identifier}", "GET", retrieve, resource.read_schema, 200),
        "create": ("", "POST", create, resource.read_schema, 201),
        "patch": ("/{identifier}", "PATCH", patch, resource.read_schema, 200),
        "delete": ("/{identifier}", "DELETE", delete, None, 204),
    }
    for operation in sorted(resource.operations):

        def permission(operation: str):
            async def authorize(principal: principal_type) -> None:
                await resource.policy.authorize(operation, principal)

            return authorize

        path, method, handler, response_model, status = definitions[operation]
        router.add_api_route(
            path,
            resource.handlers.get(operation) or cast(Callable[..., Any], handler),
            methods=[method],
            response_model=response_model,
            status_code=status,
            operation_id=f"{resource.name}_{operation}",
            dependencies=[Depends(permission(operation))],
        )
    return router
