from collections.abc import Callable

from myapp.auth.dependencies import CurrentPrincipal
from myapp.auth.principal import Principal
from myapp.core.exceptions import AppError


def require_permissions(*permissions: str) -> Callable:
    async def dependency(principal: CurrentPrincipal) -> Principal:
        if not set(permissions) <= principal.permissions:
            raise AppError(403, "FORBIDDEN", "Permission required")
        return principal

    return dependency


def require_scopes(*scopes: str) -> Callable:
    async def dependency(principal: CurrentPrincipal) -> Principal:
        if not set(scopes) <= principal.scopes:
            raise AppError(403, "FORBIDDEN", "Scope required")
        return principal

    return dependency


def require_ownership(principal: Principal, owner_subject: str) -> None:
    # Call after loading the resource, in addition to route-level permissions.
    if principal.subject != owner_subject:
        raise AppError(403, "FORBIDDEN", "Resource access denied")
