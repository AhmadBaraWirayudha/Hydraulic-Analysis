"""
Unit tests for src/geospatial/ — PostGIS-backed node/pipe storage and the
Folium map builder.
"""

import pytest

from src.geospatial.service import (
    upsert_node, upsert_pipe, get_all_nodes, get_all_pipes,
    get_network_geometry, clear_network,
    upsert_loop_member, get_all_loops, seed_demo_network,
)
from src.geospatial.map_view import build_network_map, _pipe_velocity
from src.geospatial.models import GeoPipe


@pytest.fixture
def clean_network(clean_schema):
    """clean_schema already resets all tables, including network_nodes/pipes."""
    return None


# ── Node CRUD ───────────────────────────────────────────────────────────────
def test_upsert_node_roundtrips_coordinates_without_axis_swap(clean_network):
    """The classic PostGIS gotcha: ST_MakePoint takes (lon, lat), not
    (lat, lon) — verify our wrapper gets this right."""
    upsert_node("A", latitude=-6.9175, longitude=107.6191, label="Test node")
    nodes = get_all_nodes()
    assert len(nodes) == 1
    assert nodes[0].latitude == pytest.approx(-6.9175)
    assert nodes[0].longitude == pytest.approx(107.6191)
    assert nodes[0].label == "Test node"
    assert nodes[0].external_flow_m3s == pytest.approx(0.0)  # default


def test_upsert_node_persists_external_flow(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0, external_flow_m3s=0.015)
    nodes = get_all_nodes()
    assert nodes[0].external_flow_m3s == pytest.approx(0.015)


def test_upsert_node_external_flow_update_persists(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0, external_flow_m3s=0.010)
    upsert_node("A", latitude=0.0, longitude=0.0, external_flow_m3s=-0.005)  # update
    nodes = get_all_nodes()
    assert nodes[0].external_flow_m3s == pytest.approx(-0.005)


def test_get_external_flows_returns_dict_for_all_nodes(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0, external_flow_m3s=0.010)
    upsert_node("B", latitude=1.0, longitude=1.0, external_flow_m3s=-0.010)
    from src.geospatial.service import get_external_flows

    flows = get_external_flows()
    assert flows == {"A": pytest.approx(0.010), "B": pytest.approx(-0.010)}


def test_upsert_node_rejects_invalid_latitude(clean_network):
    with pytest.raises(ValueError, match="Latitude"):
        upsert_node("bad", latitude=200.0, longitude=0.0)


def test_upsert_node_rejects_invalid_longitude(clean_network):
    with pytest.raises(ValueError, match="Longitude"):
        upsert_node("bad", latitude=0.0, longitude=200.0)


def test_upsert_node_is_idempotent_update(clean_network):
    upsert_node("A", latitude=1.0, longitude=2.0, label="First")
    upsert_node("A", latitude=3.0, longitude=4.0, label="Updated")
    nodes = get_all_nodes()
    assert len(nodes) == 1
    assert nodes[0].latitude == pytest.approx(3.0)
    assert nodes[0].label == "Updated"


# ── Pipe CRUD ───────────────────────────────────────────────────────────────
def test_upsert_pipe_requires_existing_nodes(clean_network):
    with pytest.raises(ValueError, match="must exist as nodes"):
        upsert_pipe("p1", "ghost1", "ghost2", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)


def test_upsert_pipe_derives_geometry_from_endpoints(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0)
    upsert_node("B", latitude=1.0, longitude=1.0)
    upsert_pipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)

    pipes = get_all_pipes()
    assert len(pipes) == 1
    assert pipes[0].start_coords == pytest.approx((0.0, 0.0))
    assert pipes[0].end_coords == pytest.approx((1.0, 1.0))
    assert pipes[0].diameter_m == pytest.approx(0.1)


def test_get_network_geometry_returns_both(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0)
    upsert_node("B", latitude=1.0, longitude=1.0)
    upsert_pipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)

    nodes, pipes = get_network_geometry()
    assert len(nodes) == 2
    assert len(pipes) == 1


def test_clear_network_removes_everything(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0)
    upsert_node("B", latitude=1.0, longitude=1.0)
    upsert_pipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)
    clear_network()
    nodes, pipes = get_network_geometry()
    assert nodes == []
    assert pipes == []


# ── Loop persistence ─────────────────────────────────────────────────────────
def test_upsert_loop_member_requires_existing_pipe(clean_network):
    with pytest.raises(ValueError, match="must exist"):
        upsert_loop_member("loopA", "ghost_pipe", direction=1, sequence_order=0)


def test_upsert_loop_member_rejects_invalid_direction(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0)
    upsert_node("B", latitude=1.0, longitude=1.0)
    upsert_pipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)
    with pytest.raises(ValueError, match=r"\+1 or -1"):
        upsert_loop_member("loopA", "p1", direction=2, sequence_order=0)


def test_get_all_loops_returns_hardy_cross_compatible_objects(clean_network):
    from src.hydraulics.network import Loop

    upsert_node("A", latitude=0.0, longitude=0.0)
    upsert_node("B", latitude=1.0, longitude=1.0)
    upsert_node("C", latitude=2.0, longitude=2.0)
    upsert_pipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)
    upsert_pipe("p2", "B", "C", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)
    upsert_pipe("p3", "A", "C", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)

    upsert_loop_member("loop1", "p1", direction=1, sequence_order=0)
    upsert_loop_member("loop1", "p2", direction=1, sequence_order=1)
    upsert_loop_member("loop1", "p3", direction=-1, sequence_order=2)

    loops = get_all_loops()
    assert len(loops) == 1
    assert isinstance(loops[0], Loop)
    assert loops[0].name == "loop1"
    assert len(loops[0].members) == 3
    member_directions = {m.pipe_name: m.direction for m in loops[0].members}
    assert member_directions == {"p1": 1, "p2": 1, "p3": -1}


