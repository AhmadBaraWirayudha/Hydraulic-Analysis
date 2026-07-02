"""
Unit tests for src/hydraulics/pipe_design.py — ASME B31.3 Eq. (3a)
pressure design wall thickness, plus src/utils/validation.py's
check_pipe_design_margin warning check.

The primary correctness test (``test_pressure_design_thickness_matches_asme_worked_example``)
reproduces a published ASME B31.3 worked example exactly (1480 psig design
pressure, NPS 6 / 6.625 in OD pipe, S = 20,000 psi allowable stress, with
the standard E=W=1.0, Y=0.4 assumptions, giving t = 0.238 in) — a much
stronger check than self-consistency alone, since it verifies the
implementation against an independently-derived, known-correct result
rather than just checking the code agrees with itself.
"""

import pytest

from src.hydraulics.pipe_design import (
    pressure_design_thickness, evaluate_pipe_design, PipeDesignResult,
    DEFAULT_Y_DUCTILE_STEEL, DEFAULT_MILL_UNDERTOLERANCE,
)


# ── Gold-standard verification against the published worked example ────────
def test_pressure_design_thickness_matches_asme_worked_example():
    """ASME B31.3 Eq. (3a) published example: P=1480 psig, D=6.625 in
    (NPS 6 OD), S=20,000 psi, E=W=1.0, Y=0.4 -> t=0.238 in (exact match)."""
    t = pressure_design_thickness(1480, 6.625, 20000)
    assert t == pytest.approx(0.238, abs=5e-4)


def test_pressure_design_thickness_worked_example_matches_formula_directly():
    """Cross-check the same worked example against Eq. (3a) computed
    independently in the test, not just the rounded headline figure."""
    P, D, S, E, W, Y = 1480, 6.625, 20000, 1.0, 1.0, 0.4
    expected = (P * D) / (2 * (S * E * W + P * Y))
    assert pressure_design_thickness(P, D, S, E, W, Y) == pytest.approx(expected)


def test_pressure_design_thickness_defaults_match_common_case_e_w_y():
    """E=1.0, W=1.0, Y=0.4 are the defaults, so the worked example can be
    called with just P, D, S."""
    assert pressure_design_thickness(1480, 6.625, 20000) == pytest.approx(
        pressure_design_thickness(1480, 6.625, 20000, 1.0, 1.0, DEFAULT_Y_DUCTILE_STEEL)
    )


# ── Formula self-consistency ────────────────────────────────────────────────
def test_pressure_design_thickness_matches_formula_general_case():
    P, D, S, E, W, Y = 600, 12.75, 17500, 0.85, 1.0, 0.4
    expected = (P * D) / (2 * (S * E * W + P * Y))
    assert pressure_design_thickness(P, D, S, E, W, Y) == pytest.approx(expected)


def test_pressure_design_thickness_scales_linearly_with_diameter():
    """D appears only in the numerator, so t is exactly proportional to D
    at fixed P, S, E, W, Y."""
    t_base = pressure_design_thickness(1000, 4.0, 18000)
    t_double = pressure_design_thickness(1000, 8.0, 18000)
    assert t_double == pytest.approx(2 * t_base)


def test_pressure_design_thickness_increases_with_pressure():
    t_low = pressure_design_thickness(500, 6.625, 20000)
    t_high = pressure_design_thickness(1500, 6.625, 20000)
    assert t_high > t_low


def test_pressure_design_thickness_decreases_with_allowable_stress():
    """A stronger material (higher S) needs less wall, all else equal."""
    t_weak = pressure_design_thickness(1000, 6.625, 15000)
    t_strong = pressure_design_thickness(1000, 6.625, 25000)
    assert t_strong < t_weak


def test_pressure_design_thickness_decreases_with_quality_factor():
    """A better weld joint quality factor (higher E) needs less wall."""
    t_low_e = pressure_design_thickness(1000, 6.625, 20000, quality_factor=0.6)
    t_high_e = pressure_design_thickness(1000, 6.625, 20000, quality_factor=1.0)
    assert t_high_e < t_low_e


