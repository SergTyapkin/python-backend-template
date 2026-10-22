# mypy: disable-error-code=valid-type
# User DTOs are generated from the declaration, just like resource schemas.

from fastapi import APIRouter, Request, Response
from pydantic import Field, SecretStr, create_model

from myapp.api.responses import Schema
from myapp.core.dependencies import Session
from myapp.modules.auth.dependencies import LocalSession, require_origin
from myapp.modules.auth.service import AuthService
from myapp.modules.users.models import User
from myapp.resources.schemas import generate_schema

router = APIRouter(prefix="/auth", tags=["Local auth"])


Credentials = create_model(
    "Credentials",
    __base__=generate_schema(User, "create"),
    password=(SecretStr, Field(min_length=12, max_length=128)),
)
UserRead = generate_schema(User, "read")
LoginRead = create_model("LoginRead", __base__=Schema, user=(UserRead, ...), csrf_token=(str, ...))


@router.post("/register", response_model=UserRead, status_code=201, operation_id="auth_register")
async def register(payload: Credentials, request: Request, session: Session) -> UserRead:
    require_origin(request)
    if not request.app.state.settings.session.allow_registration:
        from myapp.core.exceptions import AppError

        raise AppError(403, "REGISTRATION_DISABLED", "Registration disabled")
    user = await AuthService().register(
        session,
        payload.model_dump()["username"],
        payload.model_dump()["password"].get_secret_value(),
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=LoginRead, operation_id="auth_login")
async def login(
    payload: Credentials, request: Request, response: Response, session: Session
) -> LoginRead:
    require_origin(request)
    user, token, csrf = await AuthService().login(
        session,
        request.app.state.settings,
        payload.model_dump()["username"],
        payload.model_dump()["password"].get_secret_value(),
    )
    secure = request.app.state.settings.environment != "development"
    response.set_cookie(
        "session",
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=request.app.state.settings.session.ttl_seconds,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginRead.model_validate({"user": UserRead.model_validate(user), "csrf_token": csrf})


@router.get("/me", response_model=UserRead, operation_id="auth_me")
async def me(pair: LocalSession) -> UserRead:
    return UserRead.model_validate(pair[0])


@router.post("/logout", status_code=204, operation_id="auth_logout")
async def logout(
    pair: LocalSession, session: Session, response: Response, request: Request
) -> Response:
    await session.delete(pair[1])
    await session.flush()
    response.delete_cookie(
        "session",
        path="/",
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.environment != "development",
    )
    response.status_code = 204
    response.headers["Cache-Control"] = "no-store"
    return response
