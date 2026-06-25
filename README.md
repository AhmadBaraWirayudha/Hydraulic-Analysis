# Hydraulic Distribution Analysis Toolkit

A modular, config-driven Python package for analyzing water distribution
pipelines using the **Darcy–Weisbach** and **Swamee–Jain (1976)** equations originally developed to evaluate pipe-diameter choices for the **Citra
Srie Pradita** housing estate, and rebuilt here as a reusable engineering
module rather than a one-off script. Now with the governance layer a
multi-engineer team actually needs: **role-based access control**, **audit
logging**, and a **PostGIS-backed geospatial map** of the physical network.

## Features

- **Role-based access control (RBAC)**: two demo roles — Field Technician
  (view-only) and Lead Engineer (can run ad-hoc scenarios and edit YAML
  configuration). Enforced on every page, not just hidden in the UI; see
  `tests/test_streamlit_rbac.py` for the automated proof (using Streamlit's
  official `AppTest` framework — simulated logins, not just code review).
- **Audit logging**: every scenario run and configuration edit is recorded
  to PostgreSQL — who, when, and (for config edits) the exact field-level
  diff — viewable on the Audit Log page.
- **Geospatial network view**: the pipe network's real physical layout,
  stored in PostGIS and rendered on an interactive Folium map, color-coded
  by velocity against the SNI 03-6481-2000 range — the Lean Dashboard's
  Mura (unevenness) lens, applied spatially.
- **Hydraulic calculations**: friction factor (laminar/turbulent dispatch),
  Reynolds number, major (Darcy-Weisbach) and minor (K-factor) head losses,
  pump shaft power, and **exergy destruction** (Gouy-Stodola theorem) for
  irreversibility/waste analysis.
- **Explicit Swamee-Jain design equations**: solve directly for required
  diameter or achievable flow rate given a target head loss — no iterative
  Colebrook-White solving needed.
- **Temperature-dependent fluid properties**: Andrade viscosity and
  Antoine vapor-pressure equations, with coefficients fitted (not guessed)
  against standard reference data for water — see
  `src/hydraulics/fluid_properties.py` for fit methodology and accuracy.
  Generic fitting utilities are included so you can calibrate either
  equation for other fluids.
- **NPSH (cavitation) check**: `src/hydraulics/npsh.py` computes NPSH
  available and, given a pump's NPSHr, flags cavitation risk (<100%
  margin) or a thin margin (<120%) — another Poka-Yoke-style safety check,
  optional per scenario.
- **VFD / electrical analysis**: `src/hydraulics/electrical.py` —
  pump affinity laws (flow ∝ N, head ∝ N², power ∝ N³) for variable-speed
  energy optimization; three-phase apparent/real/reactive power and power
  factor; NEMA-defined voltage unbalance percentage with a Poka-Yoke check
  against NEMA's 5% operating limit. (The derating-factor-vs-unbalance
  *curve* itself is published as a graph in NEMA MG1-14.36, not a formula,
  and varies by motor class/load — this module gives you an interpolation
  utility to apply your own motor's published curve rather than a
  one-size-fits-all guess.)
- **Lifecycle Cost Analysis (LCCA)**: `src/economics/` compares pipe/pump
  CAPEX against the present value of electricity OPEX over a configurable
  horizon — a financial-dashboard view of the same hydraulic tradeoff
  (smaller pipe = cheaper upfront, dramatically more expensive to run).
  No real-world prices are hardcoded; every cost input is explicitly
  user-supplied (see `configs/economics_config.yaml`). Provides factual
  present-value arithmetic only, not investment recommendations.
