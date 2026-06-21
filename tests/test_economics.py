"""
Unit tests for src/economics/lcca.py and scenario_economics.py — lifecycle
cost analysis (CAPEX/OPEX, present value of cost streams).
"""

import pytest

from src.economics.lcca import (
    interpolate_cost_curve, pipe_capex, annual_energy_cost,
    evaluate_lifecycle_cost, LCCAResult,
)
from src.economics.scenario_economics import (
    EconomicAssumptions, evaluate_scenario_lifecycle_cost, compare_lifecycle_costs,
)
from src.simulation.scenario import run_simulation


# ── interpolate_cost_curve ──────────────────────────────────────────────────
def test_interpolate_cost_curve_exact_points():
    curve = [(0.01, 5.0), (0.05, 12.0), (0.10, 28.0)]
    assert interpolate_cost_curve(0.01, curve) == pytest.approx(5.0)
    assert interpolate_cost_curve(0.10, curve) == pytest.approx(28.0)


def test_interpolate_cost_curve_midpoint():
    curve = [(0.0, 10.0), (10.0, 20.0)]
    assert interpolate_cost_curve(5.0, curve) == pytest.approx(15.0)


def test_interpolate_cost_curve_clamps_outside_range():
    curve = [(0.01, 5.0), (0.10, 28.0)]
    assert interpolate_cost_curve(-1.0, curve) == pytest.approx(5.0)
    assert interpolate_cost_curve(1.0, curve) == pytest.approx(28.0)


def test_interpolate_cost_curve_rejects_too_few_points():
    with pytest.raises(ValueError):
        interpolate_cost_curve(0.05, [(0.01, 5.0)])


def test_interpolate_cost_curve_rejects_unsorted():
    with pytest.raises(ValueError):
        interpolate_cost_curve(0.05, [(0.10, 28.0), (0.01, 5.0)])


# ── pipe_capex ──────────────────────────────────────────────────────────────
def test_pipe_capex_known_value():
    assert pipe_capex(length_m=100.0, unit_cost_per_m=15.0) == pytest.approx(1500.0)


def test_pipe_capex_rejects_negative_inputs():
    with pytest.raises(ValueError):
        pipe_capex(-10.0, 15.0)
    with pytest.raises(ValueError):
        pipe_capex(100.0, -15.0)


# ── annual_energy_cost ───────────────────────────────────────────────────────
def test_annual_energy_cost_known_value():
    # 1000 W = 1 kW; 8760 h/year continuous; $0.15/kWh
    cost = annual_energy_cost(1000.0, 8760, 0.15)
    assert cost == pytest.approx(1 * 8760 * 0.15)


def test_annual_energy_cost_zero_power_is_zero():
    assert annual_energy_cost(0.0, 8760, 0.15) == 0.0


def test_annual_energy_cost_rejects_invalid_hours():
    with pytest.raises(ValueError):
        annual_energy_cost(1000.0, -1, 0.15)
    with pytest.raises(ValueError):
        annual_energy_cost(1000.0, 9000, 0.15)  # > 8760 h/year is impossible


def test_annual_energy_cost_rejects_negative_inputs():
    with pytest.raises(ValueError):
        annual_energy_cost(-100.0, 8760, 0.15)
    with pytest.raises(ValueError):
        annual_energy_cost(1000.0, 8760, -0.15)


# ── evaluate_lifecycle_cost ──────────────────────────────────────────────────
def test_evaluate_lifecycle_cost_zero_discount_rate_is_simple_sum():
    """With 0% discount and 0% escalation, PV = capex + years * annual_opex."""
    result = evaluate_lifecycle_cost(capex=1000.0, annual_opex=100.0, years=10, discount_rate=0.0)
    assert isinstance(result, LCCAResult)
    assert result.present_value_opex == pytest.approx(1000.0)  # 10 * 100
    assert result.total_lifecycle_cost == pytest.approx(2000.0)


def test_evaluate_lifecycle_cost_higher_discount_rate_reduces_pv():
    low_r = evaluate_lifecycle_cost(1000.0, 100.0, years=10, discount_rate=0.03)
    high_r = evaluate_lifecycle_cost(1000.0, 100.0, years=10, discount_rate=0.10)
    assert high_r.present_value_opex < low_r.present_value_opex


def test_evaluate_lifecycle_cost_escalation_increases_pv():
    flat = evaluate_lifecycle_cost(1000.0, 100.0, years=10, discount_rate=0.05,
                                     opex_escalation_rate=0.0)
    escalating = evaluate_lifecycle_cost(1000.0, 100.0, years=10, discount_rate=0.05,
                                           opex_escalation_rate=0.03)
    assert escalating.present_value_opex > flat.present_value_opex


def test_evaluate_lifecycle_cost_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        evaluate_lifecycle_cost(-100.0, 100.0, 10, 0.05)
    with pytest.raises(ValueError):
        evaluate_lifecycle_cost(1000.0, -100.0, 10, 0.05)
    with pytest.raises(ValueError):
        evaluate_lifecycle_cost(1000.0, 100.0, 0, 0.05)
    with pytest.raises(ValueError):
        evaluate_lifecycle_cost(1000.0, 100.0, 10, -1.5)


