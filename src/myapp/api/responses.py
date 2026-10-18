from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Schema(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True, extra="forbid"
    )


class ErrorResponse(Schema):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse}
    for status in (400, 401, 403, 404, 409, 413, 422, 429, 500, 503, 504)
}