def test_upsert_loop_member_is_idempotent_update(clean_network):
    upsert_node("A", latitude=0.0, longitude=0.0)
    upsert_node("B", latitude=1.0, longitude=1.0)
    upsert_pipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6)
    upsert_loop_member("loop1", "p1", direction=1, sequence_order=0)
    upsert_loop_member("loop1", "p1", direction=-1, sequence_order=0)  # update direction

    loops = get_all_loops()
    assert len(loops[0].members) == 1
    assert loops[0].members[0].direction == -1


# ── seed_demo_network ─────────────────────────────────────────────────────────
def test_seed_demo_network_creates_full_topology(clean_network):
    seed_demo_network()
    nodes, pipes = get_network_geometry()
    loops = get_all_loops()
    assert len(nodes) == 4
    assert len(pipes) == 5
    assert len(loops) == 2


def test_seed_demo_network_persists_external_flows_that_balance(clean_network):
    from src.geospatial.service import get_external_flows

    seed_demo_network()
    flows = get_external_flows()
    assert flows["1"] == pytest.approx(0.010)
    assert flows["4"] == pytest.approx(-0.010)
    assert flows["2"] == pytest.approx(0.0)
    assert flows["3"] == pytest.approx(0.0)
    assert sum(flows.values()) == pytest.approx(0.0)  # mass must balance


def test_seed_demo_network_solvable_via_generic_spanning_tree_solver(clean_network):
    """End-to-end with NO hardcoded pipe names anywhere: external flows
    come from the database, the initial guess comes from the generic
    spanning-tree solver, and the result still converges — this is
    exactly what the Network Map page now does."""
    from src.hydraulics.network import compute_initial_flows_spanning_tree, PipeNetwork, NetworkPipe
    from src.geospatial.service import get_external_flows
    from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY

    seed_demo_network()
    nodes, pipes = get_network_geometry()
    loops = get_all_loops()
    external_flows = get_external_flows()

    network_pipes = [
        NetworkPipe(p.name, p.start_node, p.end_node, p.diameter_m, p.length_m, p.roughness_m)
        for p in pipes
    ]
    initial_flows = compute_initial_flows_spanning_tree(network_pipes, external_flows)
    network = PipeNetwork(network_pipes, loops, density=WATER_DENSITY, viscosity=WATER_VISCOSITY)
    solution = network.solve(initial_flows)

    assert solution.converged


def test_seed_demo_network_is_solvable(clean_network):
    """End-to-end: the seeded demo network should actually solve via
    Hardy Cross without errors, using the persisted loop topology."""
    from src.hydraulics.network import PipeNetwork, NetworkPipe
    from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY

    seed_demo_network()
    nodes, pipes = get_network_geometry()
    loops = get_all_loops()

    network_pipes = [
        NetworkPipe(p.name, p.start_node, p.end_node, p.diameter_m, p.length_m, p.roughness_m)
        for p in pipes
    ]
    network = PipeNetwork(network_pipes, loops, density=WATER_DENSITY, viscosity=WATER_VISCOSITY)
    solution = network.solve({"12": 0.006, "13": 0.004, "23": 0.0, "24": 0.006, "34": 0.004})
    assert solution.converged


def test_seed_demo_network_is_idempotent(clean_network):
    seed_demo_network()
    seed_demo_network()  # should not raise or duplicate
    nodes, pipes = get_network_geometry()
    assert len(nodes) == 4
    assert len(pipes) == 5


# ── Map building (no DB needed — operates on in-memory model objects) ─────
def test_pipe_velocity_known_value():
    pipe = GeoPipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6,
                    start_coords=(0, 0), end_coords=(1, 1))
    # A = pi*0.1^2/4 = 0.007854; v = Q/A
    v = _pipe_velocity(pipe, flow_m3s=0.0007854)
    assert v == pytest.approx(0.1, rel=1e-3)


def test_pipe_velocity_none_when_no_flow_data():
    pipe = GeoPipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6,
                    start_coords=(0, 0), end_coords=(1, 1))
    assert _pipe_velocity(pipe, flow_m3s=None) is None


def test_pipe_velocity_sign_independent():
    pipe = GeoPipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6,
                    start_coords=(0, 0), end_coords=(1, 1))
    v_pos = _pipe_velocity(pipe, flow_m3s=0.001)
    v_neg = _pipe_velocity(pipe, flow_m3s=-0.001)
    assert v_pos == pytest.approx(v_neg)


def test_build_network_map_creates_valid_map_object():
    from src.geospatial.models import GeoNode

    nodes = [
        GeoNode("A", latitude=0.0, longitude=0.0, label="Source"),
        GeoNode("B", latitude=1.0, longitude=1.0, label="Demand"),
    ]
    pipes = [
        GeoPipe("p1", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6,
                start_coords=(0.0, 0.0), end_coords=(1.0, 1.0)),
    ]
    fmap = build_network_map(nodes, pipes, flows={"p1": 0.0005})
    html = fmap._repr_html_()
    assert "leaflet" in html.lower() or len(html) > 100  # sanity: produced real map content


def test_build_network_map_works_without_flow_data():
    from src.geospatial.models import GeoNode

    nodes = [GeoNode("A", 0.0, 0.0), GeoNode("B", 1.0, 1.0)]
    pipes = [GeoPipe("p1", "A", "B", 0.1, 100, 1.5e-6, (0.0, 0.0), (1.0, 1.0))]
    fmap = build_network_map(nodes, pipes, flows=None)
    assert fmap is not None


def test_build_network_map_rejects_empty_nodes():
    with pytest.raises(ValueError, match="at least one node"):
        build_network_map([], [], flows=None)
