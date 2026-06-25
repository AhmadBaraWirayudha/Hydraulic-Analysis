"""
Audit log models — traceability for who did what, when, in a corporate
environment where decisions must be auditable.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class AuditLogEntry:
    """One audit log record."""

    id: int
    username: str
    action: str
    details: dict
    created_at: datetime
