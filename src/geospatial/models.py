"""
Geospatial network models — physical (lat/lon) representation of the
pipe network, layered on top of the existing Hardy Cross
``hydraulics.network`` topology (which is purely topological — node
names and pipe connections, no real-world coordinates).
"""

from dataclasses import dataclass


@dataclass
class GeoNode:
    """A network node with a real-world position.

    ``external_flow_m3s`` is the net external supply (+) or demand (-)
    at this node [m³/s] — e.g. a source reservoir's inflow, or a demand
    point's draw. Defaults to 0.0 (a pure junction, neither supplying nor
    demanding). Feeds directly into
    ``hydraulics.network.compute_initial_flows_spanning_tree`` to
    automatically construct a valid Hardy Cross starting flow for
    whatever topology is actually stored — see the Network Map page.
    """

    name: str
    latitude: float
    longitude: float
    label: str | None = None
    external_flow_m3s: float = 0.0


@dataclass
class GeoPipe:
    """A network pipe with its physical geometry (the straight-line path
    between its two endpoint nodes — sufficient for visualization; real
    pipe routing along streets/easements would need a richer geometry,
    out of scope here)."""

    name: str
    start_node: str
    end_node: str
    diameter_m: float
    length_m: float
    roughness_m: float
    start_coords: tuple[float, float]   # (lat, lon)
    end_coords: tuple[float, float]     # (lat, lon)
