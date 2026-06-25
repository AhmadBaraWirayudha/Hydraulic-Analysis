"""
Synthetic training data generators for the predictive-maintenance demo
modules in this package.

IMPORTANT — read before using any model trained on this data:
Every dataset here is **synthetic**. The hydraulic baseline (head loss,
pressure drop at a given roughness) is computed via this project's own
verified Darcy-Weisbach engine — that part is real physics. But the
*degradation trend over time*, *sensor noise*, and *injected anomalies*
are all fabricated for demonstration purposes, calibrated to "look
reasonable" rather than measured from any real pipeline. Treat models
fit on this data as a worked demonstration of the ML *pattern* — how you'd
structure training and inference for this problem — not as validated
predictive tools. Swap in your own real inspection records / sensor logs
via the same function signatures for actual predictive-maintenance use.
"""

import numpy as np
import pandas as pd

from ..simulation.scenario import run_simulation


def generate_synthetic_roughness_degradation(
    diameter_m: float,
    flow_rate_m3s: float,
    length_m: float,
    days: int = 730,
    initial_roughness_m: float = 1.5e-6,
    degradation_rate: float = 5.6e-8,
    noise_std_fraction: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic time series of pipe roughness degradation and its
    resulting hydraulic impact, for demonstrating a regression-based
    predictive-maintenance model.

    The degradation law used here — roughness growing with sqrt(time) — is
    a commonly assumed *simplified* pattern for scaling/fouling growth in
    introductory treatments, NOT a validated measurement from any specific
    pipe or water chemistry. Real degradation depends heavily on water
    chemistry, pipe material, flow regime, and maintenance history;
    calibrate against your own inspection/cleaning records for real use.

    Parameters
    ----------
    diameter_m, flow_rate_m3s, length_m : float  pipe parameters, held
                                           fixed; only roughness varies
                                           over the synthetic timeline
    days                 : int    number of daily synthetic observations
    initial_roughness_m  : float  starting (clean-pipe) roughness [m]
    degradation_rate     : float  fabricated growth-rate coefficient
    noise_std_fraction   : float  sensor/measurement noise, as a fraction
                            of the current true roughness
    seed                 : int    RNG seed, for reproducibility

    Returns
    -------
    pd.DataFrame with columns: day, roughness_m, head_loss_m, pressure_drop_Pa
    (head_loss_m and pressure_drop_Pa are computed via the real
    Darcy-Weisbach engine at each day's synthetic roughness value — only
    the roughness trend and its noise are fabricated).
    """
    rng = np.random.default_rng(seed)
    days_arr = np.arange(days)

    true_roughness = initial_roughness_m + degradation_rate * np.sqrt(days_arr)
    noise = rng.normal(0, noise_std_fraction, size=days) * true_roughness
    roughness_with_noise = np.clip(true_roughness + noise, initial_roughness_m * 0.5, None)

    head_losses = []
    pressure_drops = []
    for r in roughness_with_noise:
        result = run_simulation(
            diameter_m=diameter_m, flow_rate_m3s=flow_rate_m3s,
            length_m=length_m, roughness_m=float(r),
        )
        head_losses.append(result.head_loss.total_loss_m)
        pressure_drops.append(result.pressure_drop)

    return pd.DataFrame({
        "day": days_arr,
        "roughness_m": roughness_with_noise,
        "head_loss_m": head_losses,
        "pressure_drop_Pa": pressure_drops,
    })


def generate_synthetic_sensor_data_with_anomalies(
    base_pressure_Pa: float,
    base_flow_m3s: float,
    n_samples: int = 500,
    noise_std_fraction: float = 0.02,
    n_anomalies: int = 15,
    anomaly_magnitude_fraction: float = 0.3,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic pressure/flow sensor readings with injected anomalies
    (sudden pressure drops simulating a leak or cavitation onset), for
    demonstrating anomaly detection. Includes ground-truth anomaly labels
    so detector performance can be evaluated against a known answer key —
    real deployments won't have this luxury, which is exactly why this is
    a demonstration dataset, not a benchmark of real-world performance.

    FABRICATED data — see module docstring.

    Parameters
    ----------
    base_pressure_Pa, base_flow_m3s : float  steady-state operating point
    n_samples           : int    number of synthetic samples
    noise_std_fraction  : float  normal sensor noise, as a fraction of
                           the base value
    n_anomalies         : int    number of injected anomalous samples
    anomaly_magnitude_fraction : float  severity of injected anomalies,
                           as a fraction of base_pressure_Pa
    seed                : int    RNG seed

    Returns
    -------
    pd.DataFrame with columns: sample, pressure_Pa, flow_m3s, is_true_anomaly
    """
    rng = np.random.default_rng(seed)

    pressure = base_pressure_Pa + rng.normal(0, noise_std_fraction * base_pressure_Pa, n_samples)
    flow = base_flow_m3s + rng.normal(0, noise_std_fraction * base_flow_m3s, n_samples)
    is_anomaly = np.zeros(n_samples, dtype=bool)

    n_anomalies = min(n_anomalies, n_samples)
    anomaly_indices = rng.choice(n_samples, size=n_anomalies, replace=False)
    for idx in anomaly_indices:
        pressure[idx] -= anomaly_magnitude_fraction * base_pressure_Pa * rng.uniform(0.5, 1.5)
        is_anomaly[idx] = True

    return pd.DataFrame({
        "sample": np.arange(n_samples),
        "pressure_Pa": pressure,
        "flow_m3s": flow,
        "is_true_anomaly": is_anomaly,
    })
