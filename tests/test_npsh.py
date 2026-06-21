"""
Unit tests for src/hydraulics/npsh.py — NPSH available calculation and
margin evaluation against a manufacturer's NPSHr.
"""

import pytest

from src.hydraulics.npsh import npsh_available, evaluate_npsh, NPSHResult
from src.utils.constants import WATER_DENSITY, GRAVITY


def test_npsh_available_known_formula():
    # NPSHa = (Pi - Pv)/(rho*g) + zi - hL
    Pi, Pv, rho, zi, hL = 101_325, 2_339, WATER_DENSITY, 1.0, 0.5
    expected = (Pi - Pv) / (rho * GRAVITY) + zi - hL
    assert npsh_available(Pi, Pv, rho, zi, hL) == pytest.approx(expected)


def test_npsh_available_default_elevation_and_loss_are_zero():
    Pi, Pv, rho = 101_325, 2_339, WATER_DENSITY
    expected = (Pi - Pv) / (rho * GRAVITY)
    assert npsh_available(Pi, Pv, rho) == pytest.approx(expected)


def test_npsh_available_suction_lift_reduces_npsh():
    Pi, Pv, rho = 101_325, 2_339, WATER_DENSITY
    flooded = npsh_available(Pi, Pv, rho, inlet_elevation_m=2.0)
    lifted = npsh_available(Pi, Pv, rho, inlet_elevation_m=-2.0)
    assert lifted < flooded


def test_npsh_available_higher_vapor_pressure_reduces_npsh():
    """Hotter fluid (higher Pv) should have less available NPSH, all else equal."""
    Pi, rho = 101_325, WATER_DENSITY
    npsh_cold = npsh_available(Pi, vapor_pressure_Pa=2_339, density=rho)   # ~20C
    npsh_hot = npsh_available(Pi, vapor_pressure_Pa=19_932, density=rho)  # ~60C
    assert npsh_hot < npsh_cold


def test_npsh_available_rejects_nonpositive_suction_pressure():
    with pytest.raises(ValueError):
        npsh_available(0, 2339, WATER_DENSITY)
    with pytest.raises(ValueError):
        npsh_available(-100, 2339, WATER_DENSITY)


def test_npsh_available_rejects_negative_vapor_pressure():
    with pytest.raises(ValueError):
        npsh_available(101325, -10, WATER_DENSITY)


def test_npsh_available_rejects_negative_suction_head_loss():
    with pytest.raises(ValueError):
        npsh_available(101325, 2339, WATER_DENSITY, suction_head_loss_m=-1.0)


# ── evaluate_npsh ──────────────────────────────────────────────────────────
def test_evaluate_npsh_without_required_skips_margin():
    result = evaluate_npsh(101325, 2339, WATER_DENSITY)
    assert isinstance(result, NPSHResult)
    assert result.npsh_required_m is None
    assert result.margin_m is None
    assert result.margin_ratio is None
    assert result.npsh_available_m > 0


def test_evaluate_npsh_with_required_computes_margin():
    result = evaluate_npsh(101325, 2339, WATER_DENSITY, npsh_required_m=5.0)
    assert result.margin_m == pytest.approx(result.npsh_available_m - 5.0)
    assert result.margin_ratio == pytest.approx(result.npsh_available_m / 5.0)


def test_evaluate_npsh_rejects_nonpositive_required():
    with pytest.raises(ValueError):
        evaluate_npsh(101325, 2339, WATER_DENSITY, npsh_required_m=0.0)
    with pytest.raises(ValueError):
        evaluate_npsh(101325, 2339, WATER_DENSITY, npsh_required_m=-1.0)
