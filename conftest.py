"""Shared pytest fixtures: disposable test Postgres DB (no containers)."""
import os
import pytest
import sqlalchemy as sa
from sqlalchemy import text

TEST_DB = os.environ.get("APIX_TEST_DB", "test_apix")
ADMIN_URL = os.environ.get(
    "APIX_TEST_ADMIN_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
)


def _test_url() -> str:
    return os.environ.get(
        "APIX_TEST_DATABASE_URL",
        f"postgresql+psycopg://postgres:postgres@localhost:5432/{TEST_DB}",
    )


@pytest.fixture(scope="session")
def test_db_url():
    """Create a disposable database on the local Postgres instance, apply schema, drop on teardown."""
    admin = sa.create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    url = _test_url()
    eng = sa.create_engine(url)
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path) as f:
        raw = f.read()
    # Strip TimescaleDB-specific calls when extension is absent.
    raw = raw.replace("SELECT create_hypertable('fares', 'scrape_timestamp');", "")
    with eng.begin() as conn:
        for stmt in [s.strip() for s in raw.split(";") if s.strip()]:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass
    yield url
    eng.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}"'))
    admin.dispose()
