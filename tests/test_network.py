"""
Unit tests for src/hydraulics/network.py — Hardy Cross loop-balancing
method for closed-loop pipe networks.

The primary correctness test (``test_hardy_cross_matches_wikipedia_worked_example``)
reproduces a published worked example exactly (Wikipedia: Hardy Cross
method), including matching its stated intermediate result after exactly
one iteration — this is a much stronger check than self-consistency alone
(e.g. checking that head losses balance at convergence), since it
verifies the algorithm against an independently-derived, known-correct
numeric trace, including the simultaneous (not sequential) loop-update
convention the standard method uses.
"""

import pytest

from src.hydraulics.network import (
    hardy_cross_solve, Loop, LoopMember, NetworkSolution,
    PipeNetwork, NetworkPipe, compute_initial_flows_spanning_tree,
)
from src.utils.constants import WATER_DENSITY, WATER_VISCOSITY, PVC_ROUGHNESS


# ── Gold-standard verification against the published worked example ────────
@pytest.fixture
def wikipedia_network():
    """Wikipedia's Hardy Cross worked example: 4 nodes, 5 pipes, 2 loops,
    abstract head-loss law h = r*Q^2 (not real Darcy-Weisbach — this
    example is specifically designed to test the loop-balancing algorithm
    itself, independent of any particular physical head-loss formula)."""
    r = {"12": 1, "13": 5, "23": 1, "24": 5, "34": 1}

    def head_loss_fn(name, Q):
        return r[name] * Q ** 2

    initial_flows = {"12": 5.0, "13": 5.0, "23": 0.0, "24": 5.0, "34": 5.0}
    loop123 = Loop("123", [LoopMember("12", +1), LoopMember("23", +1), LoopMember("13", -1)])
    loop234 = Loop("234", [LoopMember("23", -1), LoopMember("24", +1), LoopMember("34", -1)])

    return dict(
        pipe_names=["12", "13", "23", "24", "34"],
        loops=[loop123, loop234],
        head_loss_fn=head_loss_fn,
        initial_flows=initial_flows,
    )


def test_hardy_cross_matches_wikipedia_worked_example_after_one_iteration(wikipedia_network):
    """The published example states the network is exactly solved after a
    single iteration: Q12=6.66, Q13=3.33, Q23=3.33, Q24=3.33, Q34=6.66
    (all in the example's units, L/s)."""
    result = hardy_cross_solve(
        **wikipedia_network, n=2.0, max_iterations=1, tolerance=1e-12,
    )
    assert result.flows["12"] == pytest.approx(6.6667, abs=1e-3)
    assert result.flows["13"] == pytest.approx(3.3333, abs=1e-3)
    assert result.flows["23"] == pytest.approx(3.3333, abs=1e-3)
    assert result.flows["24"] == pytest.approx(3.3333, abs=1e-3)
    assert result.flows["34"] == pytest.approx(6.6667, abs=1e-3)


def test_hardy_cross_wikipedia_example_converges_immediately(wikipedia_network):
    """The article notes this particular example is exactly balanced after
    one iteration — a second iteration should produce a negligible
    correction (already converged)."""
    result = hardy_cross_solve(
        **wikipedia_network, n=2.0, max_iterations=10, tolerance=1e-9,
    )
    assert result.converged is True
    assert result.iterations <= 2


def test_hardy_cross_wikipedia_example_satisfies_continuity_throughout(wikipedia_network):
    """Node continuity (built into the initial guess) must be preserved by
    every Hardy Cross correction — loop corrections add/subtract the same
    delta_q to both pipes meeting at a node within a loop, by construction."""
    result = hardy_cross_solve(**wikipedia_network, n=2.0, max_iterations=10, tolerance=1e-9)
    flows = result.flows
    # Node 1: external +10, outflow Q12+Q13
    assert (flows["12"] + flows["13"]) == pytest.approx(10.0, abs=1e-3)
    # Node 2: inflow Q12, outflow Q23+Q24
    assert flows["12"] == pytest.approx(flows["23"] + flows["24"], abs=1e-3)
    # Node 3: inflow Q13+Q23, outflow Q34
    assert (flows["13"] + flows["23"]) == pytest.approx(flows["34"], abs=1e-3)
    # Node 4: inflow Q24+Q34, external -10
    assert (flows["24"] + flows["34"]) == pytest.approx(10.0, abs=1e-3)


