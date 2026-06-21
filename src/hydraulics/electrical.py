"""
Electrical and motor dynamics: VFD pump affinity laws, three-phase
electrical power relationships, and voltage-unbalance checking.

References
----------
Pump affinity laws — Karassik, I.J. et al. (2008). Pump Handbook, 4th ed.
  McGraw-Hill.
NEMA MG1-14.36 — voltage unbalance definition and the 5% maximum
  recommended operating threshold (the precise derating-vs-unbalance
  *curve* in MG1-14.36 is published as a graph, not a closed-form formula,
  and published numeric approximations of it vary across secondary
  sources by motor class and load level — see ``check_voltage_unbalance``
  for why this module does not hardcode a specific derating curve).
"""

import math
from dataclasses import dataclass


# ── VFD / Pump Affinity Laws ──────────────────────────────────────────────────
@dataclass
class AffinityResult:
    """Pump performance at a new speed, scaled from a known reference point."""

    flow_m3s: float
    head_m: float
    power_W: float
    speed_ratio: float    # N_new / N_ref


def apply_affinity_laws(
    flow_ref_m3s: float,
    head_ref_m: float,
    power_ref_W: float,
    speed_ratio: float,
) -> AffinityResult:
    """Scale a pump's known performance point to a new speed via the
    affinity laws:

        Q2/Q1 = N2/N1
        H2/H1 = (N2/N1)^2
        P2/P1 = (N2/N1)^3

    Valid for the same pump operating on the same system curve with only
    speed changed (e.g. VFD speed control) — not for comparing different
    pump models or impeller trims.

    Parameters
    ----------
    flow_ref_m3s  : float  flow rate at the reference speed [m³/s]
    head_ref_m    : float  head at the reference speed [m]
    power_ref_W   : float  shaft power at the reference speed [W]
    speed_ratio   : float  N_new / N_ref (e.g. 0.8 for 80% speed)

    Returns
    -------
    AffinityResult
        Scaled flow, head, and power at the new speed.
    """
    if speed_ratio <= 0:
        raise ValueError(f"Speed ratio must be positive. Got {speed_ratio}.")
    if flow_ref_m3s < 0 or head_ref_m < 0 or power_ref_W < 0:
        raise ValueError("Reference flow, head, and power must be non-negative.")

    return AffinityResult(
        flow_m3s=flow_ref_m3s * speed_ratio,
        head_m=head_ref_m * speed_ratio ** 2,
        power_W=power_ref_W * speed_ratio ** 3,
        speed_ratio=speed_ratio,
    )


def speed_ratio_for_target_flow(flow_ref_m3s: float, flow_target_m3s: float) -> float:
    """Solve the affinity flow law for the speed ratio needed to hit a
    target flow rate: N2/N1 = Q2/Q1.
    """
    if flow_ref_m3s <= 0:
        raise ValueError(f"Reference flow must be positive. Got {flow_ref_m3s}.")
    if flow_target_m3s < 0:
        raise ValueError(f"Target flow must be non-negative. Got {flow_target_m3s}.")
    return flow_target_m3s / flow_ref_m3s


def speed_ratio_for_target_head(head_ref_m: float, head_target_m: float) -> float:
    """Solve the affinity head law for the speed ratio needed to hit a
    target head: N2/N1 = sqrt(H2/H1).
    """
    if head_ref_m <= 0:
        raise ValueError(f"Reference head must be positive. Got {head_ref_m}.")
    if head_target_m < 0:
        raise ValueError(f"Target head must be non-negative. Got {head_target_m}.")
    return math.sqrt(head_target_m / head_ref_m)


# ── Three-phase electrical power ──────────────────────────────────────────────
@dataclass
class ElectricalPowerResult:
    """Three-phase electrical power breakdown."""

    apparent_power_VA: float
    real_power_W: float
    reactive_power_VAR: float
    power_factor: float


def three_phase_apparent_power(line_voltage_V: float, line_current_A: float) -> float:
    """Three-phase apparent power: S = sqrt(3) * V_line * I_line [VA]."""
    if line_voltage_V < 0 or line_current_A < 0:
        raise ValueError("Voltage and current must be non-negative.")
    return math.sqrt(3) * line_voltage_V * line_current_A


