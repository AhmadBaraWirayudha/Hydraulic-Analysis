"""
ASME B31.3 (Process Piping) — straight pipe wall thickness under internal
pressure, Equation (3a).

Equation (3a) gives the *pressure design thickness* t for straight pipe
under internal pressure, valid in the thin-wall regime (t < D/6,
equivalently P/(S E) <= 0.385):

    t = P D / (2 (S E W + P Y))

where P is the internal design gauge pressure, D is the pipe outside
diameter, S is the material's allowable stress at design temperature, E is
the longitudinal weld joint quality factor, W is a weld-strength reduction
factor (relevant only at elevated temperature, per Table 302.3.5), and Y is
a dimensionless coefficient from Table 304.1.1 that depends on material and
temperature — 0.4 for ferritic/austenitic steel and most other ductile
metals at or below 900 F (482 C), which is the default used here and covers
the large majority of ambient/moderate-temperature water and process
distribution piping.

t alone is *not* a thickness to specify or order. ``evaluate_pipe_design``
carries the full design workflow forward: add the corrosion/mechanical
allowance (B31.3 para. 304.1.2(a): t_m = t + c), then gross that up for the
pipe mill's manufacturing under-tolerance to get the nominal thickness you
actually need to order — and, optionally, checks a candidate schedule wall
thickness against that requirement.

References
----------
ASME B31.3-2022, Process Piping, Chapter II, Part 1, paragraph 304.1.2,
  Equation (3a), and Table 304.1.1 (values of Y).
"""

from dataclasses import dataclass

# Y per ASME B31.3 Table 304.1.1, ferritic/austenitic steel and other
# ductile metals at <= 900 F (482 C) — covers the large majority of
# water/process distribution piping at ambient-to-moderate temperatures.
# Cast iron and elevated-temperature service use different tabulated
# values; override this for your actual material/temperature.
DEFAULT_Y_DUCTILE_STEEL: float = 0.4

# Common manufacturing under-tolerance on wall thickness for seamless pipe
# (the widely-cited 12.5% figure for API 5L / ASME B36.10-listed product
# forms). Welded pipe and other product specs can differ — check your
# actual mill/product spec and override if needed.
DEFAULT_MILL_UNDERTOLERANCE: float = 0.125


@dataclass
class PipeDesignResult:
    """Full ASME B31.3 Eq. (3a) wall-thickness design workflow result."""

    pressure_design_thickness_in: float    # t,  Eq (3a) — no allowances
    minimum_required_thickness_in: float   # t_m = t + allowances
    nominal_thickness_required_in: float   # t_m grossed up for mill under-tolerance
    thin_wall_assumption_valid: bool       # t < D/6 — Eq (3a) applicability
    selected_thickness_in: float | None
    derated_selected_thickness_in: float | None  # selected, after mill under-tolerance
    selected_thickness_adequate: bool | None
    margin_in: float | None                # derated_selected_thickness - t_m
    margin_ratio: float | None             # derated_selected_thickness / t_m


def pressure_design_thickness(
    design_pressure_psig: float,
    outside_diameter_in: float,
    allowable_stress_psi: float,
    quality_factor: float = 1.0,
    weld_strength_reduction_factor: float = 1.0,
    coefficient_y: float = DEFAULT_Y_DUCTILE_STEEL,
) -> float:
    """ASME B31.3 Eq. (3a): pressure design thickness of straight pipe
    under internal pressure [in].

        t = P D / (2 (S E W + P Y))

    Parameters
    ----------
    design_pressure_psig : float
        Internal design gauge pressure, P [psig].
    outside_diameter_in : float
        Pipe outside diameter, D [in].
    allowable_stress_psi : float
        Material allowable stress at design temperature, S [psi] (ASME
        B31.3 Table A-1).
    quality_factor : float
        Longitudinal weld joint quality factor, E (ASME B31.3 Table
        A-1B). 1.0 for seamless pipe; lower for some welded product forms.
    weld_strength_reduction_factor : float
        High-temperature weld strength reduction factor, W (ASME B31.3
        Table 302.3.5). 1.0 below the temperature range where this
        applies — the common case for water/process distribution piping.
    coefficient_y : float
        Dimensionless coefficient, Y (ASME B31.3 Table 304.1.1).

    Returns
    -------
    float
        Pressure design thickness, t [in] — the bare Eq. (3a) result,
        *before* corrosion/mechanical allowances or mill tolerance. Do not
        specify this directly as an order thickness — see
        ``evaluate_pipe_design``.
    """
    if design_pressure_psig <= 0:
        raise ValueError(
            f"Design pressure must be positive. Got {design_pressure_psig} psig."
        )
    if outside_diameter_in <= 0:
        raise ValueError(
            f"Outside diameter must be positive. Got {outside_diameter_in} in."
        )
    if outside_diameter_in > 120:
        raise ValueError(
            f"Outside diameter {outside_diameter_in} in is unrealistically large "
            "(>120 in / 10 ft). Check unit conversion — did you mean mm?"
        )
    if allowable_stress_psi <= 0:
        raise ValueError(
            f"Allowable stress must be positive. Got {allowable_stress_psi} psi."
        )
    if not (0 < quality_factor <= 1.0):
        raise ValueError(f"Quality factor E must be in (0, 1]. Got {quality_factor}.")
    if not (0 < weld_strength_reduction_factor <= 1.0):
        raise ValueError(
            f"Weld strength reduction factor W must be in (0, 1]. "
            f"Got {weld_strength_reduction_factor}."
        )
    if not (0 <= coefficient_y <= 0.7):
        raise ValueError(
            f"Coefficient Y must be in [0, 0.7] per ASME B31.3 Table 304.1.1. "
            f"Got {coefficient_y}."
        )

    return (design_pressure_psig * outside_diameter_in) / (
        2 * (
            allowable_stress_psi * quality_factor * weld_strength_reduction_factor
            + design_pressure_psig * coefficient_y
        )
    )


