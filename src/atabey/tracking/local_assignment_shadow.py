from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.optimize import linear_sum_assignment

from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class PairHypothesis:
    child_1_id: str
    child_2_id: str
    base_score: float
    base_rank: int


@dataclass(frozen=True)
class LocalAssignmentResult:
    child_1_id: str
    child_2_id: str
    base_score: float
    base_rank: int
    local_rank: int
    competing_parents: int
    disputed_targets: int
    baseline_matched_parents: int
    constrained_matched_parents: int
    displaced_parents: int
    baseline_cost_um: float
    constrained_cost_um: float
    assignment_cost_increase_um: float


def _distance(left: Detection, right: Detection) -> float:
    return float(
        np.linalg.norm(
            np.asarray(left.position_um, dtype=float) - np.asarray(right.position_um, dtype=float)
        )
    )


def _prediction(parent: Detection, predecessor: Detection | None) -> np.ndarray:
    position = np.asarray(parent.position_um, dtype=float)
    if predecessor is None:
        return position
    return position + (position - np.asarray(predecessor.position_um, dtype=float))


def _prediction_error(
    parent: Detection,
    target: Detection,
    predecessor: Detection | None,
) -> float:
    return float(np.linalg.norm(np.asarray(target.position_um, dtype=float) - _prediction(parent, predecessor)))


def _predecessors(graph: LineageGraph, nodes: dict[str, Detection]) -> dict[str, Detection]:
    candidates: dict[str, list[Detection]] = {}
    for edge in graph.edges:
        source = nodes.get(edge.source_id)
        target = nodes.get(edge.target_id)
        if source is None or target is None or int(source.t) + 1 != int(target.t):
            continue
        candidates.setdefault(target.node_id, []).append(source)
    return {
        target_id: min(sources, key=lambda node: node.node_id)
        for target_id, sources in candidates.items()
    }


def _is_plausible(
    parent: Detection,
    target: Detection,
    predecessor: Detection | None,
    gate_um: float,
) -> bool:
    return _distance(parent, target) <= gate_um and _prediction_error(parent, target, predecessor) <= gate_um


def _discover_competitors(
    graph: LineageGraph,
    focal_parent: Detection,
    pair_target_ids: set[str],
    *,
    nodes: dict[str, Detection],
    predecessors: dict[str, Detection],
    gate_um: float,
) -> tuple[list[Detection], int]:
    previous = [node for node in graph.detections if int(node.t) == int(focal_parent.t)]
    current = [node for node in graph.detections if int(node.t) == int(focal_parent.t) + 1]
    current_by_id = {node.node_id: node for node in current}
    incoming: dict[str, list[str]] = {}
    for edge in graph.edges:
        incoming.setdefault(edge.target_id, []).append(edge.source_id)

    competitor_ids: set[str] = set()
    disputed_targets = 0
    for target_id in pair_target_ids:
        target = current_by_id.get(target_id)
        if target is None:
            continue
        target_has_competitor = False
        for source_id in incoming.get(target_id, []):
            source = nodes.get(source_id)
            if (
                source is not None
                and source.node_id != focal_parent.node_id
                and int(source.t) == int(focal_parent.t)
                and _is_plausible(source, target, predecessors.get(source.node_id), gate_um)
            ):
                competitor_ids.add(source.node_id)
                target_has_competitor = True

        plausible_previous = [
            parent
            for parent in previous
            if parent.node_id != focal_parent.node_id
            and _is_plausible(parent, target, predecessors.get(parent.node_id), gate_um)
        ]
        if plausible_previous:
            nearest_parent = min(plausible_previous, key=lambda parent: (_distance(parent, target), parent.node_id))
            valid_targets = [
                candidate
                for candidate in current
                if _is_plausible(
                    nearest_parent,
                    candidate,
                    predecessors.get(nearest_parent.node_id),
                    gate_um,
                )
            ]
            if valid_targets:
                nearest_target = min(
                    valid_targets,
                    key=lambda candidate: (
                        _prediction_error(
                            nearest_parent,
                            candidate,
                            predecessors.get(nearest_parent.node_id),
                        ),
                        candidate.node_id,
                    ),
                )
                if nearest_target.node_id == target.node_id:
                    competitor_ids.add(nearest_parent.node_id)
                    target_has_competitor = True
        if target_has_competitor:
            disputed_targets += 1

    return sorted((nodes[node_id] for node_id in competitor_ids), key=lambda node: node.node_id), disputed_targets


