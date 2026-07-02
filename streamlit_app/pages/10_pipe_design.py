"""
Streamlit page: ASME B31.3 pipe wall thickness (pressure design).

Eq. (3a) pressure design thickness, plus corrosion/mechanical allowances
and mill manufacturing under-tolerance, with an optional adequacy check
against a candidate schedule thickness. View-only (both roles) — like the
Economics page, this is a standalone calculator driven entirely by its
own sidebar inputs, not an action that mutates any shared/persisted
state, so it isn't restricted to Lead Engineer.
"""

import sys
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "streamlit_app"))

from auth_helpers import require_login, render_user_badge
from src.hydraulics.pipe_design import (
    evaluate_pipe_design,
    DEFAULT_Y_DUCTILE_STEEL,
    DEFAULT_MILL_UNDERTOLERANCE,
)
from src.utils.validation import check_pipe_design_margin

st.set_page_config(page_title="Pipe Design — Hydraulic Simulator", page_icon="🔧", layout="wide")

user = require_login()
render_user_badge(user)

st.title("🔧 Pipe Wall Thickness (ASME B31.3 Pressure Design)")
st.caption(
    "ASME B31.3 Eq. (3a) pressure design thickness for straight pipe "
    "under internal pressure, plus corrosion/mechanical allowances and "
    "mill manufacturing under-tolerance — valid in the thin-wall regime "
    "(t < D/6). Defaults below reproduce this project's README worked "
    "example: an NPS 6 (6.625\" OD) carbon steel pipe at 1480 psig, "
    "checking whether Schedule 40 (0.280\") still holds up once a "
    "realistic corrosion allowance is applied."
)

# ── Design conditions ──────────────────────────────────────────────────────
st.sidebar.header("Design Conditions")
design_pressure_psig = st.sidebar.number_input(
    "Design pressure (psig)", min_value=0.1, value=1480.0, step=10.0,
)
outside_diameter_in = st.sidebar.number_input(
    "Pipe outside diameter, D (in)", min_value=0.1, max_value=120.0,
    value=6.625, step=0.125, format="%.3f",
    help="NPS 6 Sch 40/80 OD = 6.625 in — the default here.",
)

# ── Material (ASME B31.3 Table A-1 / A-1B / 304.1.1) ──────────────────────
st.sidebar.header("Material")
allowable_stress_psi = st.sidebar.number_input(
    "Allowable stress, S (psi)", min_value=1.0, value=20000.0, step=500.0,
    help="ASME B31.3 Table A-1, at design temperature.",
)
quality_factor = st.sidebar.slider(
    "Quality factor, E", min_value=0.05, max_value=1.0, value=1.0, step=0.05,
    help="ASME B31.3 Table A-1B. 1.0 for seamless pipe; lower for some "
         "welded product forms.",
)
weld_strength_reduction_factor = st.sidebar.slider(
    "Weld strength reduction factor, W", min_value=0.05, max_value=1.0,
    value=1.0, step=0.05,
    help="Table 302.3.5. 1.0 below the elevated-temperature range where "
         "this factor applies — the common case for water/process "
         "distribution piping.",
)
coefficient_y = st.sidebar.number_input(
    "Coefficient Y", min_value=0.0, max_value=0.7,
    value=float(DEFAULT_Y_DUCTILE_STEEL), step=0.05,
    help="ASME B31.3 Table 304.1.1. 0.4 for ferritic/austenitic steel and "
         "most ductile metals ≤900°F (482°C) — covers the large majority "
         "of water/process distribution piping.",
)

# ── Allowances (para. 304.1.2(a): t_m = t + c) ─────────────────────────────
st.sidebar.header("Allowances")
corrosion_allowance_in = st.sidebar.number_input(
    "Corrosion/erosion allowance, c (in)", min_value=0.0, value=0.0625,
    step=0.01, format="%.4f",
)
mechanical_allowance_in = st.sidebar.number_input(
    "Mechanical (thread/groove) allowance (in)", min_value=0.0, value=0.0,
    step=0.01, format="%.4f",
)
mill_undertolerance_pct = st.sidebar.slider(
    "Mill manufacturing under-tolerance (%)", min_value=0.0, max_value=30.0,
    value=float(DEFAULT_MILL_UNDERTOLERANCE) * 100, step=0.5,
    help="12.5% is the commonly-cited figure for seamless pipe under "
         "product-form specs like API 5L. Set to 0 if your spec "
         "guarantees minimum (not nominal) wall.",
)
mill_undertolerance_fraction = mill_undertolerance_pct / 100.0

