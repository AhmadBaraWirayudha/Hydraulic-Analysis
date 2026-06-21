"""
Scenario assembly: combines the low-level hydraulics modules (friction,
head_loss, pump) into a single ``run_simulation`` call that produces all
metrics needed for reporting and the Streamlit dashboard.
"""

from dataclasses import dataclass

from ..utils.constants import WATER_DENSITY, WATER_VISCOSITY, PVC_ROUGHNESS, GRAVITY
from ..utils.validation import check_velocity, check_pump_load, check_npsh_margin
from ..hydraulics.head_loss import total_head_loss, HeadLossResult
from ..hydraulics.pump import pump_shaft_power, exergy_destruction, PumpPowerResult, ExergyResult
from ..hydraulics.npsh import evaluate_npsh, NPSHResult


@dataclass
class PipeScenario:
    """Input parameters fully describing one hydraulic scenario.

    ``static_head_m`` is the elevation gain / required delivery pressure
    head between the pump outlet and the system's discharge point — e.g. a
    water tower's height, or a minimum required tap pressure expressed as
    head. This is *useful*, recoverable energy (in the Gouy-Stodola sense
    it is not destroyed — lifting water or pressurizing it is reversible
    work), distinct from the friction/minor losses in ``head_loss_m``,
    which *are* irreversibly destroyed. The pump must supply both; only
    the friction-loss portion counts toward exergy destruction. Defaults
    to 0.0 (pure friction-loss analysis, matching the reference report).

    ``rated_power_W`` is the pump's rated/nameplate shaft power, used only
    for the Lean *Muri* (overburden) check — flags when required shaft
    power exceeds 80%/100% of this rating. None (default) skips the check.

    ``suction_pressure_Pa`` / ``vapor_pressure_Pa`` / ``inlet_elevation_m``
    / ``suction_head_loss_m`` / ``npsh_required_m`` together drive the NPSH
    (cavitation) check — see ``hydraulics.npsh``. The check only runs if
    both ``suction_pressure_Pa`` and ``vapor_pressure_Pa`` are supplied;
    ``npsh_required_m`` is additionally needed to get a margin warning
    rather than just the raw NPSHa value. Use
    ``hydraulics.fluid_properties.water_vapor_pressure(temperature_K)`` to
    derive ``vapor_pressure_Pa`` for water at a given operating temperature.
    """

    diameter_m: float
    flow_rate_m3s: float
    length_m: float = 100.0
    roughness_m: float = PVC_ROUGHNESS
    density: float = WATER_DENSITY
    viscosity: float = WATER_VISCOSITY
    fittings: dict[str, float] | None = None
    static_head_m: float = 0.0
    eta_pump: float = 0.75
    eta_motor: float = 0.90
    ambient_temp_K: float = 298.15
    rated_power_W: float | None = None
    suction_pressure_Pa: float | None = None
    vapor_pressure_Pa: float | None = None
    inlet_elevation_m: float = 0.0
    suction_head_loss_m: float = 0.0
    npsh_required_m: float | None = None
    label: str = ""


@dataclass
class ScenarioResult:
    """Full output of a single hydraulic scenario run."""

    scenario: PipeScenario
    head_loss: HeadLossResult
    pump: PumpPowerResult
    exergy: ExergyResult
    velocity_warning: str | None = None
    pump_load_warning: str | None = None
    npsh: NPSHResult | None = None
    npsh_warning: str | None = None

    # ── Convenience accessors used by the Streamlit UI ───────────────────────
    @property
    def pressure_drop(self) -> float:
        """Friction pressure drop along the pipe [Pa] = ρ g h_f (excludes static lift)."""
        return self.scenario.density * GRAVITY * self.head_loss.total_loss_m

    @property
    def total_head_m(self) -> float:
        """Total head the pump must supply [m] = friction/minor losses + static lift."""
        return self.head_loss.total_loss_m + self.scenario.static_head_m

    @property
    def efficiency(self) -> float:
        """Overall pump-train efficiency (η_pump · η_motor), as a fraction."""
        return self.pump.overall_efficiency

    def pressure_curve(self, n_points: int = 50):
        """Build a Plotly figure of pressure vs. distance along the pipe.

        Lazily imports the plotting module so headless/test usage doesn't
        require Plotly to be installed.
        """
        from ..plots.plot_pressure import pressure_vs_distance_figure
        return pressure_vs_distance_figure(self, n_points=n_points)


