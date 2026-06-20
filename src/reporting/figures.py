"""
Static (matplotlib) figure generation for the PDF report.

These are deliberately separate from the interactive Plotly figures in
``src/plots/`` — Plotly figures are for the Streamlit dashboard; these are
flattened PNGs meant to be embedded in ``reports/final_report.pdf``.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless rendering, no display needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "figure.dpi": 150,
})


def fig_head_loss_comparison(summary: pd.DataFrame, out_path: Path) -> Path:
    """Bar chart: total head loss by scenario."""
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    colors = ["#d62728" if "half" in s.lower() or "1/2" in s.lower() else "#2ca02c"
              for s in summary["scenario"]]
    bars = ax.bar(summary["scenario"], summary["total_loss_m"], color=colors)
    ax.set_ylabel(r"Head loss, $h_f$ (m)")
    ax.set_title("Total Head Loss by Scenario")
    ax.bar_label(bars, fmt="%.3f", padding=3)
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def fig_diameter_sweep(sweep_df: pd.DataFrame, out_path: Path) -> Path:
    """Line chart: head loss vs. diameter (log-log), the core sensitivity result."""
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.plot(sweep_df["diameter_m"] * 1000, sweep_df["total_loss_m"],
            marker="o", color="#1f77b4", linewidth=2)
    ax.set_xlabel("Diameter (mm)")
    ax.set_ylabel(r"Head loss, $h_f$ (m)")
    ax.set_yscale("log")
    ax.set_title("Head Loss vs. Pipe Diameter")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def fig_pressure_profile(profiles: dict[str, tuple[np.ndarray, np.ndarray]], out_path: Path) -> Path:
    """Overlaid pressure-vs-distance lines for multiple scenarios.

    Parameters
    ----------
    profiles : dict[str, (distances_m, pressure_Pa)]
    """
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    for label, (distances, pressures) in profiles.items():
        ax.plot(distances, pressures, label=label, linewidth=2)
    ax.set_xlabel("Distance along pipe (m)")
    ax.set_ylabel("Pressure remaining (Pa)")
    ax.set_title("Pressure Profile Along Pipeline")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def fig_energy_balance(rows: list[dict], out_path: Path) -> Path:
    """100%-stacked bar chart: composition of shaft power (motor/pump losses,
    useful work, exergy destroyed) per scenario, with absolute totals annotated.

    A normalized (100%) stacked bar is used rather than an absolute-power
    stacked bar because scenarios in this analysis can differ in total power
    by several orders of magnitude (e.g. a 1/2" vs. 4" pipe) — on an absolute
    scale, the smaller scenario's bar would be visually indistinguishable
    from zero. Normalizing to composition keeps every scenario's breakdown
    visible; the absolute total is preserved as a text annotation instead.

    Parameters
    ----------
    rows : list of dicts with keys:
        label, motor_loss_W, pump_loss_W, useful_work_W, exergy_destroyed_W
    """
    labels = [r["label"] for r in rows]
    motor = np.array([r["motor_loss_W"] for r in rows])
    pump = np.array([r["pump_loss_W"] for r in rows])
    useful = np.array([r["useful_work_W"] for r in rows])
    destroyed = np.array([r["exergy_destroyed_W"] for r in rows])
    totals = motor + pump + useful + destroyed
    totals_safe = np.where(totals > 0, totals, 1.0)  # avoid div-by-zero

    motor_pct = motor / totals_safe * 100
    pump_pct = pump / totals_safe * 100
    destroyed_pct = destroyed / totals_safe * 100
    useful_pct = useful / totals_safe * 100

    fig, ax = plt.subplots(figsize=(6.5, 4.3))
    x = np.arange(len(labels))
    ax.bar(x, motor_pct, label="Motor losses", color="#1f77b4")
    ax.bar(x, pump_pct, bottom=motor_pct, label="Pump losses", color="#ff7f0e")
    ax.bar(x, destroyed_pct, bottom=motor_pct + pump_pct,
           label="Exergy destroyed (friction)", color="#d62728")
    ax.bar(x, useful_pct, bottom=motor_pct + pump_pct + destroyed_pct,
           label="Useful work delivered", color="#17becf")

    for i, total in enumerate(totals):
        ax.text(i, 103, f"Total:\n{total:,.3g} W", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Share of shaft power output (%)")
    ax.set_ylim(0, 122)
    ax.set_title("Shaft Power Energy Balance (Composition)")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path


def fig_monte_carlo_histogram(mc_df: pd.DataFrame, column: str, out_path: Path,
                               x_label: str | None = None) -> Path:
    """Histogram of a Monte Carlo output column, with P5/median/P95 marked."""
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.hist(mc_df[column], bins=40, color="#9467bd", alpha=0.85, edgecolor="white")
    p05, med, p95 = mc_df[column].quantile([0.05, 0.5, 0.95])
    for val, style, lab in [(p05, "--", "P5"), (med, "-", "Median"), (p95, "--", "P95")]:
        ax.axvline(val, color="black", linestyle=style, linewidth=1)
        ax.text(val, ax.get_ylim()[1] * 0.95, lab, rotation=90, va="top", fontsize=8)
    ax.set_xlabel(x_label or column)
    ax.set_ylabel("Count")
    ax.set_title(f"Monte Carlo Distribution: {x_label or column}")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def fig_pareto_loss(head_loss_result, out_path: Path) -> Path:
    """Pareto chart of head-loss sources (Lean *Muda*): friction vs. each
    fitting's contribution, sorted descending, with a cumulative-% line.

    Parameters
    ----------
    head_loss_result : hydraulics.head_loss.HeadLossResult
    """
    sources = {"Friction\n(major loss)": head_loss_result.major_loss_m}
    if head_loss_result.fittings:
        sources.update(head_loss_result.fittings)
    items = sorted(sources.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    values = np.array([v for _, v in items])
    total = values.sum()
    cumulative_pct = np.cumsum(values) / total * 100 if total > 0 else np.zeros_like(values)

    fig, ax1 = plt.subplots(figsize=(6.5, 3.8))
    ax1.bar(labels, values, color="#d62728")
    ax1.set_ylabel("Head loss (m)")
    ax1.set_title("Pareto Chart of Head-Loss Sources (Muda)")
    ax1.tick_params(axis="x", labelsize=8)
    ax2 = ax1.twinx()
    ax2.plot(range(len(labels)), cumulative_pct, color="#1f3b57", marker="o", linewidth=2)
    ax2.set_ylabel("Cumulative %")
    ax2.set_ylim(0, 110)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    return out_path
