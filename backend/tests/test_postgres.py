"""Integration tests against a real PostgreSQL database.

Skipped unless UNDM_TEST_DATABASE_URL points at a disposable database, e.g.
postgresql+psycopg://undm:undm@localhost:5432/undm_test. The schema is
dropped and recreated through the Alembic migrations.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from api_helpers import FIREWALL, FIREWALL_INTENT, SWITCH, SWITCH_INTENT
from fastapi.testclient import TestClient
from sqlalchemy import text

from undm.api.app import create_app
from undm.config import Settings
from undm.db.session import make_engine, make_session_factory

URL = os.environ.get("UNDM_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="UNDM_TEST_DATABASE_URL not set")
BACKEND = Path(__file__).resolve().parents[1]


def alembic(*args):
    env = dict(os.environ, UNDM_DATABASE_URL=URL)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def pg_client():
    engine = make_engine(URL)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    app = create_app(settings=Settings(database_url=URL, log_level="WARNING"),
                     session_factory=make_session_factory(engine))
    with TestClient(app) as client:
        yield client


def test_migrations_match_models(pg_client):
    r = alembic("check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_full_flow_on_postgres(pg_client):
    c = pg_client
    pid = c.post("/api/projects", json={"name": "PG flow"}).json()["id"]
    ids = []
    for body, intent in ((SWITCH, SWITCH_INTENT), (FIREWALL, FIREWALL_INTENT)):
        did = c.post(f"/api/projects/{pid}/devices", json=body).json()["id"]
        c.put(f"/api/devices/{did}/intent", json=intent)
        assert c.post(f"/api/devices/{did}/configs/generate").json()["ok"]
        ids.append(did)
    dep = c.post(f"/api/projects/{pid}/deployments", json={"device_ids": ids}).json()
    c.post(f"/api/deployments/{dep['id']}/approve")
    out = c.post(f"/api/deployments/{dep['id']}/execute").json()
    assert out["state"] == "succeeded", out["events"]
    assert all(c.get(f"/api/devices/{d}").json()["locked_by_deployment_id"] is None for d in ids)
    assert len(c.get("/api/audit").json()) >= 8