def run_simulation(
    diameter_m: float,
    flow_rate_m3s: float,
    length_m: float = 100.0,
    roughness_m: float = PVC_ROUGHNESS,
    density: float = WATER_DENSITY,
    viscosity: float = WATER_VISCOSITY,
    fittings: dict[str, float] | None = None,
    static_head_m: float = 0.0,
    eta_pump: float = 0.75,
    eta_motor: float = 0.90,
    ambient_temp_K: float = 298.15,
    rated_power_W: float | None = None,
    suction_pressure_Pa: float | None = None,
    vapor_pressure_Pa: float | None = None,
    inlet_elevation_m: float = 0.0,
    suction_head_loss_m: float = 0.0,
    npsh_required_m: float | None = None,
    label: str = "",
) -> ScenarioResult:
    """Run a complete hydraulic scenario: head loss → pump power → exergy.

    This is the single entry point used by the Streamlit app, notebooks,
    and the Monte Carlo / sensitivity modules.

    Parameters
    ----------
    diameter_m    : float  internal pipe diameter [m]
    flow_rate_m3s : float  volumetric flow rate Q [m³/s]
    length_m      : float  pipe length L [m]
    roughness_m   : float  absolute roughness ε [m] (default: PVC)
    density       : float  fluid density ρ [kg/m³] (default: water @ 25 °C)
    viscosity     : float  dynamic viscosity μ [Pa·s] (default: water @ 25 °C)
    fittings      : dict[str, float] | None  fitting name -> count
    static_head_m : float  elevation gain / required delivery head [m]
                            (useful, non-destroyed lift the pump must also
                            supply on top of friction losses; default 0.0)
    eta_pump      : float  pump hydraulic efficiency (0, 1]
    eta_motor     : float  motor efficiency (0, 1]
    ambient_temp_K: float  reference temperature for exergy calc [K]
    rated_power_W : float | None  pump's rated shaft power [W], for the
                            Lean Muri (overburden) check; None skips it
    suction_pressure_Pa : float | None  absolute suction-source pressure [Pa];
                            with vapor_pressure_Pa, enables the NPSH check
    vapor_pressure_Pa   : float | None  fluid vapor pressure at operating
                            temp [Pa]; see hydraulics.fluid_properties
    inlet_elevation_m   : float  suction source elevation vs. pump
                            centerline [m] (negative = suction lift)
    suction_head_loss_m : float  friction loss in suction-side piping [m]
    npsh_required_m     : float | None  pump's NPSHr from its curve [m];
                            adds a margin warning on top of raw NPSHa
    label         : str    optional scenario name, for reporting

    Returns
    -------
    ScenarioResult
        Full breakdown of head loss, pump power, and exergy destruction,
        plus convenience properties (.pressure_drop, .total_head_m,
        .efficiency) and a lazy .pressure_curve() Plotly figure builder.
    """
    scenario = PipeScenario(
        diameter_m=diameter_m,
        flow_rate_m3s=flow_rate_m3s,
        length_m=length_m,
        roughness_m=roughness_m,
        density=density,
        viscosity=viscosity,
        fittings=fittings,
        static_head_m=static_head_m,
        eta_pump=eta_pump,
        eta_motor=eta_motor,
        ambient_temp_K=ambient_temp_K,
        rated_power_W=rated_power_W,
        suction_pressure_Pa=suction_pressure_Pa,
        vapor_pressure_Pa=vapor_pressure_Pa,
        inlet_elevation_m=inlet_elevation_m,
        suction_head_loss_m=suction_head_loss_m,
        npsh_required_m=npsh_required_m,
        label=label,
    )

    hl = total_head_loss(
        flow_rate_m3s=flow_rate_m3s,
        diameter_m=diameter_m,
        length_m=length_m,
        roughness_m=roughness_m,
        density=density,
        viscosity=viscosity,
        fittings=fittings,
    )

    # The pump must overcome BOTH the friction/minor losses AND any static
    # lift / required delivery head — size shaft power on the total.
    total_head_for_pump = hl.total_loss_m + static_head_m

    pump_result = pump_shaft_power(
        flow_rate_m3s=flow_rate_m3s,
        head_loss_m=total_head_for_pump,
        density=density,
        eta_pump=eta_pump,
        eta_motor=eta_motor,
    )

    # Only the friction/minor-loss portion is irreversible — static lift is
    # useful (recoverable) work and does not count as destroyed exergy.
    exergy_result = exergy_destruction(
        flow_rate_m3s=flow_rate_m3s,
        head_loss_m=hl.total_loss_m,
        density=density,
        shaft_power_W=pump_result.shaft_power_W,
        ambient_temp_K=ambient_temp_K,
    )

    v_warning = check_velocity(hl.velocity_m_s)
    load_warning = check_pump_load(pump_result.shaft_power_W, rated_power_W)

    # NPSH check only runs if both suction and vapor pressure are known —
    # without them there's no way to compute NPSHa at all.
    npsh_result = None
    npsh_warning = None
    if suction_pressure_Pa is not None and vapor_pressure_Pa is not None:
        npsh_result = evaluate_npsh(
            suction_pressure_Pa=suction_pressure_Pa,
            vapor_pressure_Pa=vapor_pressure_Pa,
            density=density,
            inlet_elevation_m=inlet_elevation_m,
            suction_head_loss_m=suction_head_loss_m,
            npsh_required_m=npsh_required_m,
        )
        npsh_warning = check_npsh_margin(npsh_result.npsh_available_m, npsh_required_m)

    return ScenarioResult(
        scenario=scenario,
        head_loss=hl,
        pump=pump_result,
        exergy=exergy_result,
        velocity_warning=v_warning,
        pump_load_warning=load_warning,
        npsh=npsh_result,
        npsh_warning=npsh_warning,
    )


