"""
Audit log service: records who performed an action, when, and with what
parameters — for traceability of decisions in a corporate environment.

Every write operation that matters for accountability (running an ad-hoc
scenario, editing a YAML config) should call ``log_action`` with enough
detail in ``details`` to reconstruct exactly what happened, without
relying on anyone remembering or re-deriving it later.
"""

import json

import psycopg2.extras

from ..db import get_connection
from .models import AuditLogEntry


def log_action(username: str, action: str, details: dict | None = None) -> None:
    """Record an audit log entry.

    Parameters
    ----------
    username : str   who performed the action (the authenticated user's
                username — never log on behalf of an unauthenticated
                actor)
    action   : str   short, consistent action identifier, e.g.
                "run_scenario", "edit_config", "login", "login_failed"
    details  : dict | None
                arbitrary JSON-serializable parameters describing exactly
                what happened — e.g. {"diameter_m": 0.1016,
                "flow_rate_m3s": 0.0005} for a scenario run, or
                {"file": "scenario_config.yaml", "field": "discount_rate",
                "old_value": 0.07, "new_value": 0.08} for a config edit
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log (username, action, details) VALUES (%s, %s, %s)",
                (username, action, json.dumps(details or {})),
            )


def get_audit_log(limit: int = 100, username: str | None = None) -> list[AuditLogEntry]:
    """Query recent audit log entries, most recent first.

    Parameters
    ----------
    limit    : int           maximum entries to return
    username : str | None    if supplied, filter to only this user's actions

    Returns
    -------
    list[AuditLogEntry]
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if username is not None:
                cur.execute(
                    "SELECT id, username, action, details, created_at FROM audit_log "
                    "WHERE username = %s ORDER BY created_at DESC LIMIT %s",
                    (username, limit),
                )
            else:
                cur.execute(
                    "SELECT id, username, action, details, created_at FROM audit_log "
                    "ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
            rows = cur.fetchall()
    return [
        AuditLogEntry(id=r["id"], username=r["username"], action=r["action"],
                       details=r["details"], created_at=r["created_at"])
        for r in rows
    ]