# ── Scenario integration ─────────────────────────────────────────────────────
@pytest.fixture
def assumptions():
    return EconomicAssumptions(
        unit_cost_per_m=15.0,
        operating_hours_per_year=8760,
        electricity_price_per_kWh=0.15,
        years=20,
        discount_rate=0.07,
    )


def test_evaluate_scenario_lifecycle_cost_smoke(assumptions):
    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    lcca = evaluate_scenario_lifecycle_cost(result, assumptions)
    assert lcca.capex == pytest.approx(100.0 * 15.0)
    assert lcca.total_lifecycle_cost >= lcca.capex


def test_evaluate_scenario_lifecycle_cost_includes_pump_capex(assumptions):
    assumptions.pump_capex = 500.0
    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    lcca = evaluate_scenario_lifecycle_cost(result, assumptions)
    assert lcca.capex == pytest.approx(100.0 * 15.0 + 500.0)


def test_compare_lifecycle_costs_small_pipe_has_higher_total_cost(assumptions):
    """Mirrors the report's core finding: despite lower CAPEX, the narrow
    pipe's OPEX dominates and its total lifecycle cost is far higher."""
    small = run_simulation(diameter_m=0.0127, flow_rate_m3s=0.0005, length_m=100.0,
                            label="half_inch")
    large = run_simulation(diameter_m=0.1016, flow_rate_m3s=0.0005, length_m=100.0,
                            label="four_inch")
    results = {"half_inch": small, "four_inch": large}
    df = compare_lifecycle_costs(results, assumptions)

    half_row = df[df["scenario"] == "half_inch"].iloc[0]
    four_row = df[df["scenario"] == "four_inch"].iloc[0]

    assert half_row["capex"] == four_row["capex"]  # same unit_cost_per_m here
    assert half_row["total_lifecycle_cost"] > four_row["total_lifecycle_cost"]


def test_compare_lifecycle_costs_with_diameter_dependent_capex(assumptions):
    """When CAPEX scales with diameter (realistic), large pipe should still
    win on total lifecycle cost if OPEX savings dominate."""
    from src.economics.lcca import interpolate_cost_curve

    cost_curve = [(0.0127, 5.0), (0.0508, 12.0), (0.1016, 28.0)]

    small = run_simulation(diameter_m=0.0127, flow_rate_m3s=0.0005, length_m=100.0)
    large = run_simulation(diameter_m=0.1016, flow_rate_m3s=0.0005, length_m=100.0)

    small_assumptions = EconomicAssumptions(
        unit_cost_per_m=interpolate_cost_curve(small.scenario.diameter_m, cost_curve),
        operating_hours_per_year=8760, electricity_price_per_kWh=0.15,
        years=20, discount_rate=0.07,
    )
    large_assumptions = EconomicAssumptions(
        unit_cost_per_m=interpolate_cost_curve(large.scenario.diameter_m, cost_curve),
        operating_hours_per_year=8760, electricity_price_per_kWh=0.15,
        years=20, discount_rate=0.07,
    )

    small_lcca = evaluate_scenario_lifecycle_cost(small, small_assumptions)
    large_lcca = evaluate_scenario_lifecycle_cost(large, large_assumptions)

    assert large_lcca.capex > small_lcca.capex            # bigger pipe costs more upfront
    assert large_lcca.total_lifecycle_cost < small_lcca.total_lifecycle_cost  # but wins overall


# ── Config-driven economics ──────────────────────────────────────────────────
def test_load_economics_config_reads_real_file():
    from src.simulation.config_loader import load_economics_config

    econ_config = load_economics_config(config_dir="configs")
    assert "pipe_cost_curve" in econ_config
    assert "discount_rate" in econ_config
    assert econ_config["years"] > 0


def test_build_economic_assumptions_for_diameter_interpolates():
    from src.economics.scenario_economics import build_economic_assumptions_for_diameter
    from src.simulation.config_loader import load_economics_config

    econ_config = load_economics_config(config_dir="configs")
    assumptions_small = build_economic_assumptions_for_diameter(econ_config, 0.0127)
    assumptions_large = build_economic_assumptions_for_diameter(econ_config, 0.1016)
    assert assumptions_small.unit_cost_per_m < assumptions_large.unit_cost_per_m


def test_compare_lifecycle_costs_with_econ_config_end_to_end():
    from src.simulation.config_loader import load_pipeline, load_economics_config
    from src.economics.scenario_economics import compare_lifecycle_costs

    pipeline = load_pipeline(config_dir="configs")
    econ_config = load_economics_config(config_dir="configs")
    df = compare_lifecycle_costs(pipeline["results"], econ_config=econ_config)

    assert len(df) == 2
    half = df[df["scenario"] == "half_inch_baseline"].iloc[0]
    four = df[df["scenario"] == "four_inch_baseline"].iloc[0]
    # Real-world-shaped result: four-inch costs more upfront, far less overall.
    assert four["capex"] > half["capex"]
    assert four["total_lifecycle_cost"] < half["total_lifecycle_cost"]


def test_compare_lifecycle_costs_rejects_both_or_neither_argument():
    from src.economics.scenario_economics import compare_lifecycle_costs

    result = run_simulation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    with pytest.raises(ValueError):
        compare_lifecycle_costs({"x": result})  # neither supplied
