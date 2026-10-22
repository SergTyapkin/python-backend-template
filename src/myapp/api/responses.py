from typing import Any

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_default=True)


class ErrorResponse(Schema):
    code: str
    message: str
    details: Any = None
    request_id: str | None = None


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse}
    for status in (400, 401, 403, 404, 409, 413, 422, 429, 500, 503, 504)
}
