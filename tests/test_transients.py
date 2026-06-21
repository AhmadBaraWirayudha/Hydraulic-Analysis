"""
Unit tests for src/hydraulics/transients.py — Korteweg wave speed,
Joukowsky surge pressure, and rapid/slow closure classification.

Reference checks:
- Rigid-pipe limit (E -> infinity) must reduce to the unconfined sonic
  speed sqrt(K/rho) (~1485 m/s for water) — a strong, source-independent
  sanity check on the Korteweg formula implementation.
- Steel/PVC wave speeds should fall within commonly cited literature
  ranges (steel ~1000-1500 m/s, plastics noticeably lower).
"""

import math
import pytest

from src.hydraulics.transients import (
    wave_speed, joukowsky_surge_pressure, pipe_critical_period_s,
    evaluate_water_hammer, WaterHammerResult,
)
from src.utils.validation import check_water_hammer_risk
from src.utils.constants import (
    WATER_BULK_MODULUS_PA, WATER_DENSITY,
    STEEL_YOUNGS_MODULUS_PA, PVC_YOUNGS_MODULUS_PA,
)


# ── wave_speed ──────────────────────────────────────────────────────────────
def test_wave_speed_rigid_pipe_limit_matches_unconfined_sonic_speed():
    """As E -> infinity, a -> sqrt(K/rho) (the unconfined speed of sound in
    the fluid) — a strong, material-independent sanity check."""
    a = wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.005, youngs_modulus_Pa=1e15)
    expected = math.sqrt(WATER_BULK_MODULUS_PA / WATER_DENSITY)
    assert a == pytest.approx(expected, rel=1e-4)


def test_wave_speed_steel_pipe_within_literature_range():
    a = wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.005, STEEL_YOUNGS_MODULUS_PA)
    assert 1000 <= a <= 1500   # commonly cited steel-pipe range


def test_wave_speed_pvc_lower_than_steel():
    """Plastic pipes are less stiff -> lower wave speed than steel, all else equal."""
    a_steel = wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.005, STEEL_YOUNGS_MODULUS_PA)
    a_pvc = wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.005, PVC_YOUNGS_MODULUS_PA)
    assert a_pvc < a_steel


def test_wave_speed_thinner_wall_reduces_speed():
    """A thinner wall (relative to diameter) is less stiff -> lower wave speed."""
    a_thick = wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.010, STEEL_YOUNGS_MODULUS_PA)
    a_thin = wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.002, STEEL_YOUNGS_MODULUS_PA)
    assert a_thin < a_thick


def test_wave_speed_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        wave_speed(-1, WATER_DENSITY, 0.1, 0.005, STEEL_YOUNGS_MODULUS_PA)
    with pytest.raises(ValueError):
        wave_speed(WATER_BULK_MODULUS_PA, 0, 0.1, 0.005, STEEL_YOUNGS_MODULUS_PA)
    with pytest.raises(ValueError):
        wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0, 0.005, STEEL_YOUNGS_MODULUS_PA)
    with pytest.raises(ValueError):
        wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0, STEEL_YOUNGS_MODULUS_PA)
    with pytest.raises(ValueError):
        wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.005, 0)


# ── joukowsky_surge_pressure ────────────────────────────────────────────────
def test_joukowsky_surge_pressure_known_formula():
    dp = joukowsky_surge_pressure(density=1000.0, wave_speed_m_s=1200.0, delta_v_m_s=2.0)
    assert dp == pytest.approx(1000.0 * 1200.0 * 2.0)


def test_joukowsky_surge_pressure_sign_independent():
    """Surge magnitude only depends on |delta_v| — direction doesn't matter."""
    dp_pos = joukowsky_surge_pressure(1000.0, 1200.0, 2.0)
    dp_neg = joukowsky_surge_pressure(1000.0, 1200.0, -2.0)
    assert dp_pos == pytest.approx(dp_neg)


def test_joukowsky_surge_pressure_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        joukowsky_surge_pressure(-1000.0, 1200.0, 2.0)
    with pytest.raises(ValueError):
        joukowsky_surge_pressure(1000.0, -1200.0, 2.0)


