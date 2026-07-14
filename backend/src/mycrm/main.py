from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mycrm.api import api_router
from mycrm.core.config import get_settings
from mycrm.core.database import engine
from mycrm.core.errors import install_error_handlers
from mycrm.core.logging import configure_logging
from mycrm.core.middleware import install_request_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.logger.info("Application started")
    yield
    await engine.dispose()
    app.state.logger.info("Application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        lifespan=lifespan,
    )
    app.state.logger = configure_logging(settings.log_level)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_request_middleware(app)
    install_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
