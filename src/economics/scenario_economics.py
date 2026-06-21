"""
Ties Lifecycle Cost Analysis (LCCA) to ``ScenarioResult`` objects, so pipe
diameter / pump choices already evaluated hydraulically can be compared
economically without re-deriving CAPEX/OPEX inputs by hand.
"""

from dataclasses import dataclass

import pandas as pd

from .lcca import evaluate_lifecycle_cost, annual_energy_cost, pipe_capex, LCCAResult, interpolate_cost_curve


@dataclass
class EconomicAssumptions:
    """Shared economic assumptions applied across a set of scenarios.

    None of these are hardcoded defaults meant to represent real prices —
    every field must be explicitly supplied, reflecting the caller's own
    cost data (see module docstring in ``lcca.py``).
    """

    unit_cost_per_m: float            # installed pipe cost per metre
    operating_hours_per_year: float
    electricity_price_per_kWh: float
    years: int
    discount_rate: float
    opex_escalation_rate: float = 0.0
    pump_capex: float = 0.0            # additional upfront pump/install cost, if any


def evaluate_scenario_lifecycle_cost(
    scenario_result, assumptions: EconomicAssumptions
) -> LCCAResult:
    """Compute the full LCCA for one ``ScenarioResult``, using its pipe
    length/diameter and pump electrical draw as the physical inputs.

    Parameters
    ----------
    scenario_result : simulation.scenario.ScenarioResult
    assumptions     : EconomicAssumptions

    Returns
    -------
    LCCAResult
    """
    capex = pipe_capex(
        scenario_result.scenario.length_m, assumptions.unit_cost_per_m
    ) + assumptions.pump_capex

    annual_opex = annual_energy_cost(
        electrical_power_W=scenario_result.pump.shaft_power_W,
        operating_hours_per_year=assumptions.operating_hours_per_year,
        electricity_price_per_kWh=assumptions.electricity_price_per_kWh,
    )

    return evaluate_lifecycle_cost(
        capex=capex,
        annual_opex=annual_opex,
        years=assumptions.years,
        discount_rate=assumptions.discount_rate,
        opex_escalation_rate=assumptions.opex_escalation_rate,
    )


def build_economic_assumptions_for_diameter(
    econ_config: dict, diameter_m: float
) -> EconomicAssumptions:
    """Build ``EconomicAssumptions`` for a specific pipe diameter from the
    parsed contents of ``economics_config.yaml`` — interpolates
    ``pipe_cost_curve`` at the given diameter for ``unit_cost_per_m``, and
    reads the remaining fields directly.

    Parameters
    ----------
    econ_config : dict   parsed ``economics_config.yaml`` (see
                  ``simulation.config_loader.load_economics_config``)
    diameter_m  : float  pipe diameter to look up on the cost curve [m]

    Returns
    -------
    EconomicAssumptions
    """
    unit_cost = interpolate_cost_curve(diameter_m, [tuple(p) for p in econ_config["pipe_cost_curve"]])
    return EconomicAssumptions(
        unit_cost_per_m=unit_cost,
        operating_hours_per_year=econ_config["operating_hours_per_year"],
        electricity_price_per_kWh=econ_config["electricity_price_per_kWh"],
        years=econ_config["years"],
        discount_rate=econ_config["discount_rate"],
        opex_escalation_rate=econ_config.get("opex_escalation_rate", 0.0),
        pump_capex=econ_config.get("pump_capex", 0.0),
    )


def compare_lifecycle_costs(
    scenario_results: dict[str, "ScenarioResult"],  # noqa: F821 (avoid circular import)
    assumptions: EconomicAssumptions | None = None,
    econ_config: dict | None = None,
) -> pd.DataFrame:
    """Compare lifecycle cost across multiple named scenarios.

    Parameters
    ----------
    scenario_results : dict[str, ScenarioResult]  e.g. from
                        ``simulation.config_loader.load_pipeline()['results']``
    assumptions       : EconomicAssumptions | None
                        applied identically to all scenarios (same
                        unit_cost_per_m regardless of diameter)
    econ_config       : dict | None
                        if supplied instead of ``assumptions``, builds a
                        diameter-specific ``EconomicAssumptions`` per
                        scenario via ``build_economic_assumptions_for_diameter``
                        — use this when CAPEX should scale with diameter.

    Exactly one of ``assumptions`` or ``econ_config`` must be supplied.

    Returns
    -------
    pd.DataFrame
        One row per scenario: capex, annual_opex_year1, present_value_opex,
        total_lifecycle_cost.
    """
    if (assumptions is None) == (econ_config is None):
        raise ValueError("Supply exactly one of `assumptions` or `econ_config`.")

    rows = []
    for name, result in scenario_results.items():
        scenario_assumptions = assumptions or build_economic_assumptions_for_diameter(
            econ_config, result.scenario.diameter_m
        )
        lcca = evaluate_scenario_lifecycle_cost(result, scenario_assumptions)
        rows.append({
            "scenario": name,
            "diameter_mm": result.scenario.diameter_m * 1000,
            "unit_cost_per_m": scenario_assumptions.unit_cost_per_m,
            "capex": lcca.capex,
            "annual_opex_year1": lcca.annual_opex_year1,
            "present_value_opex": lcca.present_value_opex,
            "total_lifecycle_cost": lcca.total_lifecycle_cost,
        })
    return pd.DataFrame(rows)