- **Predictive maintenance (ML demo)**: `src/machine_learning/` —
  Random Forest regression for forecasting pipe roughness degradation,
  plus two complementary anomaly-detection approaches (a transparent SPC
  control chart, and an Isolation Forest for multivariate patterns).
  **Read the module docstrings before trusting any number here**: training
  data is synthetic — the hydraulic baseline is real (computed via this
  project's own Darcy-Weisbach engine), but the degradation trend, sensor
  noise, and anomalies are fabricated for demonstration. This shows the ML
  *pattern*, not a validated predictive tool; swap in real inspection/
  sensor data for actual use.
- **Network analysis (Hardy Cross)**: `src/hydraulics/network.py` solves
  flow distribution in closed-loop pipe networks — multiple interconnected
  pipes, not just one line. The core loop-balancing solver is verified
  exactly against a published worked example (Wikipedia's Hardy Cross
  method article), including matching its stated intermediate iteration,
  not just checking self-consistency at convergence.
- **Water hammer (transient surge) analysis**: `src/hydraulics/transients.py`
  — Korteweg wave speed + Joukowsky surge pressure, with rapid-vs-slow
  valve-closure classification and a Poka-Yoke check against the pipe's
  rated pressure. Wave-speed formula validated against its rigid-pipe
  limit (reduces exactly to the unconfined speed of sound in water) and
  literature-typical wave speeds for steel/PVC pipe.
- **Simulation layer**: config-driven scenarios (`configs/*.yaml`) — cross-
  referenced and validated by `src/simulation/config_loader.py`, so adding
  a scenario, pipe, or fluid means editing YAML, not Python — plus Monte
  Carlo uncertainty propagation and one-at-a-time sensitivity sweeps with
  normalized elasticity coefficients.
- **Visualization**: pressure-vs-distance curves, head-loss/efficiency
  sweep plots, Monte Carlo histograms, and an energy-flow **Sankey diagram**
  that frames frictional exergy loss as Lean *Muda* (waste).
- **Poka-Yoke validation**: every calculation path validates inputs first
  (positive diameter/length/flow, density/viscosity sanity, roughness <
  diameter, pump efficiency in (0,1]) and raises clear `ValueError`s before
  any physics runs. Velocity is also checked against the **SNI
  03-6481-2000** recommended range (0.9–2.0 m/s).
- **Lean Six Sigma 3M analysis**: *Muda* (waste) via exergy destruction +
  a Pareto chart of loss sources (friction vs. each fitting); *Mura*
  (unevenness) via a cross-scenario utilization heatmap; *Muri*
  (overburden) via a configurable pump-rated-capacity check that flags
  >80%/100% load. All three are brought together on a dedicated **Lean
  Dashboard** Streamlit page and in the PDF report.
- **Interactive dashboard**: a Streamlit app (Input → Compare → Results →
  About) for non-programmers to run scenarios and explore results.
- **PDF report generation**: `src/reporting/` assembles a full engineering
  report (`reports/final_report.pdf`) — methodology, scenario comparison
  table, head-loss/diameter-sensitivity/pressure-profile/energy-balance
  figures, Monte Carlo uncertainty section, and Lean/Poka-Yoke notes —
  directly from the current `configs/*.yaml`, with no hardcoded values.
- **Tested & CI'd**: pytest unit tests for every formula module, GitHub
  Actions CI (lint + test on Python 3.10/3.11), Dockerized Streamlit app.

## Project Structure

```
hydraulic-analysis/
├── .devcontainer/             # VS Code dev container (Python, ruff, Jupyter)
├── .streamlit/config.toml    # production Streamlit settings (theme, no usage stats)
├── .env.example                # database connection settings template
├── docker-compose.yml         # app + PostGIS-enabled Postgres, for local/production-like testing
├── DEPLOYMENT.md              # Streamlit Cloud / Docker / PaaS deployment guide
├── Makefile                   # make install|test|lint|report|run|docker-build|...
├── configs/                 # YAML scenario/pipe/fluid/economics configs
├── data/                     # raw/processed input data
├── docs/                     # design notes, user guide
├── notebooks/                # exploratory/demo notebooks
├── reports/                  # generated report figures/PDFs
│   ├── figures/              # PNG figures embedded in the PDF report
│   └── final_report.pdf      # generated by src/reporting/build_report.py
├── src/
│   ├── hydraulics/           # friction.py, swamee_jain.py, head_loss.py, pump.py,
│   │                         # fluid_properties.py, npsh.py, electrical.py,
│   │                         # network.py, transients.py
│   ├── simulation/           # scenario.py, monte_carlo.py, sensitivity.py, config_loader.py
│   ├── economics/            # lcca.py, scenario_economics.py
│   ├── machine_learning/     # synthetic_data.py, degradation_model.py, anomaly_detection.py
│   ├── auth/                 # models.py (User, Role), service.py (RBAC + bcrypt hashing)
│   ├── audit/                # models.py, service.py (who/when/what logging)
│   ├── geospatial/            # models.py, service.py (PostGIS CRUD), map_view.py (Folium)
│   ├── db.py                 # shared PostgreSQL/PostGIS connection + schema
│   ├── plots/                # plot_pressure.py, plot_efficiency.py, sankey.py, pareto.py (interactive, for Streamlit)
│   ├── reporting/            # figures.py, build_report.py (static, for the PDF report)
│   └── utils/                # constants.py, units.py, validation.py, yaml_diff.py
├── streamlit_app/             # app.py (login) + auth_helpers.py +
│   │                         # pages/{1_input,2_compare,3_results,4_lean_dashboard,
│   │                         #         5_economics,6_network_map,7_config_editor,
│   │                         #         8_audit_log,9_about}.py + Dockerfile
└── tests/                     # pytest suite (DB-dependent tests skip cleanly if no Postgres reachable)
```

## Installation

The dashboard now requires PostgreSQL with the PostGIS extension (for
login/RBAC, audit logging, and the network map). The easiest path is
Docker, which sets up both the app and a correctly-configured database in
one command:

```bash
git clone <repo-url>
cd hydraulic-analysis
docker compose up --build
```

Visit `http://localhost:8501` and sign in with one of the demo accounts:

| Username | Password | Role | Access |
|---|---|---|---|
| `technician` | `technician123` | Field Technician | View-only — all dashboards |
| `engineer` | `engineer123` | Lead Engineer | Full — also runs scenarios, edits config, views audit log |

**Change these before any real deployment** — they're seeded automatically
on first run for demonstration purposes only.

### Without Docker

You'll need your own PostgreSQL+PostGIS instance (see
[DEPLOYMENT.md](DEPLOYMENT.md)), then:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit with your database connection details
export $(grep -v '^#' .env | xargs)   # or use your own env-loading approach
streamlit run streamlit_app/app.py
```

The pure hydraulics/economics/ML modules (`src/hydraulics/`,
`src/simulation/`, `src/economics/`, `src/machine_learning/`) have no
database dependency and work standalone — only `src/auth/`, `src/audit/`,
and `src/geospatial/` (and the Streamlit pages that use them) need Postgres.

Or open in VS Code with the **Dev Containers** extension and "Reopen in
Container" — `.devcontainer/` provides Python, ruff linting, and Jupyter
pre-installed (separate from `streamlit_app/Dockerfile`, which builds the
production dashboard image rather than a dev environment; note the
devcontainer doesn't include Postgres — pair it with `docker compose up -d db`
if you need the database while developing).

## Usage

### As a library

```python
from src.simulation.scenario import run_simulation

