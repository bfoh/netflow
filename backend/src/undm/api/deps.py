"""Request-scoped dependencies."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from undm.config import Settings
from undm.drivers.registry import DriverRegistry


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_registry(request: Request) -> DriverRegistry:
    registry: DriverRegistry = request.app.state.registry
    return registry


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_actor(x_undm_actor: Annotated[str | None, Header()] = None) -> str:
    """Who is acting. ATTRIBUTION ONLY - this is not authentication.

    Authentication and role-based authorization are a planned milestone; until
    then the API must only be bound to localhost.
    """
    return (x_undm_actor or "local-user").strip()[:120] or "local-user"


SessionDep = Annotated[Session, Depends(get_session)]
RegistryDep = Annotated[DriverRegistry, Depends(get_registry)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ActorDep = Annotated[str, Depends(get_actor)]
