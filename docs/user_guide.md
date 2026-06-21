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
| `result.npsh` | `None`, or an `NPSHResult` (`.npsh_available_m`, `.margin_m`, `.margin_ratio`) if suction/vapor pressure were supplied |
| `result.npsh_warning` | `None`, or a cavitation-risk/thin-margin warning if `npsh_required_m` was also supplied |

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

## 6. Temperature-dependent properties & NPSH (cavitation)

Water's viscosity and vapor pressure both change significantly with
temperature. `src/hydraulics/fluid_properties.py` provides pre-fitted
Andrade (viscosity) and Antoine (vapor pressure) equations for water,
calibrated against standard reference data (0-100 °C; see the module's
docstring for fit accuracy):

```python
from src.hydraulics.fluid_properties import water_viscosity, water_vapor_pressure

mu_60C = water_viscosity(333.15)           # Pa.s
pv_60C = water_vapor_pressure(333.15)      # Pa
```

For a different fluid, calibrate your own coefficients from a few
reference data points:

```python
from src.hydraulics.fluid_properties import fit_andrade_coefficients

A, B = fit_andrade_coefficients(
    temperatures_K=[280, 300, 320, 340],
    viscosities_Pas=[0.0014, 0.00085, 0.00058, 0.00042],
)
```

NPSH (cavitation risk) is an optional per-scenario check — supply both
`suction_pressure_Pa` and `vapor_pressure_Pa` to compute NPSH available;
add `npsh_required_m` (from the pump's manufacturer curve) to also get a
margin warning:

```python
result = run_simulation(
    diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
    suction_pressure_Pa=101_325,   # atmospheric, open suction
    vapor_pressure_Pa=water_vapor_pressure(333.15),
    inlet_elevation_m=-1.5,         # negative = suction lift
    suction_head_loss_m=0.3,
    npsh_required_m=4.0,
)
print(result.npsh.npsh_available_m, result.npsh.margin_ratio, result.npsh_warning)
```

Margin thresholds: NPSHa < NPSHr triggers a cavitation-risk error-level
warning; a margin under 20% triggers a thin-margin warning. Both fields
are `None` by default — the check is fully optional and skipped unless
both pressures are supplied.

## 7. VFD / electrical analysis

`src/hydraulics/electrical.py` provides pump affinity laws for
variable-speed (VFD) analysis — given a pump's known performance at one
speed, scale it to another:

```python
from src.hydraulics.electrical import apply_affinity_laws, speed_ratio_for_target_flow

Q_ref, H_ref, P_ref = 0.01, 20.0, 1000.0   # known performance at full speed
ratio = speed_ratio_for_target_flow(Q_ref, flow_target_m3s=0.7 * Q_ref)
result = apply_affinity_laws(Q_ref, H_ref, P_ref, speed_ratio=ratio)
print(result.power_W)   # power drops with the CUBE of speed ratio
```

See `notebooks/vfd_energy_optimization.ipynb` for the full energy-savings
analysis — at 80% speed, power drops to ~51% of full-speed power.

Three-phase electrical power and voltage-unbalance utilities are also
included:

```python
from src.hydraulics.electrical import evaluate_three_phase_power, voltage_unbalance_percent
from src.utils.validation import check_voltage_unbalance

power = evaluate_three_phase_power(line_voltage_V=400, line_current_A=10, power_factor=0.85)
unbalance_pct = voltage_unbalance_percent([460, 467, 450])   # NEMA's own worked example -> 1.96%
print(check_voltage_unbalance(unbalance_pct))
```

Note: the precise motor-derating-factor-vs-unbalance *curve* is published
by NEMA MG1-14.36 as a graph, not a formula, and varies by motor class and
load level. `check_voltage_unbalance` only checks against NEMA's
consistently-cited 1%/5% thresholds; use
`derating_factor_from_curve(unbalance_pct, your_motor_curve_points)` to
apply your specific motor's published derating curve.

## 8. Lifecycle Cost Analysis (LCCA)

`src/economics/` translates the hydraulic results into a financial
comparison — CAPEX (pipe + pump installation) vs. the present value of
OPEX (electricity over the analysis horizon). **No real-world prices are
hardcoded** — every cost input is explicit, either supplied directly or
read from `configs/economics_config.yaml` (which itself only contains
illustrative placeholder values you should replace with real quotes).

```python
from src.simulation.config_loader import load_pipeline, load_economics_config
from src.economics.scenario_economics import compare_lifecycle_costs

pipeline = load_pipeline(config_dir="configs")
econ_config = load_economics_config(config_dir="configs")

df = compare_lifecycle_costs(pipeline["results"], econ_config=econ_config)
print(df[["scenario", "capex", "present_value_opex", "total_lifecycle_cost"]])
```

For a single scenario with your own assumptions (rather than the config
file's diameter-dependent cost curve):

```python
from src.economics.scenario_economics import EconomicAssumptions, evaluate_scenario_lifecycle_cost

assumptions = EconomicAssumptions(
    unit_cost_per_m=28.0,             # your own supplier quote
    operating_hours_per_year=8760,
    electricity_price_per_kWh=0.15,   # your local tariff
    years=20,
    discount_rate=0.07,               # your organization's discount rate
)
lcca = evaluate_scenario_lifecycle_cost(your_scenario_result, assumptions)
print(lcca.capex, lcca.present_value_opex, lcca.total_lifecycle_cost)
```

This computes factual present-value arithmetic only (consistent with the
``NPV = sum(C_t/(1+r)^t) - C0`` structure from common LCCA references,
applied to a cost stream rather than a net-cash-flow stream — lower total
is better here, unlike a conventional positive-is-good investment NPV).
It is not a substitute for financial or engineering advice on an actual
capital-allocation decision.

See the **Economics** page in the Streamlit dashboard for an interactive
version with adjustable assumptions and a break-even calculation.

## 9. Network Analysis & Water Hammer

`src/hydraulics/network.py` solves flow distribution in closed-loop pipe
networks (multiple interconnected pipes, not just one line) via the
Hardy Cross method:

```python
from src.hydraulics.network import PipeNetwork, NetworkPipe, Loop, LoopMember

pipes = [
    NetworkPipe("12", "1", "2", diameter_m=0.10, length_m=200.0, roughness_m=PVC_ROUGHNESS),
    # ... more pipes
]
loop123 = Loop("123", [LoopMember("12", +1), LoopMember("23", +1), LoopMember("13", -1)])
network = PipeNetwork(pipes, [loop123, ...], density=WATER_DENSITY, viscosity=WATER_VISCOSITY)

# ALWAYS check continuity before solving — a bad initial guess silently
# converges to a wrong answer.
residuals = network.check_node_continuity(initial_flows, external_flow={"1": 0.05, "4": -0.05})
result = network.solve(initial_flows)
```

The core loop-balancing algorithm (`hardy_cross_solve`) is generic — it
accepts any monotonic head-loss law via a `head_loss_fn(pipe_name, |Q|)`
callback, not just Darcy-Weisbach, mirroring how the method was
originally formulated. It's verified exactly against a published worked
example (see `tests/test_network.py`), including matching the example's
stated intermediate iteration — not just checking self-consistency at
convergence.

`src/hydraulics/transients.py` predicts water hammer (transient pressure
surge) from a sudden velocity change — e.g. fast valve closure:

```python
from src.hydraulics.transients import evaluate_water_hammer
from src.utils.validation import check_water_hammer_risk

result = evaluate_water_hammer(
    bulk_modulus_Pa=WATER_BULK_MODULUS_PA, density=WATER_DENSITY,
    diameter_m=0.1016, wall_thickness_m=0.006, youngs_modulus_Pa=STEEL_YOUNGS_MODULUS_PA,
    length_m=200.0, delta_v_m_s=2.0, closure_time_s=0.05,
    initial_pressure_Pa=300_000,
)
print(result.peak_pressure_Pa, result.is_rapid_closure)
print(check_water_hammer_risk(result.peak_pressure_Pa, pipe_rated_pressure_Pa=1_000_000))
```

Closures faster than the pipe's critical period (`2L/wave_speed`) produce
the full Joukowsky surge; slower closures are reduced via the standard
linear-closure approximation. See
`notebooks/network_and_transients.ipynb` for the full demonstration,
including the (correct, verified) result that slow-closure surge is
actually independent of pipe material — only fast closures are sensitive
to pipe stiffness.

**Caveat**: both modules are screening/preliminary-design tools. Real
network design (especially many-loop systems) and critical water-hammer
certification typically use dedicated software (EPANET, transient
solvers using the method of characteristics) for production decisions.

## 10. Loading scenarios from config files

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

## 11. Running the dashboard

```bash
streamlit run streamlit_app/app.py
```

Navigate: **Input** (set parameters, run) → **Compare** (scenarios loaded
straight from `configs/*.yaml`) → **Results** (metrics, pressure curve,
energy Sankey) → **Lean Dashboard** (Muda waste ranking + Pareto, Mura
utilization heatmap, Muri pump-overburden alerts, across all scenarios) →
**Economics** (CAPEX vs. OPEX lifecycle cost, adjustable assumptions,
break-even calculation) → **About** (methodology/references).

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

## 12. Generating the PDF report

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

## 13. Running tests

```bash
pytest --maxfail=1 --disable-warnings -q
```
