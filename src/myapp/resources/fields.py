from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Any, ClassVar, TypedDict, Unpack

from sqlalchemy import MetaData
from sqlmodel import Field, SQLModel

from myapp.db.base import Base


class FieldAccess(StrEnum):
    READ_WRITE = "read_write"
    READ_ONLY = "read_only"
    CREATE_ONLY = "create_only"
    SERVER_ONLY = "server_only"


class ResourceModel(SQLModel):
    metadata: ClassVar[MetaData] = Base.metadata


class FieldOptions(TypedDict, total=False):
    default: Any
    default_factory: Callable[[], Any]
    title: str
    description: str
    min_length: int
    max_length: int
    pattern: str
    ge: float
    gt: float
    le: float
    lt: float
    primary_key: bool
    foreign_key: str
    ondelete: Any
    unique: bool
    index: bool
    nullable: bool
    sa_type: Any
    sa_column: Any
    sa_column_kwargs: Mapping[str, Any]


def api_field(
    *, access: FieldAccess = FieldAccess.SERVER_ONLY, **options: Unpack[FieldOptions]
) -> Any:
    """SQLModel Field plus explicit API access; SQLModel owns DB options and defaults."""
    if "schema_extra" in options or "json_schema_extra" in options:
        raise ValueError("api_field reserves schema_extra for field access metadata")
    unknown = options.keys() - FieldOptions.__annotations__.keys()
    if unknown:
        raise ValueError(f"Unsupported api_field options: {sorted(unknown)}")
    if not isinstance(access, FieldAccess):
        raise ValueError("access must be a FieldAccess value")
    forwarded: dict[str, Any] = dict(options)
    extra: dict[str, Any] = {"json_schema_extra": {"resource_access": access.value}}
    if "pattern" in forwarded:
        extra["pattern"] = forwarded.pop("pattern")
    return Field(**forwarded, schema_extra=extra)