def load_scenario_from_config(config: dict) -> PipeScenario:
    """Build a ``PipeScenario`` from a parsed YAML/JSON config dict.

    Expected keys mirror ``PipeScenario`` fields; missing optional keys fall
    back to module defaults. See ``configs/scenario_config.yaml`` for an
    example, and ``configs/pipe_config.yaml`` / ``configs/fluid_config.yaml``
    for how pipe and fluid properties are typically separated and merged
    upstream of this call.
    """
    return PipeScenario(
        diameter_m=config["diameter_m"],
        flow_rate_m3s=config["flow_rate_m3s"],
        length_m=config.get("length_m", 100.0),
        roughness_m=config.get("roughness_m", PVC_ROUGHNESS),
        density=config.get("density", WATER_DENSITY),
        viscosity=config.get("viscosity", WATER_VISCOSITY),
        fittings=config.get("fittings"),
        static_head_m=config.get("static_head_m", 0.0),
        eta_pump=config.get("eta_pump", 0.75),
        eta_motor=config.get("eta_motor", 0.90),
        ambient_temp_K=config.get("ambient_temp_K", 298.15),
        rated_power_W=config.get("rated_power_W"),
        suction_pressure_Pa=config.get("suction_pressure_Pa"),
        vapor_pressure_Pa=config.get("vapor_pressure_Pa"),
        inlet_elevation_m=config.get("inlet_elevation_m", 0.0),
        suction_head_loss_m=config.get("suction_head_loss_m", 0.0),
        npsh_required_m=config.get("npsh_required_m"),
        label=config.get("label", ""),
    )
