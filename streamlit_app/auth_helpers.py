"""
Shared authentication helpers for Streamlit pages. Every page calls
``require_login()`` at the top (and ``require_role()`` additionally, on
pages restricted to Lead Engineers).

This lives in ``streamlit_app/`` rather than ``src/`` deliberately: it's
pure Streamlit UI glue (session state, forms, st.stop()), not business
logic. The actual auth logic it calls into (``src.auth.service``) has no
Streamlit dependency and is fully unit-testable on its own.
"""

import os
import time

import streamlit as st

from src.db import init_schema
from src.auth.service import authenticate, seed_demo_users, is_rate_limited, LOGIN_RATE_LIMIT_WINDOW_MINUTES
from src.auth.models import Role, User
from src.audit.service import log_action

# Idle-session timeout, overridable via environment variable. A page
# interaction (any rerun) within this window keeps the session alive;
# the clock resets on every page load, so it's an idle timeout, not an
# absolute session lifetime.
SESSION_TIMEOUT_SECONDS = int(os.environ.get("HYDRAULIC_SESSION_TIMEOUT_SECONDS", str(30 * 60)))


def _ensure_db_ready() -> None:
    """Initialize schema + seed demo users once per server process (not
    once per page load — session_state persists this across reruns within
    the same session, but a fresh server process will re-run it once)."""
    if st.session_state.get("_db_initialized"):
        return
    try:
        init_schema()
        seed_demo_users()
        st.session_state["_db_initialized"] = True
    except Exception as e:
        st.error(f"⚠️ Could not reach the database: {e}")
        st.info(
            "This dashboard requires PostgreSQL+PostGIS for login, audit "
            "logging, and the network map. Run `docker compose up` (starts "
            "both the app and a Postgres+PostGIS service), or see "
            "DEPLOYMENT.md for other options."
        )
        st.stop()


def render_login_form() -> None:
    st.title("🔒 Sign in")
    st.caption(
        "Demo credentials — **technician** / technician123 (Field Technician, "
        "view-only) or **engineer** / engineer123 (Lead Engineer, full access). "
        "Change these before any real deployment."
    )
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if submitted:
        if username and is_rate_limited(username):
            st.error(
                f"🚫 Too many failed login attempts for this account. Try "
                f"again in a few minutes (limit resets "
                f"{LOGIN_RATE_LIMIT_WINDOW_MINUTES} minutes after the first "
                f"of the recent failures, or immediately on a correct login)."
            )
            log_action(username, "login_rate_limited", {})
            return

        user = authenticate(username, password)
        if user is not None:
            st.session_state["user"] = user
            st.session_state["_last_activity_ts"] = time.time()
            log_action(user.username, "login", {})
            st.rerun()
        else:
            st.error("Invalid username or password.")
            log_action(username or "(blank)", "login_failed", {})


def require_login() -> User:
    """Call at the top of every page. Renders a login form and halts page
    execution (via st.stop()) if no one is signed in or the session has
    expired from inactivity; otherwise returns the signed-in User and
    refreshes the activity timestamp.
    """
    _ensure_db_ready()

    if "user" not in st.session_state:
        render_login_form()
        st.stop()

    now = time.time()
    last_activity = st.session_state.get("_last_activity_ts")
    if last_activity is not None and (now - last_activity) > SESSION_TIMEOUT_SECONDS:
        expired_user = st.session_state["user"]
        log_action(expired_user.username, "session_expired", {})
        del st.session_state["user"]
        del st.session_state["_last_activity_ts"]
        st.warning("⏱️ Your session expired due to inactivity. Please sign in again.")
        render_login_form()
        st.stop()

    st.session_state["_last_activity_ts"] = now
    return st.session_state["user"]


def require_role(user: User, allowed: Role | list[Role], page_name: str = "this page") -> None:
    """Call after require_login() on pages restricted to specific
    role(s). Shows an access-denied message and halts execution
    (st.stop()) if the user's role isn't in ``allowed``.
    """
    allowed_roles = [allowed] if isinstance(allowed, Role) else allowed
    if user.role not in allowed_roles:
        allowed_names = " or ".join(r.display_name for r in allowed_roles)
        st.error(
            f"🔒 Access denied: {page_name} requires the **{allowed_names}** "
            f"role. You are signed in as **{user.role.display_name}**."
        )
        st.caption(
            "This is RBAC working as intended, not a bug — sign in as "
            "**engineer** (Lead Engineer) to access this page."
        )
        st.stop()


def render_user_badge(user: User) -> None:
    """Sidebar widget showing who's signed in, their role, idle-session
    time remaining, and a logout button. Call on every page after
    require_login()."""
    st.sidebar.divider()
    st.sidebar.caption(f"Signed in as **{user.full_name or user.username}**")
    st.sidebar.caption(f"Role: {user.role.display_name}")

    last_activity = st.session_state.get("_last_activity_ts")
    if last_activity is not None:
        remaining_min = max(0, SESSION_TIMEOUT_SECONDS - (time.time() - last_activity)) / 60
        st.sidebar.caption(f"Session active (idle timeout in ~{remaining_min:.0f} min)")

    if st.sidebar.button("Log out"):
        log_action(user.username, "logout", {})
        del st.session_state["user"]
        st.rerun()
