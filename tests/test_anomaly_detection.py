"""
Unit tests for src/machine_learning/anomaly_detection.py — both the SPC
control-chart method and the Isolation Forest ML method.
"""

import numpy as np
import pytest

from src.machine_learning.anomaly_detection import (
    compute_spc_control_limits, flag_spc_anomalies, SPCControlLimits,
    fit_isolation_forest_detector, detect_anomalies, IsolationForestAnomalyResult,
    evaluate_detector_against_ground_truth,
)
from src.machine_learning.synthetic_data import generate_synthetic_sensor_data_with_anomalies


# ── SPC control charts ──────────────────────────────────────────────────────
def test_compute_spc_control_limits_known_values():
    """Constant baseline (zero moving range) -> UCL/LCL collapse to the center."""
    baseline = np.array([100.0, 100.0, 100.0, 100.0])
    limits = compute_spc_control_limits(baseline)
    assert limits.center_line == pytest.approx(100.0)
    assert limits.upper_control_limit == pytest.approx(100.0)
    assert limits.lower_control_limit == pytest.approx(100.0)


def test_compute_spc_control_limits_symmetric_around_center():
    baseline = np.array([98.0, 102.0, 99.0, 101.0, 100.0])
    limits = compute_spc_control_limits(baseline)
    assert (limits.upper_control_limit - limits.center_line) == pytest.approx(
        limits.center_line - limits.lower_control_limit
    )


def test_compute_spc_control_limits_wider_with_higher_n_sigma():
    baseline = np.array([98.0, 102.0, 99.0, 101.0, 100.0])
    narrow = compute_spc_control_limits(baseline, n_sigma=1.0)
    wide = compute_spc_control_limits(baseline, n_sigma=3.0)
    assert wide.upper_control_limit > narrow.upper_control_limit


def test_compute_spc_control_limits_rejects_too_few_points():
    with pytest.raises(ValueError):
        compute_spc_control_limits(np.array([100.0]))


def test_flag_spc_anomalies_flags_outliers():
    limits = SPCControlLimits(center_line=100.0, upper_control_limit=110.0, lower_control_limit=90.0)
    values = np.array([95.0, 105.0, 150.0, 50.0, 100.0])
    flags = flag_spc_anomalies(values, limits)
    np.testing.assert_array_equal(flags, [False, False, True, True, False])


# ── Isolation Forest ─────────────────────────────────────────────────────────
def test_fit_isolation_forest_detector_returns_fitted_model():
    rng = np.random.default_rng(0)
    features = rng.normal(0, 1, size=(200, 2))
    model = fit_isolation_forest_detector(features, contamination=0.05)
    assert hasattr(model, "predict")


def test_detect_anomalies_flags_obvious_outliers():
    rng = np.random.default_rng(0)
    normal = rng.normal(0, 1, size=(200, 2))
    model = fit_isolation_forest_detector(normal, contamination=0.05)

    # Test on the normal data plus a few obvious outliers far from the cluster.
    outliers = np.array([[50.0, 50.0], [-50.0, -50.0]])
    test_features = np.vstack([normal[:10], outliers])
    result = detect_anomalies(model, test_features)

    assert isinstance(result, IsolationForestAnomalyResult)
    assert result.anomaly_flags[-2:].all()   # the two obvious outliers should be flagged


def test_isolation_forest_on_synthetic_sensor_data_reasonable_performance():
    """End-to-end demonstration on the synthetic benchmark: a reasonably
    well-tuned Isolation Forest should catch a majority of obvious
    pressure-drop anomalies without flagging the entire dataset."""
    df = generate_synthetic_sensor_data_with_anomalies(
        base_pressure_Pa=300_000, base_flow_m3s=0.0005, n_samples=400,
        n_anomalies=20, anomaly_magnitude_fraction=0.3, seed=7,
    )
    features = df[["pressure_Pa", "flow_m3s"]].values
    model = fit_isolation_forest_detector(features, contamination=0.05)
    result = detect_anomalies(model, features)

    metrics = evaluate_detector_against_ground_truth(result.anomaly_flags, df["is_true_anomaly"])
    assert metrics["recall"] > 0.5      # catches a majority of real anomalies
    assert metrics["precision"] > 0.3   # not flagging everything as anomalous


# ── evaluate_detector_against_ground_truth ──────────────────────────────────
def test_evaluate_detector_perfect_match():
    true_flags = np.array([True, False, True, False])
    predicted = np.array([True, False, True, False])
    metrics = evaluate_detector_against_ground_truth(predicted, true_flags)
    assert metrics["precision"] == pytest.approx(1.0)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["f1"] == pytest.approx(1.0)


def test_evaluate_detector_no_predictions():
    true_flags = np.array([True, False, True, False])
    predicted = np.array([False, False, False, False])
    metrics = evaluate_detector_against_ground_truth(predicted, true_flags)
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["n_false_negatives"] == 2


def test_evaluate_detector_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        evaluate_detector_against_ground_truth([True, False], [True, False, True])