result = run_simulation(
    diameter_m=0.1016,        # 4 inch pipe
    flow_rate_m3s=0.0005,     # 0.5 L/s
    length_m=100.0,
    fittings={"elbow_90_standard": 4, "gate_valve_open": 1},
    eta_pump=0.75,
    eta_motor=0.90,
)

print(f"Pressure drop: {result.pressure_drop:.1f} Pa")
print(f"Pump shaft power: {result.pump.shaft_power_W:.1f} W")
print(f"Exergy destroyed: {result.exergy.exergy_destruction_W:.2f} W")
if result.velocity_warning:
    print(result.velocity_warning)
```

### Comparing pipe sizes (sensitivity sweep)

```python
import numpy as np
from src.simulation.scenario import PipeScenario
from src.simulation.sensitivity import sweep_parameter

base = PipeScenario(diameter_m=0.1, flow_rate_m3s=0.0005, length_m=100.0)
df = sweep_parameter(base, "diameter_m", np.linspace(0.0127, 0.1016, 10))
print(df[["diameter_m", "total_loss_m", "pressure_drop_Pa"]])
```

### Monte Carlo uncertainty

```python
from src.simulation.monte_carlo import run_monte_carlo, ParameterUncertainty

unc = [ParameterUncertainty("flow_rate_m3s", "triangular",
                             {"low": 0.0003, "mode": 0.0005, "high": 0.0009})]
mc_df = run_monte_carlo(base, unc, n_samples=2000)
print(mc_df["total_loss_m"].describe())
```

### Temperature-dependent viscosity & NPSH (cavitation)

```python
from src.hydraulics.fluid_properties import water_viscosity, water_vapor_pressure
from src.simulation.scenario import run_simulation

# Hot process water at 60 degC — viscosity and vapor pressure both shift
viscosity_60C = water_viscosity(333.15)
vapor_pressure_60C = water_vapor_pressure(333.15)

result = run_simulation(
    diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0,
    viscosity=viscosity_60C,
    suction_pressure_Pa=101_325,      # atmospheric, open suction tank
    vapor_pressure_Pa=vapor_pressure_60C,
    inlet_elevation_m=-1.5,            # 1.5 m suction lift
    npsh_required_m=4.0,               # from the pump's manufacturer curve
)
print(result.npsh.npsh_available_m, result.npsh_warning)
```

### VFD energy optimization (pump affinity laws)

```python
from src.hydraulics.electrical import apply_affinity_laws, speed_ratio_for_target_flow

# Pump's known performance at full speed
Q_ref, H_ref, P_ref = 0.01, 20.0, 1000.0   # m3/s, m, W

