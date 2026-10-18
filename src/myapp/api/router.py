from fastapi import APIRouter, Request

from myapp.api.responses import Schema
from myapp.core.exceptions import AppError

router = APIRouter()
api_router = APIRouter(prefix="/api/v1")
# Explicitly include business module routers here; an empty API namespace is intentional.


class Health(Schema):
    status: str


class Version(Schema):
    version: str
    git_sha: str


@router.get("/health/live", response_model=Health, tags=["Infrastructure"])
async def live() -> Health:
    return Health(status="ok")


@router.get("/health/ready", response_model=Health, tags=["Infrastructure"])
async def ready(request: Request) -> Health:
    if not await request.app.state.database.ready():
        raise AppError(503, "NOT_READY", "Service not ready")
    return Health(status="ready")


@router.get("/version", response_model=Version, tags=["Infrastructure"])
async def version(request: Request) -> Version:
    settings = request.app.state.settings
    return Version(version=settings.build_version, git_sha=settings.git_sha)
