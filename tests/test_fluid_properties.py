"""
Unit tests for src/hydraulics/fluid_properties.py — Andrade viscosity and
Antoine vapor pressure equations, including the pre-fitted water
convenience functions.

Reference values are standard steam-table / engineering-toolbox figures
for water; tolerances match the documented fit accuracy (see
fluid_properties.py and utils/constants.py docstrings).
"""

import numpy as np
import pytest

from src.hydraulics.fluid_properties import (
    andrade_viscosity, fit_andrade_coefficients, water_viscosity, water_viscosity_warning,
    antoine_vapor_pressure, fit_antoine_coefficients, water_vapor_pressure,
    water_vapor_pressure_warning,
)
from src.utils.constants import WATER_THERMAL_FIT_MIN_K, WATER_THERMAL_FIT_MAX_K


# ── Andrade viscosity ──────────────────────────────────────────────────────
def test_andrade_viscosity_known_formula():
    # mu = A * exp(B/T); sanity check the raw formula directly.
    A, B, T = 1e-6, 2000.0, 300.0
    expected = A * np.exp(B / T)
    assert andrade_viscosity(A, B, T) == pytest.approx(expected)


def test_andrade_viscosity_rejects_nonpositive_temperature():
    with pytest.raises(ValueError):
        andrade_viscosity(1e-6, 2000.0, 0.0)
    with pytest.raises(ValueError):
        andrade_viscosity(1e-6, 2000.0, -10.0)


def test_andrade_viscosity_decreases_with_temperature():
    """Physical sanity check: liquid viscosity should drop as temperature rises."""
    A, B = 1.846506e-6, 1853.5603
    mu_cold = andrade_viscosity(A, B, 280.0)
    mu_hot = andrade_viscosity(A, B, 360.0)
    assert mu_hot < mu_cold


def test_water_viscosity_matches_known_reference_values():
    # Reference: water viscosity @ 20 degC ~= 1.002 mPa.s (within fit accuracy ~3%)
    mu_20C = water_viscosity(293.15)
    assert mu_20C == pytest.approx(1.002e-3, rel=0.05)

    # Reference: water viscosity @ 0 degC ~= 1.787 mPa.s (fit is weakest here, ~8.5% off)
    mu_0C = water_viscosity(273.15)
    assert mu_0C == pytest.approx(1.787e-3, rel=0.10)

    # Reference: water viscosity @ 100 degC ~= 0.282 mPa.s
    mu_100C = water_viscosity(373.15)
    assert mu_100C == pytest.approx(0.282e-3, rel=0.10)


def test_water_viscosity_warning_within_range_is_none():
    assert water_viscosity_warning(293.15) is None
    assert water_viscosity_warning(WATER_THERMAL_FIT_MIN_K) is None
    assert water_viscosity_warning(WATER_THERMAL_FIT_MAX_K) is None


def test_water_viscosity_warning_outside_range():
    assert water_viscosity_warning(WATER_THERMAL_FIT_MIN_K - 10) is not None
    assert water_viscosity_warning(WATER_THERMAL_FIT_MAX_K + 10) is not None


def test_fit_andrade_coefficients_roundtrip():
    """Fitting against data generated from known A, B should recover them."""
    A_true, B_true = 2.0e-6, 1900.0
    temps = np.array([280.0, 300.0, 320.0, 340.0, 360.0])
    visc = A_true * np.exp(B_true / temps)
    A_fit, B_fit = fit_andrade_coefficients(temps, visc)
    assert A_fit == pytest.approx(A_true, rel=1e-6)
    assert B_fit == pytest.approx(B_true, rel=1e-6)


def test_fit_andrade_coefficients_rejects_too_few_points():
    with pytest.raises(ValueError):
        fit_andrade_coefficients(np.array([300.0]), np.array([1e-3]))


def test_fit_andrade_coefficients_rejects_nonpositive_viscosity():
    with pytest.raises(ValueError):
        fit_andrade_coefficients(np.array([280.0, 300.0]), np.array([1e-3, -1e-3]))


# ── Antoine vapor pressure ─────────────────────────────────────────────────
def test_antoine_vapor_pressure_known_formula():
    A, B, C, T = 10.0, 1700.0, -30.0, 350.0
    expected = 10 ** (A - B / (T + C))
    assert antoine_vapor_pressure(A, B, C, T) == pytest.approx(expected)


def test_antoine_vapor_pressure_rejects_singularity():
    # T + C <= 0 should raise rather than silently blow up.
    with pytest.raises(ValueError):
        antoine_vapor_pressure(10.0, 1700.0, -350.0, 300.0)  # T+C = -50


def test_water_vapor_pressure_matches_boiling_point_exactly():
    """100 degC must equal 1 atm (101,325 Pa) by definition — strong sanity check."""
    p = water_vapor_pressure(373.15)
    assert p == pytest.approx(101_325, rel=0.001)


def test_water_vapor_pressure_matches_known_reference_values():
    # Reference: water vapor pressure @ 20 degC ~= 2339 Pa
    assert water_vapor_pressure(293.15) == pytest.approx(2339, rel=0.01)
    # Reference: water vapor pressure @ 60 degC ~= 19932 Pa
    assert water_vapor_pressure(333.15) == pytest.approx(19932, rel=0.01)


def test_water_vapor_pressure_increases_with_temperature():
    p_cold = water_vapor_pressure(280.0)
    p_hot = water_vapor_pressure(360.0)
    assert p_hot > p_cold


def test_water_vapor_pressure_warning_within_range_is_none():
    assert water_vapor_pressure_warning(293.15) is None


def test_water_vapor_pressure_warning_outside_range():
    assert water_vapor_pressure_warning(WATER_THERMAL_FIT_MIN_K - 5) is not None
    assert water_vapor_pressure_warning(WATER_THERMAL_FIT_MAX_K + 5) is not None


def test_fit_antoine_coefficients_roundtrip():
    """Fitting against data generated from known A, B, C should recover them closely."""
    A_true, B_true, C_true = 10.0, 1700.0, -35.0
    temps = np.array([280.0, 300.0, 320.0, 340.0, 360.0, 373.15])
    pressures = 10 ** (A_true - B_true / (temps + C_true))
    A_fit, B_fit, C_fit = fit_antoine_coefficients(temps, pressures)
    assert A_fit == pytest.approx(A_true, rel=1e-3)
    assert B_fit == pytest.approx(B_true, rel=1e-3)
    assert C_fit == pytest.approx(C_true, rel=1e-2)


def test_fit_antoine_coefficients_rejects_too_few_points():
    with pytest.raises(ValueError):
        fit_antoine_coefficients(np.array([280.0, 300.0]), np.array([1000.0, 2000.0]))
