"""
Pipe flow fundamentals: cross-sectional area, mean velocity, Reynolds number,
and Darcy friction-factor dispatch (laminar vs turbulent).

The turbulent-regime friction factor itself (Swamee-Jain explicit
approximation) lives in ``swamee_jain.py`` — this module only decides
*which* regime applies and delegates accordingly, mirroring the original
project skeleton's separation of "general Darcy-Weisbach/Reynolds" from
"Swamee-Jain specifics".

All functions operate in SI units (metres, seconds, kilograms, pascals).

References
----------
Darcy-Weisbach friction factor for pipe flow — Engineering Toolbox.
"""

from ..utils.constants import PI, RE_LAMINAR_MAX
from .swamee_jain import swamee_jain_friction_factor


def pipe_area(diameter_m: float) -> float:
    """Cross-sectional area of a circular pipe [m²].

    A = π D² / 4

    Parameters
    ----------
    diameter_m : float
        Internal pipe diameter [m].
    """
    return PI * diameter_m ** 2 / 4.0


def flow_velocity(flow_rate_m3s: float, diameter_m: float) -> float:
    """Mean (bulk) flow velocity [m/s].

    v = Q / A

    Parameters
    ----------
    flow_rate_m3s : float
        Volumetric flow rate [m³/s].
    diameter_m : float
        Internal pipe diameter [m].
    """
    return flow_rate_m3s / pipe_area(diameter_m)


def reynolds_number(
    velocity_m_s: float,
    diameter_m: float,
    density: float,
    viscosity: float,
) -> float:
    """Dimensionless Reynolds number.

    Re = ρ v D / μ

    Parameters
    ----------
    velocity_m_s : float  [m/s]
    diameter_m   : float  [m]
    density      : float  [kg/m³]
    viscosity    : float  [Pa·s]  dynamic viscosity
    """
    return density * velocity_m_s * diameter_m / viscosity


def darcy_friction_factor(
    reynolds: float,
    diameter_m: float,
    roughness_m: float,
) -> float:
    """Darcy friction factor, dispatching by flow regime.

    For laminar flow (Re < 2300):
        f = 64 / Re                                  (Hagen-Poiseuille)

    For turbulent flow (Re ≥ 2300):
        delegates to the Swamee-Jain explicit approximation
        (see ``swamee_jain.swamee_jain_friction_factor``).

    Parameters
    ----------
    reynolds   : float  Reynolds number (dimensionless)
    diameter_m : float  internal pipe diameter [m]
    roughness_m: float  absolute pipe roughness ε [m]
    """
    if reynolds <= 0:
        raise ValueError(f"Reynolds number must be positive. Got {reynolds}.")
    if reynolds < RE_LAMINAR_MAX:
        return 64.0 / reynolds                       # Hagen-Poiseuille
    return swamee_jain_friction_factor(reynolds, diameter_m, roughness_m)
