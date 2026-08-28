from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from atabey.types import Detection, LineageGraph


EdgeKey = tuple[str, str]


@dataclass(frozen=True)
class BoundedIlpShadowResult:
    sample_id: str
    trigger_source_id: str
    trigger_target_id: str
    solver_status: str
    recommendation: str
    source_count: int
    intermediate_count: int
    future_count: int
    variable_count: int
    baseline_objective_um: float | None
    optimized_objective_um: float | None
    objective_improvement_um: float | None
    proposed_removed_edges: tuple[EdgeKey, ...]
    proposed_added_edges: tuple[EdgeKey, ...]
    removed_edges: tuple[EdgeKey, ...]
    added_edges: tuple[EdgeKey, ...]


@dataclass(frozen=True)
class _PathOption:
    source_id: str
    intermediate_id: str | None
    future_id: str | None
    edges: tuple[EdgeKey, ...]
    kinematic_cost_um: float
    deviation_count: int


def audit_bounded_ilp_window(
    graph: LineageGraph,
    *,
    trigger_source_id: str,
    trigger_target_id: str,
    max_link_distance_um: float = 9.0,
    baseline_change_penalty_um: float = 2.0,
    minimum_improvement_um: float = 0.5,
    terminal_penalty_um: float = 9.0,
    max_variables: int = 512,
    time_limit_seconds: float = 5.0,
) -> BoundedIlpShadowResult:
    """Compare a bounded joint assignment with the baseline without mutation.

    The trigger identifies a three-frame local window. High change penalties and
    the minimum-improvement gate make abstention the default. A recommendation
    is a shadow stability hypothesis, not evidence of biological identity.
    """

    if max_link_distance_um <= 0.0:
        raise ValueError("max_link_distance_um must be positive")
    if baseline_change_penalty_um < 0.0:
        raise ValueError("baseline_change_penalty_um must be non-negative")
    if minimum_improvement_um < 0.0:
        raise ValueError("minimum_improvement_um must be non-negative")
    if terminal_penalty_um < 0.0:
        raise ValueError("terminal_penalty_um must be non-negative")
    if max_variables < 1:
        raise ValueError("max_variables must be positive")
    if time_limit_seconds <= 0.0:
        raise ValueError("time_limit_seconds must be positive")

    nodes = {node.node_id: node for node in graph.detections}
    if len(nodes) != len(graph.detections):
        raise ValueError("Detection node IDs must be unique")
    source = nodes.get(trigger_source_id)
    target = nodes.get(trigger_target_id)
    if source is None or target is None:
        raise ValueError("Trigger edge references an absent detection")
    if int(target.t) != int(source.t) + 1:
        raise ValueError("Trigger edge must connect adjacent frames")

    baseline_edges = {
        (edge.source_id, edge.target_id)
        for edge in graph.edges
        if edge.relation == "continuation"
        and edge.source_id in nodes
        and edge.target_id in nodes
        and int(nodes[edge.target_id].t) == int(nodes[edge.source_id].t) + 1
    }
    if (trigger_source_id, trigger_target_id) not in baseline_edges:
        raise ValueError("Trigger edge is not an accepted baseline continuation")
    outgoing = _unique_outgoing(baseline_edges)
    incoming = _unique_incoming(baseline_edges)
    predecessor = {
        target_id: nodes[source_id]
        for target_id, source_id in incoming.items()
    }

    frame = int(source.t)
    sources, intermediates = _local_component(
        nodes=nodes,
        frame=frame,
        trigger_source=source,
        trigger_target=target,
        predecessor=predecessor,
        incoming=incoming,
        max_link_distance_um=max_link_distance_um,
    )
    futures = sorted(
        (node for node in graph.detections if int(node.t) == frame + 2),
        key=lambda node: node.node_id,
    )
    intermediate_ids = {node.node_id for node in intermediates}
    protected_future_ids = {
        node.node_id
        for node in futures
        if incoming.get(node.node_id) not in intermediate_ids
        and incoming.get(node.node_id) is not None
    }

    options: list[_PathOption] = []
    baseline_paths: dict[str, tuple[EdgeKey, ...]] = {}
    for local_source in sources:
        baseline_path = _baseline_path(local_source.node_id, outgoing, nodes, frame)
        baseline_paths[local_source.node_id] = baseline_path
        source_options = _path_options(
            source=local_source,
            predecessor=predecessor.get(local_source.node_id),
            intermediates=intermediates,
            futures=futures,
            protected_future_ids=protected_future_ids,
            baseline_path=baseline_path,
            max_link_distance_um=max_link_distance_um,
            terminal_penalty_um=terminal_penalty_um,
        )
        if not any(option.edges == baseline_path for option in source_options):
            source_options.append(
                _option_from_edges(
                    local_source,
                    baseline_path,
                    nodes,
                    predecessor.get(local_source.node_id),
                    terminal_penalty_um,
                    baseline_path,
                )
            )
        options.extend(source_options)

    variable_count = len(options)
    candidate_future_ids = {
        option.future_id for option in options if option.future_id is not None
    }
    base_result = dict(
        sample_id=graph.sample_id,
        trigger_source_id=trigger_source_id,
        trigger_target_id=trigger_target_id,
        source_count=len(sources),
        intermediate_count=len(intermediates),
        future_count=len(candidate_future_ids),
        variable_count=variable_count,
    )
    if variable_count > max_variables:
        return BoundedIlpShadowResult(
            **base_result,
            solver_status="budget_exceeded",
            recommendation="keep_baseline",
            baseline_objective_um=None,
            optimized_objective_um=None,
            objective_improvement_um=None,
            proposed_removed_edges=(),
            proposed_added_edges=(),
            removed_edges=(),
            added_edges=(),
        )

    baseline_objective = sum(
        next(
            option.kinematic_cost_um
            for option in options
            if option.source_id == source_id and option.edges == path
        )
        for source_id, path in baseline_paths.items()
    )
    costs = np.asarray(
        [
            option.kinematic_cost_um
            + baseline_change_penalty_um * option.deviation_count
            + index * 1e-9
            for index, option in enumerate(options)
        ],
        dtype=float,
    )
    constraint = _assignment_constraints(options, sources, intermediates, futures)
    solution = milp(
        costs,
        integrality=np.ones(variable_count, dtype=np.int8),
        bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
        constraints=constraint,
        options={"time_limit": float(time_limit_seconds), "presolve": True},
    )
    status = {0: "optimal", 1: "time_limit", 2: "infeasible", 3: "unbounded"}.get(
        int(solution.status), "solver_error"
    )
    if status != "optimal" or solution.x is None or solution.fun is None:
        return BoundedIlpShadowResult(
            **base_result,
            solver_status=status,
            recommendation="keep_baseline",
            baseline_objective_um=baseline_objective,
            optimized_objective_um=None,
            objective_improvement_um=None,
            proposed_removed_edges=(),
            proposed_added_edges=(),
            removed_edges=(),
            added_edges=(),
        )

    selected = [option for option, value in zip(options, solution.x) if value > 0.5]
    optimized_objective = sum(
        option.kinematic_cost_um + baseline_change_penalty_um * option.deviation_count
        for option in selected
    )
    improvement = baseline_objective - optimized_objective
    baseline_local_edges = {edge for path in baseline_paths.values() for edge in path}
    optimized_edges = {edge for option in selected for edge in option.edges}
    proposed_removed = tuple(sorted(baseline_local_edges - optimized_edges))
    proposed_added = tuple(sorted(optimized_edges - baseline_local_edges))
    recommend = bool(
        proposed_removed
        and proposed_added
        and improvement >= minimum_improvement_um
    )
    return BoundedIlpShadowResult(
        **base_result,
        solver_status=status,
        recommendation="shadow_alternative" if recommend else "keep_baseline",
        baseline_objective_um=baseline_objective,
        optimized_objective_um=optimized_objective,
        objective_improvement_um=improvement,
        proposed_removed_edges=proposed_removed,
        proposed_added_edges=proposed_added,
        removed_edges=proposed_removed if recommend else (),
        added_edges=proposed_added if recommend else (),
    )