# What if demand drops to 70% of design flow?
ratio = speed_ratio_for_target_flow(Q_ref, flow_target_m3s=0.7 * Q_ref)
result = apply_affinity_laws(Q_ref, H_ref, P_ref, speed_ratio=ratio)
print(f"Speed: {ratio:.0%}, Power: {result.power_W:.1f} W "
      f"({result.power_W/P_ref:.0%} of full-speed power)")
```

See `notebooks/vfd_energy_optimization.ipynb` for the full cube-law savings analysis.

### Lifecycle cost analysis (LCCA)

```python
from src.simulation.config_loader import load_pipeline, load_economics_config
from src.economics.scenario_economics import compare_lifecycle_costs

pipeline = load_pipeline(config_dir="configs")
econ_config = load_economics_config(config_dir="configs")

df = compare_lifecycle_costs(pipeline["results"], econ_config=econ_config)
print(df[["scenario", "capex", "present_value_opex", "total_lifecycle_cost"]])
# -> the 4" pipe costs more upfront but is dramatically cheaper over 20 years
```

### Network analysis (Hardy Cross)

```python
from src.hydraulics.network import PipeNetwork, NetworkPipe, Loop, LoopMember
from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY, PVC_ROUGHNESS

pipes = [
    NetworkPipe("12", "1", "2", diameter_m=0.10, length_m=200.0, roughness_m=PVC_ROUGHNESS),
    NetworkPipe("13", "1", "3", diameter_m=0.075, length_m=250.0, roughness_m=PVC_ROUGHNESS),
    NetworkPipe("23", "2", "3", diameter_m=0.05, length_m=150.0, roughness_m=PVC_ROUGHNESS),
    NetworkPipe("24", "2", "4", diameter_m=0.075, length_m=200.0, roughness_m=PVC_ROUGHNESS),
    NetworkPipe("34", "3", "4", diameter_m=0.10, length_m=200.0, roughness_m=PVC_ROUGHNESS),
]
loop123 = Loop("123", [LoopMember("12", +1), LoopMember("23", +1), LoopMember("13", -1)])
loop234 = Loop("234", [LoopMember("23", -1), LoopMember("24", +1), LoopMember("34", -1)])
network = PipeNetwork(pipes, [loop123, loop234], density=WATER_DENSITY, viscosity=WATER_VISCOSITY)

initial_flows = {"12": 0.030, "13": 0.020, "23": 0.0, "24": 0.030, "34": 0.020}
result = network.solve(initial_flows)   # always check_node_continuity first!
print(result.flows, result.converged)
```

See `notebooks/network_and_transients.ipynb` — the core solver is verified
exactly against a published worked example before being trusted on real
pipe geometry.

### Water hammer (transient surge)

```python
from src.hydraulics.transients import evaluate_water_hammer
from src.utils.constants import WATER_BULK_MODULUS_PA, STEEL_YOUNGS_MODULUS_PA, WATER_DENSITY

result = evaluate_water_hammer(
    bulk_modulus_Pa=WATER_BULK_MODULUS_PA, density=WATER_DENSITY,
    diameter_m=0.1016, wall_thickness_m=0.006, youngs_modulus_Pa=STEEL_YOUNGS_MODULUS_PA,
    length_m=200.0, delta_v_m_s=2.0, closure_time_s=0.05,   # fast valve closure
    initial_pressure_Pa=300_000,
)
print(result.peak_pressure_Pa, result.is_rapid_closure)
```

### Predictive maintenance (ML demo — synthetic data, read the caveats)

```python
from src.machine_learning.synthetic_data import generate_synthetic_roughness_degradation
from src.machine_learning.degradation_model import fit_degradation_model, predict_maintenance_threshold_day

df = generate_synthetic_roughness_degradation(diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0)
model_result = fit_degradation_model(df["day"], df["roughness_m"])
threshold_day = predict_maintenance_threshold_day(
    model_result, roughness_threshold_m=df["roughness_m"].iloc[0] * 1.5,
)
print(f"Test R2: {model_result.test_r2:.3f}, predicted maintenance trigger: day {threshold_day}")
```

See `notebooks/predictive_maintenance.ipynb` for the full degradation
forecasting + anomaly detection (SPC vs. Isolation Forest) demonstration.

### Role-based access control & audit logging

```python
from src.db import init_schema
from src.auth.service import seed_demo_users, authenticate
from src.audit.service import log_action, get_audit_log

init_schema()           # idempotent — creates tables if they don't exist
seed_demo_users()        # creates the two demo accounts if absent

