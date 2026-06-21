"""
Sensitivity analysis: one-at-a-time (OAT) parameter sweeps for hydraulic
scenarios. Useful for "diameter vs head loss" style comparisons (see
``notebooks/compare_pipes.ipynb``) and for ranking which inputs the
results are most sensitive to.
"""

from dataclasses import replace

import numpy as np
import pandas as pd

from .scenario import PipeScenario, run_simulation


def sweep_parameter(
    base_scenario: PipeScenario,
    parameter: str,
    values: list[float] | np.ndarray,
) -> pd.DataFrame:
    """Vary a single scenario parameter across a list of values.

    Parameters
    ----------
    base_scenario : PipeScenario
        Baseline scenario; all fields except ``parameter`` are held fixed.
    parameter      : str
        Name of the ``PipeScenario`` field to vary, e.g. ``"diameter_m"``.
    values         : list[float] | np.ndarray
        Values to sweep through.

    Returns
    -------
    pd.DataFrame
        One row per swept value, with the swept parameter plus output
        metrics: ``velocity_m_s, reynolds, friction_factor, total_loss_m,
        pressure_drop_Pa, shaft_power_W, exergy_destroyed_W``.

    Example
    -------
    >>> base = PipeScenario(diameter_m=0.1, flow_rate_m3s=0.01)
    >>> df = sweep_parameter(base, "diameter_m", np.linspace(0.02, 0.2, 10))
    """
    if not hasattr(base_scenario, parameter):
        raise ValueError(
            f"'{parameter}' is not a valid PipeScenario field. "
            f"Valid fields: {list(base_scenario.__dataclass_fields__)}"
        )

    rows = []
    for val in values:
        scenario = replace(base_scenario, **{parameter: val})
        try:
            result = run_simulation(
                diameter_m=scenario.diameter_m,
                flow_rate_m3s=scenario.flow_rate_m3s,
                length_m=scenario.length_m,
                roughness_m=scenario.roughness_m,
                density=scenario.density,
                viscosity=scenario.viscosity,
                fittings=scenario.fittings,
                static_head_m=scenario.static_head_m,
                eta_pump=scenario.eta_pump,
                eta_motor=scenario.eta_motor,
                ambient_temp_K=scenario.ambient_temp_K,
                rated_power_W=scenario.rated_power_W,
                suction_pressure_Pa=scenario.suction_pressure_Pa,
                vapor_pressure_Pa=scenario.vapor_pressure_Pa,
                inlet_elevation_m=scenario.inlet_elevation_m,
                suction_head_loss_m=scenario.suction_head_loss_m,
                npsh_required_m=scenario.npsh_required_m,
            )
        except ValueError as e:
            rows.append({parameter: val, "error": str(e)})
            continue

        rows.append({
            parameter: val,
            "velocity_m_s": result.head_loss.velocity_m_s,
            "reynolds": result.head_loss.reynolds,
            "friction_factor": result.head_loss.friction_factor,
            "total_loss_m": result.head_loss.total_loss_m,
            "pressure_drop_Pa": result.pressure_drop,
            "shaft_power_W": result.pump.shaft_power_W,
            "exergy_destroyed_W": result.exergy.exergy_destruction_W,
        })

    return pd.DataFrame(rows)


def sweep_multiple(
    base_scenario: PipeScenario,
    parameter_grids: dict[str, list[float]],
) -> dict[str, pd.DataFrame]:
    """Run independent one-at-a-time sweeps for several parameters.

    Parameters
    ----------
    base_scenario   : PipeScenario  baseline scenario
    parameter_grids : dict[str, list[float]]
        Mapping of parameter name -> list of values to sweep, e.g.
        ``{"diameter_m": [...], "flow_rate_m3s": [...]}``.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of parameter name -> sweep result DataFrame (see
        ``sweep_parameter``).
    """
    return {
        name: sweep_parameter(base_scenario, name, values)
        for name, values in parameter_grids.items()
    }


def normalized_sensitivity(
    base_scenario: PipeScenario,
    parameter: str,
    perturbation: float = 0.10,
    output_metric: str = "total_loss_m",
) -> float:
    """Compute a normalized (elasticity) sensitivity coefficient.

        S = (ΔY / Y₀) / (ΔX / X₀)

    i.e. the % change in the chosen output metric per % change in the input
    parameter, evaluated by perturbing ±``perturbation`` around the base
    value. Useful for ranking which inputs matter most without worrying
    about differing units/scales.

    Parameters
    ----------
    base_scenario : PipeScenario
    parameter     : str    field to perturb, e.g. "diameter_m"
    perturbation  : float  fractional perturbation (default ±10%)
    output_metric : str    column name from ``sweep_parameter`` output to
                            track, e.g. "total_loss_m", "pressure_drop_Pa"

    Returns
    -------
    float
        Dimensionless elasticity. |S| > 1 means the output is more
        sensitive (in relative terms) than the input; |S| < 1 means less.
    """
    x0 = getattr(base_scenario, parameter)
    if x0 == 0:
        raise ValueError(f"Cannot compute elasticity around zero base value for '{parameter}'.")

    x_lo, x_hi = x0 * (1 - perturbation), x0 * (1 + perturbation)
    df = sweep_parameter(base_scenario, parameter, [x_lo, x0, x_hi])

    if "error" in df.columns and df["error"].notna().any():
        raise ValueError(f"Sweep failed for '{parameter}': {df['error'].dropna().tolist()}")

    y_lo, y0, y_hi = df[output_metric].tolist()
    dy = y_hi - y_lo
    dx = x_hi - x_lo
    return (dy / y0) / (dx / x0)
