"""
Unit tests for src/hydraulics/electrical.py — pump affinity laws,
three-phase electrical power, and voltage unbalance utilities.
"""

import pytest

from src.hydraulics.electrical import (
    apply_affinity_laws, AffinityResult,
    speed_ratio_for_target_flow, speed_ratio_for_target_head,
    three_phase_apparent_power, evaluate_three_phase_power, ElectricalPowerResult,
    motor_current_from_shaft_power,
    voltage_unbalance_percent, derating_factor_from_curve,
)


# ── Affinity laws ──────────────────────────────────────────────────────────
def test_apply_affinity_laws_known_ratios():
    r = apply_affinity_laws(flow_ref_m3s=0.01, head_ref_m=20.0, power_ref_W=1000.0, speed_ratio=0.8)
    assert isinstance(r, AffinityResult)
    assert r.flow_m3s == pytest.approx(0.008)       # linear
    assert r.head_m == pytest.approx(12.8)            # squared: 20 * 0.64
    assert r.power_W == pytest.approx(512.0)           # cubed: 1000 * 0.512


def test_apply_affinity_laws_full_speed_is_identity():
    r = apply_affinity_laws(0.01, 20.0, 1000.0, speed_ratio=1.0)
    assert r.flow_m3s == pytest.approx(0.01)
    assert r.head_m == pytest.approx(20.0)
    assert r.power_W == pytest.approx(1000.0)


def test_apply_affinity_laws_rejects_nonpositive_speed_ratio():
    with pytest.raises(ValueError):
        apply_affinity_laws(0.01, 20.0, 1000.0, speed_ratio=0.0)
    with pytest.raises(ValueError):
        apply_affinity_laws(0.01, 20.0, 1000.0, speed_ratio=-0.5)


def test_apply_affinity_laws_rejects_negative_reference_values():
    with pytest.raises(ValueError):
        apply_affinity_laws(-0.01, 20.0, 1000.0, speed_ratio=0.8)


def test_speed_ratio_for_target_flow_roundtrip():
    ratio = speed_ratio_for_target_flow(flow_ref_m3s=0.01, flow_target_m3s=0.008)
    assert ratio == pytest.approx(0.8)
    r = apply_affinity_laws(0.01, 20.0, 1000.0, speed_ratio=ratio)
    assert r.flow_m3s == pytest.approx(0.008)


def test_speed_ratio_for_target_head_roundtrip():
    ratio = speed_ratio_for_target_head(head_ref_m=20.0, head_target_m=12.8)
    assert ratio == pytest.approx(0.8)
    r = apply_affinity_laws(0.01, 20.0, 1000.0, speed_ratio=ratio)
    assert r.head_m == pytest.approx(12.8)


def test_speed_ratio_for_target_flow_rejects_nonpositive_reference():
    with pytest.raises(ValueError):
        speed_ratio_for_target_flow(0.0, 0.008)


def test_speed_ratio_for_target_head_rejects_nonpositive_reference():
    with pytest.raises(ValueError):
        speed_ratio_for_target_head(0.0, 12.8)


# ── Three-phase electrical power ──────────────────────────────────────────
def test_three_phase_apparent_power_known_formula():
    import math
    S = three_phase_apparent_power(400, 10)
    assert S == pytest.approx(math.sqrt(3) * 400 * 10)


def test_three_phase_apparent_power_rejects_negative_inputs():
    with pytest.raises(ValueError):
        three_phase_apparent_power(-400, 10)
    with pytest.raises(ValueError):
        three_phase_apparent_power(400, -10)


def test_evaluate_three_phase_power_consistent_with_pythagorean_relation():
    result = evaluate_three_phase_power(line_voltage_V=400, line_current_A=10, power_factor=0.85)
    assert isinstance(result, ElectricalPowerResult)
    # S^2 = P^2 + Q^2
    assert result.apparent_power_VA ** 2 == pytest.approx(
        result.real_power_W ** 2 + result.reactive_power_VAR ** 2
    )


def test_evaluate_three_phase_power_unity_pf_has_zero_reactive():
    result = evaluate_three_phase_power(400, 10, power_factor=1.0)
    assert result.reactive_power_VAR == pytest.approx(0.0, abs=1e-9)
    assert result.real_power_W == pytest.approx(result.apparent_power_VA)


def test_evaluate_three_phase_power_rejects_invalid_power_factor():
    with pytest.raises(ValueError):
        evaluate_three_phase_power(400, 10, power_factor=1.5)
    with pytest.raises(ValueError):
        evaluate_three_phase_power(400, 10, power_factor=-1.5)


def test_motor_current_from_shaft_power_increases_with_lower_efficiency():
    i_high_eta = motor_current_from_shaft_power(1000.0, 400, 0.85, motor_efficiency=0.95)
    i_low_eta = motor_current_from_shaft_power(1000.0, 400, 0.85, motor_efficiency=0.70)
    assert i_low_eta > i_high_eta


def test_motor_current_from_shaft_power_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        motor_current_from_shaft_power(-100, 400, 0.85)
    with pytest.raises(ValueError):
        motor_current_from_shaft_power(1000, 400, 0.0)
    with pytest.raises(ValueError):
        motor_current_from_shaft_power(1000, 400, 0.85, motor_efficiency=0.0)
    with pytest.raises(ValueError):
        motor_current_from_shaft_power(1000, 0, 0.85)


# ── Voltage unbalance ──────────────────────────────────────────────────────
def test_voltage_unbalance_percent_matches_nema_worked_example():
    """NEMA MG1's own worked example: 460, 467, 450 V -> 1.96% unbalance."""
    pct = voltage_unbalance_percent([460, 467, 450])
    assert pct == pytest.approx(1.9607843137254901, rel=1e-9)


def test_voltage_unbalance_percent_zero_for_balanced_supply():
    assert voltage_unbalance_percent([400, 400, 400]) == pytest.approx(0.0)


def test_voltage_unbalance_percent_rejects_wrong_count():
    with pytest.raises(ValueError):
        voltage_unbalance_percent([400, 400])
    with pytest.raises(ValueError):
        voltage_unbalance_percent([400, 400, 400, 400])


def test_voltage_unbalance_percent_rejects_nonpositive_voltage():
    with pytest.raises(ValueError):
        voltage_unbalance_percent([400, 0, 400])
    with pytest.raises(ValueError):
        voltage_unbalance_percent([400, -10, 400])


def test_derating_factor_from_curve_interpolates_linearly():
    curve = [(0, 1.0), (1, 1.0), (5, 0.85)]
    assert derating_factor_from_curve(0.5, curve) == pytest.approx(1.0)
    assert derating_factor_from_curve(3.0, curve) == pytest.approx(1.0 + (3 - 1) / 4 * (0.85 - 1.0))


def test_derating_factor_from_curve_clamps_outside_range():
    curve = [(0, 1.0), (1, 1.0), (5, 0.85)]
    assert derating_factor_from_curve(-1, curve) == pytest.approx(1.0)
    assert derating_factor_from_curve(10, curve) == pytest.approx(0.85)


def test_derating_factor_from_curve_rejects_too_few_points():
    with pytest.raises(ValueError):
        derating_factor_from_curve(2.0, [(0, 1.0)])


def test_derating_factor_from_curve_rejects_unsorted_points():
    with pytest.raises(ValueError):
        derating_factor_from_curve(2.0, [(5, 0.85), (0, 1.0)])
