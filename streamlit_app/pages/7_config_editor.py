"""
Streamlit page: edit the YAML configuration files that drive every
scenario, cost assumption, and Monte Carlo/sensitivity setting.

Restricted to the Lead Engineer role — this is exactly the "authority to
modify YAML configurations" the RBAC model reserves for that role. Every
save is validated (must parse as YAML) and logged field-by-field to the
audit log, so exactly what changed is always reconstructable later.
"""

import sys
from pathlib import Path

import streamlit as st
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "streamlit_app"))

from auth_helpers import require_login, require_role, render_user_badge
from src.auth.models import Role
from src.audit.service import log_action
from src.utils.yaml_diff import diff_dicts

st.set_page_config(page_title="Config Editor — Hydraulic Simulator", page_icon="📝", layout="wide")

user = require_login()
require_role(user, Role.LEAD_ENGINEER, "the Config Editor")
render_user_badge(user)

st.title("📝 Configuration Editor")
st.caption(
    "Edits to these files take effect on every page that reads "
    "`configs/*.yaml` — Compare, Lean Dashboard, Economics, Network Map. "
    "Every save is validated and logged field-by-field to the audit log."
)
st.info(
    "📌 **Persistence depends on deployment**: this writes directly to "
    "the `configs/` files on disk. With `docker compose up` (which "
    "volume-mounts `configs/`), changes persist on the host. On an "
    "ephemeral container deployment (no volume mount), changes are lost "
    "on restart — they won't survive a redeploy. See DEPLOYMENT.md.",
    icon="📌",
)

CONFIG_DIR = PROJECT_ROOT / "configs"
CONFIG_FILES = [
    "pipe_config.yaml", "fluid_config.yaml", "scenario_config.yaml", "economics_config.yaml",
]

selected_file = st.selectbox("File to edit", CONFIG_FILES)
file_path = CONFIG_DIR / selected_file

if not file_path.exists():
    st.error(f"File not found: {file_path}")
    st.stop()

original_text = file_path.read_text()

if st.session_state.get("_config_editor_file") != selected_file:
    # Switched files — reset the editor buffer to the file's current contents.
    st.session_state["_config_editor_text"] = original_text
    st.session_state["_config_editor_file"] = selected_file

edited_text = st.text_area(
    f"Editing `{selected_file}`", value=st.session_state["_config_editor_text"],
    height=500, key="_config_editor_textarea",
)

col1, col2 = st.columns([1, 4])
with col1:
    save_clicked = st.button("💾 Save", type="primary")
with col2:
    preview_clicked = st.button("🔍 Preview changes")

if preview_clicked or save_clicked:
    try:
        new_parsed = yaml.safe_load(edited_text)
        old_parsed = yaml.safe_load(original_text)
    except yaml.YAMLError as e:
        st.error(f"⚠️ Invalid YAML — not saved: {e}")
        st.stop()

    changes = diff_dicts(old_parsed or {}, new_parsed or {})

    if not changes:
        st.info("No changes detected.")
    else:
        st.subheader(f"{len(changes)} field(s) changed")
        for c in changes:
            st.markdown(f"- **{c['field']}**: `{c['old_value']}` → `{c['new_value']}`")

    if save_clicked:
        if changes:
            file_path.write_text(edited_text)
            log_action(user.username, "edit_config", {
                "file": selected_file,
                "changes": changes,
            })
            st.session_state["_config_editor_text"] = edited_text
            st.success(f"✅ Saved {len(changes)} change(s) to `{selected_file}` and logged to the audit trail.")
        else:
            st.info("Nothing to save — no changes detected.")
