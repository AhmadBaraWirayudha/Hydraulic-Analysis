"""
Shared pytest fixtures.

Database-dependent tests (auth, audit, geospatial) need a running
PostgreSQL+PostGIS instance — available via ``docker compose up`` locally,
or a service container in CI (see .github/workflows/ci.yml). Rather than
hard-failing the entire test run when no database is reachable (e.g. a
contributor running `pytest` without first starting Postgres), the
``db_available`` fixture below detects this up front and the affected
test modules skip cleanly with a clear message.
"""

import pytest

from src.db import get_connection, reset_schema


def _db_reachable() -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_available():
    """Session-scoped: skip all dependent tests immediately if no
    database is reachable, rather than failing one-by-one with confusing
    connection errors."""
    if not _db_reachable():
        pytest.skip(
            "No PostgreSQL/PostGIS database reachable at the configured "
            "HYDRAULIC_DB_* connection settings — start one with "
            "`docker compose up -d db` (or see docs/user_guide.md) to run "
            "these tests."
        )
    return True


@pytest.fixture
def clean_schema(db_available):
    """Reset all enterprise tables to a known-empty state before each test
    that uses this fixture — keeps DB-backed tests independent of each
    other's leftover data."""
    reset_schema()
    yield
    # No teardown needed — the next test's reset_schema() call cleans up.
