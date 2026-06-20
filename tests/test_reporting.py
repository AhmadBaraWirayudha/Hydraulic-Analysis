"""
Unit tests for src/reporting/ — figure generation and PDF report assembly.

These are lighter-weight smoke/sanity tests (file exists, has pages, key
inputs are honored) rather than pixel-level checks, since the report's
visual correctness was verified manually by rendering pages to PNG.
"""

import pandas as pd
import pytest

from src.reporting.figures import (
    fig_head_loss_comparison, fig_diameter_sweep, fig_energy_balance,
    fig_monte_carlo_histogram,
)
from src.reporting.build_report import generate_report, register_fonts


@pytest.fixture
def tmp_figdir(tmp_path):
    d = tmp_path / "figures"
    d.mkdir()
    return d


def test_fig_head_loss_comparison_creates_file(tmp_figdir):
    summary = pd.DataFrame({
        "scenario": ["half_inch_baseline", "four_inch_baseline"],
        "total_loss_m": [137.0, 0.008],
    })
    path = fig_head_loss_comparison(summary, tmp_figdir / "fig1.png")
    assert path.exists()
    assert path.stat().st_size > 0


def test_fig_diameter_sweep_creates_file(tmp_figdir):
    sweep_df = pd.DataFrame({
        "diameter_m": [0.02, 0.05, 0.1],
        "total_loss_m": [10.0, 1.0, 0.1],
    })
    path = fig_diameter_sweep(sweep_df, tmp_figdir / "fig2.png")
    assert path.exists()


def test_fig_energy_balance_handles_orders_of_magnitude_difference(tmp_figdir):
    """The composition chart should not divide-by-zero or crash when one
    scenario's total power is many orders of magnitude smaller than another's."""
    rows = [
        dict(label="big", motor_loss_W=100.0, pump_loss_W=200.0,
             useful_work_W=0.0, exergy_destroyed_W=700.0),
        dict(label="tiny", motor_loss_W=0.001, pump_loss_W=0.002,
             useful_work_W=0.0, exergy_destroyed_W=0.05),
    ]
    path = fig_energy_balance(rows, tmp_figdir / "fig4.png")
    assert path.exists()


def test_fig_energy_balance_handles_all_zero_row(tmp_figdir):
    """A scenario with zero total power (e.g. zero flow) shouldn't crash
    the normalization (division by zero)."""
    rows = [
        dict(label="zero", motor_loss_W=0.0, pump_loss_W=0.0,
             useful_work_W=0.0, exergy_destroyed_W=0.0),
    ]
    path = fig_energy_balance(rows, tmp_figdir / "fig4_zero.png")
    assert path.exists()


def test_fig_monte_carlo_histogram_creates_file(tmp_figdir):
    mc_df = pd.DataFrame({"total_loss_m": [0.01, 0.012, 0.009, 0.015, 0.008] * 20})
    path = fig_monte_carlo_histogram(mc_df, "total_loss_m", tmp_figdir / "fig5.png")
    assert path.exists()


def test_register_fonts_returns_valid_font_name():
    font = register_fonts()
    assert font in ("DejaVuSans", "Helvetica")


def test_generate_report_produces_valid_pdf(tmp_path):
    """End-to-end: generate the report against the real configs/ directory
    and confirm a non-trivial, multi-page PDF is produced."""
    from pypdf import PdfReader

    output_pdf = tmp_path / "test_report.pdf"
    figures_dir = tmp_path / "figures"

    result_path = generate_report(
        output_pdf=output_pdf, figures_dir=figures_dir, config_dir="configs"
    )

    assert result_path == output_pdf
    assert output_pdf.exists()
    assert output_pdf.stat().st_size > 10_000  # not a near-empty/broken PDF

    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) >= 5
    assert "Hydraulic" in (reader.metadata.title or "")

    # Figures should have been generated alongside the PDF.
    pngs = list(figures_dir.glob("*.png"))
    assert len(pngs) == 6
