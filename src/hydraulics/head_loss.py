"""
Head loss calculations: major (friction) losses via Darcy-Weisbach, and
minor (fitting/valve) losses via the K-factor method.

References
----------
Darcy-Weisbach equation — Engineering Toolbox / White, F.M., Fluid Mechanics.
"""

from dataclasses import dataclass, field

from ..utils.constants import GRAVITY
from ..utils.validation import validate_pipe, validate_flow, validate_fluid
from .friction import flow_velocity, reynolds_number, darcy_friction_factor


# ── Common minor-loss K-factors (typical literature values) ─────────────────
# Used as a convenience lookup; override per-project as needed.
K_FACTORS: dict[str, float] = {
    "elbow_90_standard": 0.9,
    "elbow_90_long_radius": 0.6,
    "elbow_45": 0.4,
    "tee_through": 0.2,
    "tee_branch": 1.0,
    "gate_valve_open": 0.2,
    "globe_valve_open": 10.0,
    "check_valve": 2.5,
    "entrance_sharp": 0.5,
    "entrance_rounded": 0.05,
    "exit": 1.0,
}


@dataclass
class HeadLossResult:
    """Container for a single head-loss calculation."""

    velocity_m_s: float
    reynolds: float
    friction_factor: float
    major_loss_m: float          # Darcy-Weisbach friction loss
    minor_loss_m: float          # Sum of fitting/valve losses
    total_loss_m: float          # major + minor
    fittings: dict[str, float] = field(default_factory=dict)


def major_head_loss(
    flow_rate_m3s: float,
    diameter_m: float,
    length_m: float,
    roughness_m: float,
    density: float,
    viscosity: float,
    g: float = GRAVITY,
) -> HeadLossResult:
    """Compute major (friction) head loss via Darcy-Weisbach.

        h_f = f (L/D) (v² / 2g)

    Parameters
    ----------
    flow_rate_m3s : float  volumetric flow rate Q [m³/s]
    diameter_m    : float  internal pipe diameter D [m]
    length_m      : float  pipe length L [m]
    roughness_m   : float  absolute roughness ε [m]
    density       : float  fluid density ρ [kg/m³]
    viscosity     : float  dynamic viscosity μ [Pa·s]
    g             : float  gravitational acceleration [m/s²]

    Returns
    -------
    HeadLossResult
        velocity, Reynolds number, friction factor, and major loss [m]
        (minor_loss_m = 0, total_loss_m = major_loss_m).
    """
    validate_pipe(diameter_m, length_m, roughness_m)
    validate_flow(flow_rate_m3s)
    validate_fluid(density, viscosity)

    v = flow_velocity(flow_rate_m3s, diameter_m)
    re = reynolds_number(v, diameter_m, density, viscosity)
    f = darcy_friction_factor(re, diameter_m, roughness_m)
    h_f = f * (length_m / diameter_m) * (v ** 2) / (2 * g)

    return HeadLossResult(
        velocity_m_s=v,
        reynolds=re,
        friction_factor=f,
        major_loss_m=h_f,
        minor_loss_m=0.0,
        total_loss_m=h_f,
    )


def minor_head_loss(velocity_m_s: float, k_factor: float, g: float = GRAVITY) -> float:
    """Minor loss for a single fitting/valve.

        h_minor = K (v² / 2g)

    Parameters
    ----------
    velocity_m_s : float  local mean velocity through the fitting [m/s]
    k_factor     : float  dimensionless loss coefficient K
    g            : float  gravitational acceleration [m/s²]
    """
    if k_factor < 0:
        raise ValueError(f"K-factor must be non-negative. Got {k_factor}.")
    return k_factor * (velocity_m_s ** 2) / (2 * g)


def total_head_loss(
    flow_rate_m3s: float,
    diameter_m: float,
    length_m: float,
    roughness_m: float,
    density: float,
    viscosity: float,
    fittings: dict[str, float] | None = None,
    g: float = GRAVITY,
) -> HeadLossResult:
    """Compute total head loss = major (friction) + minor (fittings).

    Parameters
    ----------
    fittings : dict[str, float] | None
        Mapping of fitting name -> count, e.g. ``{"elbow_90_standard": 4,
        "gate_valve_open": 1}``. Names are looked up in ``K_FACTORS``; pass
        a custom dict to override.
    other params : see ``major_head_loss``.

    Returns
    -------
    HeadLossResult
        Full breakdown of velocity, Reynolds number, friction factor,
        major/minor/total losses, and the per-fitting loss breakdown [m].
    """
    major = major_head_loss(
        flow_rate_m3s, diameter_m, length_m, roughness_m, density, viscosity, g
    )

    fitting_losses: dict[str, float] = {}
    minor_total = 0.0
    if fittings:
        for name, count in fittings.items():
            if name not in K_FACTORS:
                raise ValueError(
                    f"Unknown fitting '{name}'. Known fittings: {list(K_FACTORS)}"
                )
            loss = minor_head_loss(major.velocity_m_s, K_FACTORS[name], g) * count
            fitting_losses[name] = loss
            minor_total += loss

    return HeadLossResult(
        velocity_m_s=major.velocity_m_s,
        reynolds=major.reynolds,
        friction_factor=major.friction_factor,
        major_loss_m=major.major_loss_m,
        minor_loss_m=minor_total,
        total_loss_m=major.major_loss_m + minor_total,
        fittings=fitting_losses,
    )