def _solve_assignment(
    parents: list[Detection],
    targets: list[Detection],
    predecessors: dict[str, Detection],
    *,
    gate_um: float,
    reserved_target_ids: set[str],
) -> tuple[int, float]:
    if not parents:
        return 0, 0.0
    available = [target for target in targets if target.node_id not in reserved_target_ids]
    unmatched_cost = gate_um * 1000.0
    invalid_cost = unmatched_cost * 2.0
    matrix = np.full((len(parents), len(available) + len(parents)), unmatched_cost, dtype=float)
    for row, parent in enumerate(parents):
        predecessor = predecessors.get(parent.node_id)
        for column, target in enumerate(available):
            if _is_plausible(parent, target, predecessor, gate_um):
                matrix[row, column] = _prediction_error(parent, target, predecessor) + column * 1e-12
        for dummy in range(len(parents)):
            matrix[row, len(available) + dummy] = unmatched_cost + dummy * 1e-9
    matrix[matrix >= invalid_cost] = invalid_cost
    rows, columns = linear_sum_assignment(matrix)
    matched_costs = [
        float(matrix[row, column])
        for row, column in zip(rows, columns)
        if column < len(available) and matrix[row, column] < unmatched_cost
    ]
    return len(matched_costs), float(sum(matched_costs))


def rank_local_pair_hypotheses(
    graph: LineageGraph,
    focal_parent_id: str,
    hypotheses: Iterable[PairHypothesis],
    *,
    gate_um: float = 9.0,
) -> list[LocalAssignmentResult]:
    """Rank daughter pairs by local ownership contention without mutating the graph."""
    nodes = {node.node_id: node for node in graph.detections}
    focal_parent = nodes.get(focal_parent_id)
    if focal_parent is None:
        raise ValueError(f"Focal parent {focal_parent_id!r} is absent from the graph")
    pairs = list(hypotheses)
    if not pairs:
        return []
    current_targets = [
        node for node in graph.detections if int(node.t) == int(focal_parent.t) + 1
    ]
    predecessors = _predecessors(graph, nodes)
    scored: list[tuple[PairHypothesis, int, int, int, int, float, float, float]] = []
    for pair in pairs:
        reserved = {pair.child_1_id, pair.child_2_id}
        if not reserved.issubset(nodes):
            missing = sorted(reserved.difference(nodes))
            raise ValueError(f"Pair references absent targets: {missing}")
        competitors, disputed_targets = _discover_competitors(
            graph,
            focal_parent,
            reserved,
            nodes=nodes,
            predecessors=predecessors,
            gate_um=gate_um,
        )
        baseline_matched, baseline_cost = _solve_assignment(
            competitors,
            current_targets,
            predecessors,
            gate_um=gate_um,
            reserved_target_ids=set(),
        )
        constrained_matched, constrained_cost = _solve_assignment(
            competitors,
            current_targets,
            predecessors,
            gate_um=gate_um,
            reserved_target_ids=reserved,
        )
        displaced = max(0, baseline_matched - constrained_matched)
        cost_increase = max(0.0, constrained_cost - baseline_cost) if displaced == 0 else 0.0
        scored.append(
            (
                pair,
                len(competitors),
                disputed_targets,
                baseline_matched,
                constrained_matched,
                displaced,
                baseline_cost,
                constrained_cost,
                cost_increase,
            )
        )

    ordered = sorted(
        range(len(scored)),
        key=lambda index: (
            scored[index][5],
            round(scored[index][8], 12),
            -scored[index][0].base_score,
            scored[index][0].child_1_id,
            scored[index][0].child_2_id,
        ),
    )
    ranks = {index: rank for rank, index in enumerate(ordered, start=1)}
    results: list[LocalAssignmentResult] = []
    for index, values in enumerate(scored):
        pair, count, disputed, baseline_n, constrained_n, displaced, baseline_cost, constrained_cost, increase = values
        results.append(
            LocalAssignmentResult(
                child_1_id=pair.child_1_id,
                child_2_id=pair.child_2_id,
                base_score=pair.base_score,
                base_rank=pair.base_rank,
                local_rank=ranks[index],
                competing_parents=count,
                disputed_targets=disputed,
                baseline_matched_parents=baseline_n,
                constrained_matched_parents=constrained_n,
                displaced_parents=displaced,
                baseline_cost_um=baseline_cost,
                constrained_cost_um=constrained_cost,
                assignment_cost_increase_um=increase,
            )
        )
    return sorted(results, key=lambda result: result.local_rank)
