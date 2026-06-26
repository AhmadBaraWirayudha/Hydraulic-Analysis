"""
Geospatial service: stores and retrieves the pipe network's physical
(lat/lon) geometry in PostGIS, and ties it to the existing
``hydraulics.network`` Hardy Cross topology for map visualization.

PostGIS convention: ``ST_MakePoint(x, y)`` takes (longitude, latitude)
order — easy to get backwards. All functions here take/return
(latitude, longitude) in the conventional order and handle the
longitude-first conversion internally.
"""


from ..db import get_connection
from .models import GeoNode, GeoPipe


def upsert_node(
    name: str,
    latitude: float,
    longitude: float,
    label: str | None = None,
    external_flow_m3s: float = 0.0,
) -> None:
    """Insert or update a network node's position and external flow.

    Parameters
    ----------
    name      : str    unique node identifier (matches the Hardy Cross
                 network's node naming, e.g. "1", "2", "reservoir")
    latitude  : float  in [-90, 90]
    longitude : float  in [-180, 180]
    label     : str | None  human-readable display name
    external_flow_m3s : float
                 net external supply (+) or demand (-) at this node
                 [m³/s]; 0.0 (default) for a pure junction. Feeds
                 ``hydraulics.network.compute_initial_flows_spanning_tree``
                 so the Network Map page can solve any stored topology
                 automatically, not just one hardcoded shape.
    """
    if not (-90 <= latitude <= 90):
        raise ValueError(f"Latitude must be in [-90, 90]. Got {latitude}.")
    if not (-180 <= longitude <= 180):
        raise ValueError(f"Longitude must be in [-180, 180]. Got {longitude}.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO network_nodes (name, label, external_flow_m3s, geom)
                VALUES (%s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                ON CONFLICT (name) DO UPDATE
                    SET label = EXCLUDED.label,
                        external_flow_m3s = EXCLUDED.external_flow_m3s,
                        geom = EXCLUDED.geom
                """,
                (name, label, external_flow_m3s, longitude, latitude),
            )


def upsert_pipe(
    name: str,
    start_node: str,
    end_node: str,
    diameter_m: float,
    length_m: float,
    roughness_m: float,
) -> None:
    """Insert or update a pipe, automatically deriving its line geometry
    from its two endpoint nodes (both must already exist via
    ``upsert_node``).

    Parameters
    ----------
    name        : str    unique pipe identifier (matches the Hardy Cross
                   network's pipe naming)
    start_node, end_node : str  must reference existing node names
    diameter_m, length_m, roughness_m : float  pipe properties
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM network_nodes WHERE name IN (%s, %s)", (start_node, end_node))
            if len(cur.fetchall()) < 2:
                raise ValueError(
                    f"Both '{start_node}' and '{end_node}' must exist as nodes before "
                    f"creating pipe '{name}'."
                )
            cur.execute(
                """
                INSERT INTO network_pipes
                    (name, start_node, end_node, diameter_m, length_m, roughness_m, geom)
                SELECT %s, %s, %s, %s, %s, %s,
                       ST_MakeLine(n1.geom, n2.geom)
                FROM network_nodes n1, network_nodes n2
                WHERE n1.name = %s AND n2.name = %s
                ON CONFLICT (name) DO UPDATE
                    SET diameter_m = EXCLUDED.diameter_m,
                        length_m = EXCLUDED.length_m,
                        roughness_m = EXCLUDED.roughness_m,
                        geom = EXCLUDED.geom
                """,
                (name, start_node, end_node, diameter_m, length_m, roughness_m, start_node, end_node),
            )


def get_all_nodes() -> list[GeoNode]:
    """Return every stored network node."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name, label, ST_Y(geom), ST_X(geom), external_flow_m3s "
                "FROM network_nodes ORDER BY name"
            )
            rows = cur.fetchall()
    return [
        GeoNode(name=r[0], label=r[1], latitude=r[2], longitude=r[3], external_flow_m3s=r[4])
        for r in rows
    ]


def get_all_pipes() -> list[GeoPipe]:
    """Return every stored network pipe, with both endpoints' coordinates."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.name, p.start_node, p.end_node, p.diameter_m, p.length_m, p.roughness_m,
                       ST_Y(n1.geom), ST_X(n1.geom), ST_Y(n2.geom), ST_X(n2.geom)
                FROM network_pipes p
                JOIN network_nodes n1 ON p.start_node = n1.name
                JOIN network_nodes n2 ON p.end_node = n2.name
                ORDER BY p.name
                """
            )
            rows = cur.fetchall()
    return [
        GeoPipe(
            name=r[0], start_node=r[1], end_node=r[2],
            diameter_m=r[3], length_m=r[4], roughness_m=r[5],
            start_coords=(r[6], r[7]), end_coords=(r[8], r[9]),
        )
        for r in rows
    ]


def upsert_loop_member(loop_name: str, pipe_name: str, direction: int, sequence_order: int) -> None:
    """Add (or update) one pipe's membership in a named loop.

    Parameters
    ----------
    loop_name      : str   identifies the loop (multiple pipes share this)
    pipe_name      : str   must reference an existing pipe
    direction      : int   +1 or -1 — see ``hydraulics.network.LoopMember``
    sequence_order : int   traversal order within the loop (for display/
                            debugging only; the solver doesn't need a
                            particular order, just complete membership)
    """
    if direction not in (1, -1):
        raise ValueError(f"direction must be +1 or -1. Got {direction}.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM network_pipes WHERE name = %s", (pipe_name,))
            if cur.fetchone() is None:
                raise ValueError(f"Pipe '{pipe_name}' must exist before adding it to a loop.")
            cur.execute(
                """
                INSERT INTO network_loops (loop_name, pipe_name, direction, sequence_order)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (loop_name, pipe_name) DO UPDATE
                    SET direction = EXCLUDED.direction, sequence_order = EXCLUDED.sequence_order
                """,
                (loop_name, pipe_name, direction, sequence_order),
            )


def get_all_loops() -> list:
    """Return every stored loop as ``hydraulics.network.Loop`` objects,
    ready to pass straight into ``hydraulics.network.hardy_cross_solve``
    or ``PipeNetwork.solve``.

    Returns
    -------
    list[hydraulics.network.Loop]
    """
    from ..hydraulics.network import Loop, LoopMember

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT loop_name, pipe_name, direction FROM network_loops "
                "ORDER BY loop_name, sequence_order"
            )
            rows = cur.fetchall()

    loops: dict[str, list] = {}
    for loop_name, pipe_name, direction in rows:
        loops.setdefault(loop_name, []).append(LoopMember(pipe_name, direction))
    return [Loop(name=name, members=members) for name, members in loops.items()]


def get_external_flows() -> dict[str, float]:
    """Convenience: return {node_name: external_flow_m3s} for every
    stored node, ready to pass directly to
    ``hydraulics.network.compute_initial_flows_spanning_tree``."""
    return {n.name: n.external_flow_m3s for n in get_all_nodes()}


def get_network_geometry() -> tuple[list[GeoNode], list[GeoPipe]]:
    """Convenience: fetch both nodes and pipes in one call."""
    return get_all_nodes(), get_all_pipes()


def clear_network() -> None:
    """Delete all stored nodes, pipes, and loops. Used by tests and
    re-seeding — NEVER call against a production database with real
    network data."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM network_loops")
            cur.execute("DELETE FROM network_pipes")
            cur.execute("DELETE FROM network_nodes")


def seed_demo_network() -> None:
    """Set up the demo 4-node, 2-loop network used throughout this
    project's network-analysis examples (notebooks/network_and_transients.ipynb,
    tests/test_network.py) — but with real geographic coordinates (a
    plausible residential layout near Bandung, Indonesia, matching the
    Citra Srie Pradita context the rest of this project references) and
    persisted external flows, so it can be solved automatically by
    ``hydraulics.network.compute_initial_flows_spanning_tree`` without any
    page-level hardcoding of which nodes are sources/demands.

    Safe to call repeatedly — clears any existing network data first.
    """
    clear_network()

    upsert_node("1", latitude=-6.9175, longitude=107.6191, label="Source reservoir",
                external_flow_m3s=0.010)   # 10 L/s supply
    upsert_node("2", latitude=-6.9180, longitude=107.6200, label="Junction A")
    upsert_node("3", latitude=-6.9185, longitude=107.6195, label="Junction B")
    upsert_node("4", latitude=-6.9190, longitude=107.6205, label="Demand point",
                external_flow_m3s=-0.010)  # 10 L/s demand

    upsert_pipe("12", "1", "2", diameter_m=0.10, length_m=200.0, roughness_m=1.5e-6)
    upsert_pipe("13", "1", "3", diameter_m=0.075, length_m=250.0, roughness_m=1.5e-6)
    upsert_pipe("23", "2", "3", diameter_m=0.05, length_m=150.0, roughness_m=1.5e-6)
    upsert_pipe("24", "2", "4", diameter_m=0.075, length_m=200.0, roughness_m=1.5e-6)
    upsert_pipe("34", "3", "4", diameter_m=0.10, length_m=200.0, roughness_m=1.5e-6)

    upsert_loop_member("123", "12", direction=1, sequence_order=0)
    upsert_loop_member("123", "23", direction=1, sequence_order=1)
    upsert_loop_member("123", "13", direction=-1, sequence_order=2)

    upsert_loop_member("234", "23", direction=-1, sequence_order=0)
    upsert_loop_member("234", "24", direction=1, sequence_order=1)
    upsert_loop_member("234", "34", direction=-1, sequence_order=2)
