"""
Unit tests for src/hydraulics/friction.py and swamee_jain.py.

Reference values cross-checked against the LaTeX report's worked example
(½" vs 4" PVC pipe comparison) and standard fluid-mechanics textbook cases.
"""

import pytest

from src.hydraulics.friction import (
    pipe_area,
    flow_velocity,
    reynolds_number,
    darcy_friction_factor,
)
from src.hydraulics.swamee_jain import (
    swamee_jain_friction_factor,
    solve_diameter_for_head_loss,
    solve_flow_for_head_loss,
)
from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY, PVC_ROUGHNESS


def test_pipe_area_known_value():
    # D = 0.1 m -> A = pi*0.01/4 = 0.0078539816...
    assert pipe_area(0.1) == pytest.approx(0.00785398, rel=1e-5)


def test_flow_velocity_known_value():
    # Q = 0.01 m3/s, D = 0.1 m -> v = Q/A
    v = flow_velocity(0.01, 0.1)
    assert v == pytest.approx(0.01 / pipe_area(0.1), rel=1e-9)


def test_reynolds_number_known_value():
    re = reynolds_number(1.0, 0.1, WATER_DENSITY, WATER_VISCOSITY)
    assert re == pytest.approx(WATER_DENSITY * 1.0 * 0.1 / WATER_VISCOSITY, rel=1e-9)


def test_reynolds_number_scales_linearly_with_velocity():
    re1 = reynolds_number(1.0, 0.1, WATER_DENSITY, WATER_VISCOSITY)
    re2 = reynolds_number(2.0, 0.1, WATER_DENSITY, WATER_VISCOSITY)
    assert re2 == pytest.approx(2 * re1)


def test_laminar_friction_factor_hagen_poiseuille():
    # Re = 1000 (laminar) -> f = 64/Re = 0.064
    f = darcy_friction_factor(1000, diameter_m=0.1, roughness_m=PVC_ROUGHNESS)
    assert f == pytest.approx(0.064, rel=1e-9)


def test_turbulent_friction_factor_matches_swamee_jain_directly():
    re = 50_000
    d = 0.05
    eps = PVC_ROUGHNESS
    f_dispatch = darcy_friction_factor(re, d, eps)
    f_direct = swamee_jain_friction_factor(re, d, eps)
    assert f_dispatch == pytest.approx(f_direct)


def test_swamee_jain_friction_factor_reasonable_range():
    # For smooth PVC pipe at moderate Re, f should be in a sensible range
    # (~0.015-0.04 for typical water distribution conditions).
    f = swamee_jain_friction_factor(50_000, 0.1, PVC_ROUGHNESS)
    assert 0.01 < f < 0.05


def test_friction_factor_decreases_with_increasing_reynolds_turbulent():
    d, eps = 0.1, PVC_ROUGHNESS
    f_low = swamee_jain_friction_factor(10_000, d, eps)
    f_high = swamee_jain_friction_factor(1_000_000, d, eps)
    assert f_high < f_low


def test_friction_factor_zero_roughness_still_positive():
    f = swamee_jain_friction_factor(50_000, 0.1, 0.0)
    assert f > 0


def test_friction_factor_raises_on_nonpositive_reynolds():
    with pytest.raises(ValueError):
        darcy_friction_factor(0, 0.1, PVC_ROUGHNESS)
    with pytest.raises(ValueError):
        darcy_friction_factor(-100, 0.1, PVC_ROUGHNESS)


def test_swamee_jain_solve_diameter_for_head_loss_roundtrip():
    """Solve for D given a target head loss, then verify forward calc agrees."""
    from src.hydraulics.head_loss import major_head_loss

    Q = 0.01          # m3/s
    h_f_target = 5.0  # m
    L = 100.0
    eps = PVC_ROUGHNESS
    nu = WATER_VISCOSITY / WATER_DENSITY

    D = solve_diameter_for_head_loss(Q, h_f_target, L, eps, nu)
    assert D > 0

    result = major_head_loss(Q, D, L, eps, WATER_DENSITY, WATER_VISCOSITY)
    # Swamee-Jain explicit diameter formula is an approximation; allow ~10% tolerance.
    assert result.major_loss_m == pytest.approx(h_f_target, rel=0.10)


def test_swamee_jain_solve_flow_for_head_loss_roundtrip():
    """Solve for Q given D and head loss, then verify forward calc agrees."""
    from src.hydraulics.head_loss import major_head_loss

    D = 0.1
    h_f_target = 5.0
    L = 100.0
    eps = PVC_ROUGHNESS
    nu = WATER_VISCOSITY / WATER_DENSITY

    Q = solve_flow_for_head_loss(D, h_f_target, L, eps, nu)
    assert Q > 0

    result = major_head_loss(Q, D, L, eps, WATER_DENSITY, WATER_VISCOSITY)
    # This is solved via exact root-finding against the same friction-factor
    # relation, so it should match very tightly.
    assert result.major_loss_m == pytest.approx(h_f_target, rel=1e-6)


def test_smaller_diameter_increases_head_loss():
    """Core physical sanity check mirroring the report's ½'' vs 4'' comparison."""
    from src.hydraulics.head_loss import major_head_loss

    Q = 0.0005  # m3/s
    L = 100.0
    eps = PVC_ROUGHNESS

    small = major_head_loss(Q, 0.0127, L, eps, WATER_DENSITY, WATER_VISCOSITY)
    large = major_head_loss(Q, 0.1016, L, eps, WATER_DENSITY, WATER_VISCOSITY)

    assert small.major_loss_m > large.major_loss_m
