"""
Geospatial network models — physical (lat/lon) representation of the
pipe network, layered on top of the existing Hardy Cross
``hydraulics.network`` topology (which is purely topological — node
names and pipe connections, no real-world coordinates).
"""

from dataclasses import dataclass


@dataclass
class GeoNode:
    """A network node with a real-world position."""

    name: str
    latitude: float
    longitude: float
    label: str | None = None


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
