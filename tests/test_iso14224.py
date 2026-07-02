"""
Unit tests for src/machine_learning/iso14224.py — ISO 14224 reliability
taxonomy constants and piping-failure classification helpers.

Tests are intentionally non-prescriptive about specific code string values
(which are defined by the standard and not ours to change) but check that:
  - the taxonomy constants are non-empty and consistent
  - classify_degradation_scenario() returns the right types and identifies
    reduced-flow as the failure mode (since roughness increase reduces
    effective throughput)
  - annotate_anomaly_flags() correctly propagates flags, scores, and ISO
    codes, and validates its inputs
"""

import numpy as np
import pytest

from src.machine_learning.iso14224 import (
    EQUIPMENT_CLASS,
    EQUIPMENT_CLASS_CODE,
    FM_LEAKAGE_EXTERNAL,
    FM_LEAKAGE_INTERNAL,
    FM_REDUCED_FLOW,
    FM_NO_FLOW,
    FM_ABNORMAL_READING,
    FM_VIBRATION,
    FM_STRUCTURAL,
    MECH_CORROSION,
    MECH_EROSION,
    MECH_FOULING,
    MECH_FATIGUE,
    MECH_CAVITATION,
    MECH_CRACKING,
    MECH_OVERHEATING,
    MECH_WEAR,
    MECH_BLOCKAGE,
    DET_CONDITION_MONITORING,
    DET_AUTOMATIC,
    BOUNDARY_ITEMS,
    AnomalyRecord,
    DegradationScenarioClassification,
    annotate_anomaly_flags,
    classify_degradation_scenario,
)


# ── Taxonomy constants: basic sanity ────────────────────────────────────────

def test_equipment_class_is_piping():
    assert EQUIPMENT_CLASS == "Piping"


def test_equipment_class_code_is_nonempty():
    assert len(EQUIPMENT_CLASS_CODE) > 0


def test_all_failure_mode_codes_are_nonempty():
    for code in (
        FM_LEAKAGE_EXTERNAL, FM_LEAKAGE_INTERNAL, FM_REDUCED_FLOW,
        FM_NO_FLOW, FM_ABNORMAL_READING, FM_VIBRATION, FM_STRUCTURAL,
    ):
        assert len(code) > 0, f"Empty failure mode code: {code!r}"


def test_all_failure_mechanism_codes_are_nonempty():
    for code in (
        MECH_CORROSION, MECH_EROSION, MECH_FOULING, MECH_FATIGUE,
        MECH_CAVITATION, MECH_CRACKING, MECH_OVERHEATING, MECH_WEAR,
        MECH_BLOCKAGE,
    ):
        assert len(code) > 0, f"Empty failure mechanism code: {code!r}"


def test_failure_mode_codes_are_distinct():
    codes = [
        FM_LEAKAGE_EXTERNAL, FM_LEAKAGE_INTERNAL, FM_REDUCED_FLOW,
        FM_NO_FLOW, FM_ABNORMAL_READING, FM_VIBRATION, FM_STRUCTURAL,
    ]
    assert len(codes) == len(set(codes)), "Duplicate failure mode codes"


def test_failure_mechanism_codes_are_distinct():
    codes = [
        MECH_CORROSION, MECH_EROSION, MECH_FOULING, MECH_FATIGUE,
        MECH_CAVITATION, MECH_CRACKING, MECH_OVERHEATING, MECH_WEAR,
        MECH_BLOCKAGE,
    ]
    assert len(codes) == len(set(codes)), "Duplicate failure mechanism codes"


def test_boundary_items_nonempty_tuple():
    assert isinstance(BOUNDARY_ITEMS, tuple)
    assert len(BOUNDARY_ITEMS) > 0
    for item in BOUNDARY_ITEMS:
        assert isinstance(item, str) and len(item) > 0


def test_detection_method_codes_are_nonempty():
    assert len(DET_CONDITION_MONITORING) > 0
    assert len(DET_AUTOMATIC) > 0


# ── classify_degradation_scenario ───────────────────────────────────────────

def test_classify_degradation_scenario_returns_correct_type():
    result = classify_degradation_scenario()
    assert isinstance(result, DegradationScenarioClassification)


def test_classify_degradation_scenario_failure_mode_is_reduced_flow():
    """Roughness growth restricts effective throughput — ISO 14224 maps
    this to 'Reduced flow' (FLR), not 'No flow' (FLN) or leakage."""
    result = classify_degradation_scenario()
    assert result.failure_mode == FM_REDUCED_FLOW


def test_classify_degradation_scenario_primary_mechanism_is_fouling_or_corrosion():
    """Both fouling (scaling/deposit) and corrosion (wall loss) increase
    roughness — either is a legitimate primary mechanism; both are
    represented in the classification."""
    result = classify_degradation_scenario()
    assert result.failure_mechanism_primary in (MECH_FOULING, MECH_CORROSION)


def test_classify_degradation_scenario_secondary_mechanism_is_fouling_or_corrosion():
    result = classify_degradation_scenario()
    assert result.failure_mechanism_secondary in (MECH_FOULING, MECH_CORROSION)


def test_classify_degradation_scenario_primary_and_secondary_differ():
    result = classify_degradation_scenario()
    assert result.failure_mechanism_primary != result.failure_mechanism_secondary


def test_classify_degradation_scenario_detection_is_condition_monitoring():
    """The ML demo models trend-based condition monitoring (scheduled
    head-loss measurements), not operator observation or functional test."""
    result = classify_degradation_scenario()
    assert result.detection_method == DET_CONDITION_MONITORING


