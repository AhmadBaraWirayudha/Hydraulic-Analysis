"""
Poka-Yoke (mistake-proofing) validation for hydraulic inputs.

All validators raise ValueError with a descriptive message on failure.
Use ``warn_only=True`` variants to get a warning string instead.

References
----------
SNI 03-6481-2000 — Sistem Penyediaan Air Minum (velocity criteria)
"""

from .constants import SNI_VELOCITY_MIN, SNI_VELOCITY_MAX


# ── Pipe geometry ─────────────────────────────────────────────────────────────
def validate_pipe(diameter_m: float, length_m: float, roughness_m: float) -> None:
    """Raise ValueError if pipe parameters are physically implausible."""
    if diameter_m <= 0:
        raise ValueError(
            f"Pipe diameter must be positive. Got {diameter_m} m."
        )
    if diameter_m > 3.0:
        raise ValueError(
            f"Diameter {diameter_m:.3f} m is unrealistically large (>3 m). "
            "Check unit conversion — did you mean mm?"
        )
    if length_m <= 0:
        raise ValueError(
            f"Pipe length must be positive. Got {length_m} m."
        )
    if roughness_m < 0:
        raise ValueError(
            f"Absolute roughness must be ≥ 0. Got {roughness_m} m."
        )
    if roughness_m >= diameter_m:
        raise ValueError(
            f"Roughness ({roughness_m} m) must be less than diameter ({diameter_m} m)."
        )


# ── Flow rate ─────────────────────────────────────────────────────────────────
def validate_flow(flow_rate_m3s: float) -> None:
    """Raise ValueError if flow rate is out of range."""
    if flow_rate_m3s < 0:
        raise ValueError(
            f"Flow rate must be non-negative. Got {flow_rate_m3s} m³/s."
        )
    if flow_rate_m3s > 50.0:
        raise ValueError(
            f"Flow rate {flow_rate_m3s} m³/s is unrealistically high (>50 m³/s). "
            "Check unit conversion — did you mean L/s?"
        )


# ── Fluid properties ──────────────────────────────────────────────────────────
def validate_fluid(density: float, viscosity: float) -> None:
    """Raise ValueError if fluid properties are unphysical."""
    if density <= 0:
        raise ValueError(f"Fluid density must be positive. Got {density} kg/m³.")
    if density > 20_000:
        raise ValueError(f"Density {density} kg/m³ seems unrealistic (>20 000 kg/m³).")
    if viscosity <= 0:
        raise ValueError(f"Dynamic viscosity must be positive. Got {viscosity} Pa·s.")


# ── Pump efficiencies ─────────────────────────────────────────────────────────
def validate_pump(eta_p: float, eta_m: float) -> None:
    """Raise ValueError if pump/motor efficiencies are out of (0, 1]."""
    if not (0 < eta_p <= 1.0):
        raise ValueError(
            f"Pump hydraulic efficiency must be in (0, 1]. Got {eta_p}."
        )
    if not (0 < eta_m <= 1.0):
        raise ValueError(
            f"Motor efficiency must be in (0, 1]. Got {eta_m}."
        )


# ── Pump load (Muri / overburden check) ──────────────────────────────────
def check_pump_load(shaft_power_W: float, rated_power_W: float | None) -> str | None:
    """Return a warning if pump shaft power approaches or exceeds rated
    capacity (the Lean *Muri* / overburden signal), or None if acceptable
    or no rated capacity was supplied.

    Thresholds: >100% rated = overloaded (likely premature failure risk);
    80-100% = approaching overburden, flagged as a planning signal.

    Parameters
    ----------
    shaft_power_W : float        required pump shaft power [W]
    rated_power_W : float | None pump's rated/nameplate shaft power [W];
                                  None skips the check entirely (no rated
                                  pump configured for this scenario)
    """
    if rated_power_W is None or rated_power_W <= 0:
        return None
    load_factor = shaft_power_W / rated_power_W
    if load_factor > 1.0:
        return (
            f"⚠️  Pump overloaded (Muri): operating at {load_factor:.0%} of rated "
            f"capacity ({shaft_power_W:,.2f} W vs {rated_power_W:,.2f} W rated). "
            f"Risk of premature failure — select a larger pump or reduce demand."
        )
    if load_factor > 0.8:
        return (
            f"⚠️  Pump load at {load_factor:.0%} of rated capacity — approaching "
            f"the overburden threshold (Muri). Consider headroom for future demand growth."
        )
    return None


# ── Flow velocity (SNI guideline check) ──────────────────────────────────────
def check_velocity(velocity_m_s: float) -> str | None:
    """
    Return a warning string if velocity is outside SNI 03-6481-2000 guidelines,
    or None if acceptable.

    Recommended range: 0.9 – 2.0 m/s for distribution mains.
    """
    if velocity_m_s < 0.3:
        return (
            f"⚠️  v = {velocity_m_s:.3f} m/s is very low. "
            "Risk of sediment deposition. "
            f"SNI recommends ≥ {SNI_VELOCITY_MIN} m/s."
        )
    if velocity_m_s < SNI_VELOCITY_MIN:
        return (
            f"⚠️  v = {velocity_m_s:.3f} m/s is below SNI minimum "
            f"({SNI_VELOCITY_MIN} m/s). Consider a smaller pipe diameter."
        )
    if velocity_m_s > SNI_VELOCITY_MAX:
        return (
            f"⚠️  v = {velocity_m_s:.3f} m/s exceeds SNI maximum "
            f"({SNI_VELOCITY_MAX} m/s). Risk of water hammer."
        )
    return None  # within acceptable range
