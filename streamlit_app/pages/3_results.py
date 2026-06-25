"""
Streamlit page: display results from the most recent simulation run
(set in st.session_state by the Input page).
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth_helpers import require_login, render_user_badge
from src.plots.sankey import energy_flow_sankey

st.set_page_config(page_title="Results — Hydraulic Simulator", page_icon="📊", layout="wide")

user = require_login()
render_user_badge(user)

st.title("📊 Simulation Results")

result = st.session_state.get("scenario_result")

if result is None:
    st.warning("No simulation has been run yet. Go to the **Input** page first.")
    st.stop()

s = result.scenario
st.caption(f"Scenario: **{s.label or 'Unnamed'}** — D = {s.diameter_m*1000:.1f} mm, "
           f"L = {s.length_m:.0f} m, Q = {s.flow_rate_m3s*1000:.3f} L/s")

# ── Key metrics ───────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Pressure Drop", f"{result.pressure_drop:,.1f} Pa")
col2.metric("Total Head Loss", f"{result.head_loss.total_loss_m:.3f} m")
col3.metric("Pump Shaft Power", f"{result.pump.shaft_power_W:,.1f} W")
col4.metric("Overall Efficiency", f"{result.efficiency*100:.1f} %")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Velocity", f"{result.head_loss.velocity_m_s:.3f} m/s")
col6.metric("Reynolds Number", f"{result.head_loss.reynolds:,.0f}")
col7.metric("Friction Factor (f)", f"{result.head_loss.friction_factor:.4f}")
col8.metric("Exergy Destroyed", f"{result.exergy.exergy_destruction_W:.2f} W")

if result.velocity_warning:
    st.warning(result.velocity_warning)
if result.pump_load_warning:
    if "overloaded" in result.pump_load_warning.lower():
        st.error(result.pump_load_warning)
    else:
        st.warning(result.pump_load_warning)

st.divider()

# ── Head loss breakdown ──────────────────────────────────────────────────────
st.subheader("Head Loss Breakdown")
bc1, bc2, bc3 = st.columns(3)
bc1.metric("Major (friction) loss", f"{result.head_loss.major_loss_m:.3f} m")
bc2.metric("Minor (fittings) loss", f"{result.head_loss.minor_loss_m:.3f} m")
bc3.metric("Static lift / delivery head", f"{s.static_head_m:.3f} m")
st.caption(f"Total head supplied by pump: **{result.total_head_m:.3f} m** "
           f"(friction + minor losses + static lift)")
if result.head_loss.fittings:
    st.dataframe(
        {"Fitting": list(result.head_loss.fittings.keys()),
         "Head Loss (m)": [f"{v:.4f}" for v in result.head_loss.fittings.values()]},
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ── NPSH (cavitation) ─────────────────────────────────────────────────────────
if result.npsh is not None:
    st.subheader("NPSH (Cavitation Check)")
    nc1, nc2, nc3 = st.columns(3)
    nc1.metric("NPSH Available", f"{result.npsh.npsh_available_m:.2f} m")
    if result.npsh.npsh_required_m is not None:
        nc2.metric("NPSH Required", f"{result.npsh.npsh_required_m:.2f} m")
        nc3.metric("Margin", f"{result.npsh.margin_ratio*100:.0f}%",
                   delta=f"{result.npsh.margin_m:+.2f} m")
    if result.npsh_warning:
        if "cavitation" in result.npsh_warning.lower():
            st.error(result.npsh_warning)
        else:
            st.warning(result.npsh_warning)
    elif result.npsh.npsh_required_m is not None:
        st.success("Comfortable NPSH margin (≥20% above required).")
    st.divider()

# ── Pressure curve ────────────────────────────────────────────────────────────
st.subheader("Pressure vs. Distance")
st.plotly_chart(result.pressure_curve(), use_container_width=True)

st.divider()

# ── Energy Sankey ─────────────────────────────────────────────────────────────
st.subheader("Energy Flow (Lean: Muda / Waste View)")
st.plotly_chart(energy_flow_sankey(result), use_container_width=True)
st.caption(
    "Exergy destroyed represents irrecoverable work potential lost to friction — "
    "this is the *Muda* (waste) signal for the Lean dashboard."
)
