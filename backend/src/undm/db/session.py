"""Engine and session management.

PostgreSQL is the supported database. SQLite is accepted for automated tests
(in-memory) and as a development-only fallback on workstations without
PostgreSQL; it is not supported for shared or production use.
"""

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        in_memory = url in ("sqlite://", "sqlite:///:memory:")
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            # An in-memory database exists per connection, so share one.
            poolclass=StaticPool if in_memory else None,
        )
        event.listen(engine, "connect", _sqlite_foreign_keys)
        return engine
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session
