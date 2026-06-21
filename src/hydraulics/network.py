"""
Hardy Cross method for flow distribution in closed-loop pipe networks.

The core solver (``hardy_cross_solve``) is deliberately generic: it accepts
any head-loss law via a caller-supplied ``head_loss_fn(pipe_name, |Q|) ->
h_f``, exactly mirroring how the method was originally formulated (Cross,
1936) and is described on its reference pages — the method works for any
monotonic head-loss-vs-flow relation (Darcy-Weisbach, Hazen-Williams, even
Ohm's law for analogous electrical circuits), not just one specific
formula. ``PipeNetwork`` wraps the generic solver with a concrete
Darcy-Weisbach head-loss function built from real pipe geometry, for
everyday hydraulic use.

Method
------
For each loop, the flow correction is:

    dQ = -sum(signed h_f) / (n * sum(h_f / |Q|))

where n=2 for Darcy-Weisbach (h_f locally ~ Q^2). Corrections are applied
loop-by-loop, repeated over outer iterations until the largest correction
across all loops drops below tolerance.

The initial flow assignment MUST already satisfy node continuity (inflow
= outflow at every junction) — this is the caller's responsibility; use
``PipeNetwork.check_node_continuity`` to verify before solving.

References
----------
Cross, H. (1936). Analysis of flow in networks of conduits or conductors.
  University of Illinois Engineering Experiment Station, Bulletin No. 286.
Houghtalen, R.J. et al. Fundamentals of Hydraulic Engineering Systems.
"""

from dataclasses import dataclass
from typing import Callable

from .head_loss import major_head_loss


@dataclass
class LoopMember:
    """One pipe's participation in a loop.

    ``direction`` is +1 if traversing the loop in its chosen direction
    means going the same way as the pipe's own defined positive direction
    (its ``start_node -> end_node``), or -1 if traversing the loop means
    going against it.
    """

    pipe_name: str
    direction: int   # +1 or -1


@dataclass
class Loop:
    """A closed loop in the network: an ordered set of pipes with their
    traversal direction relative to each pipe's own positive convention."""

    name: str
    members: list[LoopMember]


@dataclass
class NetworkSolution:
    """Result of a Hardy Cross network solve."""

    flows: dict[str, float]          # final signed flow per pipe
    head_losses: dict[str, float]    # head loss magnitude per pipe
    iterations: int
    converged: bool
    max_correction: float            # largest |dQ| in the final iteration


def hardy_cross_solve(
    pipe_names: list[str],
    loops: list[Loop],
    head_loss_fn: Callable[[str, float], float],
    initial_flows: dict[str, float],
    n: float = 2.0,
    max_iterations: int = 50,
    tolerance: float = 1e-6,
    flow_floor: float = 1e-9,
) -> NetworkSolution:
    """Generic Hardy Cross loop-balancing solver.

    Parameters
    ----------
    pipe_names    : list[str]  every pipe in the network (including any
                     not part of a loop — e.g. tree-like branches whose
                     flow is already fully fixed by continuity; these are
                     simply never touched by a loop correction)
    loops         : list[Loop]
    head_loss_fn  : Callable[[pipe_name, Q_magnitude], h_f_magnitude]
                     any monotonic head-loss law — this is what makes the
                     method work for Darcy-Weisbach, Hazen-Williams, etc.
                     without changing the solver itself
    initial_flows : dict[str, float]
                     starting guess for each pipe's signed flow (positive
                     = along its defined start->end direction). MUST
                     already satisfy node continuity.
    n             : float  assumed local exponent of the head-loss law
                     (h_f ~ Q^n); 2.0 for Darcy-Weisbach
    max_iterations: int    maximum outer iterations
    tolerance     : float  convergence threshold on the largest |dQ|
    flow_floor    : float  minimum |Q| used when evaluating head_loss_fn,
                     to avoid division by zero for a pipe at exactly zero
                     flow (the true h_f/Q ratio is well-behaved in this
                     limit for power-law losses, so a small floor
                     introduces negligible error)

    Returns
    -------
    NetworkSolution
    """
    missing = set(pipe_names) - set(initial_flows)
    if missing:
        raise ValueError(f"initial_flows is missing pipes: {sorted(missing)}")
    for loop in loops:
        if not loop.members:
            raise ValueError(f"Loop '{loop.name}' has no members.")
        for member in loop.members:
            if member.pipe_name not in pipe_names:
                raise ValueError(
                    f"Loop '{loop.name}' references unknown pipe '{member.pipe_name}'."
                )
            if member.direction not in (1, -1):
                raise ValueError(
                    f"Loop '{loop.name}' member '{member.pipe_name}' direction must be "
                    f"+1 or -1. Got {member.direction}."
                )

    flows = dict(initial_flows)
    max_correction = float("inf")
    iterations_run = 0

    for iteration in range(1, max_iterations + 1):
        max_correction = 0.0
        # Snapshot flows at the start of this iteration: every loop's
        # correction this round is computed from the SAME starting point
        # (matching the standard textbook convention), then all
        # corrections are applied together at the end of the iteration —
        # not applied sequentially loop-by-loop, which would let an
        # earlier loop's update leak into a later loop's correction for
        # any pipe shared between them within the same outer iteration.
        snapshot = dict(flows)
        pending_updates: dict[str, float] = {name: 0.0 for name in pipe_names}

        for loop in loops:
            signed_hf_sum = 0.0
            hf_over_q_sum = 0.0

            for member in loop.members:
                Q_signed = snapshot[member.pipe_name]
                Q_mag = max(abs(Q_signed), flow_floor)
                hf = head_loss_fn(member.pipe_name, Q_mag)

                flow_sign = 1.0 if Q_signed >= 0 else -1.0
                signed_hf_sum += member.direction * flow_sign * hf
                hf_over_q_sum += hf / Q_mag

            if hf_over_q_sum == 0:
                continue
            delta_q = -signed_hf_sum / (n * hf_over_q_sum)

            for member in loop.members:
                pending_updates[member.pipe_name] += member.direction * delta_q

            max_correction = max(max_correction, abs(delta_q))

        for name, update in pending_updates.items():
            flows[name] += update

        iterations_run = iteration
        if max_correction < tolerance:
            break

    head_losses = {
        name: head_loss_fn(name, max(abs(flows[name]), flow_floor)) for name in pipe_names
    }

    return NetworkSolution(
        flows=flows,
        head_losses=head_losses,
        iterations=iterations_run,
        converged=max_correction < tolerance,
        max_correction=max_correction,
    )


