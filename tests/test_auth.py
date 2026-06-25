"""
Unit tests for src/auth/ — password hashing, user creation, and
authentication against a real PostgreSQL database.

Requires a reachable Postgres instance (see conftest.py's db_available
fixture) — skips cleanly if none is available.
"""

import pytest

from src.auth.models import User, Role
from src.auth.service import (
    hash_password, verify_password, create_user, get_user_by_username,
    authenticate, list_users, seed_demo_users,
)


# ── Password hashing (no DB needed) ─────────────────────────────────────────
def test_hash_password_produces_verifiable_hash():
    hashed = hash_password("correct_password")
    assert verify_password("correct_password", hashed) is True


def test_hash_password_rejects_wrong_password():
    hashed = hash_password("correct_password")
    assert verify_password("wrong_password", hashed) is False


def test_hash_password_never_stores_plaintext():
    hashed = hash_password("my_secret_password")
    assert "my_secret_password" not in hashed


def test_hash_password_same_password_different_hashes():
    """bcrypt's automatic salting means hashing the same password twice
    should produce different hashes."""
    h1 = hash_password("same_password")
    h2 = hash_password("same_password")
    assert h1 != h2
    assert verify_password("same_password", h1)
    assert verify_password("same_password", h2)


# ── Role model ────────────────────────────────────────────────────────────
def test_role_display_names():
    assert Role.FIELD_TECHNICIAN.display_name == "Field Technician"
    assert Role.LEAD_ENGINEER.display_name == "Lead Engineer"


def test_user_permissions_by_role():
    from datetime import datetime, timezone

    technician = User(1, "tech1", "Tech", Role.FIELD_TECHNICIAN, datetime.now(timezone.utc))
    engineer = User(2, "eng1", "Eng", Role.LEAD_ENGINEER, datetime.now(timezone.utc))

    assert technician.can_edit_config is False
    assert technician.can_run_scenarios is False
    assert engineer.can_edit_config is True
    assert engineer.can_run_scenarios is True


# ── Database-backed tests ───────────────────────────────────────────────────
def test_create_and_authenticate_user(clean_schema):
    created = create_user("alice", "secret123", Role.LEAD_ENGINEER, "Alice Smith")
    assert created.username == "alice"
    assert created.role == Role.LEAD_ENGINEER

    authenticated = authenticate("alice", "secret123")
    assert authenticated is not None
    assert authenticated.username == "alice"
    assert authenticated.id == created.id


def test_authenticate_wrong_password_returns_none(clean_schema):
    create_user("bob", "correct_password", Role.FIELD_TECHNICIAN)
    assert authenticate("bob", "wrong_password") is None


def test_authenticate_nonexistent_user_returns_none(clean_schema):
    assert authenticate("nobody", "whatever") is None


def test_create_user_rejects_duplicate_username(clean_schema):
    create_user("charlie", "pw1", Role.FIELD_TECHNICIAN)
    with pytest.raises(ValueError, match="already exists"):
        create_user("charlie", "pw2", Role.LEAD_ENGINEER)


def test_get_user_by_username_returns_none_if_not_found(clean_schema):
    assert get_user_by_username("ghost") is None


def test_get_user_by_username_finds_existing_user(clean_schema):
    create_user("dana", "pw", Role.LEAD_ENGINEER, "Dana Lee")
    found = get_user_by_username("dana")
    assert found is not None
    assert found.full_name == "Dana Lee"


def test_list_users_returns_all_created_users(clean_schema):
    create_user("user_a", "pw", Role.FIELD_TECHNICIAN)
    create_user("user_b", "pw", Role.LEAD_ENGINEER)
    usernames = {u.username for u in list_users()}
    assert usernames == {"user_a", "user_b"}


def test_seed_demo_users_creates_both_roles(clean_schema):
    seed_demo_users()
    usernames_and_roles = {(u.username, u.role) for u in list_users()}
    assert ("technician", Role.FIELD_TECHNICIAN) in usernames_and_roles
    assert ("engineer", Role.LEAD_ENGINEER) in usernames_and_roles


def test_seed_demo_users_is_idempotent(clean_schema):
    seed_demo_users()
    seed_demo_users()  # should not raise or create duplicates
    usernames = [u.username for u in list_users()]
    assert usernames.count("technician") == 1
    assert usernames.count("engineer") == 1


def test_seeded_demo_users_can_authenticate(clean_schema):
    seed_demo_users()
    tech = authenticate("technician", "technician123")
    eng = authenticate("engineer", "engineer123")
    assert tech is not None and tech.role == Role.FIELD_TECHNICIAN
    assert eng is not None and eng.role == Role.LEAD_ENGINEER
