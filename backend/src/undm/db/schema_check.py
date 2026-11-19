"""Detect a database that is older than the code (migrations not applied).

Without this, an outdated database only shows up as unexplained errors on some
pages (for example a missing column). The check runs once at startup and the
result is reported by /api/health so the UI can say exactly what to do.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import Engine, inspect

UPGRADE_HINT = (
    "Stop the backend, then in the backend folder run "
    "'.venv\\Scripts\\python.exe -m alembic upgrade head' (Windows) or "
    "'.venv/bin/alembic upgrade head' (Linux/macOS), and start the backend again.")

# backend/alembic.ini, next to the src/ folder that holds this package.
_ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def database_problem(engine: Engine, alembic_ini: Path = _ALEMBIC_INI) -> str | None:
    """A message if the database needs `alembic upgrade head`; None if it is current.

    Databases created without Alembic (tests use ``create_all``) are not judged.
    """
    if not alembic_ini.exists():
        return None  # installed without the migration scripts; nothing to compare with
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    try:
        heads = set(ScriptDirectory.from_config(Config(str(alembic_ini))).get_heads())
        with engine.connect() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
            tables = set(inspect(conn).get_table_names())
    except Exception as e:  # noqa: BLE001 - report, never block startup
        logging.getLogger("undm").warning("database check failed: %s", e)
        return None
    if not current:
        if "devices" in tables:
            return None  # created directly from the models (tests, demos)
        return "The database has not been created yet. " + UPGRADE_HINT
    if current != heads:
        return (f"The database is older than this version of UNDM (database at "
                f"{', '.join(sorted(current))}, this version needs {', '.join(sorted(heads))}). "
                + UPGRADE_HINT)
    return None
