"""
User and role models for the RBAC (role-based access control) system.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Role(str, Enum):
    """The two roles this system demonstrates.

    FIELD_TECHNICIAN : view-only — can see all dashboards/results, cannot
                        run ad-hoc scenarios or edit configuration.
    LEAD_ENGINEER     : full authority — everything a Field Technician can
                        do, plus running ad-hoc scenarios and editing the
                        YAML configuration that drives the whole pipeline.
    """

    FIELD_TECHNICIAN = "field_technician"
    LEAD_ENGINEER = "lead_engineer"

    @property
    def display_name(self) -> str:
        return {"field_technician": "Field Technician", "lead_engineer": "Lead Engineer"}[self.value]


@dataclass
class User:
    """An authenticated user."""

    id: int
    username: str
    full_name: str | None
    role: Role
    created_at: datetime

    @property
    def can_edit_config(self) -> bool:
        """Whether this user may modify YAML configuration files."""
        return self.role == Role.LEAD_ENGINEER

    @property
    def can_run_scenarios(self) -> bool:
        """Whether this user may execute ad-hoc scenario runs (the Input page)."""
        return self.role == Role.LEAD_ENGINEER
