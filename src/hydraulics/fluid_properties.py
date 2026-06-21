"""
Temperature-dependent fluid properties: Andrade viscosity equation and
Antoine vapor pressure equation, with generic fitting utilities plus
pre-fitted convenience functions for water.

Both equations here are 2-3 parameter *engineering approximations*, not
exact thermodynamic relations — see each function's docstring for the
fitted accuracy and valid temperature range. Extrapolating beyond the
fitted range produces a warning rather than a silent (and increasingly
unreliable) extrapolation.

References
----------
Andrade, E.N. da C. (1930). The viscosity of liquids. Nature, 125, 309-310.
Antoine, C. (1888). Tensions des vapeurs: nouvelle relation entre les
  tensions et les temperatures. Comptes Rendus, 107, 681-684, 778-780, 836-837.
"""

import math

import numpy as np

from ..utils.constants import (
    WATER_ANDRADE_A, WATER_ANDRADE_B,
    WATER_ANTOINE_A, WATER_ANTOINE_B, WATER_ANTOINE_C,
    WATER_THERMAL_FIT_MIN_K, WATER_THERMAL_FIT_MAX_K,
)


def _range_warning(temperature_K: float, label: str) -> str | None:
    """Shared out-of-calibration-range warning for the water-specific fits."""
    if temperature_K < WATER_THERMAL_FIT_MIN_K or temperature_K > WATER_THERMAL_FIT_MAX_K:
        return (
            f"⚠️  {label}: temperature {temperature_K:.1f} K is outside the "
            f"fitted calibration range [{WATER_THERMAL_FIT_MIN_K:.1f}, "
            f"{WATER_THERMAL_FIT_MAX_K:.1f}] K — extrapolating beyond this "
            f"range is increasingly unreliable."
        )
    return None


# ── Andrade viscosity equation ────────────────────────────────────────────────
def andrade_viscosity(A: float, B: float, temperature_K: float) -> float:
    """Dynamic viscosity via the (2-parameter) Andrade equation.

        mu(T) = A * exp(B / T)

    Parameters
    ----------
    A : float  pre-exponential coefficient [Pa·s]
    B : float  exponential coefficient [K]
    temperature_K : float  absolute temperature [K]

    Returns
    -------
    float
        Dynamic viscosity [Pa·s].
    """
    if temperature_K <= 0:
        raise ValueError(f"Temperature must be positive (Kelvin). Got {temperature_K} K.")
    return A * math.exp(B / temperature_K)


def fit_andrade_coefficients(
    temperatures_K: np.ndarray, viscosities_Pas: np.ndarray
) -> tuple[float, float]:
    """Fit Andrade coefficients (A, B) to calibration data via linear
    regression of ln(mu) vs. 1/T — the standard fitting procedure for this
    equation (only 2 points are strictly needed; more points average out
    measurement noise).

    Parameters
    ----------
    temperatures_K   : array-like  calibration temperatures [K]
    viscosities_Pas  : array-like  measured dynamic viscosities [Pa·s]

    Returns
    -------
    (A, B) : tuple[float, float]
    """
    temperatures_K = np.asarray(temperatures_K, dtype=float)
    viscosities_Pas = np.asarray(viscosities_Pas, dtype=float)
    if len(temperatures_K) < 2:
        raise ValueError("Need at least 2 calibration points to fit Andrade coefficients.")
    if np.any(viscosities_Pas <= 0):
        raise ValueError("All viscosities must be positive.")

    x = 1.0 / temperatures_K
    y = np.log(viscosities_Pas)
    B, ln_A = np.polyfit(x, y, 1)
    return float(np.exp(ln_A)), float(B)


