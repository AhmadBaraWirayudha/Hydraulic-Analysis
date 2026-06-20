# User Guide

## 1. Installation

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Running a single scenario

```python
from src.simulation.scenario import run_simulation

result = run_simulation(
    diameter_m=0.1016,      # 4 inch
    flow_rate_m3s=0.0005,   # 0.5 L/s
    length_m=100.0,
)
```

`result` is a `ScenarioResult` with:

| Attribute | Meaning |
|---|---|
| `result.head_loss.velocity_m_s` | Mean flow velocity [m/s] |
| `result.head_loss.reynolds` | Reynolds number |
| `result.head_loss.friction_factor` | Darcy friction factor f |
| `result.head_loss.major_loss_m` | Friction head loss [m] |
| `result.head_loss.minor_loss_m` | Fitting head loss [m] |
| `result.head_loss.total_loss_m` | Total head loss [m] |
| `result.pressure_drop` | Friction pressure drop [Pa] (property, excludes static lift) |
| `result.total_head_m` | Total head the pump supplies: losses + static lift (property) |
| `result.pump.shaft_power_W` | Required pump shaft power [W] |
| `result.efficiency` | Overall pump-train efficiency (property) |
| `result.exergy.exergy_destruction_W` | Exergy destroyed to friction only [W] |
| `result.velocity_warning` | `None` or an SNI-guideline warning string |
| `result.pump_load_warning` | `None`, or a Muri (overburden) warning if `rated_power_W` was set and load exceeds 80% |

By default `static_head_m=0.0` (a pure friction-loss analysis, matching
the reference report). Set it to model a water tower's elevation or a
minimum required delivery pressure — that portion is treated as *useful*
work (not destroyed exergy), since lifting/pressurizing water is
reversible in the Gouy-Stodola sense, unlike frictional dissipation:

```python
result = run_simulation(
    diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
    static_head_m=20.0,   # e.g. a 20 m water tower
)
```

If any input is unphysical (negative flow, zero diameter, roughness ≥
diameter, pump efficiency outside (0,1], etc.) a `ValueError` is raised
immediately with a specific message — catch it where you call
`run_simulation`.

## 3. Comparing pipe diameters (the original report's use case)

```python
import numpy as np
from src.simulation.scenario import PipeScenario
from src.simulation.sensitivity import sweep_parameter

base = PipeScenario(diameter_m=0.0127, flow_rate_m3s=0.0005, length_m=100.0)
df = sweep_parameter(base, "diameter_m", [0.0127, 0.1016])  # 1/2" vs 4"
print(df[["diameter_m", "velocity_m_s", "total_loss_m", "shaft_power_W"]])
```

See `notebooks/compare_pipes.ipynb` for the full worked comparison with plots.

## 4. Uncertainty analysis (Monte Carlo)

```python
from src.simulation.monte_carlo import run_monte_carlo, ParameterUncertainty, summary_statistics

uncertainties = [
    ParameterUncertainty("flow_rate_m3s", "triangular",
                          {"low": 0.0003, "mode": 0.0005, "high": 0.0009}),
    ParameterUncertainty("roughness_m", "uniform",
                          {"low": 1.0e-6, "high": 3.0e-6}),
]

mc_df = run_monte_carlo(base, uncertainties, n_samples=2000, seed=42)
print(summary_statistics(mc_df, columns=["total_loss_m", "shaft_power_W"]))
```

See `notebooks/uncertainty.ipynb` for histograms and percentile bands.

## 5. Exergy analysis

```python
print(f"Exergy destroyed: {result.exergy.exergy_destruction_W:.2f} W")
print(f"As fraction of shaft power: {result.exergy.exergy_destruction_fraction:.1%}")
```

See `notebooks/exergy_analysis.ipynb` for the full Gouy-Stodola write-up.

## 6. Loading scenarios from config files

There are two levels of config support:

**Single scenario from a flat dict** — useful for quick scripting:

```python
import yaml
from src.simulation.scenario import load_scenario_from_config

with open("configs/pipe_config.yaml") as f:
    pipes = yaml.safe_load(f)["pipes"]

scenario = load_scenario_from_config({
    **pipes["four_inch"],
    "flow_rate_m3s": 0.0005,
})
```

**Full config-driven pipeline** — cross-references all three YAML files
(`pipe_config.yaml`, `fluid_config.yaml`, `scenario_config.yaml`) and runs
every named scenario, plus the Monte Carlo and sensitivity blocks defined
there, with no hardcoded values in your script:

```python
from src.simulation.config_loader import load_pipeline

pipeline = load_pipeline(config_dir="configs")

print(pipeline["summary"])  # one row per scenario: head loss, shaft power, exergy, ...

# Run the Monte Carlo / sensitivity blocks defined in scenario_config.yaml
from src.simulation.config_loader import run_monte_carlo_from_config, run_sensitivity_from_config

base = list(pipeline["scenarios"].values())[0]
mc_df = run_monte_carlo_from_config(base, pipeline["monte_carlo_config"])
sweeps = run_sensitivity_from_config(base, pipeline["sensitivity_config"])
```

Adding a new scenario, pipe, or fluid means editing YAML — no code changes
required. Cross-references are validated up front: a scenario naming a
pipe or fluid key that doesn't exist in `pipe_config.yaml` /
`fluid_config.yaml` raises a clear `ValueError` immediately, rather than
failing deep inside a simulation run.

## 7. Running the dashboard

```bash
streamlit run streamlit_app/app.py
```

Navigate: **Input** (set parameters, run) → **Compare** (scenarios loaded
straight from `configs/*.yaml`) → **Results** (metrics, pressure curve,
energy Sankey) → **Lean Dashboard** (Muda waste ranking + Pareto, Mura
utilization heatmap, Muri pump-overburden alerts, across all scenarios) →
**About** (methodology/references).

To see the Muri check in action, set `rated_power_W` on a scenario in
`configs/scenario_config.yaml` — both shipped scenarios already have one
configured, deliberately demonstrating both an overloaded and a safely
oversized pump:

```yaml
scenarios:
  - name: "half_inch_baseline"
    # ...
    rated_power_W: 750.0   # undersized vs. ~992 W required -> overloaded warning
```

## 8. Generating the PDF report

```bash
python -m src.reporting.build_report
```

Runs the full config-driven pipeline and produces:
- `reports/figures/*.png` — head loss comparison, diameter sensitivity,
  pressure profile, energy balance, and Monte Carlo histogram
- `reports/final_report.pdf` — methodology, scenario comparison table,
  all figures, Monte Carlo summary table, and Lean/Poka-Yoke notes

Regenerate any time `configs/*.yaml` changes — there are no hardcoded
values in the report itself. To customize the output location:

```python
from src.reporting.build_report import generate_report

generate_report(
    output_pdf="reports/custom_report.pdf",
    figures_dir="reports/custom_figures",
    config_dir="configs",
)
```

## 9. Running tests

```bash
pytest --maxfail=1 --disable-warnings -q
```