def test_hardy_cross_wikipedia_example_loops_balance_at_convergence(wikipedia_network):
    """At convergence, each loop's net (signed) head loss should be ~0 —
    the energy-conservation criterion the method is solving for."""
    result = hardy_cross_solve(**wikipedia_network, n=2.0, max_iterations=10, tolerance=1e-9)
    r = {"12": 1, "13": 5, "23": 1, "24": 5, "34": 1}

    def signed_hf(name, direction):
        Q = result.flows[name]
        sign = 1.0 if Q >= 0 else -1.0
        return direction * sign * r[name] * Q ** 2

    loop123_balance = signed_hf("12", +1) + signed_hf("23", +1) + signed_hf("13", -1)
    loop234_balance = signed_hf("23", -1) + signed_hf("24", +1) + signed_hf("34", -1)
    assert loop123_balance == pytest.approx(0.0, abs=1e-3)
    assert loop234_balance == pytest.approx(0.0, abs=1e-3)


# ── Input validation (Poka-Yoke) ───────────────────────────────────────────
def test_hardy_cross_rejects_missing_initial_flow(wikipedia_network):
    incomplete = dict(wikipedia_network)
    incomplete["initial_flows"] = {k: v for k, v in wikipedia_network["initial_flows"].items()
                                     if k != "34"}
    with pytest.raises(ValueError, match="missing pipes"):
        hardy_cross_solve(**incomplete)


def test_hardy_cross_rejects_loop_with_no_members(wikipedia_network):
    bad = dict(wikipedia_network)
    bad["loops"] = [Loop("empty", [])]
    with pytest.raises(ValueError, match="no members"):
        hardy_cross_solve(**bad)


def test_hardy_cross_rejects_unknown_pipe_in_loop(wikipedia_network):
    bad = dict(wikipedia_network)
    bad["loops"] = [Loop("bad", [LoopMember("nonexistent", +1)])]
    with pytest.raises(ValueError, match="unknown pipe"):
        hardy_cross_solve(**bad)


def test_hardy_cross_rejects_invalid_direction(wikipedia_network):
    bad = dict(wikipedia_network)
    bad["loops"] = [Loop("bad", [LoopMember("12", 2)])]
    with pytest.raises(ValueError, match=r"\+1 or -1"):
        hardy_cross_solve(**bad)


# ── PipeNetwork (Darcy-Weisbach wrapper) ────────────────────────────────────
@pytest.fixture
def simple_real_network():
    """A small, physically realistic 2-loop network using real pipe
    geometry, to sanity-check the Darcy-Weisbach wrapper end-to-end."""
    pipes = [
        NetworkPipe("12", "1", "2", diameter_m=0.1, length_m=100.0, roughness_m=PVC_ROUGHNESS),
        NetworkPipe("13", "1", "3", diameter_m=0.05, length_m=100.0, roughness_m=PVC_ROUGHNESS),
        NetworkPipe("23", "2", "3", diameter_m=0.05, length_m=50.0, roughness_m=PVC_ROUGHNESS),
        NetworkPipe("24", "2", "4", diameter_m=0.05, length_m=100.0, roughness_m=PVC_ROUGHNESS),
        NetworkPipe("34", "3", "4", diameter_m=0.1, length_m=100.0, roughness_m=PVC_ROUGHNESS),
    ]
    loop123 = Loop("123", [LoopMember("12", +1), LoopMember("23", +1), LoopMember("13", -1)])
    loop234 = Loop("234", [LoopMember("23", -1), LoopMember("24", +1), LoopMember("34", -1)])
    return PipeNetwork(pipes, [loop123, loop234], density=WATER_DENSITY, viscosity=WATER_VISCOSITY)


def test_pipe_network_solve_converges(simple_real_network):
    initial_flows = {"12": 0.005, "13": 0.005, "23": 0.0, "24": 0.005, "34": 0.005}
    result = simple_real_network.solve(initial_flows)
    assert isinstance(result, NetworkSolution)
    assert result.converged is True


def test_pipe_network_solve_preserves_continuity(simple_real_network):
    initial_flows = {"12": 0.005, "13": 0.005, "23": 0.0, "24": 0.005, "34": 0.005}
    result = simple_real_network.solve(initial_flows)
    external = {"1": 0.01, "4": -0.01}
    residuals = simple_real_network.check_node_continuity(result.flows, external)
    for node, residual in residuals.items():
        assert abs(residual) < 1e-6, f"Node {node} continuity violated: {residual}"


def test_pipe_network_rejects_duplicate_pipe_names():
    pipes = [
        NetworkPipe("12", "1", "2", 0.1, 100.0, PVC_ROUGHNESS),
        NetworkPipe("12", "1", "3", 0.1, 100.0, PVC_ROUGHNESS),  # duplicate name
    ]
    with pytest.raises(ValueError, match="unique"):
        PipeNetwork(pipes, [], density=WATER_DENSITY, viscosity=WATER_VISCOSITY)


