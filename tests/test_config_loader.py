"""
Unit tests for src/simulation/config_loader.py — the config-driven pipeline
that cross-references pipe_config.yaml / fluid_config.yaml / scenario_config.yaml.
"""

import pytest

from src.simulation.config_loader import (
    build_scenarios,
    run_scenarios,
    scenarios_summary_table,
    build_uncertainties,
    run_monte_carlo_from_config,
    run_sensitivity_from_config,
    load_pipeline,
)
from src.simulation.scenario import PipeScenario


# ── Fixtures: minimal in-memory configs (mirroring configs/*.yaml) ──────────
@pytest.fixture
def pipe_config():
    return {
        "pipes": {
            "half_inch": {"label": "1/2 inch PVC", "diameter_m": 0.0127,
                          "length_m": 100.0, "roughness_m": 1.5e-6},
            "four_inch": {"label": "4 inch PVC", "diameter_m": 0.1016,
                          "length_m": 100.0, "roughness_m": 1.5e-6},
        },
        "fittings": {"elbow_90_standard": 4, "gate_valve_open": 1},
    }


@pytest.fixture
def fluid_config():
    return {
        "water_25C": {"label": "Water @ 25C", "density": 997.0,
                      "viscosity": 1.0e-3, "ambient_temp_K": 298.15},
    }


@pytest.fixture
def scenario_config():
    return {
        "scenarios": [
            {"name": "half_inch_baseline", "pipe": "half_inch", "fluid": "water_25C",
             "flow_rate_m3s": 0.0005, "eta_pump": 0.75, "eta_motor": 0.90},
            {"name": "four_inch_baseline", "pipe": "four_inch", "fluid": "water_25C",
             "flow_rate_m3s": 0.0005, "eta_pump": 0.75, "eta_motor": 0.90},
        ],
        "monte_carlo": {
            "n_samples": 50,
            "seed": 1,
            "uncertainties": [
                {"name": "flow_rate_m3s", "dist": "uniform", "params": {"low": 0.0003, "high": 0.0009}},
            ],
        },
        "sensitivity": {
            "diameter_m": {"low": 0.02, "high": 0.1, "n_points": 5},
        },
    }


# ── build_scenarios ───────────────────────────────────────────────────────
def test_build_scenarios_creates_correct_count(pipe_config, fluid_config, scenario_config):
    scenarios = build_scenarios(pipe_config, fluid_config, scenario_config)
    assert set(scenarios) == {"half_inch_baseline", "four_inch_baseline"}


def test_build_scenarios_pulls_pipe_and_fluid_properties(pipe_config, fluid_config, scenario_config):
    scenarios = build_scenarios(pipe_config, fluid_config, scenario_config)
    s = scenarios["half_inch_baseline"]
    assert s.diameter_m == 0.0127
    assert s.density == 997.0
    assert s.viscosity == 1.0e-3
    assert s.fittings == {"elbow_90_standard": 4, "gate_valve_open": 1}


def test_build_scenarios_rejects_unknown_pipe(pipe_config, fluid_config, scenario_config):
    scenario_config["scenarios"][0]["pipe"] = "nonexistent_pipe"
    with pytest.raises(ValueError, match="unknown pipe"):
        build_scenarios(pipe_config, fluid_config, scenario_config)


def test_build_scenarios_rejects_unknown_fluid(pipe_config, fluid_config, scenario_config):
    scenario_config["scenarios"][0]["fluid"] = "nonexistent_fluid"
    with pytest.raises(ValueError, match="unknown fluid"):
        build_scenarios(pipe_config, fluid_config, scenario_config)


def test_build_scenarios_rejects_missing_required_field(pipe_config, fluid_config, scenario_config):
    del scenario_config["scenarios"][0]["flow_rate_m3s"]
    with pytest.raises(ValueError, match="missing required field"):
        build_scenarios(pipe_config, fluid_config, scenario_config)


def test_build_scenarios_rejects_duplicate_names(pipe_config, fluid_config, scenario_config):
    scenario_config["scenarios"].append(dict(scenario_config["scenarios"][0]))
    with pytest.raises(ValueError, match="Duplicate scenario name"):
        build_scenarios(pipe_config, fluid_config, scenario_config)


def test_build_scenarios_rejects_missing_pipes_key(fluid_config, scenario_config):
    with pytest.raises(ValueError, match="'pipes'"):
        build_scenarios({}, fluid_config, scenario_config)


