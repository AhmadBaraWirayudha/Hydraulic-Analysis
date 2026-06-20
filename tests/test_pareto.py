"""
Unit tests for src/plots/pareto.py — Muda (Pareto waste ranking) and
Mura (utilization heatmap) visualizations.
"""

import pandas as pd
import pytest

from src.plots.pareto import pareto_loss_figure, utilization_heatmap_figure, waste_ranking_figure
from src.hydraulics.head_loss import total_head_loss
from src.utils.constants import PVC_ROUGHNESS, WATER_DENSITY, WATER_VISCOSITY


@pytest.fixture
def head_loss_with_fittings():
    return total_head_loss(
        flow_rate_m3s=0.0005, diameter_m=0.0127, length_m=100.0,
        roughness_m=PVC_ROUGHNESS, density=WATER_DENSITY, viscosity=WATER_VISCOSITY,
        fittings={"elbow_90_standard": 4, "gate_valve_open": 1},
    )


@pytest.fixture
def head_loss_no_fittings():
    return total_head_loss(
        flow_rate_m3s=0.0005, diameter_m=0.0127, length_m=100.0,
        roughness_m=PVC_ROUGHNESS, density=WATER_DENSITY, viscosity=WATER_VISCOSITY,
        fittings=None,
    )


@pytest.fixture
def summary_df():
    return pd.DataFrame({
        "scenario": ["half_inch_baseline", "four_inch_baseline"],
        "velocity_m_s": [3.947, 0.062],
        "exergy_destroyed_W": [669.969, 0.038],
    })


# ── pareto_loss_figure (Muda) ─────────────────────────────────────────────
def test_pareto_loss_figure_includes_friction_and_fittings(head_loss_with_fittings):
    fig = pareto_loss_figure(head_loss_with_fittings)
    assert len(fig.data) == 2  # bar + cumulative line
    bar_labels = list(fig.data[0]["x"])
    assert "Friction (major loss)" in bar_labels
    assert "elbow_90_standard" in bar_labels
    assert "gate_valve_open" in bar_labels


def test_pareto_loss_figure_sorted_descending(head_loss_with_fittings):
    fig = pareto_loss_figure(head_loss_with_fittings)
    values = list(fig.data[0]["y"])
    assert values == sorted(values, reverse=True)


def test_pareto_loss_figure_cumulative_reaches_100_percent(head_loss_with_fittings):
    fig = pareto_loss_figure(head_loss_with_fittings)
    cumulative = list(fig.data[1]["y"])
    assert cumulative[-1] == pytest.approx(100.0, rel=1e-6)


def test_pareto_loss_figure_works_with_no_fittings(head_loss_no_fittings):
    """Should not crash when there are no minor losses at all."""
    fig = pareto_loss_figure(head_loss_no_fittings)
    bar_labels = list(fig.data[0]["x"])
    assert bar_labels == ["Friction (major loss)"]


# ── utilization_heatmap_figure (Mura) ─────────────────────────────────────
def test_utilization_heatmap_creates_one_row_per_call(summary_df):
    fig = utilization_heatmap_figure(summary_df)
    assert len(fig.data) == 1
    z = fig.data[0]["z"]
    assert len(z) == 1
    assert len(z[0]) == 2  # two scenarios


def test_utilization_heatmap_values_reflect_velocity_ratio(summary_df):
    fig = utilization_heatmap_figure(summary_df)
    z = fig.data[0]["z"][0]
    # four_inch_baseline (v=0.062 m/s) should show far lower utilization
    # than half_inch_baseline (v=3.947 m/s).
    assert z[0] > z[1]
    assert z[1] < 10  # four-inch: well under 10% of SNI max


def test_utilization_heatmap_x_labels_match_scenarios(summary_df):
    fig = utilization_heatmap_figure(summary_df)
    assert list(fig.data[0]["x"]) == ["half_inch_baseline", "four_inch_baseline"]


# ── waste_ranking_figure (Muda) ───────────────────────────────────────────
def test_waste_ranking_figure_sorts_ascending_for_horizontal_bar(summary_df):
    fig = waste_ranking_figure(summary_df)
    y_order = list(fig.data[0]["y"])
    # Horizontal bar ascending means smallest waste plotted first (bottom).
    assert y_order[0] == "four_inch_baseline"
    assert y_order[-1] == "half_inch_baseline"


def test_waste_ranking_figure_uses_log_x_axis(summary_df):
    fig = waste_ranking_figure(summary_df)
    assert fig.layout.xaxis.type == "log"
