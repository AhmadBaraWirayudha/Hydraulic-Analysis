"""
Unit tests for src/machine_learning/synthetic_data.py.

These tests check that the synthetic generators produce well-formed,
internally consistent data — NOT that the data represents real pipe
behavior (it explicitly doesn't; see the module's docstring).
"""

import numpy as np

from src.machine_learning.synthetic_data import (
    generate_synthetic_roughness_degradation,
    generate_synthetic_sensor_data_with_anomalies,
)


def test_generate_synthetic_roughness_degradation_shape():
    df = generate_synthetic_roughness_degradation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0, days=100,
    )
    assert len(df) == 100
    assert set(df.columns) == {"day", "roughness_m", "head_loss_m", "pressure_drop_Pa"}


def test_generate_synthetic_roughness_degradation_trends_upward():
    """Roughness should generally increase over time (the fabricated
    degradation trend), even with noise — check via a rolling comparison
    rather than a strict monotonic requirement (noise can cause local dips)."""
    df = generate_synthetic_roughness_degradation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0, days=730,
        noise_std_fraction=0.01,  # low noise, to make the trend clearly dominant
    )
    first_quarter_mean = df["roughness_m"].iloc[:180].mean()
    last_quarter_mean = df["roughness_m"].iloc[-180:].mean()
    assert last_quarter_mean > first_quarter_mean


def test_generate_synthetic_roughness_degradation_head_loss_increases_with_roughness():
    """Head loss should track the (real, Darcy-Weisbach-computed) impact
    of increasing roughness — a sanity check that the physics-grounded
    part of this generator is actually wired correctly."""
    df = generate_synthetic_roughness_degradation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0, days=730,
        noise_std_fraction=0.0,  # disable noise for a clean monotonic check
    )
    # With zero noise, head loss should be monotonically non-decreasing
    # (roughness only grows with sqrt(t)).
    assert (df["head_loss_m"].diff().dropna() >= -1e-12).all()


def test_generate_synthetic_roughness_degradation_reproducible_with_seed():
    df1 = generate_synthetic_roughness_degradation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0, days=50, seed=123,
    )
    df2 = generate_synthetic_roughness_degradation(
        diameter_m=0.0508, flow_rate_m3s=0.0005, length_m=100.0, days=50, seed=123,
    )
    np.testing.assert_array_equal(df1["roughness_m"].values, df2["roughness_m"].values)


def test_generate_synthetic_sensor_data_shape_and_columns():
    df = generate_synthetic_sensor_data_with_anomalies(
        base_pressure_Pa=300_000, base_flow_m3s=0.0005, n_samples=200, n_anomalies=10,
    )
    assert len(df) == 200
    assert set(df.columns) == {"sample", "pressure_Pa", "flow_m3s", "is_true_anomaly"}
    assert df["is_true_anomaly"].sum() == 10


def test_generate_synthetic_sensor_data_anomalies_are_lower_pressure():
    """Injected anomalies are designed as pressure drops — verify the
    flagged anomalous samples indeed have lower pressure than the mean
    of normal samples."""
    df = generate_synthetic_sensor_data_with_anomalies(
        base_pressure_Pa=300_000, base_flow_m3s=0.0005, n_samples=300, n_anomalies=20,
        anomaly_magnitude_fraction=0.3,
    )
    normal_mean = df.loc[~df["is_true_anomaly"], "pressure_Pa"].mean()
    anomaly_mean = df.loc[df["is_true_anomaly"], "pressure_Pa"].mean()
    assert anomaly_mean < normal_mean


def test_generate_synthetic_sensor_data_caps_anomalies_at_n_samples():
    """Requesting more anomalies than samples shouldn't crash — should
    just cap at n_samples."""
    df = generate_synthetic_sensor_data_with_anomalies(
        base_pressure_Pa=300_000, base_flow_m3s=0.0005, n_samples=5, n_anomalies=50,
    )
    assert len(df) == 5
    assert df["is_true_anomaly"].sum() == 5
