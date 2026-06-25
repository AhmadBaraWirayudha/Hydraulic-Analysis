"""
RBAC and Streamlit page integration tests, using Streamlit's official
``AppTest`` framework (simulates real script execution + widget
interaction, no browser needed).

This is the test suite that actually caught two real production bugs
during development: a bare ternary-expression-as-statement that crashed
on Streamlit's "magic" auto-display feature, and a pandas None-becomes-
NaN coercion that broke a truthiness check. Neither was — or could be —
caught by HTTP-status-code smoke tests, since Streamlit serves its static
HTML shell with a 200 regardless of what the underlying Python script
does; only actually running the script (as AppTest does) exercises the
real code path.
"""

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT_PAGES = "streamlit_app/pages"

VIEW_ONLY_PAGES = [
    "2_compare", "3_results", "4_lean_dashboard", "5_economics", "6_network_map", "9_about",
]
LEAD_ENGINEER_ONLY_PAGES = ["1_input", "7_config_editor", "8_audit_log"]


def _login(at: AppTest, username: str, password: str) -> AppTest:
    at.run()
    at.text_input[0].set_value(username)
    at.text_input[1].set_value(password)
    at.button[0].click().run()
    return at


@pytest.fixture
def seeded_db(clean_schema):
    """Ensure demo users (and for some tests, demo network) exist before
    exercising any page that depends on them."""
    from src.auth.service import seed_demo_users
    seed_demo_users()
    return None


# ── Login flow ──────────────────────────────────────────────────────────────
def test_login_form_shown_when_not_authenticated(seeded_db):
    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at.run()
    assert at.exception.len == 0
    assert any("Sign in" in t.value for t in at.title)
    assert len(at.text_input) == 2
    assert len(at.button) == 1


def test_login_with_correct_credentials_succeeds(seeded_db):
    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    assert at.exception.len == 0
    assert at.session_state["user"].username == "technician"


def test_login_with_wrong_password_shows_error_and_stays_logged_out(seeded_db):
    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at = _login(at, "technician", "wrong_password")
    assert at.exception.len == 0
    assert any("Invalid username or password" in e.value for e in at.error)
    assert "user" not in at.session_state


def test_login_failure_is_audit_logged(seeded_db):
    from src.audit.service import get_audit_log

    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    _login(at, "technician", "wrong_password")

    entries = get_audit_log()
    assert any(e.action == "login_failed" for e in entries)


def test_successful_login_is_audit_logged(seeded_db):
    from src.audit.service import get_audit_log

    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    _login(at, "engineer", "engineer123")

    entries = get_audit_log()
    assert any(e.action == "login" and e.username == "engineer" for e in entries)


# ── RBAC: Lead-Engineer-only pages ──────────────────────────────────────────
@pytest.mark.parametrize("page", LEAD_ENGINEER_ONLY_PAGES)
def test_field_technician_denied_on_lead_engineer_pages(seeded_db, page):
    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/{page}.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    assert at.exception.len == 0
    assert any("Access denied" in e.value for e in at.error)
    assert any("Lead Engineer" in e.value for e in at.error)


@pytest.mark.parametrize("page", LEAD_ENGINEER_ONLY_PAGES)
def test_lead_engineer_granted_on_lead_engineer_pages(seeded_db, page):
    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/{page}.py")
    at.default_timeout = 15
    at = _login(at, "engineer", "engineer123")
    assert at.exception.len == 0
    assert not any("Access denied" in e.value for e in at.error)


# ── View-only pages: both roles should render without exceptions ──────────
@pytest.mark.parametrize("page", VIEW_ONLY_PAGES)
def test_field_technician_can_view_dashboard_pages_without_exceptions(seeded_db, page):
    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/{page}.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    assert at.exception.len == 0
    assert not any("Access denied" in e.value for e in at.error)


@pytest.mark.parametrize("page", VIEW_ONLY_PAGES)
def test_lead_engineer_can_view_dashboard_pages_without_exceptions(seeded_db, page):
    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/{page}.py")
    at.default_timeout = 15
    at = _login(at, "engineer", "engineer123")
    assert at.exception.len == 0


# ── Logout ──────────────────────────────────────────────────────────────────
def test_logout_clears_session_and_shows_login_form_again(seeded_db):
    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    assert "user" in at.session_state

    at.sidebar.button[0].click().run()
    assert "user" not in at.session_state
    assert any("Sign in" in t.value for t in at.title)


def test_logout_is_audit_logged(seeded_db):
    from src.audit.service import get_audit_log

    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    at.sidebar.button[0].click().run()

    entries = get_audit_log()
    assert any(e.action == "logout" for e in entries)


# ── Input page: end-to-end scenario run + audit logging ────────────────────
def test_lead_engineer_running_a_scenario_is_audit_logged(seeded_db):
    from src.audit.service import get_audit_log

    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/1_input.py")
    at.default_timeout = 15
    at = _login(at, "engineer", "engineer123")
    assert at.exception.len == 0

    run_button = next(b for b in at.sidebar.button if "Run Analysis" in b.label)
    run_button.click().run()
    assert at.exception.len == 0

    entries = get_audit_log()
    run_entries = [e for e in entries if e.action == "run_scenario"]
    assert len(run_entries) == 1
    assert run_entries[0].username == "engineer"
    assert "diameter_mm" in run_entries[0].details