# ── Optional candidate schedule check ──────────────────────────────────────
with st.sidebar.expander("Check a candidate wall thickness", expanded=True):
    check_candidate = st.checkbox("Check a specific schedule", value=True)
    if check_candidate:
        selected_thickness_in = st.number_input(
            "Candidate wall thickness (in)", min_value=0.001, value=0.280,
            step=0.001, format="%.4f",
            help="E.g. 0.280 in for NPS 6 Schedule 40, 0.432 in for Schedule 80.",
        )
    else:
        selected_thickness_in = None

# ── Calculate + Poka-Yoke error handling ───────────────────────────────────
try:
    result = evaluate_pipe_design(
        design_pressure_psig=design_pressure_psig,
        outside_diameter_in=outside_diameter_in,
        allowable_stress_psi=allowable_stress_psi,
        quality_factor=quality_factor,
        weld_strength_reduction_factor=weld_strength_reduction_factor,
        coefficient_y=coefficient_y,
        corrosion_allowance_in=corrosion_allowance_in,
        mechanical_allowance_in=mechanical_allowance_in,
        mill_undertolerance_fraction=mill_undertolerance_fraction,
        selected_thickness_in=selected_thickness_in,
    )
except ValueError as e:
    st.error(f"⚠️ Input error: {e}")
    st.stop()

# ── Results ─────────────────────────────────────────────────────────────
st.subheader("Wall Thickness Build-Up")
col1, col2, col3 = st.columns(3)
col1.metric("Eq. (3a) pressure design, t", f"{result.pressure_design_thickness_in:.4f} in")
col2.metric("Min. required, t_m (+ allowances)", f"{result.minimum_required_thickness_in:.4f} in")
col3.metric("Nominal to order (+ mill tolerance)", f"{result.nominal_thickness_required_in:.4f} in")

warning = check_pipe_design_margin(
    result.derated_selected_thickness_in,
    result.minimum_required_thickness_in,
    result.thin_wall_assumption_valid,
)
if warning:
    if "undersized" in warning.lower() or "does not hold" in warning.lower():
        st.error(warning)
    else:
        st.warning(warning)
elif result.selected_thickness_in is not None:
    st.success(
        f"✅ Selected thickness ({result.selected_thickness_in:.4f} in) is adequate — "
        f"{result.derated_selected_thickness_in:.4f} in after mill under-tolerance, "
        f"a {result.margin_ratio:.2f}× margin over the "
        f"{result.minimum_required_thickness_in:.4f} in minimum required."
    )

st.divider()

# ── Build-up bar chart ─────────────────────────────────────────────────────
labels = [
    "Eq. (3a), bare<br>(pressure only)",
    "Min. required, t_m<br>(+ allowances)",
    "Nominal to order<br>(+ mill tolerance)",
]
values = [
    result.pressure_design_thickness_in,
    result.minimum_required_thickness_in,
    result.nominal_thickness_required_in,
]
colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

if result.selected_thickness_in is not None:
    labels += ["Selected<br>(as ordered)", "Selected, derated<br>(after mill tolerance)"]
    values += [result.selected_thickness_in, result.derated_selected_thickness_in]
    colors += ["#9467bd", "#2ca02c" if result.selected_thickness_adequate else "#d62728"]

fig = go.Figure(go.Bar(
    x=values, y=labels, orientation="h", marker_color=colors,
    text=[f"{v:.4f} in" for v in values], textposition="outside",
))
fig.update_layout(
    title="Wall Thickness Build-Up",
    xaxis_title="Thickness (in)",
    template="plotly_white",
    margin=dict(l=10, r=70, t=50, b=40),
    height=300 if result.selected_thickness_in is None else 380,
)
st.plotly_chart(fig, use_container_width=True)

if not result.thin_wall_assumption_valid:
    st.caption(
        "⚠️ t ≥ D/6 for this design — Eq. (3a)'s thin-wall assumption "
        "doesn't hold, so these figures should be treated as approximate "
        "only (see the warning above)."
    )
