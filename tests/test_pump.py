"""
Unit tests for src/hydraulics/pump.py (power and Gouy-Stodola exergy).
"""

import pytest

from src.hydraulics.pump import (
    hydraulic_power,
    pump_shaft_power,
    exergy_destruction,
)
from src.utils.constants import WATER_DENSITY, GRAVITY


def test_hydraulic_power_known_value():
    # P = rho * g * Q * h
    Q, h = 0.01, 10.0
    p = hydraulic_power(Q, h, WATER_DENSITY)
    expected = WATER_DENSITY * GRAVITY * Q * h
    assert p == pytest.approx(expected)


def test_hydraulic_power_zero_flow_is_zero():
    assert hydraulic_power(0.0, 10.0, WATER_DENSITY) == 0.0


def test_hydraulic_power_rejects_negative_flow():
    with pytest.raises(ValueError):
        hydraulic_power(-0.01, 10.0, WATER_DENSITY)


def test_pump_shaft_power_efficiency_increases_power_needed():
    Q, h = 0.01, 10.0
    result_high_eta = pump_shaft_power(Q, h, WATER_DENSITY, eta_pump=0.9, eta_motor=0.95)
    result_low_eta = pump_shaft_power(Q, h, WATER_DENSITY, eta_pump=0.5, eta_motor=0.7)
    # Lower efficiency means more shaft power is needed for the same hydraulic output.
    assert result_low_eta.shaft_power_W > result_high_eta.shaft_power_W
    assert result_high_eta.hydraulic_power_W == pytest.approx(result_low_eta.hydraulic_power_W)


def test_pump_shaft_power_overall_efficiency():
    result = pump_shaft_power(0.01, 10.0, WATER_DENSITY, eta_pump=0.8, eta_motor=0.9)
    assert result.overall_efficiency == pytest.approx(0.72)
    assert result.shaft_power_W == pytest.approx(result.hydraulic_power_W / 0.72)


def test_pump_shaft_power_rejects_invalid_efficiency():
    with pytest.raises(ValueError):
        pump_shaft_power(0.01, 10.0, WATER_DENSITY, eta_pump=1.5, eta_motor=0.9)
    with pytest.raises(ValueError):
        pump_shaft_power(0.01, 10.0, WATER_DENSITY, eta_pump=0.8, eta_motor=0.0)


def test_exergy_destruction_equals_friction_power():
    """Gouy-Stodola: X_destroyed should equal rho*g*Q*h_f (friction power)."""
    Q, h, T0 = 0.01, 10.0, 298.15
    shaft_power = 200.0  # arbitrary, only affects the *fraction* output
    result = exergy_destruction(Q, h, WATER_DENSITY, shaft_power, ambient_temp_K=T0)
    expected_x = WATER_DENSITY * GRAVITY * Q * h
    assert result.exergy_destruction_W == pytest.approx(expected_x)
    assert result.entropy_generation_rate_W_per_K == pytest.approx(expected_x / T0)


def test_exergy_destruction_fraction_is_between_zero_and_above():
    Q, h, T0 = 0.01, 10.0, 298.15
    shaft_power = 1000.0
    result = exergy_destruction(Q, h, WATER_DENSITY, shaft_power, ambient_temp_K=T0)
    assert result.exergy_destruction_fraction == pytest.approx(
        result.exergy_destruction_W / shaft_power
    )


def test_exergy_destruction_rejects_nonpositive_temperature():
    with pytest.raises(ValueError):
        exergy_destruction(0.01, 10.0, WATER_DENSITY, 100.0, ambient_temp_K=0)


def test_exergy_destruction_higher_ambient_temp_lowers_entropy_gen():
    Q, h = 0.01, 10.0
    shaft_power = 200.0
    cold = exergy_destruction(Q, h, WATER_DENSITY, shaft_power, ambient_temp_K=273.15)
    warm = exergy_destruction(Q, h, WATER_DENSITY, shaft_power, ambient_temp_K=320.0)
    # Same X_destroyed (doesn't depend on T0), but entropy gen rate = X/T0 is lower for higher T0.
    assert cold.exergy_destruction_W == pytest.approx(warm.exergy_destruction_W)
    assert warm.entropy_generation_rate_W_per_K < cold.entropy_generation_rate_W_per_K
