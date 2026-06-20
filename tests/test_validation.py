"""
Unit tests for src/utils/validation.py (Poka-Yoke input checks).
"""

import pytest

from src.utils.validation import (
    validate_pipe,
    validate_flow,
    validate_fluid,
    validate_pump,
    check_velocity,
    check_pump_load,
)
from src.utils.constants import SNI_VELOCITY_MIN, SNI_VELOCITY_MAX


# ── validate_pipe ──────────────────────────────────────────────────────────
def test_validate_pipe_accepts_reasonable_values():
    validate_pipe(diameter_m=0.1, length_m=100.0, roughness_m=1.5e-6)  # should not raise


def test_validate_pipe_rejects_zero_or_negative_diameter():
    with pytest.raises(ValueError):
        validate_pipe(0.0, 100.0, 1.5e-6)
    with pytest.raises(ValueError):
        validate_pipe(-0.05, 100.0, 1.5e-6)


def test_validate_pipe_rejects_unrealistically_large_diameter():
    with pytest.raises(ValueError):
        validate_pipe(5.0, 100.0, 1.5e-6)


def test_validate_pipe_rejects_nonpositive_length():
    with pytest.raises(ValueError):
        validate_pipe(0.1, 0.0, 1.5e-6)


def test_validate_pipe_rejects_negative_roughness():
    with pytest.raises(ValueError):
        validate_pipe(0.1, 100.0, -1e-6)


def test_validate_pipe_rejects_roughness_exceeding_diameter():
    with pytest.raises(ValueError):
        validate_pipe(0.001, 100.0, 0.01)  # roughness > diameter


# ── validate_flow ──────────────────────────────────────────────────────────
def test_validate_flow_accepts_zero_and_positive():
    validate_flow(0.0)
    validate_flow(0.05)


def test_validate_flow_rejects_negative():
    with pytest.raises(ValueError):
        validate_flow(-0.01)


def test_validate_flow_rejects_unrealistically_high():
    with pytest.raises(ValueError):
        validate_flow(100.0)


# ── validate_fluid ─────────────────────────────────────────────────────────
def test_validate_fluid_accepts_water_properties():
    validate_fluid(997.0, 1.0e-3)


def test_validate_fluid_rejects_nonpositive_density():
    with pytest.raises(ValueError):
        validate_fluid(0.0, 1.0e-3)
    with pytest.raises(ValueError):
        validate_fluid(-10.0, 1.0e-3)


def test_validate_fluid_rejects_nonpositive_viscosity():
    with pytest.raises(ValueError):
        validate_fluid(997.0, 0.0)


def test_validate_fluid_rejects_absurd_density():
    with pytest.raises(ValueError):
        validate_fluid(50_000.0, 1.0e-3)


# ── validate_pump ──────────────────────────────────────────────────────────
def test_validate_pump_accepts_valid_efficiencies():
    validate_pump(0.75, 0.9)
    validate_pump(1.0, 1.0)


@pytest.mark.parametrize("eta_p,eta_m", [(0.0, 0.9), (1.5, 0.9), (-0.1, 0.9)])
def test_validate_pump_rejects_invalid_pump_efficiency(eta_p, eta_m):
    with pytest.raises(ValueError):
        validate_pump(eta_p, eta_m)


@pytest.mark.parametrize("eta_p,eta_m", [(0.75, 0.0), (0.75, 1.5), (0.75, -0.1)])
def test_validate_pump_rejects_invalid_motor_efficiency(eta_p, eta_m):
    with pytest.raises(ValueError):
        validate_pump(eta_p, eta_m)


# ── check_velocity (SNI guidance, warning-only) ───────────────────────────
def test_check_velocity_within_sni_range_returns_none():
    assert check_velocity((SNI_VELOCITY_MIN + SNI_VELOCITY_MAX) / 2) is None


def test_check_velocity_below_minimum_returns_warning():
    warning = check_velocity(SNI_VELOCITY_MIN - 0.1)
    assert warning is not None
    assert "below SNI minimum" in warning


def test_check_velocity_very_low_returns_sedimentation_warning():
    warning = check_velocity(0.1)
    assert warning is not None
    assert "sediment" in warning.lower()


def test_check_velocity_above_maximum_returns_warning():
    warning = check_velocity(SNI_VELOCITY_MAX + 0.5)
    assert warning is not None
    assert "exceeds SNI maximum" in warning


# ── check_pump_load (Muri / overburden check) ─────────────────────────────
def test_check_pump_load_returns_none_when_no_rated_power():
    assert check_pump_load(500.0, None) is None
    assert check_pump_load(500.0, 0.0) is None
    assert check_pump_load(500.0, -10.0) is None


def test_check_pump_load_under_80_percent_returns_none():
    assert check_pump_load(500.0, 1000.0) is None  # 50%
    assert check_pump_load(799.0, 1000.0) is None  # 79.9%


def test_check_pump_load_between_80_and_100_percent_warns_approaching():
    warning = check_pump_load(900.0, 1000.0)  # 90%
    assert warning is not None
    assert "Muri" in warning
    assert "90%" in warning


def test_check_pump_load_over_100_percent_warns_overloaded():
    warning = check_pump_load(1200.0, 1000.0)  # 120%
    assert warning is not None
    assert "overloaded" in warning.lower()
    assert "120%" in warning


def test_check_pump_load_exactly_80_percent_is_not_yet_warned():
    """80% is the boundary; should not yet trigger (strictly > 0.8)."""
    assert check_pump_load(800.0, 1000.0) is None


def test_check_pump_load_exactly_100_percent_is_not_yet_overloaded():
    """100% is the boundary; should warn as 'approaching', not 'overloaded'."""
    warning = check_pump_load(1000.0, 1000.0)
    assert warning is not None
    assert "overloaded" not in warning.lower()
