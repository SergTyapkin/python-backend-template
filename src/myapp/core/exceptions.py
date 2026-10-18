import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from myapp.api.responses import ErrorResponse
from myapp.audit.context import request_id


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        ErrorResponse(code=code, message=message, request_id=request_id.get()).model_dump(
            by_alias=True, mode="json"
        ),
        status_code=status,
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        codes = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
            429: "RATE_LIMITED",
        }
        # HTTPException detail is deliberately not echoed: it may contain input or secrets.
        return error_response(
            exc.status_code,
            codes.get(exc.status_code, "HTTP_ERROR"),
            "Request could not be completed",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return error_response(422, "VALIDATION_ERROR", "Invalid request")

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("myapp").error(
            "unhandled_exception",
            extra={"exception_type": type(exc).__name__, "request_id": request_id.get()},
        )
        return error_response(500, "INTERNAL_ERROR", "Internal server error")
