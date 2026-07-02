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


# ── NPSH margin (cavitation risk check) ───────────────────────────────────
def check_npsh_margin(npsh_available_m: float, npsh_required_m: float | None) -> str | None:
    """Return a warning if NPSH available is insufficient relative to NPSH
    required (cavitation risk), or None if acceptable or no NPSHr was
    supplied.

    Thresholds follow common Hydraulic Institute practice: NPSHa < NPSHr is
    outright cavitation risk; a margin ratio below 1.2 (i.e. less than 20%
    headroom) is flagged as thin, since real-world margins erode with pump
    wear, suction strainer fouling, and temperature drift. This is a general
    engineering guideline, not a universal standard — some applications
    (e.g. API 610 services) call for larger margins.

    Parameters
    ----------
    npsh_available_m : float        NPSHa, computed at the operating point [m]
    npsh_required_m  : float | None NPSHr from the pump's manufacturer curve [m];
                                     None skips the check entirely
    """
    if npsh_required_m is None or npsh_required_m <= 0:
        return None
    margin_ratio = npsh_available_m / npsh_required_m
    if margin_ratio < 1.0:
        return (
            f"⚠️  Cavitation risk: NPSH available ({npsh_available_m:.2f} m) is "
            f"below NPSH required ({npsh_required_m:.2f} m) — "
            f"{margin_ratio:.0%} margin. Expect vapor bubble formation/collapse "
            f"at the impeller, causing erosion, noise, and performance loss."
        )
    if margin_ratio < 1.2:
        return (
            f"⚠️  Thin NPSH margin: {margin_ratio:.0%} of required "
            f"({npsh_available_m:.2f} m available vs {npsh_required_m:.2f} m "
            f"required). Common practice recommends ≥20% margin to absorb "
            f"wear, fouling, and operating-point drift."
        )
    return None


# ── Voltage unbalance (motor protection check) ────────────────────────────
def check_voltage_unbalance(unbalance_percent: float) -> str | None:
    """Return a warning if voltage unbalance exceeds NEMA's recommended
    operating limits, or None if within bounds.

    NEMA MG1 consistently recommends against operating motors above 5%
    voltage unbalance across all cited sources, and recommends derating
    above 1%. The precise derating *amount* between those thresholds
    depends on motor load and class and isn't hardcoded here — see
    ``hydraulics.electrical.derating_factor_from_curve`` to apply your
    motor's actual published derating curve once unbalance is flagged.

    Parameters
    ----------
    unbalance_percent : float  voltage unbalance, in percent (see
                         ``hydraulics.electrical.voltage_unbalance_percent``)
    """
    if unbalance_percent > 5.0:
        return (
            f"⚠️  Voltage unbalance {unbalance_percent:.1f}% exceeds NEMA's "
            f"5% maximum recommended operating limit. Operation above this "
            f"level is not recommended — investigate the supply before continuing."
        )
    if unbalance_percent > 1.0:
        return (
            f"⚠️  Voltage unbalance {unbalance_percent:.1f}% exceeds NEMA's 1% "
            f"threshold where derating is recommended. Apply your motor's "
            f"published derating curve (see hydraulics.electrical.derating_factor_from_curve)."
        )
    return None


# ── Water hammer (transient pressure surge) check ─────────────────────────
def check_water_hammer_risk(peak_pressure_Pa: float, pipe_rated_pressure_Pa: float | None) -> str | None:
    """Return a warning if a predicted water-hammer peak pressure
    approaches or exceeds the pipe's rated pressure, or None if acceptable
    or no rating was supplied.

    Parameters
    ----------
    peak_pressure_Pa        : float        predicted peak pressure during
                               the transient [Pa] (see
                               ``hydraulics.transients.WaterHammerResult.peak_pressure_Pa``)
    pipe_rated_pressure_Pa  : float | None  pipe's pressure rating (e.g. its
                               PN/pressure class) [Pa]; None skips the check
    """
    if pipe_rated_pressure_Pa is None or pipe_rated_pressure_Pa <= 0:
        return None
    ratio = peak_pressure_Pa / pipe_rated_pressure_Pa
    if ratio > 1.0:
        return (
            f"⚠️  Water hammer risk: predicted peak pressure ({peak_pressure_Pa/1000:.1f} kPa) "
            f"exceeds the pipe's rated pressure ({pipe_rated_pressure_Pa/1000:.1f} kPa) — "
            f"{ratio:.0%} of rating. Risk of pipe rupture — slow the valve/pump "
            f"closure, add surge protection, or select a higher-rated pipe."
        )
    if ratio > 0.8:
        return (
            f"⚠️  Predicted peak pressure is at {ratio:.0%} of the pipe's rated "
            f"pressure — thin margin for a transient event. Consider surge "
            f"protection (e.g. slower valve closure, surge tanks, relief valves)."
        )
    return None


# ── Pipe wall thickness (ASME B31.3 pressure design check) ───────────────
def check_pipe_design_margin(
    derated_selected_thickness_in: float | None,
    minimum_required_thickness_in: float,
    thin_wall_assumption_valid: bool = True,
) -> str | None:
    """Return a warning if a selected pipe wall thickness is inadequate or
    has thin margin against the ASME B31.3 minimum required thickness
    (t_m), or if the Eq. (3a) thin-wall assumption itself doesn't hold for
    this design, or None if everything checks out.

    Thresholds mirror ``check_npsh_margin``: below 100% of required is an
    outright fail; under 120% is flagged as thin, since real wall
    thickness also has to absorb manufacturing variation beyond the
    mill's stated under-tolerance and any future re-rating.

    Parameters
    ----------
    derated_selected_thickness_in : float | None
        Candidate wall thickness after mill under-tolerance [in] (see
        ``hydraulics.pipe_design.PipeDesignResult.derated_selected_thickness_in``).
        None skips the margin check entirely (no candidate thickness was
        supplied).
    minimum_required_thickness_in : float
        ASME B31.3 minimum required thickness, t_m [in] (see
        ``hydraulics.pipe_design.PipeDesignResult.minimum_required_thickness_in``).
    thin_wall_assumption_valid : bool
        Whether Eq. (3a)'s thin-wall assumption (t < D/6) held for this
        design (see
        ``hydraulics.pipe_design.PipeDesignResult.thin_wall_assumption_valid``).
    """
    if not thin_wall_assumption_valid:
        return (
            "⚠️  ASME B31.3 Eq. (3a) thin-wall assumption (t < D/6) does not "
            "hold for this design — the standard requires the thick-wall "
            "relation (Eq. 3b) instead. Treat this result as approximate and "
            "consult a more detailed analysis."
        )
    if derated_selected_thickness_in is None or minimum_required_thickness_in <= 0:
        return None
    ratio = derated_selected_thickness_in / minimum_required_thickness_in
    if ratio < 1.0:
        return (
            f"⚠️  Selected wall thickness is undersized: {derated_selected_thickness_in:.4f} in "
            f"after mill under-tolerance is below the ASME B31.3 minimum required "
            f"thickness of {minimum_required_thickness_in:.4f} in ({ratio:.0%}). "
            f"Select a heavier schedule."
        )
    if ratio < 1.2:
        return (
            f"⚠️  Thin margin: selected wall thickness clears the ASME B31.3 minimum "
            f"required thickness by only {ratio:.0%} after mill under-tolerance "
            f"({derated_selected_thickness_in:.4f} in vs {minimum_required_thickness_in:.4f} in "
            f"required). Consider the next heavier schedule for headroom."
        )
    return None