def _local_component(
    *,
    nodes: dict[str, Detection],
    frame: int,
    trigger_source: Detection,
    trigger_target: Detection,
    predecessor: dict[str, Detection],
    incoming: dict[str, str],
    max_link_distance_um: float,
) -> tuple[list[Detection], list[Detection]]:
    frame_sources = sorted(
        (node for node in nodes.values() if int(node.t) == frame),
        key=lambda node: node.node_id,
    )
    frame_targets = sorted(
        (node for node in nodes.values() if int(node.t) == frame + 1),
        key=lambda node: node.node_id,
    )
    source_ids = {trigger_source.node_id}
    target_ids = {trigger_target.node_id}
    changed = True
    while changed:
        changed = False
        for candidate_source in frame_sources:
            if candidate_source.node_id in source_ids:
                continue
            if any(
                _plausible(
                    candidate_source,
                    candidate_target,
                    predecessor.get(candidate_source.node_id),
                    max_link_distance_um,
                )
                for candidate_target in frame_targets
                if candidate_target.node_id in target_ids
            ):
                source_ids.add(candidate_source.node_id)
                changed = True
        for candidate_target in frame_targets:
            if candidate_target.node_id in target_ids:
                continue
            if any(
                _plausible(
                    candidate_source,
                    candidate_target,
                    predecessor.get(candidate_source.node_id),
                    max_link_distance_um,
                )
                for candidate_source in frame_sources
                if candidate_source.node_id in source_ids
            ):
                target_ids.add(candidate_target.node_id)
                changed = True
        for target_id in tuple(target_ids):
            owner = incoming.get(target_id)
            if owner is not None and owner not in source_ids:
                source_ids.add(owner)
                changed = True
    return (
        [node for node in frame_sources if node.node_id in source_ids],
        [node for node in frame_targets if node.node_id in target_ids],
    )


