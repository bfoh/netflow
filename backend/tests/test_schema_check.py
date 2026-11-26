"""An outdated database is reported clearly instead of failing on some pages."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from undm.api.app import create_app
from undm.config import Settings
from undm.db.models import Base
from undm.db.schema_check import database_problem
from undm.db.session import make_engine, make_session_factory

INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _migrate(url: str, revision: str) -> None:
    cfg = Config(str(INI))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, revision)


def test_current_database_is_fine(tmp_path):
    url = f"sqlite:///{tmp_path / 'head.db'}"
    _migrate(url, "head")
    assert database_problem(make_engine(url)) is None


def test_older_database_is_reported_with_the_fix(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    _migrate(url, "517d6dce2146")
    problem = database_problem(make_engine(url))
    assert problem and "older than this version" in problem
    assert "517d6dce2146" in problem and "alembic upgrade head" in problem


def test_empty_and_model_created_databases(tmp_path):
    empty = make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert "not been created yet" in (database_problem(empty) or "")
    direct = make_engine(f"sqlite:///{tmp_path / 'direct.db'}")
    Base.metadata.create_all(direct)
    assert database_problem(direct) is None  # tests and demos create tables directly


def test_health_and_api_errors_explain_the_upgrade(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    _migrate(url, "517d6dce2146")
    app = create_app(settings=Settings(database_url=url, log_level="WARNING",
                                       data_dir=str(tmp_path)),
                     session_factory=make_session_factory(make_engine(url)))
    with TestClient(app, raise_server_exceptions=False) as c:
        health = c.get("/api/health").json()
        assert health["status"] == "database_upgrade_needed"
        assert "alembic upgrade head" in health["problem"]
        # The projects table itself lacks newer columns, so any use of it explains the upgrade.
        r = c.post("/api/projects", json={"name": "P"})
        assert r.status_code == 500
        assert r.json()["error"].startswith("Database error (OperationalError)")
        assert "alembic upgrade head" in r.json()["error"]
