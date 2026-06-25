"""
Streamlit page: geospatial pipe network view.

Plots the physical (lat/lon) layout of the pipe network stored in
PostGIS, color-coded by hydraulic velocity against the SNI 03-6481-2000
recommended range — the same Mura (unevenness) lens as the Lean
Dashboard, applied spatially rather than as an abstract bar chart.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "streamlit_app"))

from auth_helpers import require_login, render_user_badge
from src.audit.service import log_action
from src.geospatial.service import get_network_geometry, get_all_loops, seed_demo_network
from src.geospatial.map_view import build_network_map, _pipe_velocity
from src.hydraulics.network import PipeNetwork, NetworkPipe
from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY, SNI_VELOCITY_MIN, SNI_VELOCITY_MAX

st.set_page_config(page_title="Network Map — Hydraulic Simulator", page_icon="🗺️", layout="wide")

user = require_login()
render_user_badge(user)

st.title("🗺️ Network Map")
st.caption(
    "The pipe network's real physical layout, stored in PostGIS and "
    "color-coded by velocity against the SNI 03-6481-2000 recommended "
    "range (0.9–2.0 m/s) — blue is under-utilized, green is within range, "
    "red is over. The same Mura (unevenness) lens as the Lean Dashboard, "
    "applied spatially."
)

try:
    nodes, pipes = get_network_geometry()
except Exception as e:
    st.error(f"⚠️ Could not reach the geospatial database: {e}")
    st.info("Run `docker compose up` to start a PostGIS-enabled Postgres alongside the app.")
    st.stop()

if not nodes:
    st.warning("No network data yet.")
    if user.can_edit_config:
        st.caption(
            "Seeding loads the demo 4-node, 2-loop network used throughout "
            "this project's network-analysis examples, with real coordinates."
        )
        if st.button("Seed demo network", type="primary"):
            seed_demo_network()
            log_action(user.username, "seed_demo_network", {})
            st.rerun()
    else:
        st.info("Ask a Lead Engineer to set up the network — Field Technicians have view-only access.")
    st.stop()

loops = get_all_loops()

if not loops:
    st.warning(
        "Network geometry exists but no loop topology is defined — the "
        "Hardy Cross solver needs loop definitions to compute flow "
        "distribution. Showing node/pipe layout without flow data."
    )
    fmap = build_network_map(nodes, pipes, flows=None)
    st_folium(fmap, width=None, height=500, returned_objects=[])
    st.stop()

# ── Flow scenario controls ───────────────────────────────────────────────────
st.sidebar.header("Flow Scenario")
st.sidebar.caption(
    "Initial split is a simple heuristic for this demo's fixed topology "
    "(60/40 across the two paths from the source), not a general network "
    "solver — see docs/user_guide.md for arbitrary topologies."
)
total_flow_Ls = st.sidebar.number_input(
    "Total supply (L/s)", min_value=0.1, max_value=100.0, value=10.0, step=0.5
)

# This initial-flow heuristic is specific to the demo network's known
# topology (node "1" = source, node "4" = demand, two paths between them
# crossed by pipe "23") — NOT a generic continuity solver. A different
# network shape would need its own initial-guess construction.
pipe_names = {p.name for p in pipes}
demo_topology = {"12", "13", "23", "24", "34"} <= pipe_names
if demo_topology:
    total_m3s = total_flow_Ls / 1000.0
    initial_flows = {
        "12": total_m3s * 0.6, "13": total_m3s * 0.4, "23": 0.0,
        "24": total_m3s * 0.6, "34": total_m3s * 0.4,
    }
else:
    st.error(
        "This page's initial-flow heuristic only supports the demo "
        "network's exact pipe names (12, 13, 23, 24, 34). Extend "
        "`6_network_map.py` with your own continuity-satisfying initial "
        "guess for a different topology."
    )
    st.stop()

network_pipes = [
    NetworkPipe(p.name, p.start_node, p.end_node, p.diameter_m, p.length_m, p.roughness_m)
    for p in pipes
]
network = PipeNetwork(network_pipes, loops, density=WATER_DENSITY, viscosity=WATER_VISCOSITY)
solution = network.solve(initial_flows)

if not solution.converged:
    st.warning(f"Hardy Cross solve did not converge within {solution.iterations} iterations.")

# ── Map ───────────────────────────────────────────────────────────────────────
fmap = build_network_map(nodes, pipes, flows=solution.flows)
st_folium(fmap, width=None, height=500, returned_objects=[])

st.divider()

# ── Table ───────────────────────────────────────────────────────────────────
st.subheader("Pipe Hydraulic State")
rows = []
for p in pipes:
    v = _pipe_velocity(p, solution.flows.get(p.name))
    status = "Under" if v < SNI_VELOCITY_MIN else ("Over" if v > SNI_VELOCITY_MAX else "In range")
    rows.append({
        "pipe": p.name, "diameter_mm": p.diameter_m * 1000, "length_m": p.length_m,
        "flow_Ls": solution.flows.get(p.name, 0.0) * 1000, "velocity_m_s": v, "status": status,
    })
df = pd.DataFrame(rows)
st.dataframe(
    df.style.format({
        "diameter_mm": "{:.1f}", "length_m": "{:.1f}",
        "flow_Ls": "{:.3f}", "velocity_m_s": "{:.3f}",
    }),
    use_container_width=True, hide_index=True,
)

if user.can_edit_config:
    with st.expander("⚙️ Re-seed demo network (Lead Engineer)"):
        st.caption("Resets all network nodes, pipes, and loops back to the demo topology.")
        if st.button("Re-seed now"):
            seed_demo_network()
            log_action(user.username, "seed_demo_network", {})
            st.rerun()
