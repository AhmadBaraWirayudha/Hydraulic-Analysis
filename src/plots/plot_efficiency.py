"""
Efficiency and sensitivity curve visualizations (pump efficiency, parameter
sweeps from ``simulation.sensitivity``).
"""

import pandas as pd
import plotly.graph_objects as go


def efficiency_curve_figure(
    sweep_df: pd.DataFrame,
    x_column: str,
    x_label: str | None = None,
) -> go.Figure:
    """Plot pump shaft power and overall efficiency vs. a swept parameter.

    Expects a DataFrame from ``simulation.sensitivity.sweep_parameter`` that
    includes ``shaft_power_W`` (efficiency itself isn't tracked per-row by
    the sweep, since η_pump/η_motor are usually held fixed — this plots
    shaft power, which is the practically relevant "efficiency" proxy
    when sweeping diameter/flow rate).

    Parameters
    ----------
    sweep_df : pd.DataFrame  output of ``sweep_parameter``
    x_column : str           column to use as the x-axis (the swept parameter)
    x_label  : str | None    axis label override

    Returns
    -------
    plotly.graph_objects.Figure
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=sweep_df[x_column],
            y=sweep_df["shaft_power_W"],
            mode="lines+markers",
            name="Shaft Power [W]",
            line=dict(color="#d62728"),
        )
    )
    fig.update_layout(
        title="Pump Shaft Power vs. " + (x_label or x_column),
        xaxis_title=x_label or x_column,
        yaxis_title="Shaft Power [W]",
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def head_loss_comparison_figure(
    sweep_df: pd.DataFrame,
    x_column: str,
    x_label: str | None = None,
) -> go.Figure:
    """Plot total head loss vs. a swept parameter (e.g. diameter comparison).

    Mirrors the "diameter vs head loss" comparison from
    ``notebooks/compare_pipes.ipynb``.
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=sweep_df[x_column],
            y=sweep_df["total_loss_m"],
            mode="lines+markers",
            name="Head Loss [m]",
            line=dict(color="#2ca02c"),
        )
    )
    fig.update_layout(
        title="Head Loss vs. " + (x_label or x_column),
        xaxis_title=x_label or x_column,
        yaxis_title="Head Loss [m]",
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def monte_carlo_histogram_figure(
    mc_df: pd.DataFrame,
    column: str,
    x_label: str | None = None,
    n_bins: int = 40,
) -> go.Figure:
    """Histogram of a Monte Carlo output metric, for the uncertainty notebook.

    Parameters
    ----------
    mc_df   : pd.DataFrame  output of ``simulation.monte_carlo.run_monte_carlo``
    column  : str           output column to histogram (e.g. "total_loss_m")
    x_label : str | None    axis label override
    n_bins  : int           number of histogram bins
    """
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=mc_df[column],
            nbinsx=n_bins,
            marker_color="#9467bd",
            opacity=0.85,
        )
    )
    fig.update_layout(
        title=f"Monte Carlo Distribution — {x_label or column}",
        xaxis_title=x_label or column,
        yaxis_title="Count",
        template="plotly_white",
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig
