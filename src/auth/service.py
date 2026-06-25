"""
Authentication service: password hashing (bcrypt), user creation, and
login verification against the ``users`` table.

Security notes
---------------
- Passwords are hashed with bcrypt (automatically salted, adaptive cost
  factor) — never stored or compared in plaintext.
- ``authenticate`` takes the same time whether the username exists or
  not is NOT guaranteed here (a real timing-attack-hardened
  implementation would always run a dummy hash comparison even on
  username-not-found) — acceptable for this demonstration, but note the
  gap if hardening for a real adversarial threat model.
"""

import bcrypt

from ..db import get_connection
from .models import User, Role


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt (includes an automatic salt)."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


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
        indistinguishable to the caller, to avoid leaking which usernames
        are registered).
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
        return None

    user_id, db_username, password_hash, full_name, role, created_at = row
    if not verify_password(plain_password, password_hash):
        return None

    return User(id=user_id, username=db_username, full_name=full_name, role=Role(role), created_at=created_at)


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
