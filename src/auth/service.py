"""
Authentication service: password hashing (bcrypt), user creation, login
verification, and login rate-limiting against the ``users`` table.

Security notes
---------------
- Passwords are hashed with bcrypt (automatically salted, adaptive cost
  factor) — never stored or compared in plaintext.
- ``authenticate`` runs a dummy bcrypt comparison even when the username
  doesn't exist (see ``_DUMMY_PASSWORD_HASH`` below), so response time
  doesn't leak whether a given username is registered — bcrypt's cost
  factor makes a real comparison and a dummy one take essentially the
  same time, closing the timing side-channel that a naive
  "return None immediately on username-not-found" implementation has.
- Login rate-limiting (``is_rate_limited`` / ``count_recent_failed_logins``)
  is backed by the audit log rather than a separate table — every failed
  login is already logged as a ``login_failed`` audit entry, so counting
  recent ones per username gives rate-limiting "for free" without a new
  table to keep in sync. A successful login resets the count (an
  attacker who eventually guesses right doesn't stay rate-limited from
  their own earlier failures; this also means the legitimate user isn't
  punished for an attacker's later, unrelated attempts on the same
  account once they've logged back in).
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt

from ..db import get_connection
from .models import User, Role

# Rate-limit thresholds, overridable via environment variables for
# deployment-specific tuning without a code change.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get("HYDRAULIC_LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_MINUTES = int(os.environ.get("HYDRAULIC_LOGIN_WINDOW_MINUTES", "15"))


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt (includes an automatic salt)."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


# Computed once at import time (not per-call — hashing is deliberately
# slow, so repeating it every call would be wasteful) and used by
# ``authenticate`` to equalize response time for nonexistent usernames.
# The dummy password itself is never used as a real credential anywhere.
_DUMMY_PASSWORD_HASH = hash_password("dummy_password_for_constant_time_comparison")


def create_user(username: str, plain_password: str, role: Role, full_name: str | None = None) -> User:
    """Create a new user with a securely hashed password.

    Parameters
    ----------
    username       : str   must be unique
    plain_password : str   raw password — hashed before storage, never
                            stored or logged in plaintext
    role           : Role
    full_name      : str | None

    Returns
    -------
    User

    Raises
    ------
    ValueError
        If the username already exists.
    """
    password_hash = hash_password(plain_password)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, full_name, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, username, full_name, role, created_at
                    """,
                    (username, password_hash, full_name, role.value),
                )
                row = cur.fetchone()
    except Exception as e:
        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
            raise ValueError(f"Username '{username}' already exists.") from e
        raise
    return User(id=row[0], username=row[1], full_name=row[2], role=Role(row[3]), created_at=row[4])


def get_user_by_username(username: str) -> User | None:
    """Look up a user by username. Returns None if not found."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, full_name, role, created_at FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
    if row is None:
        return None
    return User(id=row[0], username=row[1], full_name=row[2], role=Role(row[3]), created_at=row[4])


def authenticate(username: str, plain_password: str) -> User | None:
    """Verify a username/password pair against the database.

    Returns
    -------
    User | None
        The authenticated User on success, or None if the username
        doesn't exist or the password is wrong (deliberately
        indistinguishable to the caller — and, via the dummy-hash
        comparison below, indistinguishable by response time too).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, password_hash, full_name, role, created_at "
                "FROM users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()

    if row is None:
        # Run a real bcrypt comparison anyway against a fixed dummy hash,
        # so a nonexistent username takes the same time as a wrong
        # password for an existing one — otherwise returning immediately
        # here is a measurable timing side-channel revealing which
        # usernames are registered.
        verify_password(plain_password, _DUMMY_PASSWORD_HASH)
        return None

    user_id, db_username, password_hash, full_name, role, created_at = row
    if not verify_password(plain_password, password_hash):
        return None

    return User(id=user_id, username=db_username, full_name=full_name, role=Role(role), created_at=created_at)


def count_recent_failed_logins(username: str) -> int:
    """Count failed login attempts for ``username`` since their last
    successful login, within the rate-limiting window
    (``LOGIN_RATE_LIMIT_WINDOW_MINUTES``).

    A successful login resets the count to zero (entries before it are
    not counted), so a legitimate user who eventually logs in
    successfully isn't penalized for their own earlier typos, and isn't
    left rate-limited by an attacker's attempts that happened before
    they regained access.

    Parameters
    ----------
    username : str

    Returns
    -------
    int
    """
    from ..audit.service import get_audit_log

    window_start = datetime.now(timezone.utc) - timedelta(minutes=LOGIN_RATE_LIMIT_WINDOW_MINUTES)
    entries = get_audit_log(username=username, limit=200)  # most recent first

    count = 0
    for entry in entries:
        if entry.created_at < window_start:
            break
        if entry.action == "login":
            break
        if entry.action == "login_failed":
            count += 1
    return count


def is_rate_limited(username: str) -> bool:
    """Whether ``username`` currently has too many recent failed login
    attempts to allow another attempt right now.

    Checked by the login form *before* calling ``authenticate`` — this
    applies even to nonexistent usernames (every failed attempt is
    logged regardless of whether the username exists), so the
    rate-limit itself doesn't become a second username-existence oracle.
    """
    return count_recent_failed_logins(username) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS


def list_users() -> list[User]:
    """Return all users (for an admin/user-management view)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, full_name, role, created_at FROM users ORDER BY username"
            )
            rows = cur.fetchall()
    return [User(id=r[0], username=r[1], full_name=r[2], role=Role(r[3]), created_at=r[4]) for r in rows]


def seed_demo_users() -> None:
    """Create the two demo users this project's RBAC walkthrough uses, if
    they don't already exist. Safe to call repeatedly (idempotent)."""
    demo_users = [
        ("technician", "technician123", Role.FIELD_TECHNICIAN, "Alex (Field Technician)"),
        ("engineer", "engineer123", Role.LEAD_ENGINEER, "Sam (Lead Engineer)"),
    ]
    for username, password, role, full_name in demo_users:
        if get_user_by_username(username) is None:
            create_user(username, password, role, full_name)