def _path_options(
    *,
    source: Detection,
    predecessor: Detection | None,
    intermediates: list[Detection],
    futures: list[Detection],
    protected_future_ids: set[str],
    baseline_path: tuple[EdgeKey, ...],
    max_link_distance_um: float,
    terminal_penalty_um: float,
) -> list[_PathOption]:
    options = [
        _PathOption(
            source_id=source.node_id,
            intermediate_id=None,
            future_id=None,
            edges=(),
            kinematic_cost_um=terminal_penalty_um * 2.0,
            deviation_count=len(baseline_path),
        )
    ]
    for intermediate in intermediates:
        if not _plausible(source, intermediate, predecessor, max_link_distance_um):
            continue
        first_edge = (source.node_id, intermediate.node_id)
        first_cost = _first_step_cost(source, intermediate, predecessor)
        options.append(
            _PathOption(
                source_id=source.node_id,
                intermediate_id=intermediate.node_id,
                future_id=None,
                edges=(first_edge,),
                kinematic_cost_um=first_cost + terminal_penalty_um,
                deviation_count=_symmetric_difference_count((first_edge,), baseline_path),
            )
        )
        for future in futures:
            if future.node_id in protected_future_ids:
                continue
            if not _plausible(intermediate, future, source, max_link_distance_um):
                continue
            edges = (first_edge, (intermediate.node_id, future.node_id))
            options.append(
                _PathOption(
                    source_id=source.node_id,
                    intermediate_id=intermediate.node_id,
                    future_id=future.node_id,
                    edges=edges,
                    kinematic_cost_um=first_cost + _second_step_cost(source, intermediate, future),
                    deviation_count=_symmetric_difference_count(edges, baseline_path),
                )
            )
    return options


