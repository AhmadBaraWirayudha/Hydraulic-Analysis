"""
Monte Carlo uncertainty analysis for hydraulic scenarios.

Samples one or more input parameters from specified distributions, runs the
scenario many times, and returns the resulting distribution of output
metrics (head loss, pressure drop, pump power, exergy destruction, etc.) as
a pandas DataFrame for downstream plotting/statistics.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .scenario import PipeScenario, run_simulation


@dataclass
class ParameterUncertainty:
    """Describes the sampling distribution for one uncertain parameter.

    Parameters
    ----------
    name  : str
        Name of the ``PipeScenario`` field to vary (e.g. ``"flow_rate_m3s"``).
    dist  : {"normal", "uniform", "triangular"}
        Distribution family to sample from.
    params: dict
        Distribution parameters:
          - normal:      {"mean": float, "std": float}
          - uniform:      {"low": float, "high": float}
          - triangular:   {"low": float, "mode": float, "high": float}
    """

    name: str
    dist: Literal["normal", "uniform", "triangular"]
    params: dict


def _sample(unc: ParameterUncertainty, n: int, rng: np.random.Generator) -> np.ndarray:
    """Draw n samples for a single uncertain parameter."""
    if unc.dist == "normal":
        samples = rng.normal(unc.params["mean"], unc.params["std"], size=n)
    elif unc.dist == "uniform":
        samples = rng.uniform(unc.params["low"], unc.params["high"], size=n)
    elif unc.dist == "triangular":
        samples = rng.triangular(
            unc.params["low"], unc.params["mode"], unc.params["high"], size=n
        )
    else:
        raise ValueError(f"Unknown distribution '{unc.dist}'.")
    return samples


def run_monte_carlo(
    base_scenario: PipeScenario,
    uncertainties: list[ParameterUncertainty],
    n_samples: int = 1000,
    seed: int | None = 42,
    clip_negative: bool = True,
) -> pd.DataFrame:
    """Run a Monte Carlo uncertainty analysis.

    Parameters
    ----------
    base_scenario : PipeScenario
        Baseline scenario; fields named in ``uncertainties`` are overridden
        per-sample, all others held fixed.
    uncertainties : list[ParameterUncertainty]
        One entry per uncertain input parameter.
    n_samples     : int
        Number of Monte Carlo trials to run.
    seed          : int | None
        Random seed for reproducibility (None = nondeterministic).
    clip_negative : bool
        If True, negative samples of physically non-negative parameters
        (flow_rate_m3s, diameter_m, length_m, roughness_m) are clipped to a
        small positive epsilon rather than raising — keeps large batch runs
        from crashing on rare unphysical tail draws.

    Returns
    -------
    pd.DataFrame
        One row per trial, columns = sampled inputs + output metrics:
        ``velocity_m_s, reynolds, total_loss_m, pressure_drop_Pa,
        shaft_power_W, exergy_destroyed_W``.
    """
    rng = np.random.default_rng(seed)
    eps = 1e-9
    non_negative_fields = {"flow_rate_m3s", "diameter_m", "length_m", "roughness_m"}

    # Pre-sample all uncertain parameters
    sampled = {unc.name: _sample(unc, n_samples, rng) for unc in uncertainties}

    rows = []
    for i in range(n_samples):
        overrides = {}
        for name, values in sampled.items():
            val = values[i]
            if clip_negative and name in non_negative_fields and val <= 0:
                val = eps
            overrides[name] = val

        kwargs = dict(
            diameter_m=overrides.get("diameter_m", base_scenario.diameter_m),
            flow_rate_m3s=overrides.get("flow_rate_m3s", base_scenario.flow_rate_m3s),
            length_m=overrides.get("length_m", base_scenario.length_m),
            roughness_m=overrides.get("roughness_m", base_scenario.roughness_m),
            density=overrides.get("density", base_scenario.density),
            viscosity=overrides.get("viscosity", base_scenario.viscosity),
            fittings=base_scenario.fittings,
            static_head_m=overrides.get("static_head_m", base_scenario.static_head_m),
            eta_pump=overrides.get("eta_pump", base_scenario.eta_pump),
            eta_motor=overrides.get("eta_motor", base_scenario.eta_motor),
            ambient_temp_K=base_scenario.ambient_temp_K,
            rated_power_W=base_scenario.rated_power_W,
            suction_pressure_Pa=base_scenario.suction_pressure_Pa,
            vapor_pressure_Pa=base_scenario.vapor_pressure_Pa,
            inlet_elevation_m=base_scenario.inlet_elevation_m,
            suction_head_loss_m=base_scenario.suction_head_loss_m,
            npsh_required_m=base_scenario.npsh_required_m,
        )

        try:
            result = run_simulation(**kwargs)
        except ValueError:
            # Skip unphysical draws that still slip through (e.g. roughness
            # exceeding diameter on extreme tail combinations).
            continue

        row = {**overrides}
        row.update(
            velocity_m_s=result.head_loss.velocity_m_s,
            reynolds=result.head_loss.reynolds,
            total_loss_m=result.head_loss.total_loss_m,
            pressure_drop_Pa=result.pressure_drop,
            shaft_power_W=result.pump.shaft_power_W,
            exergy_destroyed_W=result.exergy.exergy_destruction_W,
        )
        rows.append(row)

    return pd.DataFrame(rows)


def summary_statistics(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Compute mean, std, percentiles (5/50/95) for selected output columns.

    Parameters
    ----------
    df      : pd.DataFrame  output of ``run_monte_carlo``
    columns : list[str] | None  columns to summarize; defaults to all
              numeric columns if None.
    """
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()
    summary = df[columns].agg(
        ["mean", "std", lambda s: s.quantile(0.05), "median", lambda s: s.quantile(0.95)]
    )
    summary.index = ["mean", "std", "p05", "median", "p95"]
    return summary