# ── Darcy-Weisbach convenience wrapper ────────────────────────────────────
@dataclass
class NetworkPipe:
    """A pipe segment in a network, connecting two named nodes.

    ``start_node -> end_node`` defines this pipe's positive flow direction.
    """

    name: str
    start_node: str
    end_node: str
    diameter_m: float
    length_m: float
    roughness_m: float


class PipeNetwork:
    """A closed-loop pipe network, solved via Hardy Cross with real
    Darcy-Weisbach head losses (built on ``hydraulics.head_loss``)."""

    def __init__(
        self,
        pipes: list[NetworkPipe],
        loops: list[Loop],
        density: float,
        viscosity: float,
    ):
        if len(pipes) != len({p.name for p in pipes}):
            raise ValueError("Pipe names must be unique.")
        self.pipes = {p.name: p for p in pipes}
        self.loops = loops
        self.density = density
        self.viscosity = viscosity

    def _head_loss(self, pipe_name: str, flow_magnitude_m3s: float) -> float:
        pipe = self.pipes[pipe_name]
        result = major_head_loss(
            flow_magnitude_m3s, pipe.diameter_m, pipe.length_m, pipe.roughness_m,
            self.density, self.viscosity,
        )
        return result.major_loss_m

    def check_node_continuity(
        self, flows: dict[str, float], external_flow: dict[str, float], tol: float = 1e-9
    ) -> dict[str, float]:
        """Check mass continuity at every node: outflow - inflow - external = 0.

        Parameters
        ----------
        flows         : dict[str, float]  signed flow per pipe
        external_flow : dict[str, float]  external supply (+) or demand (-)
                         at each node (unlisted nodes default to 0)

        Returns
        -------
        dict[str, float]
            Node -> residual imbalance [m³/s]. All should be ~0 for a
            valid initial flow assignment (Poka-Yoke diagnostic — non-zero
            entries identify exactly which node(s) violate continuity).
        """
        nodes = set()
        for pipe in self.pipes.values():
            nodes.add(pipe.start_node)
            nodes.add(pipe.end_node)

        residuals = {}
        for node in nodes:
            balance = external_flow.get(node, 0.0)
            for pipe in self.pipes.values():
                Q = flows.get(pipe.name, 0.0)
                if pipe.start_node == node:
                    balance -= Q
                if pipe.end_node == node:
                    balance += Q
            residuals[node] = balance
        return residuals

    def solve(
        self,
        initial_flows_m3s: dict[str, float],
        max_iterations: int = 50,
        tolerance_m3s: float = 1e-7,
    ) -> NetworkSolution:
        """Solve for the network's flow distribution. See
        ``hardy_cross_solve`` for parameter details — this just supplies
        the Darcy-Weisbach ``head_loss_fn`` and fixes ``n=2``."""
        return hardy_cross_solve(
            pipe_names=list(self.pipes),
            loops=self.loops,
            head_loss_fn=self._head_loss,
            initial_flows=initial_flows_m3s,
            n=2.0,
            max_iterations=max_iterations,
            tolerance=tolerance_m3s,
        )
