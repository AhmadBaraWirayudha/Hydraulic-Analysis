"""
Hydraulic Distribution Simulator — Streamlit app entry point.

Run with:  streamlit run streamlit_app/app.py
"""

import sys
from pathlib import Path

import streamlit as st

# Make the project's src/ package importable when run as `streamlit run app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(
    page_title="Hydraulic Distribution Simulator",
    page_icon="🚰",
    layout="wide",
)

st.title("🚰 Hydraulic Distribution Simulator")
st.markdown(
    """
Welcome! This dashboard implements the Darcy–Weisbach / Swamee–Jain pipe
flow analysis (originally developed for the Citra Srie Pradita housing
estate distribution-pipe study) as a reusable, config-driven engineering
tool.

**Use the sidebar pages to:**
- **Input** — set pipe geometry, flow rate, and fluid properties, then run a scenario
- **Compare** — view scenarios loaded straight from `configs/*.yaml`, side by side
- **Results** — view head loss, pump power, exergy destruction, pressure curve, and energy Sankey diagram
- **Lean Dashboard** — Muda (waste Pareto + ranking), Mura (utilization unevenness), and Muri (pump overburden) across all scenarios
- **About** — background on the method and references

Built with Lean / Poka-Yoke input validation: implausible inputs (negative
flow, oversized diameters, roughness exceeding diameter, etc.) are caught
before any calculation runs.
"""
)

st.info("👈 Select **Input** from the sidebar to configure and run a scenario.")
