"""
Streamlit page: audit log viewer.

"Decisions must be traceable" — this page lets a Lead Engineer review
exactly who ran what scenario, edited what configuration field, and when.
Restricted to Lead Engineer: oversight of the audit trail is itself a
governance responsibility, not a general-access view.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "streamlit_app"))

from auth_helpers import require_login, require_role, render_user_badge
from src.auth.models import Role
from src.audit.service import get_audit_log

st.set_page_config(page_title="Audit Log — Hydraulic Simulator", page_icon="🗂️", layout="wide")

user = require_login()
require_role(user, Role.LEAD_ENGINEER, "the Audit Log")
render_user_badge(user)

st.title("🗂️ Audit Log")
st.caption("Every scenario run, configuration edit, and login is recorded here — who, when, and exactly what changed.")

col1, col2 = st.columns([2, 1])
with col1:
    username_filter = st.text_input("Filter by username (leave blank for everyone)")
with col2:
    limit = st.number_input("Max entries", min_value=10, max_value=1000, value=100, step=10)

try:
    entries = get_audit_log(limit=limit, username=username_filter or None)
except Exception as e:
    st.error(f"⚠️ Could not reach the database: {e}")
    st.stop()

if not entries:
    st.info("No audit log entries yet.")
    st.stop()

action_counts = pd.Series([e.action for e in entries]).value_counts()
cols = st.columns(min(len(action_counts), 5))
for i, (action, count) in enumerate(action_counts.items()):
    cols[i % len(cols)].metric(action, count)

st.divider()

for entry in entries:
    icon = {
        "run_scenario": "▶️", "edit_config": "📝", "login": "🔓",
        "login_failed": "⚠️", "logout": "🔒", "seed_demo_network": "🗺️",
    }.get(entry.action, "•")

    with st.expander(
        f"{icon} **{entry.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}** "
        f"— {entry.username} — {entry.action}"
    ):
        if entry.action == "edit_config" and "changes" in entry.details:
            st.markdown(f"**File**: `{entry.details.get('file', '?')}`")
            for c in entry.details["changes"]:
                st.markdown(f"- **{c['field']}**: `{c['old_value']}` → `{c['new_value']}`")
        elif entry.details:
            st.json(entry.details)
        else:
            st.caption("(no additional details)")