# ── run_scenarios / scenarios_summary_table ──────────────────────────────
def test_run_scenarios_produces_results_for_every_scenario(pipe_config, fluid_config, scenario_config):
    scenarios = build_scenarios(pipe_config, fluid_config, scenario_config)
    results = run_scenarios(scenarios)
    assert set(results) == set(scenarios)
    assert all(r.pump.shaft_power_W >= 0 for r in results.values())


def test_summary_table_matches_report_pattern_half_inch_worse(pipe_config, fluid_config, scenario_config):
    """Sanity check matching the reference report: 1/2 inch should have far higher head loss."""
    scenarios = build_scenarios(pipe_config, fluid_config, scenario_config)
    results = run_scenarios(scenarios)
    df = scenarios_summary_table(results)
    half = df[df["scenario"] == "half_inch_baseline"]["total_loss_m"].iloc[0]
    four = df[df["scenario"] == "four_inch_baseline"]["total_loss_m"].iloc[0]
    assert half > four


# ── Monte Carlo from config ──────────────────────────────────────────────
def test_build_uncertainties_parses_list(scenario_config):
    uncertainties = build_uncertainties(scenario_config["monte_carlo"])
    assert len(uncertainties) == 1
    assert uncertainties[0].name == "flow_rate_m3s"
    assert uncertainties[0].dist == "uniform"


def test_build_uncertainties_rejects_missing_field():
    with pytest.raises(ValueError, match="missing field"):
        build_uncertainties({"uncertainties": [{"name": "flow_rate_m3s", "dist": "uniform"}]})


def test_run_monte_carlo_from_config_produces_rows(scenario_config):
    base = PipeScenario(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    df = run_monte_carlo_from_config(base, scenario_config["monte_carlo"])
    assert len(df) > 0
    assert "total_loss_m" in df.columns


def test_run_monte_carlo_from_config_rejects_nonpositive_n_samples(scenario_config):
    scenario_config["monte_carlo"]["n_samples"] = 0
    base = PipeScenario(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    with pytest.raises(ValueError, match="n_samples must be positive"):
        run_monte_carlo_from_config(base, scenario_config["monte_carlo"])


# ── Sensitivity from config ──────────────────────────────────────────────
def test_run_sensitivity_from_config_produces_sweep(scenario_config):
    base = PipeScenario(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    results = run_sensitivity_from_config(base, scenario_config["sensitivity"])
    assert "diameter_m" in results
    assert len(results["diameter_m"]) == 5


def test_run_sensitivity_from_config_rejects_low_ge_high(scenario_config):
    scenario_config["sensitivity"]["diameter_m"]["low"] = 0.2
    scenario_config["sensitivity"]["diameter_m"]["high"] = 0.1
    base = PipeScenario(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
    with pytest.raises(ValueError, match="must be <"):
        run_sensitivity_from_config(base, scenario_config["sensitivity"])


# ── load_pipeline (reads actual files from configs/) ─────────────────────
def test_load_pipeline_reads_real_config_files():
    """End-to-end: load the real configs/ directory shipped with the project."""
    pipeline = load_pipeline(config_dir="configs")
    assert "half_inch_baseline" in pipeline["scenarios"]
    assert "four_inch_baseline" in pipeline["scenarios"]
    assert len(pipeline["summary"]) == 2
    assert pipeline["monte_carlo_config"]["n_samples"] == 2000
    assert "diameter_m" in pipeline["sensitivity_config"]


def test_real_config_demonstrates_muri_overburden_contrast():
    """The shipped scenario_config.yaml deliberately undersizes the pump for
    half_inch_baseline (vs. its ~992 W requirement) to demonstrate the Muri
    check, while four_inch_baseline's pump is comfortably oversized."""
    pipeline = load_pipeline(config_dir="configs")
    half = pipeline["results"]["half_inch_baseline"]
    four = pipeline["results"]["four_inch_baseline"]
    assert half.pump_load_warning is not None
    assert "overloaded" in half.pump_load_warning.lower()
    assert four.pump_load_warning is None


def test_real_config_demonstrates_npsh_cavitation_contrast():
    """The shipped scenario_config.yaml deliberately gives half_inch_baseline
    a demanding NPSHr under suction lift (cavitation risk), while
    four_inch_baseline has flooded suction and a comfortable margin."""
    pipeline = load_pipeline(config_dir="configs")
    half = pipeline["results"]["half_inch_baseline"]
    four = pipeline["results"]["four_inch_baseline"]
    assert half.npsh is not None
    assert half.npsh_warning is not None
    assert "cavitation" in half.npsh_warning.lower()
    assert four.npsh is not None
    assert four.npsh_warning is None
    assert four.npsh.margin_ratio > 1.2
