"""
Folium map visualization of the physical pipe network — ties the
geospatial node/pipe geometry (``geospatial.service``) to the Hardy Cross
hydraulic solution (``hydraulics.network``), so the abstract topology
gets a physical, on-the-ground view.
"""

import branca.colormap as cm
import folium

from .models import GeoNode, GeoPipe
from ..hydraulics.friction import pipe_area
from ..utils.constants import SNI_VELOCITY_MIN, SNI_VELOCITY_MAX


def _pipe_velocity(pipe: GeoPipe, flow_m3s: float | None) -> float | None:
    """Mean velocity in a pipe given its (signed) flow, or None if no
    flow data is available for it."""
    if flow_m3s is None:
        return None
    return abs(flow_m3s) / pipe_area(pipe.diameter_m)


def build_network_map(
    nodes: list[GeoNode],
    pipes: list[GeoPipe],
    flows: dict[str, float] | None = None,
    zoom_start: int = 16,
) -> folium.Map:
    """Build an interactive Folium map of the pipe network.

    Parameters
    ----------
    nodes      : list[GeoNode]
    pipes      : list[GeoPipe]
    flows      : dict[str, float] | None
                  pipe name -> signed flow [m³/s], e.g. from
                  ``hydraulics.network.NetworkSolution.flows``. If
                  supplied, pipes are colored by velocity relative to the
                  SNI 03-6481-2000 recommended range (green = within
                  range, red = over, blue = under) — the same convention
                  as this project's Mura utilization heatmap. If None,
                  pipes are drawn in a neutral color with no velocity data.
    zoom_start : int  initial map zoom level

    Returns
    -------
    folium.Map
    """
    if not nodes:
        raise ValueError("Need at least one node to center the map.")

    center_lat = sum(n.latitude for n in nodes) / len(nodes)
    center_lon = sum(n.longitude for n in nodes) / len(nodes)
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start, tiles="OpenStreetMap")

    colormap = cm.LinearColormap(
        colors=["#2166ac", "#67a9cf", "#2ca02c", "#fddbc7", "#b2182b"],
        vmin=0.0, vmax=SNI_VELOCITY_MAX * 1.5,
        index=[0, SNI_VELOCITY_MIN * 0.5, (SNI_VELOCITY_MIN + SNI_VELOCITY_MAX) / 2,
               SNI_VELOCITY_MAX, SNI_VELOCITY_MAX * 1.5],
    )

    for pipe in pipes:
        flow = flows.get(pipe.name) if flows else None
        velocity = _pipe_velocity(pipe, flow)

        if velocity is not None:
            color = colormap(velocity)
            tooltip = (
                f"<b>Pipe {pipe.name}</b><br>"
                f"Diameter: {pipe.diameter_m*1000:.1f} mm<br>"
                f"Length: {pipe.length_m:.1f} m<br>"
                f"Flow: {flow*1000:.3f} L/s<br>"
                f"Velocity: {velocity:.3f} m/s"
            )
        else:
            color = "#777777"
            tooltip = (
                f"<b>Pipe {pipe.name}</b><br>"
                f"Diameter: {pipe.diameter_m*1000:.1f} mm<br>"
                f"Length: {pipe.length_m:.1f} m<br>"
                f"(no flow solution loaded)"
            )

        folium.PolyLine(
            locations=[pipe.start_coords, pipe.end_coords],
            color=color, weight=5, opacity=0.85, tooltip=tooltip,
        ).add_to(fmap)

    for node in nodes:
        folium.CircleMarker(
            location=[node.latitude, node.longitude],
            radius=6, color="#1a3c5e", fill=True, fill_color="#1a3c5e", fill_opacity=0.9,
            tooltip=f"<b>{node.label or node.name}</b><br>Node: {node.name}",
        ).add_to(fmap)

    if flows:
        colormap.caption = "Velocity (m/s) — green band is the SNI 03-6481-2000 recommended range"
        colormap.add_to(fmap)

    return fmap