def evaluate_three_phase_power(
    line_voltage_V: float, line_current_A: float, power_factor: float
) -> ElectricalPowerResult:
    """Full three-phase power breakdown given line voltage, line current,
    and power factor.

        S = sqrt(3) * V * I                  (apparent power, VA)
        P = S * pf                            (real power, W)
        Q = sqrt(S^2 - P^2)                   (reactive power, VAR)

    Parameters
    ----------
    line_voltage_V : float  line-to-line voltage [V]
    line_current_A : float  line current [A]
    power_factor   : float  cos(phi), in [-1, 1]

    Returns
    -------
    ElectricalPowerResult
    """
    if not (-1.0 <= power_factor <= 1.0):
        raise ValueError(f"Power factor must be in [-1, 1]. Got {power_factor}.")

    s = three_phase_apparent_power(line_voltage_V, line_current_A)
    p = s * power_factor
    q = math.sqrt(max(s ** 2 - p ** 2, 0.0))

    return ElectricalPowerResult(
        apparent_power_VA=s, real_power_W=p, reactive_power_VAR=q, power_factor=power_factor,
    )


def motor_current_from_shaft_power(
    shaft_power_W: float,
    line_voltage_V: float,
    power_factor: float,
    motor_efficiency: float = 0.90,
) -> float:
    """Solve for line current draw given required motor shaft (output) power.

        I = P_shaft / (eta_motor * sqrt(3) * V * pf)

    Parameters
    ----------
    shaft_power_W    : float  required mechanical shaft output power [W]
    line_voltage_V   : float  line-to-line voltage [V]
    power_factor     : float  cos(phi), in (0, 1]
    motor_efficiency : float  motor electrical-to-mechanical efficiency (0, 1]

    Returns
    -------
    float
        Line current [A].
    """
    if shaft_power_W < 0:
        raise ValueError(f"Shaft power must be non-negative. Got {shaft_power_W}.")
    if not (0 < power_factor <= 1.0):
        raise ValueError(f"Power factor must be in (0, 1]. Got {power_factor}.")
    if not (0 < motor_efficiency <= 1.0):
        raise ValueError(f"Motor efficiency must be in (0, 1]. Got {motor_efficiency}.")
    if line_voltage_V <= 0:
        raise ValueError(f"Line voltage must be positive. Got {line_voltage_V}.")

    electrical_input_W = shaft_power_W / motor_efficiency
    return electrical_input_W / (math.sqrt(3) * line_voltage_V * power_factor)


# ── Voltage unbalance ──────────────────────────────────────────────────────────
def voltage_unbalance_percent(phase_voltages: list[float]) -> float:
    """NEMA MG1-14.35 voltage unbalance percentage:

        %unbalance = 100 * (max deviation from average) / average

    Parameters
    ----------
    phase_voltages : list[float]  the three line-to-line (or line-to-neutral,
                      as long as all three are the same type) voltage
                      readings [V]

    Returns
    -------
    float
        Voltage unbalance, as a percentage.
    """
    if len(phase_voltages) != 3:
        raise ValueError(f"Expected exactly 3 phase voltage readings. Got {len(phase_voltages)}.")
    if any(v <= 0 for v in phase_voltages):
        raise ValueError("All phase voltages must be positive.")

    average = sum(phase_voltages) / 3
    max_deviation = max(abs(v - average) for v in phase_voltages)
    return 100 * max_deviation / average


def derating_factor_from_curve(
    unbalance_percent: float, curve_points: list[tuple[float, float]]
) -> float:
    """Linearly interpolate a motor derating factor from a user-supplied
    (unbalance_%, derating_factor) calibration curve.

    This deliberately does not ship a built-in NEMA MG1-14.36 curve as a
    hardcoded default: that curve is published as a graph (not a formula),
    and the derating factor it implies depends on motor load level and
    design class — published numeric approximations of it are inconsistent
    across secondary sources. Supply calibration points read directly from
    your motor's datasheet or the actual NEMA MG1-14.36 figure for a
    decision that matters; this function only does the interpolation.

    Parameters
    ----------
    unbalance_percent : float  voltage unbalance, in percent
    curve_points : list[(float, float)]  (unbalance_%, derating_factor)
                    points sorted by unbalance_%, e.g.
                    ``[(0, 1.0), (1, 1.0), (5, 0.85)]``

    Returns
    -------
    float
        Interpolated (or extrapolated, with a warning is the caller's
        responsibility) derating factor.
    """
    if len(curve_points) < 2:
        raise ValueError("Need at least 2 calibration points to interpolate.")
    xs = [p[0] for p in curve_points]
    ys = [p[1] for p in curve_points]
    if xs != sorted(xs):
        raise ValueError("curve_points must be sorted by ascending unbalance_percent.")

    if unbalance_percent <= xs[0]:
        return ys[0]
    if unbalance_percent >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= unbalance_percent <= xs[i + 1]:
            frac = (unbalance_percent - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + frac * (ys[i + 1] - ys[i])
    raise AssertionError("Unreachable — unbalance_percent not bracketed despite range checks.")
