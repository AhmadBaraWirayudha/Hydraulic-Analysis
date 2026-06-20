"""
Sankey diagram of energy flow through the pump-pipeline system: shaft power
input → useful hydraulic work + losses (motor loss, pump loss, friction
exergy destroyed). Used by the Streamlit dashboard's "Lean" energy view.
"""

import plotly.graph_objects as go


def energy_flow_sankey(scenario_result) -> go.Figure:
    """Build a Sankey diagram of where shaft power input ends up.

    Energy balance (all in Watts):

        Shaft Power
          ├─→ Motor Losses        = P_shaft (1 − η_motor)
          ├─→ Pump Losses         = P_shaft · η_motor (1 − η_pump)
          └─→ Hydraulic Power     = P_shaft · η_motor · η_pump
                ├─→ Exergy Destroyed (friction irreversibility)
                └─→ Useful Work Delivered (static lift / delivery head)

    Note: if ``scenario.static_head_m == 0`` (the default — a pure
    friction-loss analysis with no elevation gain or delivery-pressure
    requirement), "Useful Work Delivered" will correctly show as zero:
    in that case the pump's entire hydraulic output exists only to
    overcome friction, so all of it is destroyed exergy.

    Parameters
    ----------
    scenario_result : simulation.scenario.ScenarioResult

    Returns
    -------
    plotly.graph_objects.Figure
    """
    pump = scenario_result.pump
    exergy = scenario_result.exergy
    s = scenario_result.scenario

    p_shaft = pump.shaft_power_W
    p_hydraulic = pump.hydraulic_power_W
    motor_loss = p_shaft * (1 - s.eta_motor)
    pump_loss = (p_shaft - motor_loss) * (1 - s.eta_pump)
    x_destroyed = exergy.exergy_destruction_W
    useful_remaining = max(p_hydraulic - x_destroyed, 0.0)

    labels = [
        "Shaft Power",          # 0
        "Motor Losses",         # 1
        "Pump Losses",          # 2
        "Hydraulic Power",      # 3
        "Exergy Destroyed\n(Friction)",  # 4
        "Useful Work Delivered\n(Static Lift)",  # 5
    ]

    # Source/target indices and values for each flow segment.
    sources = [0, 0, 0, 3, 3]
    targets = [1, 2, 3, 4, 5]
    values = [motor_loss, pump_loss, p_hydraulic, x_destroyed, useful_remaining]

    node_colors = ["#1f77b4", "#d62728", "#ff7f0e", "#2ca02c", "#d62728", "#17becf"]
    link_colors = [
        "rgba(214,39,40,0.4)",   # motor losses
        "rgba(255,127,14,0.4)",  # pump losses
        "rgba(44,160,44,0.4)",   # hydraulic power
        "rgba(214,39,40,0.4)",   # exergy destroyed
        "rgba(23,190,207,0.4)",  # useful work
    ]

    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    label=labels,
                    color=node_colors,
                    pad=20,
                    thickness=18,
                ),
                link=dict(
                    source=sources,
                    target=targets,
                    value=values,
                    color=link_colors,
                ),
            )
        ]
    )
    fig.update_layout(
        title=f"Energy Flow — {s.label or 'Pipeline Scenario'}",
        font_size=12,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig
