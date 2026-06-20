"""
Pressure-vs-distance visualization along a pipeline.

Used by ``simulation.scenario.ScenarioResult.pressure_curve()`` and the
Streamlit results page.
"""

import numpy as np
import plotly.graph_objects as go

from ..utils.constants import GRAVITY


def pressure_vs_distance_figure(scenario_result, n_points: int = 50) -> go.Figure:
    """Build a Plotly line chart of pressure decreasing along the pipe.

    Assumes a uniform pipe (constant diameter/roughness along its length),
    so head loss accumulates linearly with distance; minor losses from
    fittings are applied as discrete step-drops at evenly spaced points
    along the run as an illustrative approximation (real fitting locations
    are not tracked by the scenario model).

    Parameters
    ----------
    scenario_result : simulation.scenario.ScenarioResult
    n_points        : int  resolution of the distance axis

    Returns
    -------
    plotly.graph_objects.Figure
    """
    s = scenario_result.scenario
    hl = scenario_result.head_loss

    distances = np.linspace(0, s.length_m, n_points)

    # Major (friction) loss accumulates linearly with distance.
    major_loss_per_m = hl.major_loss_m / s.length_m if s.length_m > 0 else 0.0
    cumulative_major_m = major_loss_per_m * distances

    # Minor losses (fittings) are distributed as step drops, evenly spaced,
    # purely for illustration since exact fitting positions aren't modeled.
    cumulative_minor_m = np.zeros_like(distances)
    n_fittings = len(hl.fittings) if hl.fittings else 0
    if n_fittings > 0 and hl.minor_loss_m > 0:
        step_positions = np.linspace(
            s.length_m / (n_fittings + 1), s.length_m, n_fittings, endpoint=False
        )
        minor_per_fitting = hl.minor_loss_m / n_fittings
        for pos in step_positions:
            cumulative_minor_m += np.where(distances >= pos, minor_per_fitting, 0.0)

    cumulative_loss_m = cumulative_major_m + cumulative_minor_m
    pressure_drop_Pa = s.density * GRAVITY * cumulative_loss_m

    # Reference: starting gauge pressure assumed to be the total pressure
    # drop, so the curve ends at ~0 — i.e. shows pressure *remaining*.
    p0 = s.density * GRAVITY * hl.total_loss_m
    pressure_remaining_Pa = p0 - pressure_drop_Pa

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=distances,
            y=pressure_remaining_Pa,
            mode="lines",
            name="Pressure",
            line=dict(color="#1f77b4", width=3),
        )
    )
    fig.update_layout(
        title="Pressure vs. Distance Along Pipeline",
        xaxis_title="Distance [m]",
        yaxis_title="Pressure [Pa]",
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig
