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
    count_recent_failed_logins, is_rate_limited, LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
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


# ── Constant-time username lookup ──────────────────────────────────────────
def test_authenticate_timing_nonexistent_vs_wrong_password_is_similar(clean_schema):
    """The whole point of the dummy-hash comparison: response time for a
    nonexistent username shouldn't be dramatically faster than for a
    wrong password on a real account (which would leak which usernames
    are registered). Uses a generous tolerance (not a precise timing-
    attack benchmark) since CI/sandboxed environments have noisy timing."""
    import time

    create_user("real_user", "correct_password", Role.FIELD_TECHNICIAN)

    t0 = time.perf_counter()
    authenticate("nonexistent_user_xyz", "whatever")
    t1 = time.perf_counter()
    authenticate("real_user", "wrong_password")
    t2 = time.perf_counter()

    nonexistent_time = t1 - t0
    wrong_password_time = t2 - t1
    # Generous bound: nonexistent-username path should take at least 50%
    # as long as the real comparison (a naive unhardened implementation
    # would typically be 100-1000x faster, since it skips bcrypt entirely).
    assert nonexistent_time > wrong_password_time * 0.5


def test_authenticate_still_correctly_rejects_nonexistent_user(clean_schema):
    """Hardening shouldn't change the actual (non-timing) behavior."""
    assert authenticate("nonexistent_user_xyz", "whatever") is None


# ── Login rate limiting ─────────────────────────────────────────────────────
def test_count_recent_failed_logins_zero_initially(clean_schema):
    assert count_recent_failed_logins("alice") == 0


def test_count_recent_failed_logins_counts_login_failed_entries(clean_schema):
    from src.audit.service import log_action

    for _ in range(3):
        log_action("alice", "login_failed", {})
    assert count_recent_failed_logins("alice") == 3


def test_is_rate_limited_false_under_threshold(clean_schema):
    from src.audit.service import log_action

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS - 1):
        log_action("alice", "login_failed", {})
    assert is_rate_limited("alice") is False


def test_is_rate_limited_true_at_threshold(clean_schema):
    from src.audit.service import log_action

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        log_action("alice", "login_failed", {})
    assert is_rate_limited("alice") is True


def test_is_rate_limited_resets_after_successful_login(clean_schema):
    from src.audit.service import log_action

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        log_action("alice", "login_failed", {})
    assert is_rate_limited("alice") is True

    log_action("alice", "login", {})
    assert is_rate_limited("alice") is False


def test_is_rate_limited_applies_to_nonexistent_usernames_too(clean_schema):
    """Rate limiting must not itself become a username-existence oracle —
    a nonexistent username hammered repeatedly should also get limited."""
    from src.audit.service import log_action

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        log_action("totally_made_up_user", "login_failed", {})
    assert is_rate_limited("totally_made_up_user") is True


def test_is_rate_limited_false_for_blank_username(clean_schema):
    assert is_rate_limited("") is False


def test_is_rate_limited_per_username_independent(clean_schema):
    """Failed attempts on one account shouldn't rate-limit a different one."""
    from src.audit.service import log_action

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        log_action("alice", "login_failed", {})
    assert is_rate_limited("alice") is True
    assert is_rate_limited("bob") is False
