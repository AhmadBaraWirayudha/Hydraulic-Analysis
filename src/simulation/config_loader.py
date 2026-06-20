"""
Config-driven pipeline: assembles ``PipeScenario`` objects, Monte Carlo
uncertainty specs, and sensitivity sweep grids directly from the YAML files
in ``configs/`` — so running a different set of scenarios means editing
YAML, not Python.

This replaces hardcoded values in scripts/notebooks with a single
``load_pipeline()`` call. Poka-Yoke: every cross-reference (a scenario
naming a pipe/fluid key that doesn't exist) and every required field is
checked up front, raising a clear ``ValueError`` rather than failing deep
inside a simulation run.

Expected file layout
---------------------
configs/pipe_config.yaml:
    pipes:
      <pipe_key>: {diameter_m, length_m, roughness_m, label?}
    fittings: {<fitting_name>: <count>}   # optional, shared default

configs/fluid_config.yaml:
    <fluid_key>: {density, viscosity, ambient_temp_K, label?}

configs/scenario_config.yaml:
    scenarios:
      - {name, pipe, fluid, flow_rate_m3s, static_head_m?, eta_pump?,
         eta_motor?, fittings?}
    monte_carlo: {n_samples, seed, uncertainties: [{name, dist, params}]}
    sensitivity: {<param_name>: {low, high, n_points}}
"""

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from ..utils.constants import WATER_DENSITY, WATER_VISCOSITY, PVC_ROUGHNESS
from .scenario import PipeScenario, ScenarioResult, run_simulation
from .monte_carlo import ParameterUncertainty, run_monte_carlo
from .sensitivity import sweep_parameter


def load_yaml(path: str | Path) -> dict:
    """Read and parse a single YAML config file."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"Config file is empty: {path}")
    return data


def build_scenarios(
    pipe_config: dict,
    fluid_config: dict,
    scenario_config: dict,
) -> dict[str, PipeScenario]:
    """Cross-reference the three parsed configs into named ``PipeScenario`` objects.

    Parameters
    ----------
    pipe_config     : dict  parsed contents of ``pipe_config.yaml``
    fluid_config    : dict  parsed contents of ``fluid_config.yaml``
    scenario_config : dict  parsed contents of ``scenario_config.yaml``

    Returns
    -------
    dict[str, PipeScenario]
        Mapping of scenario name -> fully assembled scenario.

    Raises
    ------
    ValueError
        If a scenario references an unknown pipe/fluid key, or a required
        field is missing.
    """
    if "pipes" not in pipe_config:
        raise ValueError("pipe_config.yaml must contain a top-level 'pipes' key.")
    if "scenarios" not in scenario_config:
        raise ValueError("scenario_config.yaml must contain a top-level 'scenarios' key.")

    pipes = pipe_config["pipes"]
    default_fittings = pipe_config.get("fittings")
    fluids = fluid_config

    scenarios: dict[str, PipeScenario] = {}

    for i, entry in enumerate(scenario_config["scenarios"]):
        if "name" not in entry:
            raise ValueError(f"scenarios[{i}] is missing required field 'name'.")
        name = entry["name"]

        for required in ("pipe", "fluid", "flow_rate_m3s"):
            if required not in entry:
                raise ValueError(f"Scenario '{name}' is missing required field '{required}'.")

        pipe_key, fluid_key = entry["pipe"], entry["fluid"]
        if pipe_key not in pipes:
            raise ValueError(
                f"Scenario '{name}' references unknown pipe '{pipe_key}'. "
                f"Known pipes: {sorted(pipes)}"
            )
        if fluid_key not in fluids:
            raise ValueError(
                f"Scenario '{name}' references unknown fluid '{fluid_key}'. "
                f"Known fluids: {sorted(fluids)}"
            )

        pipe = pipes[pipe_key]
        fluid = fluids[fluid_key]

        if name in scenarios:
            raise ValueError(f"Duplicate scenario name '{name}' in scenario_config.yaml.")

        scenarios[name] = PipeScenario(
            diameter_m=pipe["diameter_m"],
            flow_rate_m3s=entry["flow_rate_m3s"],
            length_m=pipe.get("length_m", 100.0),
            roughness_m=pipe.get("roughness_m", PVC_ROUGHNESS),
            density=fluid.get("density", WATER_DENSITY),
            viscosity=fluid.get("viscosity", WATER_VISCOSITY),
            fittings=entry.get("fittings", default_fittings),
            static_head_m=entry.get("static_head_m", 0.0),
            eta_pump=entry.get("eta_pump", 0.75),
            eta_motor=entry.get("eta_motor", 0.90),
            ambient_temp_K=fluid.get("ambient_temp_K", 298.15),
            rated_power_W=entry.get("rated_power_W"),
            label=f"{pipe.get('label', pipe_key)} / {fluid.get('label', fluid_key)}",
        )

    return scenarios


def run_scenarios(scenarios: dict[str, PipeScenario]) -> dict[str, ScenarioResult]:
    """Run every scenario in the dict through ``run_simulation``.

    Returns
    -------
    dict[str, ScenarioResult]
    """
    results = {}
    for name, s in scenarios.items():
        results[name] = run_simulation(
            diameter_m=s.diameter_m,
            flow_rate_m3s=s.flow_rate_m3s,
            length_m=s.length_m,
            roughness_m=s.roughness_m,
            density=s.density,
            viscosity=s.viscosity,
            fittings=s.fittings,
            static_head_m=s.static_head_m,
            eta_pump=s.eta_pump,
            eta_motor=s.eta_motor,
            ambient_temp_K=s.ambient_temp_K,
            rated_power_W=s.rated_power_W,
            label=s.label,
        )
    return results


def scenarios_summary_table(results: dict[str, ScenarioResult]) -> pd.DataFrame:
    """Flatten a dict of ScenarioResult into a single comparison DataFrame."""
    rows = []
    for name, r in results.items():
        rows.append({
            "scenario": name,
            "label": r.scenario.label,
            "diameter_m": r.scenario.diameter_m,
            "flow_rate_m3s": r.scenario.flow_rate_m3s,
            "velocity_m_s": r.head_loss.velocity_m_s,
            "reynolds": r.head_loss.reynolds,
            "total_loss_m": r.head_loss.total_loss_m,
            "pressure_drop_Pa": r.pressure_drop,
            "shaft_power_W": r.pump.shaft_power_W,
            "exergy_destroyed_W": r.exergy.exergy_destruction_W,
            "velocity_warning": r.velocity_warning,
            "pump_load_warning": r.pump_load_warning,
        })
    return pd.DataFrame(rows)


def build_uncertainties(monte_carlo_config: dict) -> list[ParameterUncertainty]:
    """Parse the 'uncertainties' list from a scenario_config's 'monte_carlo' block."""
    uncertainties = []
    for i, u in enumerate(monte_carlo_config.get("uncertainties", [])):
        for required in ("name", "dist", "params"):
            if required not in u:
                raise ValueError(f"monte_carlo.uncertainties[{i}] is missing field '{required}'.")
        uncertainties.append(ParameterUncertainty(name=u["name"], dist=u["dist"], params=u["params"]))
    return uncertainties


