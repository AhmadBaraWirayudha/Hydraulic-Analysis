"""
NPSH (Net Positive Suction Head) calculation — the standard check for
pump cavitation risk.

Cavitation occurs when local pressure at the pump impeller eye drops below
the fluid's vapor pressure, causing vapor bubbles to form and then
violently collapse downstream — eroding the impeller and causing
performance loss, noise, and vibration. NPSH quantifies the safety margin
above the fluid's vapor pressure at the pump suction.

References
----------
Hydraulic Institute Standards (ANSI/HI) — NPSH margin guidelines.
Karassik, I.J. et al. (2008). Pump Handbook, 4th ed. McGraw-Hill.
"""

from dataclasses import dataclass

from ..utils.constants import GRAVITY


@dataclass
class NPSHResult:
    """Container for an NPSH (cavitation) check."""

    npsh_available_m: float            # NPSHa
    npsh_required_m: float | None      # NPSHr (manufacturer-specified), if known
    margin_m: float | None             # NPSHa - NPSHr, if NPSHr was supplied
    margin_ratio: float | None         # NPSHa / NPSHr, if NPSHr was supplied


def npsh_available(
    suction_pressure_Pa: float,
    vapor_pressure_Pa: float,
    density: float,
    inlet_elevation_m: float = 0.0,
    suction_head_loss_m: float = 0.0,
    g: float = GRAVITY,
) -> float:
    """Net Positive Suction Head available at the pump inlet [m].

        NPSHa = (P_i - P_v) / (rho * g) + z_i - h_L

    Parameters
    ----------
    suction_pressure_Pa : float
        Absolute pressure at the suction source surface [Pa] (e.g.
        atmospheric pressure ~101,325 Pa for an open tank/reservoir).
    vapor_pressure_Pa : float
        Fluid's vapor pressure at the operating temperature [Pa] — see
        ``hydraulics.fluid_properties.water_vapor_pressure``.
    density : float
        Fluid density [kg/m³].
    inlet_elevation_m : float
        Elevation of the suction source surface relative to the pump
        centerline [m]. Positive = flooded suction (source above pump,
        favorable); negative = suction lift (source below pump, working
        against gravity).
    suction_head_loss_m : float
        Friction head loss in the suction-side piping between the source
        and the pump inlet [m] (always a loss; use
        ``hydraulics.head_loss.major_head_loss`` on the suction line if
        modeling it explicitly).
    g : float
        Gravitational acceleration [m/s²].

    Returns
    -------
    float
        NPSH available [m].
    """
    if suction_pressure_Pa <= 0:
        raise ValueError(f"Suction pressure must be positive. Got {suction_pressure_Pa} Pa.")
    if vapor_pressure_Pa < 0:
        raise ValueError(f"Vapor pressure must be non-negative. Got {vapor_pressure_Pa} Pa.")
    if suction_head_loss_m < 0:
        raise ValueError(f"Suction head loss must be non-negative. Got {suction_head_loss_m} m.")

    return (
        (suction_pressure_Pa - vapor_pressure_Pa) / (density * g)
        + inlet_elevation_m
        - suction_head_loss_m
    )


def evaluate_npsh(
    suction_pressure_Pa: float,
    vapor_pressure_Pa: float,
    density: float,
    inlet_elevation_m: float = 0.0,
    suction_head_loss_m: float = 0.0,
    npsh_required_m: float | None = None,
    g: float = GRAVITY,
) -> NPSHResult:
    """Compute NPSHa and, if a manufacturer NPSHr is supplied, the margin
    against it.

    Parameters
    ----------
    npsh_required_m : float | None
        Pump's required NPSH at the operating flow rate, from the
        manufacturer's pump curve. None skips the margin comparison
        (NPSHa is still computed and returned).
    other params : see ``npsh_available``.

    Returns
    -------
    NPSHResult
    """
    npsh_a = npsh_available(
        suction_pressure_Pa, vapor_pressure_Pa, density,
        inlet_elevation_m, suction_head_loss_m, g,
    )

    margin_m = None
    margin_ratio = None
    if npsh_required_m is not None:
        if npsh_required_m <= 0:
            raise ValueError(f"NPSH required must be positive. Got {npsh_required_m} m.")
        margin_m = npsh_a - npsh_required_m
        margin_ratio = npsh_a / npsh_required_m

    return NPSHResult(
        npsh_available_m=npsh_a,
        npsh_required_m=npsh_required_m,
        margin_m=margin_m,
        margin_ratio=margin_ratio,
    )
