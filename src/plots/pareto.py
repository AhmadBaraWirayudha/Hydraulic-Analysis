"""
Lean Six Sigma 3M visualizations: Muda (waste) and Mura (unevenness).

Muri (overburden) is handled as a textual/metric check in
``utils.validation.check_pump_load`` rather than a chart, since it's a
single pump-vs-rating comparison per scenario — best surfaced as a clear
warning message, not a plot.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from ..utils.constants import SNI_VELOCITY_MAX


def pareto_loss_figure(head_loss_result) -> go.Figure:
    """Pareto chart of head-loss sources for one scenario (Lean *Muda*).

    Breaks total head loss into its major (friction) component and each
    individual fitting's minor-loss contribution, sorted descending, with
    a cumulative-percentage line — the classic Pareto view for identifying
    which waste sources to address first.

    Parameters
    ----------
    head_loss_result : hydraulics.head_loss.HeadLossResult
        Must have ``major_loss_m`` and (optionally) a ``fittings`` dict of
        per-fitting head loss in metres (as returned by
        ``hydraulics.head_loss.total_head_loss``).

    Returns
    -------
    plotly.graph_objects.Figure
    """
    sources = {"Friction (major loss)": head_loss_result.major_loss_m}
    if head_loss_result.fittings:
        sources.update(head_loss_result.fittings)

    items = sorted(sources.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    values = np.array([v for _, v in items])
    total = values.sum()
    cumulative_pct = np.cumsum(values) / total * 100 if total > 0 else np.zeros_like(values)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=values, name="Head loss (m)",
        marker_color="#d62728", yaxis="y1",
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=cumulative_pct, name="Cumulative %",
        mode="lines+markers", line=dict(color="#1f3b57", width=2),
        yaxis="y2",
    ))
    fig.update_layout(
        title="Pareto Chart of Head-Loss Sources (Muda)",
        xaxis_title="Loss source",
        yaxis=dict(title="Head loss (m)", side="left"),
        yaxis2=dict(title="Cumulative %", side="right", overlaying="y",
                     range=[0, 105], showgrid=False),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=50, r=50, t=70, b=40),
    )
    return fig


def utilization_heatmap_figure(summary: pd.DataFrame) -> go.Figure:
    """Heatmap of pipe-velocity utilization across scenarios (Lean *Mura*).

    Utilization is expressed as velocity relative to the SNI-recommended
    band, normalized so that 0% = no flow, 100% = at the SNI maximum
    (2.0 m/s), and values can exceed 100% for over-utilized (too-fast)
    segments. A diverging colorscale centered on the recommended band
    makes both under-utilized (cold) and over-utilized (hot) segments
    immediately visible side by side — the unevenness signal Mura is
    meant to catch.

    Parameters
    ----------
    summary : pd.DataFrame
        Must have ``scenario`` and ``velocity_m_s`` columns (as returned
        by ``simulation.config_loader.scenarios_summary_table``).

    Returns
    -------
    plotly.graph_objects.Figure
    """
    utilization_pct = summary["velocity_m_s"] / SNI_VELOCITY_MAX * 100

    fig = go.Figure(data=go.Heatmap(
        z=[utilization_pct.tolist()],
        x=summary["scenario"].tolist(),
        y=["Utilization"],
        colorscale=[
            [0.0, "#2166ac"],   # under-utilized (cold)
            [0.45, "#67a9cf"],
            [0.5, "#f7f7f7"],   # ~balanced, near SNI max
            [0.55, "#fddbc7"],
            [1.0, "#b2182b"],   # over-utilized (hot)
        ],
        zmid=100,
        text=[[f"{v:.0f}%" for v in utilization_pct]],
        texttemplate="%{text}",
        textfont=dict(size=14),
        colorbar=dict(title="% of SNI max velocity"),
    ))
    fig.update_layout(
        title="Pipe Utilization Across Scenarios (Mura)",
        template="plotly_white",
        margin=dict(l=80, r=20, t=50, b=40),
        height=220,
    )
    return fig


def waste_ranking_figure(summary: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart ranking scenarios by exergy destroyed (Muda),
    the direct quantitative waste signal, log-scaled since scenarios in
    this analysis can differ by orders of magnitude.

    Parameters
    ----------
    summary : pd.DataFrame
        Must have ``scenario`` and ``exergy_destroyed_W`` columns.
    """
    sorted_df = summary.sort_values("exergy_destroyed_W", ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=sorted_df["exergy_destroyed_W"], y=sorted_df["scenario"],
        orientation="h", marker_color="#d62728",
    ))
    fig.update_layout(
        title="Exergy Destroyed by Scenario — Waste Ranking (Muda)",
        xaxis_title="Exergy destroyed (W)",
        xaxis_type="log",
        template="plotly_white",
        margin=dict(l=120, r=20, t=50, b=40),
    )
    return fig
