"""
Assembles ``reports/final_report.pdf`` — a full engineering report covering
methodology, scenario comparison, pressure profile, diameter sensitivity,
exergy/energy balance, Monte Carlo uncertainty, and Lean/Poka-Yoke notes.

Run directly to (re)generate the report from the current ``configs/*.yaml``:

    python -m src.reporting.build_report

Uses DejaVu Sans (bundled with most Linux distros) instead of the default
Helvetica so Greek symbols (ε, ρ, η, ν, μ, Δ) used in the methodology
section render correctly — the PDF skill's base-14 fonts (WinAnsiEncoding)
do not include Greek glyphs.
"""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image, KeepTogether,
)

from ..simulation.config_loader import (
    load_pipeline, run_monte_carlo_from_config, run_sensitivity_from_config,
)
from ..simulation.monte_carlo import summary_statistics
from ..utils.constants import GRAVITY
from .figures import (
    fig_head_loss_comparison, fig_diameter_sweep, fig_pressure_profile,
    fig_energy_balance, fig_monte_carlo_histogram, fig_pareto_loss,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEJAVU_DIR = Path("/usr/share/fonts/truetype/dejavu")


def fitted_image(path: str | Path, width: float) -> Image:
    """Build a reportlab Image flowable scaled to ``width``, preserving the
    PNG's actual aspect ratio (read from the file) rather than assuming a
    fixed figsize ratio that could silently drift out of sync with
    ``figures.py``."""
    from PIL import Image as PILImage
    with PILImage.open(path) as im:
        px_w, px_h = im.size
    return Image(str(path), width=width, height=width * px_h / px_w)


# ── Font registration ─────────────────────────────────────────────────────
def register_fonts() -> str:
    """Register DejaVu Sans with reportlab; fall back to Helvetica if absent.

    Returns
    -------
    str
        "DejaVuSans" if registration succeeded, else "Helvetica".
    """
    regular = DEJAVU_DIR / "DejaVuSans.ttf"
    bold = DEJAVU_DIR / "DejaVuSans-Bold.ttf"
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))
        return "DejaVuSans"
    return "Helvetica"


def build_styles(base_font: str) -> dict:
    bold_font = f"{base_font}-Bold" if base_font == "DejaVuSans" else "Helvetica-Bold"
    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle("ReportTitle", parent=base["Title"], fontName=bold_font,
                                 fontSize=22, leading=26, spaceAfter=6),
        "Subtitle": ParagraphStyle("ReportSubtitle", parent=base["Normal"], fontName=base_font,
                                    fontSize=13, leading=17, textColor=colors.HexColor("#444444"),
                                    spaceAfter=4),
        "Meta": ParagraphStyle("ReportMeta", parent=base["Normal"], fontName=base_font,
                                fontSize=10, textColor=colors.HexColor("#777777")),
        "H1": ParagraphStyle("H1", parent=base["Heading1"], fontName=bold_font,
                              fontSize=15, spaceBefore=14, spaceAfter=8,
                              textColor=colors.HexColor("#1a3c5e")),
        "H2": ParagraphStyle("H2", parent=base["Heading2"], fontName=bold_font,
                              fontSize=12, spaceBefore=10, spaceAfter=6,
                              textColor=colors.HexColor("#1a3c5e")),
        "Body": ParagraphStyle("Body", parent=base["Normal"], fontName=base_font,
                                fontSize=10, leading=14, spaceAfter=6, alignment=4),  # justify
        "Caption": ParagraphStyle("Caption", parent=base["Normal"], fontName=base_font,
                                   fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"),
                                   spaceAfter=10, alignment=1),
        "Bullet": ParagraphStyle("Bullet", parent=base["Normal"], fontName=base_font,
                                  fontSize=10, leading=14, leftIndent=14, bulletIndent=4,
                                  spaceAfter=3),
    }
    return styles


# ── Table builders ────────────────────────────────────────────────────────
def _header_style(base_font: str) -> ParagraphStyle:
    bold_font = f"{base_font}-Bold" if base_font == "DejaVuSans" else "Helvetica-Bold"
    return ParagraphStyle("TableHeader", fontName=bold_font, fontSize=8.5, leading=10,
                           textColor=colors.white, alignment=1)


