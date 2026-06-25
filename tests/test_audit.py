"""
Unit tests for src/audit/ — recording and querying audit log entries.
"""

from src.audit.service import log_action, get_audit_log


def test_log_action_creates_retrievable_entry(clean_schema):
    log_action("alice", "run_scenario", {"diameter_m": 0.1016, "flow_rate_m3s": 0.0005})
    entries = get_audit_log()
    assert len(entries) == 1
    assert entries[0].username == "alice"
    assert entries[0].action == "run_scenario"
    assert entries[0].details["diameter_m"] == 0.1016


def test_log_action_with_no_details_stores_empty_dict(clean_schema):
    log_action("bob", "login")
    entries = get_audit_log()
    assert entries[0].details == {}


def test_get_audit_log_orders_most_recent_first(clean_schema):
    log_action("alice", "action_1")
    log_action("alice", "action_2")
    log_action("alice", "action_3")
    entries = get_audit_log()
    assert [e.action for e in entries] == ["action_3", "action_2", "action_1"]


def test_get_audit_log_respects_limit(clean_schema):
    for i in range(10):
        log_action("alice", f"action_{i}")
    entries = get_audit_log(limit=3)
    assert len(entries) == 3


def test_get_audit_log_filters_by_username(clean_schema):
    log_action("alice", "alice_action")
    log_action("bob", "bob_action")
    log_action("alice", "alice_action_2")

    alice_entries = get_audit_log(username="alice")
    assert len(alice_entries) == 2
    assert all(e.username == "alice" for e in alice_entries)

    bob_entries = get_audit_log(username="bob")
    assert len(bob_entries) == 1


def test_log_action_preserves_nested_details(clean_schema):
    """Config-edit-style audit entries with old/new value pairs should
    round-trip through JSONB intact."""
    details = {
        "file": "scenario_config.yaml",
        "field": "discount_rate",
        "old_value": 0.07,
        "new_value": 0.08,
    }
    log_action("engineer", "edit_config", details)
    entries = get_audit_log()
    assert entries[0].details == details


def test_get_audit_log_empty_when_no_entries(clean_schema):
    assert get_audit_log() == []
