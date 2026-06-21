"""
Unit tests for src/simulation/scenario.py — full scenario assembly,
including the static-head (useful lift) vs. friction-loss (destroyed
exergy) split.
"""

import pytest

from src.simulation.scenario import run_simulation, load_scenario_from_config
from src.utils.constants import WATER_DENSITY, GRAVITY


def test_run_simulation_basic_smoke():
    result = run_simulation(diameter_m=0.1016, flow_rate_m3s=0.0005, length_m=100.0)
    assert result.head_loss.velocity_m_s > 0
    assert result.pump.shaft_power_W > 0
    assert result.exergy.exergy_destruction_W >= 0


def test_pressure_drop_excludes_static_head():
    """Friction pressure_drop should be identical whether or not static head is added."""
    no_lift = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                              static_head_m=0.0)
    with_lift = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                                static_head_m=20.0)
    assert no_lift.pressure_drop == pytest.approx(with_lift.pressure_drop)
    assert no_lift.head_loss.total_loss_m == pytest.approx(with_lift.head_loss.total_loss_m)


def test_static_head_increases_total_head_and_shaft_power():
    no_lift = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                              static_head_m=0.0)
    with_lift = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                                static_head_m=20.0)
    assert with_lift.total_head_m == pytest.approx(no_lift.head_loss.total_loss_m + 20.0)
    assert with_lift.pump.shaft_power_W > no_lift.pump.shaft_power_W


def test_exergy_destroyed_unaffected_by_static_head():
    """Static lift is useful (reversible) work — it should not count as destroyed exergy."""
    no_lift = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                              static_head_m=0.0)
    with_lift = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                                static_head_m=20.0)
    assert with_lift.exergy.exergy_destruction_W == pytest.approx(
        no_lift.exergy.exergy_destruction_W
    )


def test_default_static_head_is_zero_and_hydraulic_power_equals_exergy_destroyed():
    """With no static lift, ALL hydraulic power is destroyed to friction (no useful work)."""
    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    assert result.scenario.static_head_m == 0.0
    assert result.pump.hydraulic_power_W == pytest.approx(
        result.exergy.exergy_destruction_W
    )


def test_static_head_creates_nonzero_useful_work_in_energy_balance():
    """With static lift, hydraulic power should exceed destroyed exergy (useful work > 0)."""
    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                             static_head_m=20.0)
    useful_work = result.pump.hydraulic_power_W - result.exergy.exergy_destruction_W
    assert useful_work > 0
    expected_useful = result.scenario.density * GRAVITY * result.scenario.flow_rate_m3s * 20.0
    assert useful_work == pytest.approx(expected_useful)


def test_run_simulation_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        run_simulation(diameter_m=-0.1, flow_rate_m3s=0.0005, length_m=100.0)
    with pytest.raises(ValueError):
        run_simulation(diameter_m=0.1, flow_rate_m3s=-0.0005, length_m=100.0)


def test_velocity_warning_present_for_very_low_flow():
    result = run_simulation(diameter_m=0.1016, flow_rate_m3s=0.0001, length_m=100.0)
    assert result.velocity_warning is not None


def test_velocity_warning_absent_for_reasonable_flow():
    # Chosen to land within the SNI 0.9-2.0 m/s window for a ~50mm pipe.
    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0025, length_m=100.0)
    assert 0.9 <= result.head_loss.velocity_m_s <= 2.0
    assert result.velocity_warning is None


def test_load_scenario_from_config_defaults():
    config = {"diameter_m": 0.1, "flow_rate_m3s": 0.0005}
    scenario = load_scenario_from_config(config)
    assert scenario.length_m == 100.0
    assert scenario.static_head_m == 0.0
    assert scenario.density == WATER_DENSITY


def test_load_scenario_from_config_overrides():
    config = {
        "diameter_m": 0.1, "flow_rate_m3s": 0.0005,
        "static_head_m": 15.0, "label": "test-scenario",
    }
    scenario = load_scenario_from_config(config)
    assert scenario.static_head_m == 15.0
    assert scenario.label == "test-scenario"


# ── rated_power_W / pump_load_warning (Muri / overburden) ─────────────────
def test_pump_load_warning_none_by_default():
    """No rated_power_W configured -> Muri check is skipped entirely."""
    result = run_simulation(diameter_m=0.0127, flow_rate_m3s=0.0005, length_m=100.0)
    assert result.scenario.rated_power_W is None
    assert result.pump_load_warning is None


def test_pump_load_warning_fires_when_overloaded():
    # 1/2 inch pipe at 0.5 L/s needs ~992 W shaft power; rate it well under that.
    result = run_simulation(diameter_m=0.0127, flow_rate_m3s=0.0005, length_m=100.0,
                             rated_power_W=500.0)
    assert result.pump_load_warning is not None
    assert "overloaded" in result.pump_load_warning.lower()


def test_pump_load_warning_absent_when_comfortably_under_rated():
    # 4 inch pipe needs <1 W shaft power; a 100 W rated pump is nowhere near loaded.
    result = run_simulation(diameter_m=0.1016, flow_rate_m3s=0.0005, length_m=100.0,
                             rated_power_W=100.0)
    assert result.pump_load_warning is None


def test_load_scenario_from_config_passes_through_rated_power_w():
    config = {"diameter_m": 0.1, "flow_rate_m3s": 0.0005, "rated_power_W": 50.0}
    scenario = load_scenario_from_config(config)
    assert scenario.rated_power_W == 50.0


# ── NPSH (cavitation) integration ──────────────────────────────────────────
def test_npsh_skipped_by_default():
    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    assert result.npsh is None
    assert result.npsh_warning is None


def test_npsh_skipped_if_only_one_of_suction_vapor_pressure_given():
    """Both suction_pressure_Pa AND vapor_pressure_Pa are required to run the check."""
    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                             suction_pressure_Pa=101325)
    assert result.npsh is None
    result2 = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
                              vapor_pressure_Pa=2339)
    assert result2.npsh is None


def test_npsh_computed_when_both_pressures_given():
    result = run_simulation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
        suction_pressure_Pa=101325, vapor_pressure_Pa=2339,
    )
    assert result.npsh is not None
    assert result.npsh.npsh_available_m > 0
    assert result.npsh_warning is None  # no npsh_required_m given -> no margin warning


def test_npsh_warning_fires_with_cavitation_risk_inputs():
    from src.hydraulics.fluid_properties import water_vapor_pressure

    pv_hot = water_vapor_pressure(363.15)  # 90 degC
    result = run_simulation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
        suction_pressure_Pa=101325, vapor_pressure_Pa=pv_hot,
        inlet_elevation_m=-2.0, suction_head_loss_m=1.0, npsh_required_m=4.0,
    )
    assert result.npsh_warning is not None
    assert "cavitation" in result.npsh_warning.lower()


def test_load_scenario_from_config_passes_through_npsh_fields():
    config = {
        "diameter_m": 0.1, "flow_rate_m3s": 0.0005,
        "suction_pressure_Pa": 101325.0, "vapor_pressure_Pa": 2339.0,
        "inlet_elevation_m": -1.5, "suction_head_loss_m": 0.3,
        "npsh_required_m": 3.0,
    }
    scenario = load_scenario_from_config(config)
    assert scenario.suction_pressure_Pa == 101325.0
    assert scenario.vapor_pressure_Pa == 2339.0
    assert scenario.inlet_elevation_m == -1.5
    assert scenario.suction_head_loss_m == 0.3
    assert scenario.npsh_required_m == 3.0