def _styled_table(data: list[list], col_widths: list[float] | None, base_font: str) -> Table:
    bold_font = f"{base_font}-Bold" if base_font == "DejaVuSans" else "Helvetica-Bold"
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTNAME", (0, 1), (-1, -1), base_font),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3c5e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def summary_table_flowable(summary: pd.DataFrame, base_font: str) -> Table:
    hstyle = _header_style(base_font)
    header = [Paragraph(h, hstyle) for h in
               ["Scenario", "D<br/>(mm)", "Q<br/>(L/s)", "v<br/>(m/s)", "Re", "h_f<br/>(m)",
                "Δp<br/>(Pa)", "P_shaft<br/>(W)", "Exergy<br/>(W)"]]
    data = [header]
    for _, r in summary.iterrows():
        data.append([
            r["scenario"],
            f"{r['diameter_m']*1000:.1f}",
            f"{r['flow_rate_m3s']*1000:.3f}",
            f"{r['velocity_m_s']:.3f}",
            f"{r['reynolds']:,.0f}",
            f"{r['total_loss_m']:.4f}",
            f"{r['pressure_drop_Pa']:,.1f}",
            f"{r['shaft_power_W']:,.2f}",
            f"{r['exergy_destroyed_W']:.3f}",
        ])
    # Total width must fit within the page's usable area: A4 (21.0cm) minus
    # 2.2cm left/right margins = 16.6cm available.
    widths = [2.9*cm, 1.4*cm, 1.4*cm, 1.5*cm, 1.7*cm, 1.6*cm, 1.9*cm, 1.9*cm, 1.9*cm]
    return _styled_table(data, widths, base_font)


def mc_summary_table_flowable(stats: pd.DataFrame, base_font: str) -> Table:
    hstyle = _header_style(base_font)
    header = [Paragraph("Statistic", hstyle)] + [Paragraph(c, hstyle) for c in stats.columns]
    data = [header]
    for idx, row in stats.iterrows():
        data.append([idx] + [f"{v:,.4g}" for v in row.values])
    return _styled_table(data, None, base_font)


