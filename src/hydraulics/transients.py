"""
Water hammer (hydraulic transient) analysis: predicts the pressure surge
caused by a sudden velocity change (e.g. fast valve closure or pump trip).

Method
------
Wave (celerity) speed via the Korteweg formula for an elastic pipe:

    a = sqrt(K/rho) / sqrt(1 + (K/E)*(D/e))

Surge pressure via the Joukowsky equation (the classic instantaneous-
closure result):

    dP = rho * a * dv

A valve/pump-stop that completes within the pipe's critical period
(Tc_crit = 2L/a, the round-trip time for the pressure wave) is "rapid" and
produces the full Joukowsky surge. A slower, more gradual closure produces
a reduced surge — this module uses the standard linear-closure
approximation (sometimes called the Michaud/Allievi slow-closure formula,
which is algebraically identical to scaling the Joukowsky surge by
Tc_crit/closure_time): a simplified screening tool, not a substitute for
full transient (method-of-characteristics) simulation on a final design.

References
----------
Korteweg, D.J. (1878). Ueber die Fortpflanzungsgeschwindigkeit des
  Schalles in elastischen Roehren. Annalen der Physik und Chemie, 5, 525-542.
Joukowsky, N. (1898/1900). Ueber den hydraulischen Stoss in Wasserleitungsrohren.
Wylie, E.B. & Streeter, V.L. (1993). Fluid Transients in Systems. Prentice Hall.
AWWA Manual M11 — Steel Pipe: A Guide for Design and Installation (wave
  speed formula, same Korteweg structure with imperially-cited constants).
"""

import math
from dataclasses import dataclass


def wave_speed(
    bulk_modulus_Pa: float,
    density: float,
    diameter_m: float,
    wall_thickness_m: float,
    youngs_modulus_Pa: float,
) -> float:
    """Pressure wave (celerity) speed in a fluid-filled elastic pipe
    (Korteweg formula):

        a = sqrt(K/rho) / sqrt(1 + (K/E)*(D/e))

    Parameters
    ----------
    bulk_modulus_Pa   : float  fluid bulk modulus K [Pa] (water ~2.2 GPa)
    density           : float  fluid density rho [kg/m³]
    diameter_m        : float  pipe internal diameter D [m]
    wall_thickness_m  : float  pipe wall thickness e [m]
    youngs_modulus_Pa : float  pipe wall material's Young's modulus E [Pa]

    Returns
    -------
    float
        Wave speed [m/s]. Typically 200-1500 m/s depending on pipe
        material (lower for plastics, higher for steel/concrete).
    """
    if bulk_modulus_Pa <= 0:
        raise ValueError(f"Bulk modulus must be positive. Got {bulk_modulus_Pa} Pa.")
    if density <= 0:
        raise ValueError(f"Density must be positive. Got {density} kg/m3.")
    if diameter_m <= 0:
        raise ValueError(f"Diameter must be positive. Got {diameter_m} m.")
    if wall_thickness_m <= 0:
        raise ValueError(f"Wall thickness must be positive. Got {wall_thickness_m} m.")
    if youngs_modulus_Pa <= 0:
        raise ValueError(f"Young's modulus must be positive. Got {youngs_modulus_Pa} Pa.")

    sonic_speed_unconfined = math.sqrt(bulk_modulus_Pa / density)
    elasticity_factor = 1 + (bulk_modulus_Pa / youngs_modulus_Pa) * (diameter_m / wall_thickness_m)
    return sonic_speed_unconfined / math.sqrt(elasticity_factor)


