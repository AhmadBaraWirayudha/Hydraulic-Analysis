"""Unit conversion helpers for the hydraulic analysis package."""

from .constants import PA_PER_BAR, GRAVITY, WATER_DENSITY


# ── Length / Diameter ─────────────────────────────────────────────────────────
def inch_to_m(inch: float) -> float:
    """Convert inches to metres (1 inch = 25.4 mm)."""
    return inch * 0.0254


def mm_to_m(mm: float) -> float:
    return mm / 1000.0


def m_to_mm(m: float) -> float:
    return m * 1000.0


# ── Flow rate ─────────────────────────────────────────────────────────────────
def L_per_s_to_m3_per_s(L_per_s: float) -> float:
    return L_per_s / 1_000.0


def m3_per_s_to_L_per_s(m3: float) -> float:
    return m3 * 1_000.0


def L_per_day_to_m3_per_s(L_per_day: float) -> float:
    return L_per_day / (1_000.0 * 86_400.0)


# ── Pressure / Head ───────────────────────────────────────────────────────────
def bar_to_Pa(bar: float) -> float:
    return bar * PA_PER_BAR


def Pa_to_m_head(Pa: float, density: float = WATER_DENSITY) -> float:
    """Convert pressure [Pa] to head [m H₂O]."""
    return Pa / (density * GRAVITY)


def m_head_to_Pa(head_m: float, density: float = WATER_DENSITY) -> float:
    """Convert head [m H₂O] to pressure [Pa]."""
    return head_m * density * GRAVITY


def bar_to_m_head(bar: float, density: float = WATER_DENSITY) -> float:
    return Pa_to_m_head(bar_to_Pa(bar), density)


# ── Power ─────────────────────────────────────────────────────────────────────
def W_to_kW(W: float) -> float:
    return W / 1_000.0


def kW_to_W(kW: float) -> float:
    return kW * 1_000.0
