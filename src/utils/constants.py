"""Physical and engineering constants used throughout the hydraulic analysis.

Values taken from the LaTeX reference report (Ahmad Bara Wirayudha):
  - Water properties at ~25 °C
  - PVC absolute roughness per standard references
"""

import math

# ── Gravitational acceleration ────────────────────────────────────────────────
GRAVITY: float = 9.81          # m/s²

# ── Default fluid properties (water, ~25 °C) ─────────────────────────────────
WATER_DENSITY: float     = 997.0   # kg/m³  (ρ)
WATER_VISCOSITY: float   = 1.0e-3  # Pa·s   (μ)  dynamic viscosity

# ── Pipe material roughness ───────────────────────────────────────────────────
PVC_ROUGHNESS: float     = 1.5e-6  # m   ε — absolute roughness for PVC
STEEL_ROUGHNESS: float   = 4.6e-5  # m   ε — commercial steel (for reference)

# ── Pressure conversion ───────────────────────────────────────────────────────
PA_PER_BAR: float        = 1.0e5   # 1 bar = 100,000 Pa

# ── Math ──────────────────────────────────────────────────────────────────────
PI: float = math.pi

# ── Regime thresholds (Reynolds) ─────────────────────────────────────────────
RE_LAMINAR_MAX:     int = 2_300    # Re < 2300  → laminar
RE_TRANSITION_MAX:  int = 4_000    # 2300–4000  → transition
# Re > 4000 → turbulent (Swamee-Jain valid)

# ── SNI velocity guidelines (SNI 03-6481-2000) ───────────────────────────────
SNI_VELOCITY_MIN: float = 0.9   # m/s — minimum recommended
SNI_VELOCITY_MAX: float = 2.0   # m/s — maximum recommended

# ── Temperature-dependent fluid properties: water ────────────────────────────
# Andrade equation: mu(T) = A * exp(B/T), T in Kelvin, mu in Pa.s
#
# Fitted (linear regression of ln(mu) vs 1/T) against standard engineering
# reference viscosity values for water over 0-100 degC. R^2 = 0.9875; the
# 2-parameter Andrade form is a known engineering approximation (see
# hydraulics/fluid_properties.py docstring) — error reaches ~8.5% at the
# coldest extreme (0 degC) but stays within ~5% from 10-90 degC.
WATER_ANDRADE_A: float = 1.846506e-6   # Pa.s
WATER_ANDRADE_B: float = 1853.5603     # K

# Antoine equation: log10(P_sat [Pa]) = A - B/(T + C), T in Kelvin
#
# Fitted (nonlinear least squares) against standard steam-table saturation
# vapor pressure values for water over 0-100 degC, anchored by the exact
# normal boiling point (100 degC = 101.325 kPa at 1 atm). R^2 > 0.99999;
# max error ~1.5% at 0 degC, under 0.1% from 30-100 degC.
WATER_ANTOINE_A: float = 10.115279
WATER_ANTOINE_B: float = 1683.6919      # K
WATER_ANTOINE_C: float = -43.6293       # K

# Valid calibration range for both fits above — extrapolating outside this
# range is flagged with a warning rather than silently trusted.
# ── Water hammer / transient analysis: material properties ──────────────────
# Bulk modulus of water (commonly cited 2.14-2.2 GPa at typical operating
# temperatures across multiple independent sources; using the widely-cited
# round figure). Young's moduli below are typical/illustrative reference
# values for common pipe materials — actual values vary by grade,
# manufacturer, and (for plastics) loading rate/temperature. For a real
# design decision, use your specific pipe's datasheet, not these defaults.
WATER_BULK_MODULUS_PA: float = 2.2e9       # Pa

STEEL_YOUNGS_MODULUS_PA: float = 200e9      # Pa  (198-210 GPa typical range)
DUCTILE_IRON_YOUNGS_MODULUS_PA: float = 169e9  # Pa
PVC_YOUNGS_MODULUS_PA: float = 3.3e9        # Pa  (3.0-4.0 GPa typical range)
HDPE_YOUNGS_MODULUS_PA: float = 1.0e9       # Pa  (0.8-1.2 GPa "instantaneous"/
                                              #      dynamic modulus, relevant
                                              #      for fast transients —
                                              #      viscoelastic plastics are
                                              #      stiffer under rapid
                                              #      loading than under
                                              #      static/creep loading)
CONCRETE_YOUNGS_MODULUS_PA: float = 23e9    # Pa

WATER_THERMAL_FIT_MIN_K: float = 273.15   # 0 degC
WATER_THERMAL_FIT_MAX_K: float = 373.15   # 100 degC
