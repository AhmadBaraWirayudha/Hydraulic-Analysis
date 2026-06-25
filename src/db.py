"""
Shared PostgreSQL/PostGIS connection management and schema for the
enterprise layer: authentication (auth/), audit logging (audit/), and
geospatial network storage (geospatial/).

Connection parameters come from environment variables — never hardcode
credentials in source or commit them to YAML configs. Sensible local-dev
defaults are provided so the app works out of the box with the
docker-compose Postgres service; override every variable in production.

Environment variables
----------------------
HYDRAULIC_DB_HOST       (default: "localhost")
HYDRAULIC_DB_PORT       (default: "5432")
HYDRAULIC_DB_NAME       (default: "hydraulic_analysis")
HYDRAULIC_DB_USER       (default: "hydraulic_app")
HYDRAULIC_DB_PASSWORD   (default: "dev_password_change_in_production" —
                          a clearly-labeled placeholder; MUST be
                          overridden in any non-local deployment)
"""

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


def get_connection_params() -> dict:
    """Read database connection parameters from environment variables."""
    return dict(
        host=os.environ.get("HYDRAULIC_DB_HOST", "localhost"),
        port=os.environ.get("HYDRAULIC_DB_PORT", "5432"),
        dbname=os.environ.get("HYDRAULIC_DB_NAME", "hydraulic_analysis"),
        user=os.environ.get("HYDRAULIC_DB_USER", "hydraulic_app"),
        password=os.environ.get("HYDRAULIC_DB_PASSWORD", "dev_password_change_in_production"),
    )


@contextmanager
def get_connection():
    """Context-managed database connection — commits on clean exit, rolls
    back and re-raises on exception, always closes the connection.

    Usage
    -----
    >>> with get_connection() as conn:
    ...     with conn.cursor() as cur:
    ...         cur.execute("SELECT 1")
    """
    conn = psycopg2.connect(**get_connection_params())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) NOT NULL CHECK (role IN ('field_technician', 'lead_engineer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_username ON audit_log (username);

CREATE TABLE IF NOT EXISTS network_nodes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    label VARCHAR(100),
    geom GEOMETRY(POINT, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_network_nodes_geom ON network_nodes USING GIST (geom);

CREATE TABLE IF NOT EXISTS network_pipes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    start_node VARCHAR(50) NOT NULL REFERENCES network_nodes(name),
    end_node VARCHAR(50) NOT NULL REFERENCES network_nodes(name),
    diameter_m DOUBLE PRECISION NOT NULL,
    length_m DOUBLE PRECISION NOT NULL,
    roughness_m DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(LINESTRING, 4326)
);
CREATE INDEX IF NOT EXISTS idx_network_pipes_geom ON network_pipes USING GIST (geom);

CREATE TABLE IF NOT EXISTS network_loops (
    id SERIAL PRIMARY KEY,
    loop_name VARCHAR(50) NOT NULL,
    pipe_name VARCHAR(50) NOT NULL REFERENCES network_pipes(name),
    direction SMALLINT NOT NULL CHECK (direction IN (1, -1)),
    sequence_order INT NOT NULL,
    UNIQUE (loop_name, pipe_name)
);
"""


def init_schema() -> None:
    """Create all enterprise tables (and the PostGIS extension) if they
    don't already exist. Idempotent — safe to call on every app startup."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)


def reset_schema() -> None:
    """Drop and recreate all enterprise tables. Used by tests and local
    development resets — NEVER call this against a production database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DROP TABLE IF EXISTS network_loops CASCADE;
                DROP TABLE IF EXISTS network_pipes CASCADE;
                DROP TABLE IF EXISTS network_nodes CASCADE;
                DROP TABLE IF EXISTS audit_log CASCADE;
                DROP TABLE IF EXISTS users CASCADE;
            """)
    init_schema()