def test_pressure_design_thickness_decreases_with_weld_strength_reduction_factor():
    t_low_w = pressure_design_thickness(1000, 6.625, 20000, weld_strength_reduction_factor=0.7)
    t_high_w = pressure_design_thickness(1000, 6.625, 20000, weld_strength_reduction_factor=1.0)
    assert t_high_w < t_low_w


def test_pressure_design_thickness_decreases_with_coefficient_y():
    t_low_y = pressure_design_thickness(1000, 6.625, 20000, coefficient_y=0.0)
    t_high_y = pressure_design_thickness(1000, 6.625, 20000, coefficient_y=0.7)
    assert t_high_y < t_low_y


# ── Poka-Yoke validation: pressure_design_thickness ─────────────────────────
def test_pressure_design_thickness_rejects_nonpositive_pressure():
    with pytest.raises(ValueError):
        pressure_design_thickness(0, 6.625, 20000)
    with pytest.raises(ValueError):
        pressure_design_thickness(-100, 6.625, 20000)


def test_pressure_design_thickness_rejects_nonpositive_diameter():
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 0, 20000)
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, -1, 20000)


def test_pressure_design_thickness_rejects_unrealistically_large_diameter():
    """Catches a likely mm-vs-inch unit mistake, mirroring validate_pipe's
    diameter sanity bound."""
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 200, 20000)


def test_pressure_design_thickness_rejects_nonpositive_allowable_stress():
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, 0)
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, -500)


def test_pressure_design_thickness_rejects_quality_factor_out_of_range():
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, 20000, quality_factor=0)
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, 20000, quality_factor=1.2)


def test_pressure_design_thickness_accepts_quality_factor_boundary_of_one():
    # Should not raise -- 1.0 is the valid upper boundary, not exclusive.
    pressure_design_thickness(1000, 6.625, 20000, quality_factor=1.0)


def test_pressure_design_thickness_rejects_weld_strength_reduction_out_of_range():
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, 20000, weld_strength_reduction_factor=0)
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, 20000, weld_strength_reduction_factor=1.5)


def test_pressure_design_thickness_rejects_coefficient_y_out_of_range():
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, 20000, coefficient_y=-0.1)
    with pytest.raises(ValueError):
        pressure_design_thickness(1000, 6.625, 20000, coefficient_y=0.8)


def test_pressure_design_thickness_accepts_coefficient_y_boundaries():
    # Should not raise -- 0.0 and 0.7 are the valid inclusive boundaries.
    pressure_design_thickness(1000, 6.625, 20000, coefficient_y=0.0)
    pressure_design_thickness(1000, 6.625, 20000, coefficient_y=0.7)


# ── evaluate_pipe_design: allowances and nominal thickness ─────────────────
def test_evaluate_pipe_design_returns_result_instance():
    result = evaluate_pipe_design(1480, 6.625, 20000)
    assert isinstance(result, PipeDesignResult)


def test_evaluate_pipe_design_minimum_required_adds_allowances():
    t = pressure_design_thickness(1480, 6.625, 20000)
    result = evaluate_pipe_design(
        1480, 6.625, 20000, corrosion_allowance_in=0.05, mechanical_allowance_in=0.02,
    )
    assert result.minimum_required_thickness_in == pytest.approx(t + 0.05 + 0.02)


def test_evaluate_pipe_design_no_allowances_means_minimum_equals_bare_t():
    t = pressure_design_thickness(1480, 6.625, 20000)
    result = evaluate_pipe_design(1480, 6.625, 20000)
    assert result.minimum_required_thickness_in == pytest.approx(t)


def test_evaluate_pipe_design_nominal_thickness_grosses_up_for_mill_tolerance():
    result = evaluate_pipe_design(1480, 6.625, 20000)
    expected_nominal = result.minimum_required_thickness_in / (1 - DEFAULT_MILL_UNDERTOLERANCE)
    assert result.nominal_thickness_required_in == pytest.approx(expected_nominal)


def test_evaluate_pipe_design_zero_mill_undertolerance_means_nominal_equals_minimum():
    result = evaluate_pipe_design(1480, 6.625, 20000, mill_undertolerance_fraction=0.0)
    assert result.nominal_thickness_required_in == pytest.approx(result.minimum_required_thickness_in)


def test_evaluate_pipe_design_rejects_negative_corrosion_allowance():
    with pytest.raises(ValueError):
        evaluate_pipe_design(1480, 6.625, 20000, corrosion_allowance_in=-0.01)