# ── pipe_critical_period_s ──────────────────────────────────────────────────
def test_pipe_critical_period_known_formula():
    tc = pipe_critical_period_s(length_m=500.0, wave_speed_m_s=1000.0)
    assert tc == pytest.approx(1.0)   # 2*500/1000


def test_pipe_critical_period_rejects_nonpositive_inputs():
    with pytest.raises(ValueError):
        pipe_critical_period_s(0.0, 1000.0)
    with pytest.raises(ValueError):
        pipe_critical_period_s(500.0, 0.0)


# ── evaluate_water_hammer ────────────────────────────────────────────────────
@pytest.fixture
def pipe_params():
    return dict(
        bulk_modulus_Pa=WATER_BULK_MODULUS_PA, density=WATER_DENSITY,
        diameter_m=0.1, wall_thickness_m=0.005, youngs_modulus_Pa=STEEL_YOUNGS_MODULUS_PA,
        length_m=50.0,
    )


def test_evaluate_water_hammer_rapid_closure_gives_full_surge(pipe_params):
    result = evaluate_water_hammer(
        **pipe_params, delta_v_m_s=2.0, closure_time_s=0.01, initial_pressure_Pa=500_000,
    )
    assert isinstance(result, WaterHammerResult)
    assert result.is_rapid_closure is True
    assert result.surge_Pa == pytest.approx(result.instantaneous_surge_Pa)
    assert result.peak_pressure_Pa == pytest.approx(500_000 + result.surge_Pa)


def test_evaluate_water_hammer_slow_closure_reduces_surge(pipe_params):
    rapid = evaluate_water_hammer(**pipe_params, delta_v_m_s=2.0, closure_time_s=0.01)
    slow = evaluate_water_hammer(**pipe_params, delta_v_m_s=2.0, closure_time_s=5.0)
    assert slow.is_rapid_closure is False
    assert slow.surge_Pa < rapid.surge_Pa
    # Same instantaneous (theoretical) surge regardless of actual closure time.
    assert slow.instantaneous_surge_Pa == pytest.approx(rapid.instantaneous_surge_Pa)


def test_evaluate_water_hammer_closure_at_exactly_critical_period_is_rapid(pipe_params):
    """Boundary case: closure_time == critical_period should count as rapid
    (full surge), matching the documented '<=' rapid-closure criterion."""
    a = wave_speed(WATER_BULK_MODULUS_PA, WATER_DENSITY, 0.1, 0.005, STEEL_YOUNGS_MODULUS_PA)
    tc = pipe_critical_period_s(50.0, a)
    result = evaluate_water_hammer(**pipe_params, delta_v_m_s=2.0, closure_time_s=tc)
    assert result.is_rapid_closure is True
    assert result.surge_Pa == pytest.approx(result.instantaneous_surge_Pa)


def test_evaluate_water_hammer_rejects_nonpositive_closure_time(pipe_params):
    with pytest.raises(ValueError):
        evaluate_water_hammer(**pipe_params, delta_v_m_s=2.0, closure_time_s=0.0)


def test_evaluate_water_hammer_rejects_negative_initial_pressure(pipe_params):
    with pytest.raises(ValueError):
        evaluate_water_hammer(**pipe_params, delta_v_m_s=2.0, closure_time_s=1.0,
                               initial_pressure_Pa=-1.0)


# ── check_water_hammer_risk (Poka-Yoke) ────────────────────────────────────
def test_check_water_hammer_risk_none_when_no_rating():
    assert check_water_hammer_risk(2_000_000, None) is None
    assert check_water_hammer_risk(2_000_000, 0.0) is None


def test_check_water_hammer_risk_comfortable_margin_returns_none():
    assert check_water_hammer_risk(500_000, 1_000_000) is None  # 50%


def test_check_water_hammer_risk_thin_margin_warns():
    warning = check_water_hammer_risk(850_000, 1_000_000)  # 85%
    assert warning is not None
    assert "rupture" not in warning.lower()


def test_check_water_hammer_risk_exceeds_rating_warns_rupture_risk():
    warning = check_water_hammer_risk(1_500_000, 1_000_000)  # 150%
    assert warning is not None
    assert "rupture" in warning.lower()
