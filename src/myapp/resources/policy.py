from typing import Any

from sqlalchemy import Select

from myapp.auth.principal import Principal
from myapp.core.exceptions import AppError


class Policy:
    """Explicit deny-by-default policy. Public access also requires an explicit subclass."""

    async def authorize(self, operation: str, principal: Principal) -> None:
        raise AppError(403, "FORBIDDEN", "Resource access denied")

    def scope(self, statement: Select, model: type[Any], principal: Principal) -> Select:
        raise AppError(403, "FORBIDDEN", "Resource access denied")

    def server_values(self, principal: Principal) -> dict[str, Any]:
        return {}
