"""
Streamlit page: financial dashboard (Lifecycle Cost Analysis).

Translates the hydraulic comparison into CAPEX vs. OPEX trade-offs across
the lifecycle — the kind of view a management/financial stakeholder needs
to weigh upfront pipe cost against years of electricity to overcome
friction. This page performs factual present-value arithmetic only; it is
not financial advice, and every cost input is explicitly adjustable since
none of the defaults represent real market prices.
"""

import sys
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "streamlit_app"))

from auth_helpers import require_login, render_user_badge
from src.simulation.config_loader import load_pipeline, load_economics_config
from src.economics.scenario_economics import (
    compare_lifecycle_costs,
)

st.set_page_config(page_title="Economics — Hydraulic Simulator", page_icon="💰", layout="wide")

user = require_login()
render_user_badge(user)

st.title("💰 Lifecycle Cost Analysis (LCCA)")
st.caption(
    "Compares pipe/pump CAPEX against the present value of electricity "
    "OPEX over the analysis horizon. This page computes factual "
    "present-value arithmetic only — it is not financial advice, and the "
    "cost inputs below are illustrative placeholders, not real market "
    "prices. Replace them with your own quotes and tariffs."
)

try:
    pipeline = load_pipeline(config_dir=str(PROJECT_ROOT / "configs"))
    default_econ = load_economics_config(config_dir=str(PROJECT_ROOT / "configs"))
except ValueError as e:
    st.error(f"⚠️ Config error: {e}")
    st.stop()

results = pipeline["results"]

# ── Adjustable economic assumptions ──────────────────────────────────────────
st.sidebar.header("Economic Assumptions")
st.sidebar.caption("Defaults loaded from `configs/economics_config.yaml` — adjust freely.")

operating_hours = st.sidebar.number_input(
    "Operating hours/year", min_value=0, max_value=8760,
    value=int(default_econ["operating_hours_per_year"]), step=100,
)
electricity_price = st.sidebar.number_input(
    "Electricity price ($/kWh)", min_value=0.0,
    value=float(default_econ["electricity_price_per_kWh"]), step=0.01, format="%.3f",
)
years = st.sidebar.number_input(
    "Analysis horizon (years)", min_value=1, max_value=50,
    value=int(default_econ["years"]), step=1,
)
discount_rate_pct = st.sidebar.slider(
    "Discount rate (%)", min_value=0.0, max_value=20.0,
    value=float(default_econ["discount_rate"]) * 100, step=0.5, format="%.1f",
)
discount_rate = discount_rate_pct / 100.0
opex_escalation_pct = st.sidebar.slider(
    "OPEX escalation rate (%)", min_value=0.0, max_value=10.0,
    value=float(default_econ.get("opex_escalation_rate", 0.0)) * 100, step=0.5, format="%.1f",
)
opex_escalation = opex_escalation_pct / 100.0

st.sidebar.divider()
st.sidebar.subheader("Pipe Cost Curve ($/m by diameter)")
st.sidebar.caption("From `economics_config.yaml::pipe_cost_curve`")
for d, cost in default_econ["pipe_cost_curve"]:
    st.sidebar.text(f"  {d*1000:.1f} mm → ${cost:.2f}/m")

# Build a live econ_config dict reflecting the sidebar overrides, keeping
# the pipe_cost_curve from the file (editing that curve in the UI directly
# is out of scope for this page — edit the YAML for that).
live_econ_config = {
    **default_econ,
    "operating_hours_per_year": operating_hours,
    "electricity_price_per_kWh": electricity_price,
    "years": years,
    "discount_rate": discount_rate,
    "opex_escalation_rate": opex_escalation,
}

# ── Comparison table ──────────────────────────────────────────────────────────
df = compare_lifecycle_costs(results, econ_config=live_econ_config)

st.subheader("Lifecycle Cost Comparison")
st.dataframe(
    df.style.format({
        "diameter_mm": "{:.1f}",
        "unit_cost_per_m": "${:.2f}",
        "capex": "${:,.2f}",
        "annual_opex_year1": "${:,.2f}",
        "present_value_opex": "${:,.2f}",
        "total_lifecycle_cost": "${:,.2f}",
    }),
    use_container_width=True,
    hide_index=True,
)

cheapest = df.loc[df["total_lifecycle_cost"].idxmin(), "scenario"]
st.info(f"Lowest total lifecycle cost over {years} years: **{cheapest}** "
        f"(at the assumptions set in the sidebar).")

st.divider()

# ── CAPEX vs. OPEX stacked bar ────────────────────────────────────────────────
st.subheader("CAPEX vs. Present Value of OPEX")
fig = go.Figure()
fig.add_trace(go.Bar(x=df["scenario"], y=df["capex"], name="CAPEX", marker_color="#1f77b4"))
fig.add_trace(go.Bar(x=df["scenario"], y=df["present_value_opex"], name="PV of OPEX",
                       marker_color="#d62728"))
fig.update_layout(
    barmode="stack",
    title="Total Lifecycle Cost Breakdown",
    yaxis_title="Cost ($)",
    template="plotly_white",
    margin=dict(l=40, r=20, t=50, b=40),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Break-even analysis ──────────────────────────────────────────────────────
st.subheader("Break-Even: When Does the Larger Pipe Pay Back Its Extra CAPEX?")
if len(df) >= 2:
    sorted_df = df.sort_values("capex")
    cheap_capex_row = sorted_df.iloc[0]
    expensive_capex_row = sorted_df.iloc[-1]

    capex_diff = expensive_capex_row["capex"] - cheap_capex_row["capex"]
    annual_opex_savings = (
        cheap_capex_row["annual_opex_year1"] - expensive_capex_row["annual_opex_year1"]
    )

    if annual_opex_savings > 0:
        simple_payback_years = capex_diff / annual_opex_savings
        st.metric(
            f"Simple payback: {expensive_capex_row['scenario']} vs. {cheap_capex_row['scenario']}",
            f"{simple_payback_years:.2f} years",
        )
        st.caption(
            f"Extra upfront cost (${capex_diff:,.2f}) ÷ annual OPEX savings "
            f"(${annual_opex_savings:,.2f}/year) — a simple (undiscounted) "
            f"payback estimate, shown alongside the full discounted "
            f"lifecycle comparison above."
        )
    else:
        st.caption("The higher-CAPEX option does not have lower annual OPEX here — no payback to compute.")
