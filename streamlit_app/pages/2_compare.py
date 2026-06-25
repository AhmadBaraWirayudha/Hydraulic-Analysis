"""
Streamlit page: config-driven scenario comparison.

Loads configs/pipe_config.yaml + fluid_config.yaml + scenario_config.yaml
and runs every named scenario, with no hardcoded values in this page —
edit the YAML files to add/change scenarios.
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "streamlit_app"))

from auth_helpers import require_login, render_user_badge
from src.simulation.config_loader import load_pipeline
from src.plots.plot_efficiency import head_loss_comparison_figure

st.set_page_config(page_title="Compare — Hydraulic Simulator", page_icon="📐", layout="wide")

user = require_login()
render_user_badge(user)
st.title("📐 Config-Driven Scenario Comparison")
st.caption(
    "Scenarios below are loaded directly from `configs/pipe_config.yaml`, "
    "`configs/fluid_config.yaml`, and `configs/scenario_config.yaml` — "
    "edit those files to add or change scenarios, no code changes needed."
)

try:
    pipeline = load_pipeline(config_dir=str(PROJECT_ROOT / "configs"))
except ValueError as e:
    st.error(f"⚠️ Config error: {e}")
    st.stop()

summary = pipeline["summary"]
display_cols = [c for c in summary.columns if not c.endswith("_warning")]

st.subheader("Scenario Summary")
st.dataframe(
    summary[display_cols].style.format({
        "diameter_m": "{:.4f}",
        "flow_rate_m3s": "{:.5f}",
        "velocity_m_s": "{:.3f}",
        "reynolds": "{:,.0f}",
        "total_loss_m": "{:.4f}",
        "pressure_drop_Pa": "{:,.1f}",
        "shaft_power_W": "{:,.2f}",
        "exergy_destroyed_W": "{:.3f}",
    }),
    use_container_width=True,
    hide_index=True,
)

for _, row in summary.iterrows():
    if isinstance(row["velocity_warning"], str):
        st.warning(f"**{row['scenario']}**: {row['velocity_warning']}")
    if isinstance(row.get("pump_load_warning"), str):
        if "overloaded" in row["pump_load_warning"].lower():
            st.error(f"**{row['scenario']}**: {row['pump_load_warning']}")
        else:
            st.warning(f"**{row['scenario']}**: {row['pump_load_warning']}")
    if isinstance(row.get("npsh_warning"), str):
        if "cavitation" in row["npsh_warning"].lower():
            st.error(f"**{row['scenario']}**: {row['npsh_warning']}")
        else:
            st.warning(f"**{row['scenario']}**: {row['npsh_warning']}")

st.divider()

st.subheader("Head Loss by Scenario")
import plotly.graph_objects as go

fig = go.Figure()
fig.add_trace(go.Bar(x=summary["scenario"], y=summary["total_loss_m"], marker_color="#2ca02c"))
fig.update_layout(
    title="Total Head Loss by Scenario",
    xaxis_title="Scenario",
    yaxis_title="Head Loss (m)",
    template="plotly_white",
    margin=dict(l=40, r=20, t=50, b=40),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Sensitivity Sweeps (from `scenario_config.yaml`)")
from src.simulation.config_loader import run_sensitivity_from_config

base_scenario = list(pipeline["scenarios"].values())[0]
sweeps = run_sensitivity_from_config(base_scenario, pipeline["sensitivity_config"])

for param, df in sweeps.items():
    st.markdown(f"**Sweeping `{param}`**")
    st.plotly_chart(
        head_loss_comparison_figure(df, param, x_label=param),
        use_container_width=True,
    )
