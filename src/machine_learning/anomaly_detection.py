"""
Anomaly detection for hydraulic sensor data: flags pressure/flow readings
that deviate from expected behavior, which could indicate a leak,
blockage, or cavitation onset.

Two complementary approaches are provided:

- **SPC (Statistical Process Control) control charts**: transparent,
  interpretable, the standard Lean Six Sigma tool for exactly this use
  case (this project's Poka-Yoke/Lean Dashboard already lives in this
  tradition). Requires no "training" beyond establishing a baseline from
  known-good historical readings, and produces an auditable, fixed
  decision rule. Prefer this when interpretability matters or historical
  baseline data is limited.
- **Isolation Forest (unsupervised ML)**: can catch more complex,
  multivariate patterns at the cost of interpretability. Demonstrated
  here on the SYNTHETIC data from ``synthetic_data.py`` — see that
  module's caveats before treating performance numbers here as
  indicative of real-world performance.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest


# ── SPC control charts ──────────────────────────────────────────────────────
@dataclass
class SPCControlLimits:
    """Individuals (I) control chart limits."""

    center_line: float
    upper_control_limit: float
    lower_control_limit: float


def compute_spc_control_limits(baseline_values: np.ndarray, n_sigma: float = 3.0) -> SPCControlLimits:
    """Individuals control chart limits via the moving-range method — the
    standard SPC approach for individual (non-subgrouped) measurements
    like a single pressure sensor's readings.

        center = mean(baseline)
        sigma_hat = mean(|consecutive differences|) / 1.128
        UCL/LCL = center +/- n_sigma * sigma_hat

    The constant 1.128 is the control-chart bias-correction factor d2 for
    subgroup size 2 (consecutive-pair moving ranges), which converts the
    average moving range into an unbiased estimate of the underlying
    process standard deviation — standard SPC practice.

    Parameters
    ----------
    baseline_values : array-like  known-good ("in control") historical
                       readings — do NOT include known anomalies here, or
                       the limits will be inflated and less sensitive
    n_sigma         : float  control limit width, in standard deviations
                       (3.0 is the conventional Shewhart choice)

    Returns
    -------
    SPCControlLimits
    """
    baseline_values = np.asarray(baseline_values, dtype=float)
    if len(baseline_values) < 2:
        raise ValueError("Need at least 2 baseline values to compute control limits.")

    center = float(np.mean(baseline_values))
    moving_ranges = np.abs(np.diff(baseline_values))
    mean_moving_range = float(np.mean(moving_ranges))
    sigma_estimate = mean_moving_range / 1.128

    return SPCControlLimits(
        center_line=center,
        upper_control_limit=center + n_sigma * sigma_estimate,
        lower_control_limit=center - n_sigma * sigma_estimate,
    )


def flag_spc_anomalies(values: np.ndarray, limits: SPCControlLimits) -> np.ndarray:
    """Flag which values fall outside the control limits — the basic SPC
    "out of control" signal (a single point beyond 3-sigma).

    Returns
    -------
    np.ndarray[bool]
        True where the corresponding value is flagged as anomalous.
    """
    values = np.asarray(values, dtype=float)
    return (values > limits.upper_control_limit) | (values < limits.lower_control_limit)


# ── Isolation Forest (ML) ────────────────────────────────────────────────────
@dataclass
class IsolationForestAnomalyResult:
    """Output of applying a fitted Isolation Forest to new data."""

    anomaly_flags: np.ndarray    # bool array, True = flagged as anomaly
    anomaly_scores: np.ndarray   # lower (more negative) = more anomalous


def fit_isolation_forest_detector(
    training_features: np.ndarray,
    contamination: float = 0.05,
    random_state: int = 42,
) -> IsolationForest:
    """Fit an Isolation Forest anomaly detector.

    Parameters
    ----------
    training_features : array-like, shape (n_samples, n_features)
                         e.g. columns [pressure, flow] from historical
                         (or, for demonstration, synthetic) operating data
    contamination      : float  expected fraction of anomalies in the
                          TRAINING data — sklearn uses this to set the
                          decision threshold. Tune to your actual
                          historical anomaly rate; the default is a
                          generic placeholder, not a calibrated estimate.
    random_state        : int  seed, for reproducibility

    Returns
    -------
    sklearn.ensemble.IsolationForest
        The fitted model — pass to ``detect_anomalies`` for inference.
    """
    training_features = np.asarray(training_features, dtype=float)
    if training_features.ndim == 1:
        training_features = training_features.reshape(-1, 1)
    model = IsolationForest(contamination=contamination, random_state=random_state)
    model.fit(training_features)
    return model


def detect_anomalies(model: IsolationForest, features: np.ndarray) -> IsolationForestAnomalyResult:
    """Apply a fitted Isolation Forest to new data.

    Parameters
    ----------
    model    : IsolationForest  from ``fit_isolation_forest_detector``
    features : array-like, shape (n_samples, n_features)

    Returns
    -------
    IsolationForestAnomalyResult
    """
    features = np.asarray(features, dtype=float)
    if features.ndim == 1:
        features = features.reshape(-1, 1)
    predictions = model.predict(features)   # 1 = normal, -1 = anomaly
    scores = model.score_samples(features)
    return IsolationForestAnomalyResult(
        anomaly_flags=(predictions == -1),
        anomaly_scores=scores,
    )


def evaluate_detector_against_ground_truth(
    predicted_flags: np.ndarray, true_flags: np.ndarray
) -> dict:
    """Precision/recall/F1 of a detector's flags against known ground
    truth — only possible on synthetic/labeled benchmark data (real
    deployments rarely have a reliable ground-truth anomaly label).

    Parameters
    ----------
    predicted_flags : array-like[bool]
    true_flags      : array-like[bool]

    Returns
    -------
    dict with keys: precision, recall, f1, n_true_positives,
    n_false_positives, n_false_negatives
    """
    predicted_flags = np.asarray(predicted_flags, dtype=bool)
    true_flags = np.asarray(true_flags, dtype=bool)
    if len(predicted_flags) != len(true_flags):
        raise ValueError("predicted_flags and true_flags must have the same length.")

    tp = int(np.sum(predicted_flags & true_flags))
    fp = int(np.sum(predicted_flags & ~true_flags))
    fn = int(np.sum(~predicted_flags & true_flags))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_true_positives": tp,
        "n_false_positives": fp,
        "n_false_negatives": fn,
    }