def test_check_node_continuity_flags_imbalanced_flows(simple_real_network):
    """A flow assignment that does NOT satisfy continuity should be caught
    by check_node_continuity before the user wastes time solving it."""
    bad_flows = {"12": 0.005, "13": 0.005, "23": 0.0, "24": 0.003, "34": 0.005}  # node 2 imbalanced
    external = {"1": 0.01, "4": -0.01}
    residuals = simple_real_network.check_node_continuity(bad_flows, external)
    assert abs(residuals["2"]) > 1e-6  # should be flagged as imbalanced


def test_check_node_continuity_passes_for_valid_flows(simple_real_network):
    good_flows = {"12": 0.005, "13": 0.005, "23": 0.0, "24": 0.005, "34": 0.005}
    external = {"1": 0.01, "4": -0.01}
    residuals = simple_real_network.check_node_continuity(good_flows, external)
    for residual in residuals.values():
        assert abs(residual) < 1e-9


def test_pipe_network_solve_rejects_incomplete_initial_flows(simple_real_network):
    incomplete = {"12": 0.005, "13": 0.005, "23": 0.0, "24": 0.005}  # missing '34'
    with pytest.raises(ValueError, match="missing pipes"):
        simple_real_network.solve(incomplete)


# ── compute_initial_flows_spanning_tree ─────────────────────────────────────
def test_spanning_tree_simple_two_node():
    pipes = [NetworkPipe("AB", "A", "B", 0.1, 100, 1.5e-6)]
    flows = compute_initial_flows_spanning_tree(pipes, {"A": 10.0, "B": -10.0})
    assert flows == {"AB": pytest.approx(10.0)}


def test_spanning_tree_reversed_pipe_direction():
    """Same physical flow, but the pipe is defined in the opposite
    direction — the result's sign should flip accordingly."""
    pipes = [NetworkPipe("BA", "B", "A", 0.1, 100, 1.5e-6)]
    flows = compute_initial_flows_spanning_tree(pipes, {"A": 10.0, "B": -10.0})
    assert flows == {"BA": pytest.approx(-10.0)}


def test_spanning_tree_pure_tree_star_topology():
    """No loops at all (a pure tree) — fully determined by continuity,
    each leg should carry exactly its leaf's demand."""
    pipes = [
        NetworkPipe("center_a", "center", "a", 0.1, 50, 1.5e-6),
        NetworkPipe("center_b", "center", "b", 0.1, 50, 1.5e-6),
        NetworkPipe("center_c", "center", "c", 0.1, 50, 1.5e-6),
    ]
    flows = compute_initial_flows_spanning_tree(
        pipes, {"center": 0.030, "a": -0.010, "b": -0.010, "c": -0.010}
    )
    assert flows["center_a"] == pytest.approx(0.010)
    assert flows["center_b"] == pytest.approx(0.010)
    assert flows["center_c"] == pytest.approx(0.010)


def test_spanning_tree_parallel_pipes_one_becomes_chord():
    """Two pipes directly connecting the same pair of nodes form one
    independent loop — exactly one of them must become a zero-flow chord."""
    pipes = [
        NetworkPipe("AB_1", "A", "B", 0.1, 100, 1.5e-6),
        NetworkPipe("AB_2", "A", "B", 0.08, 100, 1.5e-6),
    ]
    flows = compute_initial_flows_spanning_tree(pipes, {"A": 10.0, "B": -10.0})
    nonzero = [v for v in flows.values() if abs(v) > 1e-9]
    zero = [v for v in flows.values() if abs(v) <= 1e-9]
    assert len(nonzero) == 1
    assert len(zero) == 1
    assert nonzero[0] == pytest.approx(10.0)


def test_spanning_tree_satisfies_continuity_exactly_on_demo_network():
    pipes = [
        NetworkPipe("12", "1", "2", 0.10, 200.0, 1.5e-6),
        NetworkPipe("13", "1", "3", 0.075, 250.0, 1.5e-6),
        NetworkPipe("23", "2", "3", 0.05, 150.0, 1.5e-6),
        NetworkPipe("24", "2", "4", 0.075, 200.0, 1.5e-6),
        NetworkPipe("34", "3", "4", 0.10, 200.0, 1.5e-6),
    ]
    external = {"1": 0.010, "4": -0.010}
    flows = compute_initial_flows_spanning_tree(pipes, external)

    network = PipeNetwork(pipes, loops=[], density=WATER_DENSITY, viscosity=WATER_VISCOSITY)
    residuals = network.check_node_continuity(flows, external)
    for node, residual in residuals.items():
        assert abs(residual) < 1e-9, f"Node {node} continuity violated: {residual}"


