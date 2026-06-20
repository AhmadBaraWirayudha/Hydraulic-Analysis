"""
Pump hydraulic/shaft power and exergy destruction (Gouy-Stodola theorem).

The exergy analysis quantifies the *quality* of energy lost to friction —
not just the head loss itself, but the associated entropy generation and
the resulting irrecoverable work potential. This mirrors the exergy
(Gouy-Stodola) section of the reference report.

References
----------
Bejan, A. (2016). Advanced Engineering Thermodynamics. Wiley.
  (Gouy-Stodola theorem: Ẋ_destroyed = T₀ · Ṣ_gen)
"""

import math
from dataclasses import dataclass

from ..utils.constants import GRAVITY
from ..utils.validation import validate_pump


@dataclass
class PumpPowerResult:
    """Container for pump power calculation results."""

    hydraulic_power_W: float   # P_h = ρ g Q h_f   (useful work delivered to fluid)
    shaft_power_W: float       # P_shaft = P_h / (η_pump · η_motor)
    overall_efficiency: float  # η_pump * η_motor


@dataclass
class ExergyResult:
    """Container for exergy destruction results (Gouy-Stodola)."""

    entropy_generation_rate_W_per_K: float  # Ṣ_gen
    exergy_destruction_W: float             # Ẋ_destroyed = T0 * Ṣ_gen
    exergy_destruction_fraction: float      # Ẋ_destroyed / P_shaft


def hydraulic_power(
    flow_rate_m3s: float,
    head_loss_m: float,
    density: float,
    g: float = GRAVITY,
) -> float:
    """Hydraulic power delivered to the fluid [W].

        P_h = ρ g Q h_f

    Parameters
    ----------
    flow_rate_m3s : float  volumetric flow rate Q [m³/s]
    head_loss_m   : float  total head the pump must overcome h_f [m]
    density       : float  fluid density ρ [kg/m³]
    g             : float  gravitational acceleration [m/s²]
    """
    if flow_rate_m3s < 0:
        raise ValueError(f"Flow rate must be non-negative. Got {flow_rate_m3s}.")
    if head_loss_m < 0:
        raise ValueError(f"Head loss must be non-negative. Got {head_loss_m}.")
    return density * g * flow_rate_m3s * head_loss_m


def pump_shaft_power(
    flow_rate_m3s: float,
    head_loss_m: float,
    density: float,
    eta_pump: float = 0.75,
    eta_motor: float = 0.90,
    g: float = GRAVITY,
) -> PumpPowerResult:
    """Pump shaft (input) power required, accounting for efficiencies.

        P_shaft = P_h / (η_pump · η_motor)

    Parameters
    ----------
    flow_rate_m3s : float  volumetric flow rate Q [m³/s]
    head_loss_m   : float  total head h_f [m]
    density       : float  fluid density ρ [kg/m³]
    eta_pump      : float  pump hydraulic efficiency (0, 1]
    eta_motor     : float  motor electrical efficiency (0, 1]
    g             : float  gravitational acceleration [m/s²]

    Returns
    -------
    PumpPowerResult
        hydraulic_power_W, shaft_power_W, overall_efficiency
    """
    validate_pump(eta_pump, eta_motor)
    p_h = hydraulic_power(flow_rate_m3s, head_loss_m, density, g)
    overall_eta = eta_pump * eta_motor
    p_shaft = p_h / overall_eta if overall_eta > 0 else math.inf
    return PumpPowerResult(
        hydraulic_power_W=p_h,
        shaft_power_W=p_shaft,
        overall_efficiency=overall_eta,
    )


def exergy_destruction(
    flow_rate_m3s: float,
    head_loss_m: float,
    density: float,
    shaft_power_W: float,
    ambient_temp_K: float = 298.15,
    g: float = GRAVITY,
) -> ExergyResult:
    """Exergy destroyed by frictional irreversibility (Gouy-Stodola theorem).

    Friction converts mechanical energy into heat irreversibly. The
    associated entropy generation rate is:

        Ṣ_gen = (ρ g Q h_f) / T₀

    and the destroyed exergy (lost work potential) follows directly:

        Ẋ_destroyed = T₀ · Ṣ_gen = ρ g Q h_f

    (Numerically this equals the hydraulic power lost to friction — the
    Gouy-Stodola theorem's contribution is in attributing this loss to
    entropy generation, which becomes meaningful when comparing multiple
    irreversibilities or non-isothermal systems.)

    Parameters
    ----------
    flow_rate_m3s  : float  volumetric flow rate Q [m³/s]
    head_loss_m    : float  friction head loss h_f [m]
    density        : float  fluid density ρ [kg/m³]
    shaft_power_W  : float  pump shaft power, for computing the destroyed
                             fraction [W]
    ambient_temp_K : float  reference (ambient) temperature T₀ [K]
                             (default 298.15 K = 25 °C)
    g              : float  gravitational acceleration [m/s²]

    Returns
    -------
    ExergyResult
        entropy_generation_rate_W_per_K, exergy_destruction_W,
        exergy_destruction_fraction (relative to shaft power input)
    """
    if ambient_temp_K <= 0:
        raise ValueError(f"Ambient temperature must be positive. Got {ambient_temp_K} K.")

    x_destroyed = density * g * flow_rate_m3s * head_loss_m  # = friction power
    s_gen = x_destroyed / ambient_temp_K
    fraction = x_destroyed / shaft_power_W if shaft_power_W > 0 else math.nan

    return ExergyResult(
        entropy_generation_rate_W_per_K=s_gen,
        exergy_destruction_W=x_destroyed,
        exergy_destruction_fraction=fraction,
    )