def test_classify_degradation_scenario_references_iso_14224():
    result = classify_degradation_scenario()
    assert "14224" in result.standard_reference


def test_classify_degradation_scenario_equipment_class_is_piping():
    result = classify_degradation_scenario()
    assert result.equipment_class == EQUIPMENT_CLASS


def test_classify_degradation_scenario_descriptions_are_nonempty():
    result = classify_degradation_scenario()
    assert len(result.failure_mode_description) > 0
    assert len(result.mechanism_description) > 0
    assert len(result.detection_description) > 0


def test_classify_degradation_scenario_is_frozen():
    """DegradationScenarioClassification is frozen — it's a taxonomy
    mapping, not mutable state."""
    result = classify_degradation_scenario()
    with pytest.raises((AttributeError, TypeError)):
        result.failure_mode = "XXX"  # type: ignore[misc]


# ── annotate_anomaly_flags ───────────────────────────────────────────────────

def test_annotate_anomaly_flags_returns_one_record_per_observation():
    flags = [False, True, False, True, False]
    scores = [-0.1, -0.6, -0.05, -0.72, -0.09]
    records = annotate_anomaly_flags(flags, scores)
    assert len(records) == len(flags)


def test_annotate_anomaly_flags_all_records_are_anomaly_record():
    flags = [True, False]
    scores = [-0.5, -0.1]
    for r in annotate_anomaly_flags(flags, scores):
        assert isinstance(r, AnomalyRecord)


def test_annotate_anomaly_flags_observation_indices_are_sequential():
    flags = [False, True, False]
    scores = [-0.1, -0.55, -0.08]
    records = annotate_anomaly_flags(flags, scores)
    assert [r.observation_index for r in records] == list(range(len(flags)))


def test_annotate_anomaly_flags_normal_observations_have_none_labels():
    flags = [False, True, False]
    scores = [-0.1, -0.6, -0.12]
    records = annotate_anomaly_flags(flags, scores)
    assert records[0].failure_mode is None
    assert records[0].failure_mechanism_candidate is None
    assert records[2].failure_mode is None


def test_annotate_anomaly_flags_anomalous_observations_have_labels():
    flags = [False, True, False]
    scores = [-0.1, -0.6, -0.12]
    records = annotate_anomaly_flags(flags, scores)
    assert records[1].failure_mode is not None
    assert records[1].failure_mechanism_candidate is not None


def test_annotate_anomaly_flags_scores_are_preserved():
    flags = np.array([True, False])
    scores = np.array([-0.65, -0.08])
    records = annotate_anomaly_flags(flags, scores)
    assert records[0].anomaly_score == pytest.approx(-0.65)
    assert records[1].anomaly_score == pytest.approx(-0.08)


def test_annotate_anomaly_flags_default_detection_method_is_automatic():
    """Default detection method is DET_AUTOMATIC — appropriate for an
    automated monitoring pipeline."""
    flags = [True]
    scores = [-0.7]
    records = annotate_anomaly_flags(flags, scores)
    assert records[0].detection_method == DET_AUTOMATIC


def test_annotate_anomaly_flags_custom_failure_mode_propagates():
    from src.machine_learning.iso14224 import FM_VIBRATION, MECH_FATIGUE
    flags = [True, False]
    scores = [-0.5, -0.1]
    records = annotate_anomaly_flags(
        flags, scores, failure_mode=FM_VIBRATION,
        failure_mechanism_candidate=MECH_FATIGUE,
    )
    assert records[0].failure_mode == FM_VIBRATION
    assert records[0].failure_mechanism_candidate == MECH_FATIGUE
    assert records[1].failure_mode is None   # still None for non-anomaly


def test_annotate_anomaly_flags_all_normal_returns_all_none_labels():
    flags = [False, False, False]
    scores = [-0.05, -0.08, -0.03]
    records = annotate_anomaly_flags(flags, scores)
    assert all(r.failure_mode is None for r in records)
    assert all(r.is_anomaly is False for r in records)


def test_annotate_anomaly_flags_all_anomalous_all_labelled():
    flags = [True, True]
    scores = [-0.7, -0.65]
    records = annotate_anomaly_flags(flags, scores)
    assert all(r.failure_mode is not None for r in records)
    assert all(r.is_anomaly is True for r in records)


def test_annotate_anomaly_flags_accepts_numpy_arrays():
    """Should accept np.ndarray without requiring list conversion."""
    flags = np.array([True, False, True])
    scores = np.array([-0.6, -0.1, -0.55])
    records = annotate_anomaly_flags(flags, scores)
    assert len(records) == 3


def test_annotate_anomaly_flags_empty_input_returns_empty_list():
    records = annotate_anomaly_flags([], [])
    assert records == []


def test_annotate_anomaly_flags_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        annotate_anomaly_flags([True, False], [-0.5])


def test_annotate_anomaly_flags_equipment_class_is_piping():
    """Every record carries the equipment class for CMMS import."""
    flags = [True]
    scores = [-0.6]
    records = annotate_anomaly_flags(flags, scores)
    assert records[0].equipment_class == EQUIPMENT_CLASS


def test_annotate_anomaly_flags_standard_reference_mentions_iso_14224():
    flags = [True]
    scores = [-0.6]
    records = annotate_anomaly_flags(flags, scores)
    assert "14224" in records[0].standard_reference