def joukowsky_surge_pressure(density: float, wave_speed_m_s: float, delta_v_m_s: float) -> float:
    """Instantaneous-closure pressure surge (Joukowsky equation):

        dP = rho * a * |dv|

    Parameters
    ----------
    density        : float  fluid density [kg/m³]
    wave_speed_m_s : float  pressure wave speed [m/s] (see ``wave_speed``)
    delta_v_m_s    : float  change in flow velocity [m/s] (sign-independent;
                      the surge magnitude only depends on |delta_v|)

    Returns
    -------
    float
        Pressure surge magnitude [Pa] — added to (for sudden deceleration,
        e.g. valve closure) or subtracted from (sudden acceleration) the
        pre-transient pressure, depending on wave direction.
    """
    if density <= 0:
        raise ValueError(f"Density must be positive. Got {density} kg/m3.")
    if wave_speed_m_s <= 0:
        raise ValueError(f"Wave speed must be positive. Got {wave_speed_m_s} m/s.")
    return density * wave_speed_m_s * abs(delta_v_m_s)


def pipe_critical_period_s(length_m: float, wave_speed_m_s: float) -> float:
    """Critical period Tc = 2L/a — the round-trip time for the pressure
    wave to travel from the disturbance to the nearest open boundary (e.g.
    a reservoir) and back.

    Closures faster than this are "rapid" and produce the full Joukowsky
    surge; slower closures produce a reduced surge (see
    ``surge_pressure_with_closure_time``).

    Parameters
    ----------
    length_m       : float  pipe length from the disturbance to the
                      nearest open boundary [m]
    wave_speed_m_s : float  pressure wave speed [m/s]
    """
    if length_m <= 0:
        raise ValueError(f"Length must be positive. Got {length_m} m.")
    if wave_speed_m_s <= 0:
        raise ValueError(f"Wave speed must be positive. Got {wave_speed_m_s} m/s.")
    return 2 * length_m / wave_speed_m_s


@dataclass
class WaterHammerResult:
    """Container for a water hammer (transient surge) analysis."""

    wave_speed_m_s: float
    critical_period_s: float
    closure_time_s: float
    is_rapid_closure: bool
    instantaneous_surge_Pa: float    # full Joukowsky surge, ignoring closure time
    surge_Pa: float                  # actual surge, accounting for closure time
    peak_pressure_Pa: float          # initial_pressure + surge


def evaluate_water_hammer(
    bulk_modulus_Pa: float,
    density: float,
    diameter_m: float,
    wall_thickness_m: float,
    youngs_modulus_Pa: float,
    length_m: float,
    delta_v_m_s: float,
    closure_time_s: float,
    initial_pressure_Pa: float = 0.0,
) -> WaterHammerResult:
    """Full water hammer evaluation: wave speed, closure classification,
    and resulting surge/peak pressure.

    Parameters
    ----------
    bulk_modulus_Pa, density, diameter_m, wall_thickness_m,
        youngs_modulus_Pa : see ``wave_speed``
    length_m            : float  pipe length to the nearest open boundary [m]
    delta_v_m_s         : float  velocity change caused by the closure [m/s]
    closure_time_s      : float  actual valve/pump-stop closure duration [s]
    initial_pressure_Pa : float  steady-state pressure before the transient [Pa]

    Returns
    -------
    WaterHammerResult
    """
    if closure_time_s <= 0:
        raise ValueError(f"Closure time must be positive. Got {closure_time_s} s.")
    if initial_pressure_Pa < 0:
        raise ValueError(f"Initial pressure must be non-negative. Got {initial_pressure_Pa} Pa.")

    a = wave_speed(bulk_modulus_Pa, density, diameter_m, wall_thickness_m, youngs_modulus_Pa)
    critical_period = pipe_critical_period_s(length_m, a)
    instantaneous_surge = joukowsky_surge_pressure(density, a, delta_v_m_s)

    is_rapid = closure_time_s <= critical_period
    if is_rapid:
        surge = instantaneous_surge
    else:
        # Simplified linear-closure approximation (Michaud/Allievi slow-closure
        # formula) — see module docstring for the limitation.
        surge = instantaneous_surge * (critical_period / closure_time_s)

    return WaterHammerResult(
        wave_speed_m_s=a,
        critical_period_s=critical_period,
        closure_time_s=closure_time_s,
        is_rapid_closure=is_rapid,
        instantaneous_surge_Pa=instantaneous_surge,
        surge_Pa=surge,
        peak_pressure_Pa=initial_pressure_Pa + surge,
    )