def _option_from_edges(
    source: Detection,
    edges: tuple[EdgeKey, ...],
    nodes: dict[str, Detection],
    predecessor: Detection | None,
    terminal_penalty_um: float,
    baseline_path: tuple[EdgeKey, ...],
) -> _PathOption:
    if not edges:
        return _PathOption(source.node_id, None, None, (), terminal_penalty_um * 2.0, 0)
    intermediate = nodes[edges[0][1]]
    cost = _first_step_cost(source, intermediate, predecessor)
    future_id = None
    if len(edges) == 1:
        cost += terminal_penalty_um
    else:
        future = nodes[edges[1][1]]
        future_id = future.node_id
        cost += _second_step_cost(source, intermediate, future)
    return _PathOption(
        source.node_id,
        intermediate.node_id,
        future_id,
        edges,
        cost,
        _symmetric_difference_count(edges, baseline_path),
    )


def _assignment_constraints(
    options: list[_PathOption],
    sources: list[Detection],
    intermediates: list[Detection],
    futures: list[Detection],
) -> LinearConstraint:
    rows: list[list[float]] = []
    lower: list[float] = []
    upper: list[float] = []
    for source in sources:
        rows.append([float(option.source_id == source.node_id) for option in options])
        lower.append(1.0)
        upper.append(1.0)
    for intermediate in intermediates:
        rows.append(
            [float(option.intermediate_id == intermediate.node_id) for option in options]
        )
        lower.append(0.0)
        upper.append(1.0)
    for future in futures:
        rows.append([float(option.future_id == future.node_id) for option in options])
        lower.append(0.0)
        upper.append(1.0)
    return LinearConstraint(np.asarray(rows), np.asarray(lower), np.asarray(upper))


def _baseline_path(
    source_id: str,
    outgoing: dict[str, str],
    nodes: dict[str, Detection],
    frame: int,
) -> tuple[EdgeKey, ...]:
    intermediate_id = outgoing.get(source_id)
    if intermediate_id is None or int(nodes[intermediate_id].t) != frame + 1:
        return ()
    edges: list[EdgeKey] = [(source_id, intermediate_id)]
    future_id = outgoing.get(intermediate_id)
    if future_id is not None and int(nodes[future_id].t) == frame + 2:
        edges.append((intermediate_id, future_id))
    return tuple(edges)


def _unique_outgoing(edges: set[EdgeKey]) -> dict[str, str]:
    outgoing: dict[str, str] = {}
    for source_id, target_id in sorted(edges):
        if source_id in outgoing:
            raise ValueError(f"Multiple continuation children for {source_id}")
        outgoing[source_id] = target_id
    return outgoing


def _unique_incoming(edges: set[EdgeKey]) -> dict[str, str]:
    incoming: dict[str, str] = {}
    for source_id, target_id in sorted(edges):
        if target_id in incoming:
            raise ValueError(f"Multiple continuation parents for {target_id}")
        incoming[target_id] = source_id
    return incoming


def _plausible(
    source: Detection,
    target: Detection,
    predecessor: Detection | None,
    gate_um: float,
) -> bool:
    return _distance(source, target) <= gate_um and _prediction_error(
        source, target, predecessor
    ) <= gate_um


def _first_step_cost(
    source: Detection,
    target: Detection,
    predecessor: Detection | None,
) -> float:
    return _prediction_error(source, target, predecessor) + 0.4 * _distance(source, target)


def _second_step_cost(source: Detection, pivot: Detection, target: Detection) -> float:
    return _prediction_error(pivot, target, source) + 0.3 * _distance(pivot, target)


def _prediction_error(
    source: Detection,
    target: Detection,
    predecessor: Detection | None,
) -> float:
    source_position = np.asarray(source.position_um, dtype=float)
    prediction = source_position
    if predecessor is not None:
        prediction = source_position + source_position - np.asarray(
            predecessor.position_um, dtype=float
        )
    return float(np.linalg.norm(np.asarray(target.position_um, dtype=float) - prediction))


def _distance(left: Detection, right: Detection) -> float:
    return float(
        np.linalg.norm(
            np.asarray(left.position_um, dtype=float)
            - np.asarray(right.position_um, dtype=float)
        )
    )


def _symmetric_difference_count(
    left: tuple[EdgeKey, ...], right: tuple[EdgeKey, ...]
) -> int:
    return len(set(left).symmetric_difference(right))