from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from myapp.api.responses import ERROR_RESPONSES
from myapp.api.router import api_router, router
from myapp.auth.jwks import JWKSCache
from myapp.auth.oidc import TokenVerifier
from myapp.core.config import Settings
from myapp.core.exceptions import register_handlers
from myapp.db.session import Database
from myapp.observability.logging import configure_logging
from myapp.observability.middleware import RequestMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(config)
        database = Database(config.database)
        app.state.database = database
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5), follow_redirects=False, trust_env=False
            ) as client:
                app.state.http = client
                app.state.verifier = TokenVerifier(config.auth, JWKSCache(config.auth, client))
                yield
        finally:
            await database.close()

    app = FastAPI(
        swagger_ui_oauth2_redirect_url=None,
        title=config.project_name,
        description=config.description,
        version=config.build_version,
        debug=False,
        lifespan=lifespan,
        responses=ERROR_RESPONSES,
    )
    app.state.settings = config
    register_handlers(app)
    app.include_router(router)
    app.include_router(api_router)
    app.add_middleware(RequestMiddleware, settings=config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    # OpenTelemetry instrumentation belongs here; exporter is deployment-owned.
    return app


app = create_app()
