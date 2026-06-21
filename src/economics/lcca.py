"""
Lifecycle Cost Analysis (LCCA): compares the capital expenditure (CAPEX) of
pipe/pump sizing choices against their operating expenditure (OPEX, mainly
electricity to overcome friction) over a multi-year horizon, discounted to
present value.

Design note on cost inputs
---------------------------
This module does **not** hardcode any real-world unit costs (pipe $/m,
electricity $/kWh, pump $/kW, etc.) — actual prices vary enormously by
region, supplier, and time, and presenting fabricated figures as if they
were reliable market data would be misleading. Every cost input here is
explicitly supplied by the caller (or interpolated from caller-supplied
calibration points, e.g. real supplier quotes at a few diameters). See
``configs/economics_config.yaml`` for where these assumptions live in the
config-driven pipeline.

This module performs factual present-value arithmetic only — it does not
provide investment recommendations. Consult a qualified financial advisor
for actual capital-allocation decisions.
"""

from dataclasses import dataclass


def interpolate_cost_curve(x: float, curve_points: list[tuple[float, float]]) -> float:
    """Linearly interpolate (or clamp-extrapolate) a cost from calibration
    points, e.g. (diameter_m, cost_per_m) pairs from real supplier quotes.

    Parameters
    ----------
    x : float  the input to look up (e.g. a pipe diameter [m])
    curve_points : list[(float, float)]  (x, cost) pairs sorted by ascending x

    Returns
    -------
    float
        Interpolated cost; clamped to the nearest endpoint if ``x`` falls
        outside the calibration range (no silent extrapolation beyond the
        edge values).
    """
    if len(curve_points) < 2:
        raise ValueError("Need at least 2 calibration points to interpolate.")
    xs = [p[0] for p in curve_points]
    ys = [p[1] for p in curve_points]
    if xs != sorted(xs):
        raise ValueError("curve_points must be sorted by ascending x.")

    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            frac = (x - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + frac * (ys[i + 1] - ys[i])
    raise AssertionError("Unreachable — x not bracketed despite range checks.")


def pipe_capex(length_m: float, unit_cost_per_m: float) -> float:
    """Pipe material + installation cost: length × unit cost.

    Parameters
    ----------
    length_m        : float  pipe length [m]
    unit_cost_per_m : float  installed cost per metre, in whatever
                              currency the caller is working in (e.g. from
                              ``interpolate_cost_curve`` against real
                              supplier quotes at the chosen diameter)
    """
    if length_m < 0:
        raise ValueError(f"Length must be non-negative. Got {length_m}.")
    if unit_cost_per_m < 0:
        raise ValueError(f"Unit cost must be non-negative. Got {unit_cost_per_m}.")
    return length_m * unit_cost_per_m


def annual_energy_cost(
    electrical_power_W: float,
    operating_hours_per_year: float,
    electricity_price_per_kWh: float,
) -> float:
    """Annual electricity cost to run the pump at a constant operating point.

        cost = (P [kW]) × (hours/year) × (price/kWh)

    Parameters
    ----------
    electrical_power_W       : float  electrical power draw [W] — use
                                ``ScenarioResult.pump.shaft_power_W``, which
                                in this codebase already represents the
                                motor's electrical input (i.e. hydraulic
                                power divided by both pump and motor
                                efficiency)
    operating_hours_per_year : float  hours/year the pump actually runs
    electricity_price_per_kWh : float  in whatever currency the caller uses

    Returns
    -------
    float
        Annual energy cost, same currency as ``electricity_price_per_kWh``.
    """
    if electrical_power_W < 0:
        raise ValueError(f"Power must be non-negative. Got {electrical_power_W}.")
    if operating_hours_per_year < 0 or operating_hours_per_year > 8760:
        raise ValueError(
            f"Operating hours/year must be in [0, 8760]. Got {operating_hours_per_year}."
        )
    if electricity_price_per_kWh < 0:
        raise ValueError(f"Electricity price must be non-negative. Got {electricity_price_per_kWh}.")

    power_kW = electrical_power_W / 1000.0
    return power_kW * operating_hours_per_year * electricity_price_per_kWh


@dataclass
class LCCAResult:
    """Lifecycle cost analysis result for one alternative (e.g. one pipe
    diameter choice)."""

    capex: float
    annual_opex_year1: float
    present_value_opex: float
    total_lifecycle_cost: float    # capex + present_value_opex
    years: int
    discount_rate: float
    opex_escalation_rate: float


def evaluate_lifecycle_cost(
    capex: float,
    annual_opex: float,
    years: int,
    discount_rate: float,
    opex_escalation_rate: float = 0.0,
) -> LCCAResult:
    """Present value of a (possibly escalating) annual cost stream, plus
    upfront capital cost — i.e. total lifecycle cost.

        PV = C0 + sum_{t=1}^{T} [OPEX * (1+g)^(t-1)] / (1+r)^t

    where C0 is CAPEX (paid at t=0, not discounted), OPEX is the year-1
    operating cost, g is the annual OPEX escalation rate (e.g. inflation or
    energy price growth), and r is the discount rate.

    Note on terminology: this follows the NPV formula structure
    ``NPV = sum(C_t / (1+r)^t) - C0`` from common LCCA references, but
    since every C_t here is a *cost* (not a net cash inflow), the result
    is a **present value of total cost** — lower is better when comparing
    alternatives, unlike a conventional investment NPV where higher/
    positive is better. This function does not recommend an alternative;
    it only computes the comparison metric.

    Parameters
    ----------
    capex                : float  upfront capital cost (pipe + pump install)
    annual_opex          : float  year-1 operating cost (e.g. from
                            ``annual_energy_cost``, plus any maintenance)
    years                : int    analysis horizon, in years
    discount_rate        : float  annual discount rate (e.g. 0.07 for 7%)
    opex_escalation_rate : float  annual OPEX growth rate (default 0 = flat)

    Returns
    -------
    LCCAResult
    """
    if capex < 0:
        raise ValueError(f"CAPEX must be non-negative. Got {capex}.")
    if annual_opex < 0:
        raise ValueError(f"Annual OPEX must be non-negative. Got {annual_opex}.")
    if years <= 0:
        raise ValueError(f"Years must be positive. Got {years}.")
    if discount_rate <= -1.0:
        raise ValueError(f"Discount rate must be > -1.0. Got {discount_rate}.")

    pv_opex = sum(
        annual_opex * (1 + opex_escalation_rate) ** (t - 1) / (1 + discount_rate) ** t
        for t in range(1, years + 1)
    )

    return LCCAResult(
        capex=capex,
        annual_opex_year1=annual_opex,
        present_value_opex=pv_opex,
        total_lifecycle_cost=capex + pv_opex,
        years=years,
        discount_rate=discount_rate,
        opex_escalation_rate=opex_escalation_rate,
    )
