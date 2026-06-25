"""
Streamlit page: about / methodology / references.
"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "streamlit_app"))

from auth_helpers import require_login, render_user_badge

st.set_page_config(page_title="About — Hydraulic Simulator", page_icon="ℹ️", layout="wide")

user = require_login()
render_user_badge(user)

st.title("ℹ️ About This Tool")

st.markdown(
    """
## Background

This tool reimplements, as a structured and reusable engineering package,
the pipe-diameter evaluation originally carried out for the **Citra Srie
Pradita** housing estate water distribution network (½″ vs 4″ PVC pipe
comparison).

## Method

- **Darcy–Weisbach equation** for major (friction) head loss
- **Swamee–Jain (1976)** explicit approximation for the turbulent friction
  factor (avoids iterative Colebrook–White solving)
- **K-factor method** for minor (fitting/valve) losses
- **Gouy–Stodola theorem** for exergy destruction due to frictional
  irreversibility, contextualizing head loss as lost work potential rather
  than just "lost pressure"

## Lean / Poka-Yoke Integration

- All inputs pass through `src/utils/validation.py` before any calculation
  runs — implausible values (negative flow, oversized diameter, roughness
  exceeding diameter, etc.) are rejected with a clear message.
- Velocities outside the **SNI 03-6481-2000** recommended range
  (0.9–2.0 m/s) trigger a warning, flagging risk of sedimentation (too
  slow) or water hammer / excess wear (too fast).
- The Energy Flow (Sankey) view on the Results page frames frictional
  exergy destruction as **Muda** (waste) in the Lean sense.

## Governance & Geospatial

- **Role-based access control**: Field Technicians have view-only access
  to every dashboard; Lead Engineers can additionally run ad-hoc
  scenarios (Input page) and edit the YAML configuration (Config Editor
  page) that drives the entire pipeline.
- **Audit logging**: every scenario run and configuration edit is
  recorded — who, when, and exactly what changed — viewable on the Audit
  Log page (Lead Engineer only).
- **Geospatial network view**: the Network Map page plots the pipe
  network's real physical layout (PostGIS-backed), color-coded by
  velocity against the SNI 03-6481-2000 recommended range — the same
  Mura (unevenness) lens as the Lean Dashboard, applied spatially.

## References

- Swamee, P.K. & Jain, A.K. (1976). *Explicit equations for pipe flow
  problems.* Journal of the Hydraulics Division, ASCE, 102(5), 657–664.
- Bejan, A. (2016). *Advanced Engineering Thermodynamics.* Wiley.
  (Gouy–Stodola theorem)
- SNI 03-6481-2000 — *Sistem Plambing 2000* / water distribution velocity
  criteria.
- SNI 03-7065-2005 — *Tata cara perencanaan sistem plambing.*

## Source Code

This Streamlit app is part of the `hydraulic-analysis` Python package.
See the project `README.md` for installation and usage instructions, and
`docs/design.md` for the full architecture write-up.
"""
)
