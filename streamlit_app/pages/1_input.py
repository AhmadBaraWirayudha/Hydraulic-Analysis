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
from src.hydraulics.fluid_properties import water_vapor_pressure

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
rated_power_input = st.sidebar.number_input(
    "Pump rated power (W), optional", min_value=0.0, value=0.0, step=10.0,
    help="Nameplate shaft power. Leave at 0 to skip the Muri (overburden) check."
)
rated_power_W = rated_power_input if rated_power_input > 0 else None

with st.sidebar.expander("⚙️ Advanced: NPSH (Cavitation) Check"):
    enable_npsh = st.checkbox("Enable NPSH check", value=False)
    if enable_npsh:
        suction_pressure_Pa = st.number_input(
            "Suction pressure (Pa)", min_value=1000.0, value=101325.0, step=100.0,
            help="Absolute pressure at the suction source surface — e.g. "
                 "atmospheric (101,325 Pa) for an open tank or reservoir.",
        )
        inlet_elevation_m = st.number_input(
            "Inlet elevation vs. pump centerline (m)", value=0.0, step=0.1,
            help="Positive = flooded suction (source above pump, favorable). "
                 "Negative = suction lift (source below pump).",
        )
        suction_head_loss_m = st.number_input(
            "Suction-side head loss (m)", min_value=0.0, value=0.0, step=0.1
        )
        npsh_required_input = st.number_input(
            "Pump's NPSHr (m), optional", min_value=0.0, value=0.0, step=0.1,
            help="From the pump's manufacturer curve. Leave at 0 to see NPSHa "
                 "without a margin comparison.",
        )
        npsh_required_m = npsh_required_input if npsh_required_input > 0 else None
        vapor_pressure_Pa = water_vapor_pressure(ambient_T)
        st.caption(f"Vapor pressure at {ambient_T - 273.15:.0f}°C ≈ {vapor_pressure_Pa:,.0f} Pa "
                   f"(derived via the Andrade/Antoine fluid-properties model)")
    else:
        suction_pressure_Pa = None
        vapor_pressure_Pa = None
        inlet_elevation_m = 0.0
        suction_head_loss_m = 0.0
        npsh_required_m = None

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
            rated_power_W=rated_power_W,
            suction_pressure_Pa=suction_pressure_Pa,
            vapor_pressure_Pa=vapor_pressure_Pa,
            inlet_elevation_m=inlet_elevation_m,
            suction_head_loss_m=suction_head_loss_m,
            npsh_required_m=npsh_required_m,
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
        if result.pump_load_warning:
            st.error(result.pump_load_warning) if "overloaded" in result.pump_load_warning.lower() \
                else st.warning(result.pump_load_warning)
        if result.npsh is not None:
            st.metric("NPSH Available", f"{result.npsh.npsh_available_m:.2f} m")
            if result.npsh_warning:
                st.error(result.npsh_warning) if "cavitation" in result.npsh_warning.lower() \
                    else st.warning(result.npsh_warning)

    except ValueError as e:
        # Poka-Yoke: surface validation failures as a clear, actionable message
        st.error(f"⚠️ Input error: {e}")
else:
    st.info("Configure parameters in the sidebar and click **Run Analysis** to begin.")
