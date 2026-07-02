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
    "2_compare", "3_results", "4_lean_dashboard", "5_economics", "6_network_map",
    "9_about", "10_pipe_design",
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


# ── Auth hardening: rate limiting ───────────────────────────────────────────
def test_repeated_failed_logins_get_rate_limited(seeded_db):
    from src.auth.service import LOGIN_RATE_LIMIT_MAX_ATTEMPTS

    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at.run()

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        at.text_input[0].set_value("technician")
        at.text_input[1].set_value("wrong_password")
        at.button[0].click().run()

    # One more attempt, this time with the CORRECT password — should
    # still be blocked, since the account is now rate-limited regardless
    # of whether the credentials are right.
    at.text_input[0].set_value("technician")
    at.text_input[1].set_value("technician123")
    at.button[0].click().run()

    assert at.exception.len == 0
    assert any("Too many failed login attempts" in e.value for e in at.error)
    assert "user" not in at.session_state


def test_rate_limiting_is_audit_logged(seeded_db):
    from src.auth.service import LOGIN_RATE_LIMIT_MAX_ATTEMPTS
    from src.audit.service import get_audit_log

    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at.run()

    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS + 1):
        at.text_input[0].set_value("technician")
        at.text_input[1].set_value("wrong_password")
        at.button[0].click().run()

    entries = get_audit_log()
    assert any(e.action == "login_rate_limited" for e in entries)


def test_successful_login_after_rate_limit_window_resets(seeded_db):
    """A correct login should always succeed when attempted BEFORE the
    rate limit kicks in (sanity check that the feature doesn't lock out
    legitimate logins under normal use)."""
    from src.auth.service import LOGIN_RATE_LIMIT_MAX_ATTEMPTS

    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at.run()

    # Fewer failures than the threshold should NOT block a subsequent
    # correct login.
    for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS - 1):
        at.text_input[0].set_value("technician")
        at.text_input[1].set_value("wrong_password")
        at.button[0].click().run()

    at.text_input[0].set_value("technician")
    at.text_input[1].set_value("technician123")
    at.button[0].click().run()

    assert "user" in at.session_state
    assert at.session_state["user"].username == "technician"


# ── Auth hardening: session expiry ──────────────────────────────────────────
def test_session_expires_after_idle_timeout(seeded_db):
    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    assert "user" in at.session_state

    # Simulate the idle timeout having elapsed by rewinding the recorded
    # last-activity timestamp, then trigger another page load.
    at.session_state["_last_activity_ts"] -= 31 * 60
    at.run()

    assert "user" not in at.session_state
    assert any("session expired" in w.value.lower() for w in at.warning)
    assert any("Sign in" in t.value for t in at.title)


def test_session_expiry_is_audit_logged(seeded_db):
    from src.audit.service import get_audit_log

    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    at.session_state["_last_activity_ts"] -= 31 * 60
    at.run()

    entries = get_audit_log()
    assert any(e.action == "session_expired" for e in entries)


def test_session_does_not_expire_within_timeout_window(seeded_db):
    """Activity within the timeout window should keep the session alive
    — a regression guard against an overly aggressive timeout."""
    at = AppTest.from_file("streamlit_app/app.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")

    # Simulate only 5 minutes of idle time (well under the 30 min default).
    at.session_state["_last_activity_ts"] -= 5 * 60
    at.run()

    assert "user" in at.session_state
    assert at.session_state["user"].username == "technician"


# ── Network Map: generic spanning-tree solver, end-to-end through the page ──
def test_network_map_seeds_and_solves_via_generic_solver(seeded_db):
    """The Network Map page should seed the demo network, solve it using
    the generic spanning-tree initial-flow construction (no pipe names
    hardcoded in the page itself), and render without error."""
    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/6_network_map.py")
    at.default_timeout = 15
    at = _login(at, "engineer", "engineer123")
    assert at.exception.len == 0

    seed_button = next(b for b in at.button if "Seed demo network" in b.label)
    seed_button.click().run()
    assert at.exception.len == 0
    assert not any("Could not construct" in e.value for e in at.error)

    # Per-node external-flow inputs should reflect the persisted demo
    # values (10 L/s source, -10 L/s demand) — confirming the page reads
    # real data rather than a page-local constant.
    flow_inputs = {ni.label: ni.value for ni in at.sidebar.number_input}
    assert any(v == pytest.approx(10.0) for v in flow_inputs.values())
    assert any(v == pytest.approx(-10.0) for v in flow_inputs.values())
    assert len(at.dataframe) == 1


