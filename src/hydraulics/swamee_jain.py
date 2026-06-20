"""
Swamee-Jain (1976) explicit equations for turbulent pipe flow.

The Colebrook-White equation for the turbulent friction factor is implicit
(f appears on both sides) and traditionally requires iteration. Swamee and
Jain derived explicit approximations — accurate to within ~1% of
Colebrook-White over their stated validity range — for three classic design
problems:

  1. Friction factor f,  given Re and ε/D           → ``swamee_jain_friction_factor``
  2. Head loss h_f,      given Q, D, L               → see ``head_loss.py``
  3. Diameter D,         given Q, h_f, L              → ``solve_diameter_for_head_loss``
  4. Flow rate Q,        given D, h_f, L              → ``solve_flow_for_head_loss``

Validity range: 5,000 < Re < 10⁸  and  10⁻⁶ < ε/D < 10⁻².

References
----------
Swamee, P.K. & Jain, A.K. (1976). Explicit equations for pipe flow problems.
  J. Hydraul. Div., ASCE, 102(5), 657-664.
"""

import math

from ..utils.constants import GRAVITY, PI


def swamee_jain_friction_factor(
    reynolds: float,
    diameter_m: float,
    roughness_m: float,
) -> float:
    """Darcy friction factor for turbulent flow (Swamee-Jain explicit form).

        f = 0.25 / [log₁₀(ε/(3.7D) + 5.74/Re^0.9)]²

    Parameters
    ----------
    reynolds   : float  Reynolds number (dimensionless), should be ≥ 2300
    diameter_m : float  internal pipe diameter [m]
    roughness_m: float  absolute pipe roughness ε [m]

    Notes
    -----
    This function does not check the flow regime — callers in laminar flow
    should use Hagen-Poiseuille (f = 64/Re) instead. See
    ``hydraulics.friction.darcy_friction_factor`` for automatic dispatch.
    """
    if reynolds <= 0:
        raise ValueError(f"Reynolds number must be positive. Got {reynolds}.")
    if diameter_m <= 0:
        raise ValueError(f"Diameter must be positive. Got {diameter_m} m.")
    term = roughness_m / (3.7 * diameter_m) + 5.74 / (reynolds ** 0.9)
    if term <= 0:
        raise ValueError("Swamee-Jain argument for log₁₀ is non-positive.")
    return 0.25 / (math.log10(term)) ** 2


def solve_diameter_for_head_loss(
    flow_rate_m3s: float,
    head_loss_m: float,
    length_m: float,
    roughness_m: float,
    kinematic_viscosity: float,
    g: float = GRAVITY,
) -> float:
    """Explicit Swamee-Jain solution for required diameter D [m].

    Given a target head loss h_f, pipe length L, flow Q and fluid kinematic
    viscosity ν, solves directly for the diameter without iterating
    Darcy-Weisbach + Colebrook:

        D = 0.66 [ ε^1.25 (L Q² / (g h_f))^4.75
                    + ν Q^9.4 (L / (g h_f))^5.2 ]^0.04

    Parameters
    ----------
    flow_rate_m3s       : float  design flow rate Q [m³/s]
    head_loss_m         : float  allowable head loss h_f [m]
    length_m            : float  pipe length L [m]
    roughness_m         : float  absolute roughness ε [m]
    kinematic_viscosity : float  ν = μ/ρ [m²/s]
    g                   : float  gravitational acceleration [m/s²]

    Returns
    -------
    float
        Required internal pipe diameter D [m].

    Notes
    -----
    Valid for 3,000 < Re < 3×10⁸ and 10⁻⁶ < ε/D < 0.02 (Swamee-Jain, 1976).
    """
    if head_loss_m <= 0:
        raise ValueError(f"Head loss must be positive. Got {head_loss_m} m.")
    if length_m <= 0:
        raise ValueError(f"Length must be positive. Got {length_m} m.")
    if flow_rate_m3s <= 0:
        raise ValueError(f"Flow rate must be positive. Got {flow_rate_m3s} m³/s.")

    term1 = roughness_m ** 1.25 * (length_m * flow_rate_m3s ** 2 / (g * head_loss_m)) ** 4.75
    term2 = (
        kinematic_viscosity
        * flow_rate_m3s ** 9.4
        * (length_m / (g * head_loss_m)) ** 5.2
    )
    return 0.66 * (term1 + term2) ** 0.04


def solve_flow_for_head_loss(
    diameter_m: float,
    head_loss_m: float,
    length_m: float,
    roughness_m: float,
    kinematic_viscosity: float,
    g: float = GRAVITY,
) -> float:
    """Solve for flow rate Q [m³/s] that produces a given head loss.

    Given pipe diameter D, length L and available head h_f, finds the flow
    rate Q such that the Darcy-Weisbach head loss (using the Swamee-Jain
    turbulent friction factor, or Hagen-Poiseuille if the solution falls in
    the laminar regime) equals ``head_loss_m``.

    Implementation note
    --------------------
    The 1976 Swamee-Jain paper also published a closed-form explicit
    approximation for this "discharge problem". However, that formula is
    itself a further approximation layered on top of the already-approximate
    turbulent friction factor, and published transcriptions of its exact
    coefficients/exponents are inconsistent across secondary sources. To
    avoid silently propagating a transcription error, this function instead
    solves the *exact* Darcy-Weisbach + Swamee-Jain relation numerically via
    Brent's method — this guarantees the result is internally consistent
    with ``major_head_loss`` / ``swamee_jain_friction_factor`` elsewhere in
    this package (verified by the round-trip test in
    ``tests/test_friction.py``), at the cost of not being a one-line closed
    form.

    Parameters
    ----------
    diameter_m          : float  internal pipe diameter D [m]
    head_loss_m         : float  available head loss h_f [m]
    length_m            : float  pipe length L [m]
    roughness_m         : float  absolute roughness ε [m]
    kinematic_viscosity : float  ν = μ/ρ [m²/s]
    g                   : float  gravitational acceleration [m/s²]

    Returns
    -------
    float
        Flow rate Q [m³/s] that produces the specified head loss.
    """
    from scipy.optimize import brentq

    if diameter_m <= 0:
        raise ValueError(f"Diameter must be positive. Got {diameter_m} m.")
    if head_loss_m <= 0:
        raise ValueError(f"Head loss must be positive. Got {head_loss_m} m.")
    if length_m <= 0:
        raise ValueError(f"Length must be positive. Got {length_m} m.")

    def head_loss_residual(v: float) -> float:
        reynolds = v * diameter_m / kinematic_viscosity
        if reynolds < 2_300:
            f = 64.0 / reynolds
        else:
            f = swamee_jain_friction_factor(reynolds, diameter_m, roughness_m)
        h_f = f * (length_m / diameter_m) * v ** 2 / (2 * g)
        return h_f - head_loss_m

    # Bracket a physically sensible velocity range [1 mm/s, 100 m/s] and
    # solve for the root with Brent's method (robust, no derivative needed).
    v_lo, v_hi = 1e-3, 100.0
    v_solution = brentq(head_loss_residual, v_lo, v_hi, xtol=1e-10, rtol=1e-12)

    area = PI * diameter_m ** 2 / 4.0
    return v_solution * area
