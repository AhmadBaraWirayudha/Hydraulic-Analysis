"""
Streamlit page: parameter input + run simulation.

Stores the resulting ScenarioResult in st.session_state for the Results page.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.simulation.scenario import run_simulation
from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY, PVC_ROUGHNESS, STEEL_ROUGHNESS

st.set_page_config(page_title="Input — Hydraulic Simulator", page_icon="🧮", layout="wide")
st.title("Hydraulic Distribution Simulator")
st.caption("Set parameters in the sidebar, then click **Run Analysis**.")

# ── Sidebar inputs ────────────────────────────────────────────────────────────
st.sidebar.header("Pipe Geometry")
diameter_mm = st.sidebar.number_input(
    "Pipe diameter (mm)", min_value=5.0, max_value=500.0, value=100.0, step=1.0
)
length_m = st.sidebar.number_input(
    "Pipe length (m)", min_value=1.0, max_value=10_000.0, value=100.0, step=10.0
)
material = st.sidebar.selectbox("Pipe material", ["PVC", "Steel"])
roughness_m = PVC_ROUGHNESS if material == "PVC" else STEEL_ROUGHNESS

st.sidebar.header("Flow")
flow_rate_Ls = st.sidebar.number_input(
    "Flow rate (L/s)", min_value=0.01, max_value=500.0, value=0.5, step=0.1
)

st.sidebar.header("Static Lift / Delivery Head")
static_head_m = st.sidebar.number_input(
    "Elevation gain or required delivery head (m)",
    min_value=0.0, max_value=200.0, value=0.0, step=1.0,
    help="Useful (non-destroyed) head the pump must also supply on top of "
         "friction losses — e.g. a water tower's height, or a minimum "
         "required tap pressure expressed as head. Leave at 0 for a pure "
         "friction-loss analysis.",
)

st.sidebar.header("Fluid (Water)")
temp_choice = st.sidebar.selectbox("Water temperature", ["25 °C (default)", "15 °C (cooler)"])
if temp_choice.startswith("25"):
    density, viscosity, ambient_T = WATER_DENSITY, WATER_VISCOSITY, 298.15
else:
    density, viscosity, ambient_T = 999.1, 1.139e-3, 288.15

st.sidebar.header("Fittings")
n_elbows = st.sidebar.number_input("90° elbows (standard)", min_value=0, max_value=50, value=4)
n_gate_valves = st.sidebar.number_input("Gate valves (open)", min_value=0, max_value=20, value=1)

st.sidebar.header("Pump / Motor")
eta_pump = st.sidebar.slider("Pump efficiency (η_pump)", 0.1, 1.0, 0.75, 0.01)
eta_motor = st.sidebar.slider("Motor efficiency (η_motor)", 0.1, 1.0, 0.90, 0.01)

run_clicked = st.sidebar.button("▶️ Run Analysis", type="primary")

# ── Run + Poka-Yoke error handling ───────────────────────────────────────────
if run_clicked:
    try:
        result = run_simulation(
            diameter_m=diameter_mm / 1000.0,
            flow_rate_m3s=flow_rate_Ls / 1000.0,
            length_m=length_m,
            roughness_m=roughness_m,
            density=density,
            viscosity=viscosity,
            fittings={
                "elbow_90_standard": n_elbows,
                "gate_valve_open": n_gate_valves,
            },
            static_head_m=static_head_m,
            eta_pump=eta_pump,
            eta_motor=eta_motor,
            ambient_temp_K=ambient_T,
            label=f"{diameter_mm:.0f} mm {material}",
        )
        st.session_state["scenario_result"] = result
        st.success("✅ Simulation complete. See the **Results** page in the sidebar.")

        col1, col2, col3 = st.columns(3)
        col1.metric("Pressure Drop", f"{result.pressure_drop:,.1f} Pa")
        col2.metric("Velocity", f"{result.head_loss.velocity_m_s:.2f} m/s")
        col3.metric("Pump Shaft Power", f"{result.pump.shaft_power_W:,.1f} W")

        if result.velocity_warning:
            st.warning(result.velocity_warning)

    except ValueError as e:
        # Poka-Yoke: surface validation failures as a clear, actionable message
        st.error(f"⚠️ Input error: {e}")
else:
    st.info("Configure parameters in the sidebar and click **Run Analysis** to begin.")