user = authenticate("engineer", "engineer123")
print(user.role.display_name, user.can_edit_config)   # Lead Engineer True

log_action(user.username, "run_scenario", {"diameter_m": 0.1016})
for entry in get_audit_log(limit=5):
    print(entry.created_at, entry.username, entry.action, entry.details)
```

RBAC is enforced on every Streamlit page via `streamlit_app/auth_helpers.py`'s
`require_login()`/`require_role()` — see `tests/test_streamlit_rbac.py` for
the automated proof (simulated logins via Streamlit's official `AppTest`
framework, not just a code-review claim).

### Geospatial network view

```python
from src.geospatial.service import seed_demo_network, get_network_geometry
from src.geospatial.map_view import build_network_map
from src.hydraulics.network import PipeNetwork, NetworkPipe
from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY

seed_demo_network()   # the same 4-node, 2-loop demo network, with real coordinates
nodes, pipes = get_network_geometry()

# Solve hydraulically (reusing the existing Hardy Cross module) and color
# the map by velocity:
from src.geospatial.service import get_all_loops
network_pipes = [NetworkPipe(p.name, p.start_node, p.end_node, p.diameter_m, p.length_m, p.roughness_m) for p in pipes]
network = PipeNetwork(network_pipes, get_all_loops(), density=WATER_DENSITY, viscosity=WATER_VISCOSITY)
solution = network.solve({"12": 0.006, "13": 0.004, "23": 0.0, "24": 0.006, "34": 0.004})

fmap = build_network_map(nodes, pipes, flows=solution.flows)
fmap.save("network_map.html")
```

### Config-driven pipeline (no hardcoded values)

```python
from src.simulation.config_loader import load_pipeline

pipeline = load_pipeline(config_dir="configs")
print(pipeline["summary"])  # every scenario in scenario_config.yaml, run and compared
```

### Generate the PDF report

```bash
python -m src.reporting.build_report
```

Produces `reports/final_report.pdf` (methodology, scenario comparison,
diameter sensitivity, pressure profile, exergy/energy balance, and Monte
Carlo uncertainty sections) plus the supporting PNGs in `reports/figures/`
— regenerate any time `configs/*.yaml` changes.

### Dashboard

```bash
streamlit run streamlit_app/app.py
```

Or via Docker:

```bash
docker build -t hydraulic-dashboard -f streamlit_app/Dockerfile .
docker run -p 8501:8501 hydraulic-dashboard
```

## Testing

```bash
pytest --maxfail=1 --disable-warnings -q
```

Tests touching `src/auth/`, `src/audit/`, `src/geospatial/`, or
`tests/test_streamlit_rbac.py` need a reachable PostgreSQL+PostGIS — they
skip cleanly with a clear message if none is found (see
`tests/conftest.py`), rather than failing the whole suite. Start one with:

```bash
docker compose up -d db
```

CI (`.github/workflows/ci.yml`) runs a `postgis/postgis` service container
automatically, so these tests always run there.

A `Makefile` wraps the common commands: `make install`, `make test`,
`make lint`, `make report`, `make run` (Streamlit), `make docker-build`,
`make docker-run`, `make compose-up`.

## Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for step-by-step instructions —
Streamlit Community Cloud (easiest, free), Docker/`docker-compose`, or
any container-platform-as-a-service (Render, Railway, Fly.io). The app
now needs a PostgreSQL+PostGIS database for login/RBAC, audit logging,
and the network map — `docker-compose.yml` provisions one automatically;
other paths need a managed Postgres instance with PostGIS enabled (most
managed Postgres providers support this with one setting or `CREATE
EXTENSION postgis;`).

## Method & References

- Darcy-Weisbach equation for major head loss; K-factor method for minor losses.
- Swamee, P.K. & Jain, A.K. (1976). *Explicit equations for pipe flow
  problems.* J. Hydraul. Div., ASCE, 102(5), 657–664.
- Bejan, A. (2016). *Advanced Engineering Thermodynamics.* Wiley — Gouy-Stodola theorem.
- SNI 03-6481-2000 / SNI 03-7065-2005 — Indonesian plumbing system standards.

See `docs/design.md` for the full architecture rationale and `docs/user_guide.md`
for a walkthrough.

## License

MIT — see `LICENSE`.

---

*Developed an engineering-grade hydraulic distribution analysis tool in
Python. Implemented Darcy–Weisbach and Swamee–Jain calculations, pump
power/exergy evaluation, and Monte Carlo sensitivity analysis. Built
interactive dashboards (Streamlit) and Lean Six Sigma-style waste analysis
(Muda/Mura/Muri) for pipeline efficiency and maintenance planning.*
