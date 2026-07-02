"""
ISO 14224 reliability taxonomy for piping systems.

ISO 14224:2016 ("Petroleum, petrochemical and natural gas industries —
Collection and exchange of reliability and maintenance data for equipment")
defines a standardised vocabulary and data structure for equipment failure
records. Section 8 / Annex D cover piping (equipment class "Piping").

This module exposes:

1.  Read-only string constants for the ISO 14224 codes most relevant to
    water-distribution and process piping — failure modes, failure
    mechanisms, and the equipment boundary items.

2.  ``classify_degradation_scenario`` — maps the roughness-degradation
    scenario that ``synthetic_data.generate_synthetic_roughness_degradation``
    models onto the appropriate ISO 14224 failure mode/mechanism, so the ML
    demo is legible to Reliability Engineers who use this standard.

3.  ``annotate_anomaly_flags`` — adds ISO 14224 labels to the boolean
    anomaly flag column returned by ``anomaly_detection.detect_anomalies``,
    producing a structured record of the type a Computerised Maintenance
    Management System (CMMS) would store.

Note: this module provides the *taxonomy* and *classification logic* from
ISO 14224.  It does not implement the full 14224 data exchange format
(which is an XML schema for CMMS interchange) — that would require
contractual/licensed access to the standard's annex schemas and is beyond
the scope of a screening/analysis tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

# ---------------------------------------------------------------------------
# § 1 — ISO 14224 taxonomy constants (piping-relevant subset)
# ---------------------------------------------------------------------------

# Equipment class (ISO 14224 Annex D, Table D.1)
EQUIPMENT_CLASS: str = "Piping"
EQUIPMENT_CLASS_CODE: str = "P"

# -- Failure modes (ISO 14224 §8.5, Table 5 — piping subset) ---------------
#: External leakage — fluid loss through pipe wall or fitting joint.
FM_LEAKAGE_EXTERNAL: str = "ELE"
#: Internal leakage — cross-contamination across an isolation point.
FM_LEAKAGE_INTERNAL: str = "ILE"
#: Reduced flow capacity — pipe can flow, but not at design throughput.
FM_REDUCED_FLOW: str = "FLR"
#: No flow — complete blockage or full wall-loss failure.
FM_NO_FLOW: str = "FLN"
#: Abnormal instrument reading — sensor signal outside expected range.
FM_ABNORMAL_READING: str = "AIR"
#: Vibration / noise above limit.
FM_VIBRATION: str = "VIB"
#: Structural failure — gross deformation or collapse.
FM_STRUCTURAL: str = "STF"

# -- Failure mechanisms (ISO 14224 §8.6, Table 6 — piping subset) ----------
#: Corrosion — electrochemical wall loss (general or localised).
MECH_CORROSION: str = "COR"
#: Erosion — wall loss driven by fluid-borne particle impingement.
MECH_EROSION: str = "ERO"
#: Fouling / scaling — deposit build-up reducing internal bore.
MECH_FOULING: str = "FOU"
#: Fatigue — cyclic-stress-driven crack growth (e.g. water hammer).
MECH_FATIGUE: str = "FAT"
#: Cavitation — vapour-bubble collapse damaging the pipe bore.
MECH_CAVITATION: str = "CAV"
#: Cracking — stress corrosion or hydrogen-induced.
MECH_CRACKING: str = "CRK"
#: Overheating — thermal degradation above design temperature.
MECH_OVERHEATING: str = "OVH"
#: Mechanical wear — abrasive contact damage.
MECH_WEAR: str = "WEA"
#: Blockage — debris accumulation without wall attack.
MECH_BLOCKAGE: str = "BLK"

# -- Detection methods (ISO 14224 §8.7 subset) ------------------------------
#: Condition monitoring — scheduled measurement-based detection.
DET_CONDITION_MONITORING: str = "CM"
#: Functional testing — detected during a scheduled test.
DET_FUNCTIONAL_TEST: str = "FT"
#: Inspection — visual or instrument survey.
DET_INSPECTION: str = "INS"
#: Operator observation — reported by operating personnel.
DET_OPERATOR: str = "OPR"
#: Automatic protective / alarm — triggered by a monitoring system.
DET_AUTOMATIC: str = "AUT"

# -- Boundary items (ISO 14224 Annex D — piping equipment boundary) ---------
BOUNDARY_ITEMS: tuple[str, ...] = (
    "Pipe body",
    "Welded / flanged joints",
    "Inline fittings (elbows, tees, reducers)",
    "Inline valves (if part of the pipe spool)",
    "Pipe supports and hangers",
)


# ---------------------------------------------------------------------------
# § 2 — Mapping the synthetic degradation scenario onto the taxonomy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DegradationScenarioClassification:
    """ISO 14224 classification of the roughness-degradation scenario
    modelled by
    ``machine_learning.synthetic_data.generate_synthetic_roughness_degradation``.
    """
    equipment_class: str = EQUIPMENT_CLASS
    equipment_class_code: str = EQUIPMENT_CLASS_CODE
    failure_mode: str = FM_REDUCED_FLOW
    failure_mode_description: str = (
        "Reduced flow capacity — increasing wall roughness raises friction "
        "losses, reducing effective flow rate at constant head."
    )
    failure_mechanism_primary: str = MECH_FOULING
    failure_mechanism_secondary: str = MECH_CORROSION
    mechanism_description: str = (
        "Roughness growth is consistent with fouling/scaling (deposit "
        "build-up) or corrosion (wall-loss pitting) — the dominant "
        "mechanism depends on the fluid chemistry and pipe material. The "
        "synthetic model uses a sqrt(time) growth law, a commonly assumed "
        "simplified pattern for these degradation types."
    )
    detection_method: str = DET_CONDITION_MONITORING
    detection_description: str = (
        "Condition monitoring: head-loss (pressure-drop) trend monitored "
        "over time; exceedance of a threshold triggers maintenance. In the "
        "demo, the Random Forest model learns this trend from synthetic "
        "measurements and predicts the threshold-crossing day."
    )
    standard_reference: str = "ISO 14224:2016 §8.5–8.7, Annex D (Piping)"


def classify_degradation_scenario() -> DegradationScenarioClassification:
    """Return the ISO 14224 classification of the roughness-degradation
    synthetic scenario.

    This is intentionally a pure lookup, not a model inference step — the
    failure mode/mechanism are determined by the scenario design, not by
    data.  Its value is documentation and communication: anyone reading a
    maintenance record generated from this module's output will see the same
    vocabulary used in their CMMS rather than opaque ML labels.

    Returns
    -------
    DegradationScenarioClassification
    """
    return DegradationScenarioClassification()


# ---------------------------------------------------------------------------
# § 3 — Annotating anomaly flags with ISO 14224 labels
# ---------------------------------------------------------------------------

@dataclass
class AnomalyRecord:
    """A single ISO 14224-labelled anomaly event, structured for CMMS
    import or audit output.

    Fields mirror ISO 14224 §8 "Failure data" record elements —
    observation_index maps to the timestamp/inspection reference, and
    failure_mode / failure_mechanism use the short codes from Tables 5–6.
    """
    observation_index: int
    is_anomaly: bool
    anomaly_score: float                    # Isolation Forest raw score
    failure_mode: str | None                # None when is_anomaly is False
    failure_mechanism_candidate: str | None
    detection_method: str
    equipment_class: str = EQUIPMENT_CLASS
    standard_reference: str = "ISO 14224:2016"


def annotate_anomaly_flags(
    anomaly_flags: Sequence[bool] | np.ndarray,
    anomaly_scores: Sequence[float] | np.ndarray,
    failure_mode: str = FM_ABNORMAL_READING,
    failure_mechanism_candidate: str = MECH_FOULING,
    detection_method: str = DET_AUTOMATIC,
) -> list[AnomalyRecord]:
    """Wrap Isolation Forest anomaly detection output in ISO 14224 labels.

    Parameters
    ----------
    anomaly_flags : sequence of bool
        Per-observation anomaly flag (True = anomaly) as returned by
        ``anomaly_detection.IsolationForestAnomalyResult.anomaly_flags``.
    anomaly_scores : sequence of float
        Raw Isolation Forest scores
        (``IsolationForestAnomalyResult.anomaly_scores``) — more negative
        means more anomalous.  Stored for audit / ranking purposes.
    failure_mode : str
        ISO 14224 failure-mode code to assign to anomalous observations.
        Defaults to ``FM_ABNORMAL_READING`` ("AIR") — appropriate when
        the anomaly is detected via a sensor reading outside expected
        range, as in the demo's head-loss / pressure-drop monitoring.
    failure_mechanism_candidate : str
        ISO 14224 failure-mechanism code to *candidate*-assign (not
        confirm — mechanism confirmation requires physical inspection).
        Defaults to ``MECH_FOULING`` ("FOU") since roughness growth is
        the root-cause in the synthetic scenario; replace with the
        appropriate code for your equipment and fluid chemistry.
    detection_method : str
        ISO 14224 detection method code. Defaults to ``DET_AUTOMATIC``
        ("AUT") for an automated monitoring system.

    Returns
    -------
    list of AnomalyRecord
        One record per observation, with ISO 14224 fields populated for
        anomalous observations and set to None for normal ones.
    """
    flags = np.asarray(anomaly_flags, dtype=bool)
    scores = np.asarray(anomaly_scores, dtype=float)
    if len(flags) != len(scores):
        raise ValueError(
            f"anomaly_flags (len {len(flags)}) and anomaly_scores "
            f"(len {len(scores)}) must have the same length."
        )
    records = []
    for i, (flag, score) in enumerate(zip(flags, scores)):
        records.append(AnomalyRecord(
            observation_index=i,
            is_anomaly=bool(flag),
            anomaly_score=float(score),
            failure_mode=failure_mode if flag else None,
            failure_mechanism_candidate=failure_mechanism_candidate if flag else None,
            detection_method=detection_method,
        ))
    return records
