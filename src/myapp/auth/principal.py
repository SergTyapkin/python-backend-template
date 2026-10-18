from typing import Any

from pydantic import BaseModel, ConfigDict


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)
    subject: str
    issuer: str
    scopes: frozenset[str] = frozenset()
    roles: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    claims: dict[str, Any] = {}
