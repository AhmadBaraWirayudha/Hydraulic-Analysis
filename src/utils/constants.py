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
