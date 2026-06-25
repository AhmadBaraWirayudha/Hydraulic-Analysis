"""
Unit tests for src/machine_learning/degradation_model.py.
"""

import numpy as np
import pytest

from src.machine_learning.degradation_model import (
    fit_degradation_model, predict_roughness, predict_maintenance_threshold_day,
    DegradationModelResult,
)
from src.machine_learning.synthetic_data import generate_synthetic_roughness_degradation


@pytest.fixture
def degradation_data():
    return generate_synthetic_roughness_degradation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0, days=730,
        noise_std_fraction=0.02,
    )


def test_fit_degradation_model_returns_result(degradation_data):
    result = fit_degradation_model(degradation_data["day"], degradation_data["roughness_m"])
    assert isinstance(result, DegradationModelResult)
    assert result.n_train + result.n_test == len(degradation_data)


def test_fit_degradation_model_fits_well_on_clean_trend(degradation_data):
    """With a clear underlying sqrt(t) trend and modest noise, a Random
    Forest should achieve a high test R^2 — this is the "does the ML
    pattern actually work on its own demo data" sanity check."""
    result = fit_degradation_model(degradation_data["day"], degradation_data["roughness_m"])
    assert result.test_r2 > 0.8


def test_fit_degradation_model_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        fit_degradation_model(np.arange(100), np.arange(50))


def test_fit_degradation_model_rejects_too_few_observations():
    with pytest.raises(ValueError, match="at least 10"):
        fit_degradation_model(np.arange(5), np.arange(5))


def test_predict_roughness_matches_training_range_trend(degradation_data):
    result = fit_degradation_model(degradation_data["day"], degradation_data["roughness_m"])
    early_pred = predict_roughness(result, [10])[0]
    late_pred = predict_roughness(result, [700])[0]
    assert late_pred > early_pred


def test_predict_maintenance_threshold_day_finds_reasonable_day(degradation_data):
    result = fit_degradation_model(degradation_data["day"], degradation_data["roughness_m"])
    initial = degradation_data["roughness_m"].iloc[0]
    threshold_day = predict_maintenance_threshold_day(
        result, roughness_threshold_m=initial * 1.5, max_day=730,
    )
    assert threshold_day is not None
    assert 0 < threshold_day <= 730


def test_predict_maintenance_threshold_day_returns_none_if_unreachable(degradation_data):
    result = fit_degradation_model(degradation_data["day"], degradation_data["roughness_m"])
    # An absurdly high threshold should never be reached within the search horizon.
    threshold_day = predict_maintenance_threshold_day(
        result, roughness_threshold_m=1.0, max_day=730,  # 1 meter of roughness!
    )
    assert threshold_day is None
