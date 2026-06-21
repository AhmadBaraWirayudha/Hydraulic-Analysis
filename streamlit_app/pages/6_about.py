"""
Streamlit page: about / methodology / references.
"""

import streamlit as st

st.set_page_config(page_title="About — Hydraulic Simulator", page_icon="ℹ️", layout="wide")
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
