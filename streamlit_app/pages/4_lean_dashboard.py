"""
Streamlit page: Lean Six Sigma 3M dashboard (Muda / Mura / Muri).

Loads the config-driven pipeline and surfaces:
  - Muda (waste):       Pareto chart of head-loss sources + exergy waste ranking
  - Mura (unevenness):  pipe-velocity utilization heatmap across scenarios
  - Muri (overburden):  pump load vs. rated capacity, per scenario

This complements the per-scenario Sankey view on the Results page by
comparing *across* scenarios — the cross-scenario view is what makes
Mura (unevenness) visible in the first place.
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.simulation.config_loader import load_pipeline
from src.plots.pareto import pareto_loss_figure, utilization_heatmap_figure, waste_ranking_figure

st.set_page_config(page_title="Lean Dashboard — Hydraulic Simulator", page_icon="🎯", layout="wide")
st.title("🎯 Lean Dashboard: Muda / Mura / Muri")
st.caption(
    "Scenarios loaded from `configs/*.yaml`. This page applies the three "
    "Lean Six Sigma waste lenses across all configured scenarios at once."
)

try:
    pipeline = load_pipeline(config_dir=str(PROJECT_ROOT / "configs"))
except ValueError as e:
    st.error(f"⚠️ Config error: {e}")
    st.stop()

results = pipeline["results"]
summary = pipeline["summary"]

# ── Muri: overburden alerts ──────────────────────────────────────────────────
st.subheader("🔴 Muri — Pump Overburden")
st.caption(
    "Compares required pump shaft power against each scenario's configured "
    "`rated_power_W` (set per-scenario in `scenario_config.yaml`; omit it to "
    "skip this check)."
)
any_muri = False
for name, r in results.items():
    if r.scenario.rated_power_W is None:
        st.info(f"**{name}**: no `rated_power_W` configured — Muri check skipped.")
        continue
    load_pct = r.pump.shaft_power_W / r.scenario.rated_power_W * 100
    cols = st.columns([1, 2])
    cols[0].metric(f"{name}", f"{load_pct:.0f}% of rated", 
                    delta=f"{r.pump.shaft_power_W:.2f} W / {r.scenario.rated_power_W:.2f} W")
    if r.pump_load_warning:
        any_muri = True
        cols[1].error(r.pump_load_warning) if "overloaded" in r.pump_load_warning.lower() \
            else cols[1].warning(r.pump_load_warning)
    else:
        cols[1].success("Within safe operating margin (<80% of rated capacity).")
if not any_muri:
    st.caption("No scenarios are currently overburdened.")

st.divider()

# ── Mura: utilization unevenness across scenarios ───────────────────────────
st.subheader("🌊 Mura — Utilization Unevenness")
st.caption(
    "Velocity as % of the SNI 03-6481-2000 maximum (2.0 m/s), across all "
    "scenarios side by side. Cold = under-utilized (sedimentation risk), "
    "hot = over-utilized (water-hammer risk)."
)
st.plotly_chart(utilization_heatmap_figure(summary), use_container_width=True)
for _, row in summary.iterrows():
    if row["velocity_warning"]:
        st.warning(f"**{row['scenario']}**: {row['velocity_warning']}")

st.divider()

# ── Muda: waste ranking + Pareto breakdown ───────────────────────────────────
st.subheader("🗑️ Muda — Waste Ranking")
st.caption("Exergy destroyed to friction, ranked across scenarios (log scale).")
st.plotly_chart(waste_ranking_figure(summary), use_container_width=True)

st.markdown("**Pareto breakdown for a selected scenario:**")
scenario_names = list(results.keys())
selected = st.selectbox("Scenario", scenario_names)
st.plotly_chart(pareto_loss_figure(results[selected].head_loss), use_container_width=True)
st.caption(
    "Identifies which loss source — friction or a specific fitting — "
    "dominates the total head loss for the selected scenario, so "
    "improvement effort targets the largest contributor first."
)
