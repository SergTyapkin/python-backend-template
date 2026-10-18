from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from myapp.audit.context import actor_id
from myapp.auth.principal import Principal
from myapp.core.exceptions import AppError

bearer = HTTPBearer(auto_error=False)


async def get_current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if credentials is None:
        raise AppError(401, "UNAUTHORIZED", "Bearer access token required")
    principal = await request.app.state.verifier.verify(credentials.credentials)
    actor_id.set(principal.subject)
    return principal


require_authenticated = get_current_principal
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