def test_network_map_flags_imbalanced_external_flow(seeded_db):
    """Editing a node's external flow to break mass balance should be
    caught with a clear error, not silently fed into the solver."""
    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/6_network_map.py")
    at.default_timeout = 15
    at = _login(at, "engineer", "engineer123")
    seed_button = next(b for b in at.button if "Seed demo network" in b.label)
    seed_button.click().run()

    # Break balance: bump the source's supply without changing the demand.
    source_input = next(ni for ni in at.sidebar.number_input if ni.value == pytest.approx(10.0))
    source_input.set_value(15.0).run()

    assert at.exception.len == 0
    assert any("must balance to ~0" in e.value for e in at.error)


# ── Pipe Design: worked example renders correctly through the real page ────
def test_pipe_design_default_matches_readme_worked_example(seeded_db):
    """The page's defaults reproduce this project's README worked example.
    Compute the expected result via the same library function used by the
    page, then check the *rendered* metrics and warning match it — this
    catches UI-wiring bugs (wrong parameter, wrong field in wrong slot,
    stale formatting) that pipe_design.py's own unit tests can't, since
    those never touch the Streamlit layer at all."""
    from src.hydraulics.pipe_design import evaluate_pipe_design
    from src.utils.validation import check_pipe_design_margin

    expected = evaluate_pipe_design(
        design_pressure_psig=1480.0,
        outside_diameter_in=6.625,
        allowable_stress_psi=20000.0,
        corrosion_allowance_in=0.0625,
        selected_thickness_in=0.280,
    )
    expected_warning = check_pipe_design_margin(
        expected.derated_selected_thickness_in,
        expected.minimum_required_thickness_in,
        expected.thin_wall_assumption_valid,
    )

    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/10_pipe_design.py")
    at.default_timeout = 15
    at = _login(at, "technician", "technician123")
    assert at.exception.len == 0

    # Independently confirms the textbook value from the README/module
    # docstring, rendered through the real page rather than asserted
    # against the function directly.
    assert expected.pressure_design_thickness_in == pytest.approx(0.2381, abs=5e-5)

    metric_values = [m.value for m in at.metric]
    assert f"{expected.pressure_design_thickness_in:.4f} in" in metric_values
    assert f"{expected.minimum_required_thickness_in:.4f} in" in metric_values
    assert f"{expected.nominal_thickness_required_in:.4f} in" in metric_values

    # Schedule 40 (the page's default candidate) is undersized once the
    # corrosion allowance is applied — the interesting, documented result.
    assert expected.selected_thickness_adequate is False
    assert expected_warning is not None
    # st.error() promotes a leading emoji into the alert's icon rather
    # than keeping it in the text body, so .value omits it (confirmed by
    # inspecting the rendered value directly) — strip it the same way
    # before comparing.
    expected_warning_text = expected_warning.split(None, 1)[1]
    assert any(e.value == expected_warning_text for e in at.error)


def test_pipe_design_unchecking_candidate_hides_adequacy_verdict(seeded_db):
    """With the candidate-check box off, the page should show the three
    build-up metrics but render no adequacy verdict (nothing to grade)."""
    at = AppTest.from_file(f"{PROJECT_ROOT_PAGES}/10_pipe_design.py")
    at.default_timeout = 15
    at = _login(at, "engineer", "engineer123")

    checkbox = next(cb for cb in at.sidebar.checkbox if "Check a specific schedule" in cb.label)
    checkbox.set_value(False).run()

    assert at.exception.len == 0
    assert len(at.metric) == 3
    assert len(at.error) == 0
    assert len(at.warning) == 0
    assert len(at.success) == 0