# ── Main report generation ────────────────────────────────────────────────
def generate_report(
    output_pdf: str | Path = None,
    figures_dir: str | Path = None,
    config_dir: str | Path = None,
) -> Path:
    """Generate the full PDF report from the current configs/*.yaml.

    Parameters
    ----------
    output_pdf  : str | Path | None  defaults to reports/final_report.pdf
    figures_dir : str | Path | None  defaults to reports/figures/
    config_dir  : str | Path | None  defaults to configs/

    Returns
    -------
    Path to the generated PDF.
    """
    output_pdf = Path(output_pdf) if output_pdf else PROJECT_ROOT / "reports" / "final_report.pdf"
    figures_dir = Path(figures_dir) if figures_dir else PROJECT_ROOT / "reports" / "figures"
    config_dir = Path(config_dir) if config_dir else PROJECT_ROOT / "configs"
    figures_dir.mkdir(parents=True, exist_ok=True)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    base_font = register_fonts()
    styles = build_styles(base_font)

    # ── Run the config-driven pipeline ───────────────────────────────────
    pipeline = load_pipeline(config_dir=config_dir)
    scenarios = pipeline["scenarios"]
    results = pipeline["results"]
    summary = pipeline["summary"]

    base_scenario = list(scenarios.values())[-1]  # use the larger/recommended pipe as MC base

    # ── Generate figures ──────────────────────────────────────────────────
    fig1 = fig_head_loss_comparison(summary, figures_dir / "fig1_head_loss_comparison.png")

    sensitivity_sweeps = run_sensitivity_from_config(base_scenario, pipeline["sensitivity_config"])
    fig2 = fig_diameter_sweep(sensitivity_sweeps["diameter_m"], figures_dir / "fig2_diameter_sweep.png")

    profiles = {}
    for name, r in results.items():
        s = r.scenario
        n_pts = 30
        distances = np.linspace(0, s.length_m, n_pts)
        major_per_m = r.head_loss.major_loss_m / s.length_m if s.length_m > 0 else 0.0
        cum_loss = major_per_m * distances + (r.head_loss.minor_loss_m * (distances / s.length_m))
        p0 = s.density * GRAVITY * r.head_loss.total_loss_m
        pressure_remaining = p0 - s.density * GRAVITY * cum_loss
        profiles[r.scenario.label or name] = (distances, pressure_remaining)
    fig3 = fig_pressure_profile(profiles, figures_dir / "fig3_pressure_profile.png")

    energy_rows = []
    for name, r in results.items():
        p_shaft = r.pump.shaft_power_W
        motor_loss = p_shaft * (1 - r.scenario.eta_motor)
        pump_loss = (p_shaft - motor_loss) * (1 - r.scenario.eta_pump)
        x_destroyed = r.exergy.exergy_destruction_W
        useful = max(r.pump.hydraulic_power_W - x_destroyed, 0.0)
        energy_rows.append(dict(label=name, motor_loss_W=motor_loss, pump_loss_W=pump_loss,
                                 useful_work_W=useful, exergy_destroyed_W=x_destroyed))
    fig4 = fig_energy_balance(energy_rows, figures_dir / "fig4_energy_balance.png")

    mc_df = run_monte_carlo_from_config(base_scenario, pipeline["monte_carlo_config"])
    fig5 = fig_monte_carlo_histogram(mc_df, "total_loss_m", figures_dir / "fig5_mc_histogram.png",
                                      x_label="Total head loss (m)")
    mc_stats = summary_statistics(
        mc_df, columns=["total_loss_m", "pressure_drop_Pa", "shaft_power_W", "exergy_destroyed_W"]
    )

    # Pareto chart (Muda): break down loss sources for the worst-case scenario.
    worst_name = summary.loc[summary["total_loss_m"].idxmax(), "scenario"]
    fig6 = fig_pareto_loss(results[worst_name].head_loss, figures_dir / "fig6_pareto.png")

    # ── Assemble PDF ──────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        str(output_pdf), pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm, topMargin=2.2*cm, bottomMargin=2.0*cm,
        title="Hydraulic Distribution Pipeline Analysis Report",
        author="Ahmad Bara Wirayudha",
    )
    story = []

    # Title block
    story.append(Spacer(1, 2.5*cm))
    story.append(Paragraph("Hydraulic Distribution Pipeline Analysis Report", styles["Title"]))
    story.append(Paragraph(
        "Evaluasi Diameter Pipa Distribusi Air Bersih — Perumahan Citra Srie Pradita",
        styles["Subtitle"]
    ))
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph(
        "Darcy–Weisbach / Swamee–Jain hydraulic analysis, pump sizing, exergy "
        "(Gouy–Stodola) evaluation, and Monte Carlo uncertainty quantification, "
        "generated by the <i>hydraulic-analysis</i> config-driven toolkit.",
        styles["Body"]
    ))
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("Author: Ahmad Bara Wirayudha", styles["Meta"]))
    story.append(Paragraph(f"Generated: {date.today().isoformat()}", styles["Meta"]))
    story.append(Paragraph("Toolkit version: 0.1.0", styles["Meta"]))
    story.append(PageBreak())

    # 1. Introduction
    story.append(Paragraph("1. Introduction &amp; Background", styles["H1"]))
    story.append(Paragraph(
        "This report evaluates pipe-diameter choices for a residential water "
        "distribution network, comparing a narrow (1/2 inch) supply pipe against "
        "a wide (4 inch) distribution pipe under an identical design flow rate. "
        "The analysis was originally carried out as a standalone calculation for "
        "the Citra Srie Pradita housing estate and has since been rebuilt as a "
        "reusable, tested, config-driven engineering package so that new pipe "
        "sizes, fluids, or operating conditions can be evaluated by editing a "
        "YAML configuration file rather than rewriting calculations.",
        styles["Body"]
    ))

    # 2. Methodology
    story.append(Paragraph("2. Methodology", styles["H1"]))
    story.append(Paragraph(
        "Major (friction) head loss is computed with the Darcy–Weisbach equation, "
        "h<sub>f</sub> = f (L/D)(v<super>2</super>/2g), where the Darcy friction factor f is obtained from "
        "the Hagen–Poiseuille relation (f = 64/Re) in laminar flow (Re &lt; 2300), or the "
        "explicit Swamee–Jain (1976) approximation in turbulent flow:",
        styles["Body"]
    ))
    story.append(Paragraph(
        "f = 0.25 / [log<sub>10</sub>(ε/(3.7D) + 5.74/Re<super>0.9</super>)]<super>2</super>",
        ParagraphStyle("Formula", parent=styles["Body"], alignment=1, fontSize=11, spaceAfter=8)
    ))
    story.append(Paragraph(
        "Minor losses from fittings (elbows, valves, entrance/exit) are added via the "
        "K-factor method, h<sub>minor</sub> = K(v<super>2</super>/2g). Required pump shaft power is "
        "P<sub>shaft</sub> = ρgQh<sub>total</sub> / (η<sub>pump</sub> η<sub>motor</sub>), where h<sub>total</sub> includes both the friction/minor "
        "losses and any static lift or required delivery head. Frictional irreversibility is "
        "quantified via the Gouy–Stodola theorem: the exergy destroyed by friction equals "
        "ρgQh<sub>f</sub> (the friction-loss portion only — static lift is reversible, useful work, "
        "not destroyed exergy). All inputs are validated against physical plausibility "
        "bounds (Poka-Yoke) before any calculation runs, and resulting velocities are "
        "checked against the SNI 03-6481-2000 recommended range of 0.9–2.0 m/s.",
        styles["Body"]
    ))

    # 3. Scenario comparison
    story.append(Paragraph("3. Scenario Comparison", styles["H1"]))
    story.append(Paragraph(
        "Table 1 compares all scenarios defined in <font name=\"Courier\">configs/scenario_config.yaml</font>, "
        "run through the identical calculation pipeline.",
        styles["Body"]
    ))
    story.append(Spacer(1, 4))
    story.append(summary_table_flowable(summary, base_font))
    story.append(Spacer(1, 10))

    for _, row in summary.iterrows():
        if row["velocity_warning"]:
            story.append(Paragraph(f"<b>{row['scenario']}:</b> {row['velocity_warning']}", styles["Body"]))

    story.append(Spacer(1, 6))
    story.append(KeepTogether([
        fitted_image(fig1, width=15.5*cm),
        Paragraph("Figure 1. Total head loss by scenario (log scale).", styles["Caption"]),
    ]))

    half = summary[summary["scenario"].str.contains("half", case=False)]
    four = summary[summary["scenario"].str.contains("four", case=False)]
    if not half.empty and not four.empty:
        ratio = half["total_loss_m"].iloc[0] / four["total_loss_m"].iloc[0]
        story.append(Paragraph(
            f"The narrow (1/2 inch) pipe produces approximately <b>{ratio:,.0f}× higher</b> "
            f"head loss than the wide (4 inch) pipe at the same flow rate — consistent "
            f"with the Darcy–Weisbach equation's strong (roughly D<super>-5</super>) sensitivity to "
            f"diameter in the turbulent regime.",
            styles["Body"]
        ))

    # 4. Diameter sensitivity
    story.append(Paragraph("4. Diameter Sensitivity Analysis", styles["H1"]))
    story.append(Paragraph(
        "Sweeping diameter continuously (per the <font name=\"Courier\">sensitivity</font> block in "
        "<font name=\"Courier\">scenario_config.yaml</font>) shows head loss falling sharply as diameter "
        "increases, with diminishing returns beyond roughly 3 inches for this flow rate.",
        styles["Body"]
    ))
    story.append(KeepTogether([
        fitted_image(fig2, width=15.5*cm),
        Paragraph("Figure 2. Head loss vs. pipe diameter (log-log).", styles["Caption"]),
    ]))

    # 5. Pressure profile
    story.append(Paragraph("5. Pressure Profile Along the Pipeline", styles["H1"]))
    story.append(Paragraph(
        "Assuming a uniform pipe (constant diameter and roughness along its length), "
        "pressure declines approximately linearly with distance under the friction-loss "
        "contribution, with discrete step-drops at fitting locations.",
        styles["Body"]
    ))
    story.append(KeepTogether([
        fitted_image(fig3, width=15.5*cm),
        Paragraph("Figure 3. Pressure remaining vs. distance along the pipe, by scenario.", styles["Caption"]),
    ]))

    story.append(PageBreak())

    # 6. Exergy / energy balance
    story.append(Paragraph("6. Exergy &amp; Energy Balance Analysis", styles["H1"]))
    story.append(Paragraph(
        "The Gouy–Stodola theorem attributes head loss not just to a pressure deficit "
        "but to irrecoverable work potential lost to entropy generation. Figure 4 breaks "
        "down required shaft power into motor losses, pump losses, exergy destroyed to "
        "friction, and any useful work delivered (static lift). In this analysis, no "
        "static lift was configured (static_head_m = 0), so the entire hydraulic power "
        "output is destroyed to friction by construction — in a real system with a water "
        "tower or required delivery pressure, that component would appear as useful work.",
        styles["Body"]
    ))
    story.append(KeepTogether([
        fitted_image(fig4, width=15.5*cm),
        Paragraph("Figure 4. Shaft power energy balance by scenario.", styles["Caption"]),
    ]))

    story.append(PageBreak())

    # 7. Uncertainty analysis
    story.append(Paragraph("7. Uncertainty Analysis (Monte Carlo)", styles["H1"]))
    story.append(Paragraph(
        f"Flow rate and pipe roughness were sampled per the <font name=\"Courier\">monte_carlo</font> block "
        f"in <font name=\"Courier\">scenario_config.yaml</font> ({pipeline['monte_carlo_config'].get('n_samples', 'N/A')} trials) "
        f"for the <b>{base_scenario.label or 'baseline'}</b> scenario, propagating input uncertainty "
        f"through the full calculation chain rather than relying on a single point estimate.",
        styles["Body"]
    ))
    story.append(KeepTogether([
        fitted_image(fig5, width=15.5*cm),
        Paragraph("Figure 5. Monte Carlo distribution of total head loss, with P5/median/P95 marked.",
                   styles["Caption"]),
    ]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Table 2. Monte Carlo summary statistics.", styles["Body"]))
    story.append(mc_summary_table_flowable(mc_stats, base_font))

    story.append(PageBreak())

    # 8. Lean / Poka-Yoke
    story.append(Paragraph("8. Lean / Poka-Yoke Integration", styles["H1"]))
    story.append(Paragraph(
        "<b>Poka-Yoke (mistake-proofing):</b> every calculation validates diameter, "
        "length, flow rate, fluid properties, and pump efficiencies before running — "
        "implausible inputs raise a clear error rather than silently producing a wrong "
        "number. Resulting velocities are also checked against the SNI 03-6481-2000 "
        "recommended range, as shown under Table 1.",
        styles["Body"]
    ))

    story.append(Paragraph(
        f"<b>Muda (waste):</b> Figure 4 quantifies waste as exergy destroyed to friction. "
        f"Figure 6 breaks the largest contributor (<b>{worst_name}</b>) down by source — "
        f"friction vs. individual fittings — so improvement effort can target whichever "
        f"single source dominates, rather than treating head loss as one undifferentiated "
        f"number.",
        styles["Body"]
    ))
    story.append(KeepTogether([
        fitted_image(fig6, width=15.5*cm),
        Paragraph(f"Figure 6. Pareto chart of head-loss sources for {worst_name}.", styles["Caption"]),
    ]))

    story.append(Paragraph(
        "<b>Mura (unevenness):</b> comparing scenarios side by side (Table 1) surfaces "
        "load imbalance directly — in this analysis the two scenarios sit at opposite "
        "extremes of utilization (one far above, one far below the SNI-recommended "
        "velocity band), which is itself the Mura signal: capacity is unevenly matched "
        "to demand across the two pipe choices.",
        styles["Body"]
    ))

    story.append(Paragraph("<b>Muri (overburden):</b> pump shaft power vs. rated capacity, "
                            "where a rated capacity is configured:", styles["Body"]))
    any_rated = False
    for name, r in results.items():
        if r.scenario.rated_power_W is None:
            continue
        any_rated = True
        load_pct = r.pump.shaft_power_W / r.scenario.rated_power_W * 100
        line = (f"<b>{name}:</b> {r.pump.shaft_power_W:,.2f} W required vs. "
                f"{r.scenario.rated_power_W:,.2f} W rated ({load_pct:.0f}%)")
        if r.pump_load_warning:
            line += f" — {r.pump_load_warning}"
        else:
            line += " — within safe operating margin."
        story.append(Paragraph(f"• {line}", styles["Bullet"]))
    if not any_rated:
        story.append(Paragraph(
            "• No scenario has a <font name=\"Courier\">rated_power_W</font> configured "
            "in scenario_config.yaml — the Muri check is skipped until a pump rating is supplied.",
            styles["Bullet"]
        ))

    # 9. Conclusions
    story.append(Paragraph("9. Conclusions &amp; Recommendations", styles["H1"]))
    story.append(Paragraph(
        "For the evaluated flow rate, the narrow (1/2 inch) pipe is hydraulically "
        "impractical, producing both excessive head loss and a velocity far outside the "
        "SNI-recommended range. The wide (4 inch) pipe is comfortably within recommended "
        "limits at this flow rate; the diameter sensitivity analysis (Section 4) can guide "
        "selection of an intermediate size if minimizing material/installation cost is also "
        "a design objective. Sensitivity and Monte Carlo results (Sections 4 and 7) should "
        "be re-run whenever demand assumptions change — both are config-driven and require "
        "no code changes to update.",
        styles["Body"]
    ))

    # References
    story.append(Paragraph("References", styles["H2"]))
    for ref in [
        "Swamee, P.K. &amp; Jain, A.K. (1976). Explicit equations for pipe flow problems. "
        "Journal of the Hydraulics Division, ASCE, 102(5), 657–664.",
        "Bejan, A. (2016). Advanced Engineering Thermodynamics. Wiley. (Gouy–Stodola theorem)",
        "SNI 03-6481-2000 — Sistem Plambing 2000.",
        "SNI 03-7065-2005 — Tata cara perencanaan sistem plambing.",
    ]:
        story.append(Paragraph(f"• {ref}", styles["Bullet"]))

    doc.build(story)
    return output_pdf


if __name__ == "__main__":
    path = generate_report()
    print(f"Report generated: {path}")
