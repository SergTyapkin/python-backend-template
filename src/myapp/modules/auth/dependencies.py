import secrets
from typing import Annotated

from fastapi import Depends, Header, Request, Response
from fastapi.security import APIKeyCookie

from myapp.audit.context import actor_id
from myapp.auth.principal import Principal
from myapp.core.dependencies import Session
from myapp.core.exceptions import AppError
from myapp.modules.auth.models import LoginSession
from myapp.modules.auth.service import AuthService, token_digest
from myapp.modules.users.models import User

cookie = APIKeyCookie(name="session", auto_error=False)


def require_origin(request: Request) -> None:
    config = request.app.state.settings
    if request.headers.get("origin") not in config.session.allowed_origins:
        raise AppError(403, "ORIGIN_FORBIDDEN", "Trusted Origin required")


async def current_session(
    request: Request,
    response: Response,
    session: Session,
    token: Annotated[str | None, Depends(cookie)],
    csrf_token: Annotated[
        str | None,
        Header(
            alias="X-CSRF-Token",
            description="CSRF token from login; required for state-changing cookie requests",
        ),
    ] = None,
) -> tuple[User, LoginSession]:
    if not token:
        raise AppError(401, "UNAUTHORIZED", "Session required")
    user, login_session = await AuthService().authenticate(session, token)
    response.headers["Cache-Control"] = "no-store"
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        supplied = csrf_token or ""
        if len(supplied) > 256 or not secrets.compare_digest(
            token_digest(supplied), login_session.csrf_hash
        ):
            raise AppError(403, "CSRF_FAILED", "Valid CSRF token required")
    actor_id.set(str(user.id))
    return user, login_session


LocalSession = Annotated[tuple[User, LoginSession], Depends(current_session)]


async def current_principal(pair: LocalSession) -> Principal:
    user, _ = pair
    return Principal(subject=str(user.id), issuer="local")