def test_evaluate_pipe_design_rejects_negative_mechanical_allowance():
    with pytest.raises(ValueError):
        evaluate_pipe_design(1480, 6.625, 20000, mechanical_allowance_in=-0.01)


def test_evaluate_pipe_design_rejects_mill_undertolerance_out_of_range():
    with pytest.raises(ValueError):
        evaluate_pipe_design(1480, 6.625, 20000, mill_undertolerance_fraction=-0.01)
    with pytest.raises(ValueError):
        evaluate_pipe_design(1480, 6.625, 20000, mill_undertolerance_fraction=1.0)


# ── evaluate_pipe_design: thin-wall (Eq. 3a) applicability ─────────────────
def test_evaluate_pipe_design_worked_example_is_within_thin_wall_regime():
    result = evaluate_pipe_design(1480, 6.625, 20000)
    assert result.thin_wall_assumption_valid is True


def test_evaluate_pipe_design_flags_thin_wall_assumption_violated():
    """At high enough P/S, t approaches/exceeds D/6 and Eq. (3a) no longer
    applies -- the standard requires Eq. (3b) instead."""
    result = evaluate_pipe_design(8000, 6.625, 20000)
    assert result.pressure_design_thickness_in > 6.625 / 6.0
    assert result.thin_wall_assumption_valid is False


# ── evaluate_pipe_design: selected-thickness adequacy check ────────────────
def test_evaluate_pipe_design_without_selected_thickness_skips_check():
    result = evaluate_pipe_design(1480, 6.625, 20000)
    assert result.selected_thickness_in is None
    assert result.derated_selected_thickness_in is None
    assert result.selected_thickness_adequate is None
    assert result.margin_in is None
    assert result.margin_ratio is None


def test_evaluate_pipe_design_schedule_80_is_adequate_with_corrosion_allowance():
    """NPS 6 Schedule 80 (0.432 in actual wall) against the worked-example
    pressure/material with a representative 1/16 in corrosion allowance."""
    result = evaluate_pipe_design(
        1480, 6.625, 20000, corrosion_allowance_in=0.0625, selected_thickness_in=0.432,
    )
    assert result.selected_thickness_adequate is True
    assert result.margin_in > 0


def test_evaluate_pipe_design_schedule_40_is_inadequate_with_corrosion_allowance():
    """NPS 6 Schedule 40 (0.280 in actual wall) looks adequate against the
    bare Eq. (3a) result (0.238 in) but fails once a realistic corrosion
    allowance and mill under-tolerance are both applied -- the whole point
    of evaluate_pipe_design over the bare equation."""
    result = evaluate_pipe_design(
        1480, 6.625, 20000, corrosion_allowance_in=0.0625, selected_thickness_in=0.280,
    )
    assert result.selected_thickness_adequate is False
    assert result.margin_in < 0


def test_evaluate_pipe_design_derates_selected_thickness_by_mill_tolerance():
    result = evaluate_pipe_design(1480, 6.625, 20000, selected_thickness_in=0.432)
    assert result.derated_selected_thickness_in == pytest.approx(0.432 * (1 - DEFAULT_MILL_UNDERTOLERANCE))


def test_evaluate_pipe_design_margin_ratio_matches_derated_over_minimum():
    result = evaluate_pipe_design(1480, 6.625, 20000, selected_thickness_in=0.432)
    expected_ratio = result.derated_selected_thickness_in / result.minimum_required_thickness_in
    assert result.margin_ratio == pytest.approx(expected_ratio)


def test_evaluate_pipe_design_rejects_nonpositive_selected_thickness():
    with pytest.raises(ValueError):
        evaluate_pipe_design(1480, 6.625, 20000, selected_thickness_in=0)
    with pytest.raises(ValueError):
        evaluate_pipe_design(1480, 6.625, 20000, selected_thickness_in=-0.1)


def test_evaluate_pipe_design_propagates_pressure_design_thickness_validation():
    """evaluate_pipe_design calls pressure_design_thickness internally, so
    its Poka-Yoke checks apply here too without duplication."""
    with pytest.raises(ValueError):
        evaluate_pipe_design(-100, 6.625, 20000)