def run_monte_carlo_from_config(
    base_scenario: PipeScenario,
    monte_carlo_config: dict,
) -> pd.DataFrame:
    """Run Monte Carlo using the 'monte_carlo' block from scenario_config.yaml."""
    uncertainties = build_uncertainties(monte_carlo_config)
    n_samples = monte_carlo_config.get("n_samples", 1000)
    seed = monte_carlo_config.get("seed", 42)
    if n_samples <= 0:
        raise ValueError(f"monte_carlo.n_samples must be positive. Got {n_samples}.")
    return run_monte_carlo(base_scenario, uncertainties, n_samples=n_samples, seed=seed)


def run_sensitivity_from_config(
    base_scenario: PipeScenario,
    sensitivity_config: dict,
) -> dict[str, pd.DataFrame]:
    """Run sweeps for every parameter listed in the 'sensitivity' block.

    Each entry must specify {low, high, n_points}.
    """
    results = {}
    for param, spec in sensitivity_config.items():
        for required in ("low", "high"):
            if required not in spec:
                raise ValueError(f"sensitivity.{param} is missing field '{required}'.")
        if spec["low"] >= spec["high"]:
            raise ValueError(
                f"sensitivity.{param}: 'low' ({spec['low']}) must be < 'high' ({spec['high']})."
            )
        n_points = spec.get("n_points", 10)
        values = np.linspace(spec["low"], spec["high"], n_points)
        results[param] = sweep_parameter(base_scenario, param, values)
    return results


def load_pipeline(config_dir: str | Path = "configs") -> dict:
    """Load all three config files and assemble the full config-driven pipeline.

    Parameters
    ----------
    config_dir : str | Path
        Directory containing ``pipe_config.yaml``, ``fluid_config.yaml``,
        and ``scenario_config.yaml``.

    Returns
    -------
    dict with keys:
        scenarios            : dict[str, PipeScenario]
        results               : dict[str, ScenarioResult]
        summary               : pd.DataFrame  (one row per scenario)
        monte_carlo_config    : dict          (raw 'monte_carlo' block)
        sensitivity_config    : dict          (raw 'sensitivity' block)
    """
    config_dir = Path(config_dir)
    pipe_config = load_yaml(config_dir / "pipe_config.yaml")
    fluid_config = load_yaml(config_dir / "fluid_config.yaml")
    scenario_config = load_yaml(config_dir / "scenario_config.yaml")

    scenarios = build_scenarios(pipe_config, fluid_config, scenario_config)
    results = run_scenarios(scenarios)
    summary = scenarios_summary_table(results)

    return {
        "scenarios": scenarios,
        "results": results,
        "summary": summary,
        "monte_carlo_config": scenario_config.get("monte_carlo", {}),
        "sensitivity_config": scenario_config.get("sensitivity", {}),
    }