def water_viscosity(temperature_K: float) -> float:
    """Dynamic viscosity of water at the given temperature, via Andrade
    coefficients pre-fitted to standard 0-100 degC reference data
    (R² = 0.9875; error up to ~8.5% at 0 degC, generally <5% from 10-90 degC
    — see ``utils.constants.WATER_ANDRADE_A/B`` for fit details).

    For applications needing better accuracy, or a different fluid
    entirely, calibrate your own coefficients with
    ``fit_andrade_coefficients`` and call ``andrade_viscosity`` directly.

    Parameters
    ----------
    temperature_K : float  water temperature [K]

    Returns
    -------
    float
        Dynamic viscosity [Pa·s].
    """
    return andrade_viscosity(WATER_ANDRADE_A, WATER_ANDRADE_B, temperature_K)


def water_viscosity_warning(temperature_K: float) -> str | None:
    """Return a warning if ``temperature_K`` falls outside the calibration
    range used to fit ``water_viscosity``'s Andrade coefficients."""
    return _range_warning(temperature_K, "Water viscosity model")


# ── Antoine vapor pressure equation ───────────────────────────────────────────
def antoine_vapor_pressure(A: float, B: float, C: float, temperature_K: float) -> float:
    """Saturation vapor pressure via the (3-parameter) Antoine equation.

        log10(P_sat [Pa]) = A - B / (T + C)

    Parameters
    ----------
    A, B, C : float  Antoine coefficients (units consistent with the
                       calibration — this implementation expects Pa, K)
    temperature_K : float  absolute temperature [K]

    Returns
    -------
    float
        Saturation vapor pressure [Pa].
    """
    if temperature_K + C <= 0:
        raise ValueError(
            f"Antoine equation singularity: T + C = {temperature_K + C} <= 0. "
            f"Temperature is far outside this correlation's valid range."
        )
    return 10 ** (A - B / (temperature_K + C))


def fit_antoine_coefficients(
    temperatures_K: np.ndarray, vapor_pressures_Pa: np.ndarray
) -> tuple[float, float, float]:
    """Fit Antoine coefficients (A, B, C) to calibration data via nonlinear
    least squares.

    Parameters
    ----------
    temperatures_K      : array-like  calibration temperatures [K]
    vapor_pressures_Pa  : array-like  measured saturation vapor pressures [Pa]

    Returns
    -------
    (A, B, C) : tuple[float, float, float]
    """
    from scipy.optimize import curve_fit

    temperatures_K = np.asarray(temperatures_K, dtype=float)
    vapor_pressures_Pa = np.asarray(vapor_pressures_Pa, dtype=float)
    if len(temperatures_K) < 3:
        raise ValueError("Need at least 3 calibration points to fit Antoine coefficients.")

    def _antoine(T, A, B, C):
        return 10 ** (A - B / (T + C))

    popt, _ = curve_fit(
        _antoine, temperatures_K, vapor_pressures_Pa,
        p0=[10.0, 1700.0, -30.0], maxfev=20000,
    )
    return float(popt[0]), float(popt[1]), float(popt[2])


def water_vapor_pressure(temperature_K: float) -> float:
    """Saturation vapor pressure of water at the given temperature, via
    Antoine coefficients pre-fitted to standard steam-table reference data
    over 0-100 degC (R² > 0.99999, max error ~1.5% at 0 degC, <0.1% from
    30-100 degC — see ``utils.constants.WATER_ANTOINE_A/B/C`` for fit
    details). Used primarily as the vapor-pressure input for NPSH
    (cavitation) calculations — see ``hydraulics.npsh``.

    Parameters
    ----------
    temperature_K : float  water temperature [K]

    Returns
    -------
    float
        Saturation vapor pressure [Pa].
    """
    return antoine_vapor_pressure(
        WATER_ANTOINE_A, WATER_ANTOINE_B, WATER_ANTOINE_C, temperature_K
    )


def water_vapor_pressure_warning(temperature_K: float) -> str | None:
    """Return a warning if ``temperature_K`` falls outside the calibration
    range used to fit ``water_vapor_pressure``'s Antoine coefficients."""
    return _range_warning(temperature_K, "Water vapor pressure model")
