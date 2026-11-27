"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from undm import __version__
from undm.api.routers import (
    deployments,
    devices,
    firmware,
    guided,
    projects,
    provisioning,
    system,
    systems,
    templates,
    topology,
    troubleshoot,
)
from undm.config import Settings, get_settings
from undm.db.schema_check import UPGRADE_HINT, database_problem
from undm.db.session import make_engine, make_session_factory
from undm.drivers.mock.lab import default_lab
from undm.drivers.registry import DriverRegistry, default_registry
from undm.logging_setup import configure_logging
from undm.services.deployments import recover_interrupted_deployments
from undm.services.errors import ServiceError
from undm.services.jobs import DeploymentJobs
from undm.transfer.hub import TransferHub


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    registry: DriverRegistry | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = app.state.session_factory.kw.get("bind")
        app.state.database_problem = database_problem(engine) if engine is not None else None
        if app.state.database_problem:
            logging.getLogger("undm").error(app.state.database_problem)
            yield  # keep serving so the UI can show the message
            return
        with app.state.session_factory() as session:
            resolved = recover_interrupted_deployments(session)
        if resolved:
            logging.getLogger("undm").warning(
                "resolved interrupted deployments", extra={"ctx": {"ids": resolved}}
            )
        yield
        app.state.deployment_jobs.stop_all("application shutdown")

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
    app.state.transfer_hub = TransferHub(settings.tftp_host, settings.tftp_port)
    app.state.deployment_jobs = DeploymentJobs()
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

    @app.exception_handler(OperationalError)
    async def _database_error(_: Request, exc: OperationalError) -> JSONResponse:
        logging.getLogger("undm").error("database error: %s", exc.orig)
        hint = getattr(app.state, "database_problem", None) or (
            "If UNDM was just updated, the database may need upgrading. " + UPGRADE_HINT)
        return JSONResponse(status_code=500, content={
            "error": f"Database error ({type(exc.orig).__name__}). {hint}", "details": None})

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("undm").exception("unhandled error")
        return JSONResponse(status_code=500, content={
            "error": f"Internal error in the backend ({type(exc).__name__}); the backend "
                     "window shows the details.", "details": None})

    for r in (system.router, projects.router, projects.credentials_router,
              projects.settings_router, devices.router,
              deployments.router, firmware.router, topology.router, provisioning.router,
              systems.router, templates.router, guided.router, troubleshoot.router):
        app.include_router(r)
    return app


def app_factory() -> FastAPI:
    """Entry point for ``uvicorn --factory undm.api.app:app_factory``."""
    return create_app()
