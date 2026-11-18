"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from undm import __version__
from undm.api.routers import deployments, devices, firmware, projects, system, topology
from undm.config import Settings, get_settings
from undm.db.session import make_engine, make_session_factory
from undm.drivers.mock.lab import default_lab
from undm.drivers.registry import DriverRegistry, default_registry
from undm.logging_setup import configure_logging
from undm.services.deployments import recover_interrupted_deployments
from undm.services.errors import ServiceError


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    registry: DriverRegistry | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with app.state.session_factory() as session:
            resolved = recover_interrupted_deployments(session)
        if resolved:
            logging.getLogger("undm").warning(
                "resolved interrupted deployments", extra={"ctx": {"ids": resolved}}
            )
        yield

    app = FastAPI(
        title="Universal Network Deployment Manager",
        version=__version__,
        description="Vendor-neutral network design, configuration and deployment API.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory or make_session_factory(
        make_engine(settings.database_url)
    )
    app.state.registry = registry or default_registry()
    default_lab().autocreate = settings.simulation_autocreate

    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "details": exc.details},
        )

    for r in (system.router, projects.router, projects.credentials_router, devices.router,
              deployments.router, firmware.router, topology.router):
        app.include_router(r)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory undm.api.app:app_factory``."""
    return create_app()