def evaluate_pipe_design(
    design_pressure_psig: float,
    outside_diameter_in: float,
    allowable_stress_psi: float,
    quality_factor: float = 1.0,
    weld_strength_reduction_factor: float = 1.0,
    coefficient_y: float = DEFAULT_Y_DUCTILE_STEEL,
    corrosion_allowance_in: float = 0.0,
    mechanical_allowance_in: float = 0.0,
    mill_undertolerance_fraction: float = DEFAULT_MILL_UNDERTOLERANCE,
    selected_thickness_in: float | None = None,
) -> PipeDesignResult:
    """Full pressure-design wall-thickness workflow: Eq. (3a) pressure
    design thickness, plus corrosion/mechanical allowances (B31.3 para.
    304.1.2(a): t_m = t + c), plus the manufacturing under-tolerance
    grossing-up that determines the nominal thickness you must actually
    order — and, optionally, a pass/fail check against a candidate
    ``selected_thickness_in`` (e.g. a standard schedule wall thickness
    from a pipe table).

    Parameters
    ----------
    corrosion_allowance_in : float
        Allowance for corrosion/erosion over the design life [in].
    mechanical_allowance_in : float
        Allowance for material removed in threading or grooving, if
        applicable [in].
    mill_undertolerance_fraction : float
        Manufacturing under-tolerance fraction — e.g. 0.125 for the
        commonly-cited 12.5% seamless-pipe figure. Set to 0.0 if your
        product spec guarantees minimum (not nominal) wall.
    selected_thickness_in : float | None
        A candidate actual wall thickness to check for adequacy (e.g. a
        standard schedule thickness under consideration). None skips the
        pass/fail check; the other fields are still computed.
    other params : see ``pressure_design_thickness``.

    Returns
    -------
    PipeDesignResult
    """
    t = pressure_design_thickness(
        design_pressure_psig, outside_diameter_in, allowable_stress_psi,
        quality_factor, weld_strength_reduction_factor, coefficient_y,
    )
    if corrosion_allowance_in < 0:
        raise ValueError(
            f"Corrosion allowance must be non-negative. Got {corrosion_allowance_in} in."
        )
    if mechanical_allowance_in < 0:
        raise ValueError(
            f"Mechanical allowance must be non-negative. Got {mechanical_allowance_in} in."
        )
    if not (0 <= mill_undertolerance_fraction < 1.0):
        raise ValueError(
            "Mill under-tolerance fraction must be in [0, 1). "
            f"Got {mill_undertolerance_fraction}."
        )

    t_m = t + corrosion_allowance_in + mechanical_allowance_in
    t_nominal = t_m / (1 - mill_undertolerance_fraction)
    thin_wall_valid = t < outside_diameter_in / 6.0

    selected_adequate = None
    derated = None
    margin_in = None
    margin_ratio = None
    if selected_thickness_in is not None:
        if selected_thickness_in <= 0:
            raise ValueError(
                f"Selected thickness must be positive. Got {selected_thickness_in} in."
            )
        derated = selected_thickness_in * (1 - mill_undertolerance_fraction)
        margin_in = derated - t_m
        margin_ratio = derated / t_m
        selected_adequate = margin_in >= 0

    return PipeDesignResult(
        pressure_design_thickness_in=t,
        minimum_required_thickness_in=t_m,
        nominal_thickness_required_in=t_nominal,
        thin_wall_assumption_valid=thin_wall_valid,
        selected_thickness_in=selected_thickness_in,
        derated_selected_thickness_in=derated,
        selected_thickness_adequate=selected_adequate,
        margin_in=margin_in,
        margin_ratio=margin_ratio,
    )
