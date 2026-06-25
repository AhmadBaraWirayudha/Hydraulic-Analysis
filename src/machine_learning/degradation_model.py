"""
Predictive maintenance: regression model for pipe roughness degradation
over time, using an ensemble (Random Forest) method.

IMPORTANT: see ``synthetic_data.py``'s module docstring. Any model fit on
data from that module is a demonstration of the ML *pattern*, not a
validated predictive tool — swap in your own real inspection/cleaning
records (same column shape: elapsed time vs. measured roughness) via
``fit_degradation_model`` for actual use.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split


@dataclass
class DegradationModelResult:
    """A fitted degradation model, plus held-out evaluation metrics."""

    model: RandomForestRegressor
    train_r2: float
    test_r2: float
    test_mae: float
    n_train: int
    n_test: int


def fit_degradation_model(
    days: np.ndarray,
    roughness_m: np.ndarray,
    n_estimators: int = 100,
    test_size: float = 0.2,
    random_state: int = 42,
) -> DegradationModelResult:
    """Fit a Random Forest regressor predicting roughness from elapsed time.

    Parameters
    ----------
    days         : array-like  elapsed time [days] for each observation
    roughness_m  : array-like  measured (or synthetic) roughness [m]
    n_estimators : int    number of trees in the forest
    test_size    : float  fraction of data held out for evaluation
    random_state : int    seed, for reproducible train/test split + fit

    Returns
    -------
    DegradationModelResult
    """
    days = np.asarray(days, dtype=float)
    roughness_m = np.asarray(roughness_m, dtype=float)
    if len(days) != len(roughness_m):
        raise ValueError(
            f"days and roughness_m must have the same length. "
            f"Got {len(days)} and {len(roughness_m)}."
        )
    if len(days) < 10:
        raise ValueError(f"Need at least 10 observations to fit/evaluate. Got {len(days)}.")

    X = days.reshape(-1, 1)
    y = roughness_m

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state)
    model.fit(X_train, y_train)

    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)

    return DegradationModelResult(
        model=model,
        train_r2=r2_score(y_train, train_pred),
        test_r2=r2_score(y_test, test_pred),
        test_mae=mean_absolute_error(y_test, test_pred),
        n_train=len(X_train),
        n_test=len(X_test),
    )


def predict_roughness(result: DegradationModelResult, days: np.ndarray) -> np.ndarray:
    """Predict roughness at the given day(s) using a fitted model.

    Note: Random Forests do not extrapolate beyond their training range —
    predictions for ``days`` well beyond the data used in
    ``fit_degradation_model`` will plateau at the nearest training
    leaf's value rather than continuing any trend. This is a real
    limitation of tree-based models for this kind of forecasting task,
    not a bug — consider a parametric model (e.g. fit your own curve to
    the assumed degradation law) if true extrapolation is required.
    """
    days = np.asarray(days, dtype=float).reshape(-1, 1)
    return result.model.predict(days)


def predict_maintenance_threshold_day(
    result: DegradationModelResult,
    roughness_threshold_m: float,
    max_day: int = 3650,
    step_days: int = 5,
) -> int | None:
    """Find the first day at which predicted roughness is expected to
    reach or exceed a maintenance-trigger threshold (e.g. "schedule
    cleaning when roughness exceeds 2x its initial value").

    Subject to the extrapolation limitation noted in ``predict_roughness``
    — this search will not find a threshold-crossing day beyond the
    model's training range; it will return None or a misleadingly early
    answer (capped at the highest training value) instead. Reliable only
    within the range of days actually present in the training data.

    Parameters
    ----------
    roughness_threshold_m : float  trigger threshold [m]
    max_day                : int   search horizon [days]
    step_days              : int   search resolution [days]

    Returns
    -------
    int | None
        First day the threshold is reached, or None if not reached within
        ``max_day``.
    """
    days_to_check = np.arange(0, max_day, step_days)
    predictions = predict_roughness(result, days_to_check)
    exceeded = days_to_check[predictions >= roughness_threshold_m]
    return int(exceeded[0]) if len(exceeded) > 0 else None