def test_spanning_tree_and_hand_crafted_guess_converge_to_same_solution():
    """The real correctness proof: two different *valid* initial guesses
    (one hand-crafted, one from the generic spanning-tree solver) must
    converge to the identical physical Hardy Cross solution, since
    convergence is independent of the (continuity-satisfying) starting
    point."""
    pipes = [
        NetworkPipe("12", "1", "2", 0.10, 200.0, 1.5e-6),
        NetworkPipe("13", "1", "3", 0.075, 250.0, 1.5e-6),
        NetworkPipe("23", "2", "3", 0.05, 150.0, 1.5e-6),
        NetworkPipe("24", "2", "4", 0.075, 200.0, 1.5e-6),
        NetworkPipe("34", "3", "4", 0.10, 200.0, 1.5e-6),
    ]
    loop123 = Loop("123", [LoopMember("12", 1), LoopMember("23", 1), LoopMember("13", -1)])
    loop234 = Loop("234", [LoopMember("23", -1), LoopMember("24", 1), LoopMember("34", -1)])
    network = PipeNetwork(pipes, [loop123, loop234], density=WATER_DENSITY, viscosity=WATER_VISCOSITY)

    hand_crafted_guess = {"12": 0.006, "13": 0.004, "23": 0.0, "24": 0.006, "34": 0.004}
    spanning_tree_guess = compute_initial_flows_spanning_tree(pipes, {"1": 0.010, "4": -0.010})

    solution_a = network.solve(hand_crafted_guess)
    solution_b = network.solve(spanning_tree_guess)

    assert solution_a.converged and solution_b.converged
    for name in ["12", "13", "23", "24", "34"]:
        assert solution_a.flows[name] == pytest.approx(solution_b.flows[name], abs=1e-6)


def test_pipe_network_compute_initial_flows_convenience_method():
    """PipeNetwork.compute_initial_flows should match the standalone
    function using the network's own pipes."""
    pipes = [NetworkPipe("AB", "A", "B", 0.1, 100, 1.5e-6)]
    network = PipeNetwork(pipes, loops=[], density=WATER_DENSITY, viscosity=WATER_VISCOSITY)
    flows = network.compute_initial_flows({"A": 5.0, "B": -5.0})
    assert flows == {"AB": pytest.approx(5.0)}


def test_spanning_tree_rejects_empty_pipe_list():
    with pytest.raises(ValueError, match="at least one pipe"):
        compute_initial_flows_spanning_tree([], {})


def test_spanning_tree_rejects_disconnected_network():
    pipes = [
        NetworkPipe("AB", "A", "B", 0.1, 100, 1.5e-6),
        NetworkPipe("CD", "C", "D", 0.1, 100, 1.5e-6),
    ]
    with pytest.raises(ValueError, match="not connected"):
        compute_initial_flows_spanning_tree(pipes, {"A": 5.0, "B": -5.0, "C": 3.0, "D": -3.0})


def test_spanning_tree_rejects_imbalanced_external_flow():
    pipes = [NetworkPipe("AB", "A", "B", 0.1, 100, 1.5e-6)]
    with pytest.raises(ValueError, match="must balance to ~0"):
        compute_initial_flows_spanning_tree(pipes, {"A": 10.0, "B": -5.0})


def test_spanning_tree_rejects_unknown_node_in_external_flow():
    pipes = [NetworkPipe("AB", "A", "B", 0.1, 100, 1.5e-6)]
    with pytest.raises(ValueError, match="not used by any pipe"):
        compute_initial_flows_spanning_tree(pipes, {"A": 10.0, "GHOST": -10.0})


def test_spanning_tree_defaults_unlisted_nodes_to_zero_external_flow():
    """A node not present in external_flow should be treated as a pure
    junction (0 external flow), not raise an error."""
    pipes = [
        NetworkPipe("AB", "A", "B", 0.1, 100, 1.5e-6),
        NetworkPipe("BC", "B", "C", 0.1, 100, 1.5e-6),
    ]
    # 'B' is a pure junction, not listed in external_flow at all.
    flows = compute_initial_flows_spanning_tree(pipes, {"A": 5.0, "C": -5.0})
    assert flows["AB"] == pytest.approx(5.0)
    assert flows["BC"] == pytest.approx(5.0)


def test_spanning_tree_works_with_geospatial_geopipe_objects():
    """The function accepts any pipe-like object with .name/.start_node/
    .end_node — not just NetworkPipe — including geospatial.models.GeoPipe."""
    from src.geospatial.models import GeoPipe

    pipes = [
        GeoPipe("AB", "A", "B", diameter_m=0.1, length_m=100, roughness_m=1.5e-6,
                start_coords=(0.0, 0.0), end_coords=(1.0, 1.0)),
    ]
    flows = compute_initial_flows_spanning_tree(pipes, {"A": 5.0, "B": -5.0})
    assert flows == {"AB": pytest.approx(5.0)}
