"""
Hydraulic Distribution Simulator — Streamlit app entry point.

Run with:  streamlit run streamlit_app/app.py
"""

import sys
from pathlib import Path

import streamlit as st

# Make the project's src/ package (and this dir's auth_helpers) importable
# when run as `streamlit run app.py` or loaded as a multipage app page.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from auth_helpers import require_login, render_user_badge

st.set_page_config(
    page_title="Hydraulic Distribution Simulator",
    page_icon="🚰",
    layout="wide",
)

user = require_login()
render_user_badge(user)

st.title("🚰 Hydraulic Distribution Simulator")
st.markdown(
    f"""
Welcome, **{user.full_name or user.username}**! This dashboard implements
the Darcy–Weisbach / Swamee–Jain pipe flow analysis (originally developed
for the Citra Srie Pradita housing estate distribution-pipe study) as a
reusable, config-driven engineering tool — now with role-based access
control, audit logging, and a geospatial network view.

You're signed in as a **{user.role.display_name}**.
{"You have full access: run ad-hoc scenarios, edit configuration, and review the audit log." if user.can_edit_config else "You have view access to all dashboards. Running ad-hoc scenarios and editing configuration requires the Lead Engineer role."}

**Use the sidebar pages to:**
- **Input** — set pipe geometry, flow rate, and fluid properties, then run a scenario *(Lead Engineer only)*
- **Compare** — view scenarios loaded straight from `configs/*.yaml`, side by side
- **Results** — view head loss, pump power, exergy destruction, pressure curve, and energy Sankey diagram
- **Lean Dashboard** — Muda (waste Pareto + ranking), Mura (utilization unevenness), and Muri (pump overburden) across all scenarios
- **Economics** — CAPEX vs. OPEX lifecycle cost comparison (factual present-value arithmetic, not financial advice)
- **Network Map** — the pipe network plotted on a real map, color-coded by hydraulic state
- **Pipe Design** — ASME B31.3 Eq. (3a) wall-thickness pressure design, with an optional adequacy check against a candidate schedule
- **Config Editor** — edit the YAML that drives every scenario *(Lead Engineer only)*
- **Audit Log** — who ran what, when *(Lead Engineer only)*
- **About** — background on the method and references

Built with Lean / Poka-Yoke input validation: implausible inputs (negative
flow, oversized diameters, roughness exceeding diameter, etc.) are caught
before any calculation runs.
"""
)

st.info("👈 Select **Input** from the sidebar to configure and run a scenario.")
