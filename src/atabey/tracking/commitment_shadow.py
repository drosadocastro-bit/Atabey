from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

import numpy as np
from scipy.spatial import cKDTree

from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageEdge, LineageGraph


@dataclass(frozen=True)
class CommitmentShadowRecord:
    source_id: str
    target_id: str
    source_frame: int
    edge_distance_um: float
    prediction_error_um: float
    forward_margin_um: float | None
    reverse_margin_um: float | None
    local_target_count: int
    local_competing_source_count: int
    changed_assignment_count: int
    reconverged: bool


@dataclass(frozen=True)
class CommitmentShadowSummary:
    sample_id: str
    horizon_frames: int
    max_counterfactual_edges: int
    eligible_edge_count: int
    counterfactual_edge_count: int
    commitment_sensitive_edge_count: int
    records: tuple[CommitmentShadowRecord, ...]


@dataclass(frozen=True)
class _Candidate:
    edge: LineageEdge
    source: Detection
    target: Detection
    edge_distance_um: float
    prediction_error_um: float
    forward_margin_um: float | None
    reverse_margin_um: float | None
    local_target_count: int
    local_competing_source_count: int

    @property
    def ambiguity_key(self) -> tuple[float, float, str, str]:
        margins = [
            margin
            for margin in (self.forward_margin_um, self.reverse_margin_um)
            if margin is not None
        ]
        minimum_margin = min(margins, default=math.inf)
        return minimum_margin, self.prediction_error_um, self.edge.source_id, self.edge.target_id


def audit_motion_mutual_commitment(
    graph: LineageGraph,
    *,
    max_link_distance_um: float = 9.0,
    horizon_frames: int = 2,
    max_counterfactual_edges: int = 64,
) -> CommitmentShadowSummary:
    """Measure motion-history sensitivity without changing the input graph.

    For each selected accepted edge, the edge's predecessor contribution is
    removed from its target and motion-mutual linking is replayed over a short
    future window. Divergence is a stability signal, not evidence of an error.
    """

    if max_link_distance_um <= 0.0:
        raise ValueError("max_link_distance_um must be positive")
    if horizon_frames < 1:
        raise ValueError("horizon_frames must be at least 1")
    if max_counterfactual_edges < 0:
        raise ValueError("max_counterfactual_edges must be non-negative")

    nodes = {node.node_id: node for node in graph.detections}
    if len(nodes) != len(graph.detections):
        raise ValueError("Detection node IDs must be unique")
    frames: dict[int, list[Detection]] = defaultdict(list)
    for node in graph.detections:
        frames[int(node.t)].append(node)
    for frame_nodes in frames.values():
        frame_nodes.sort(key=lambda node: node.node_id)

    parent_by_node_id: dict[str, Detection] = {}
    baseline_by_frame: dict[int, list[LineageEdge]] = defaultdict(list)
    for edge in graph.edges:
        source = nodes.get(edge.source_id)
        target = nodes.get(edge.target_id)
        if source is None or target is None or edge.relation != "continuation":
            continue
        if int(target.t) != int(source.t) + 1:
            continue
        if target.node_id in parent_by_node_id:
            raise ValueError(f"Multiple continuation parents for {target.node_id}")
        parent_by_node_id[target.node_id] = source
        baseline_by_frame[int(source.t)].append(edge)

    last_frame = max(frames, default=-1)
    candidates: list[_Candidate] = []
    for source_frame, edges in baseline_by_frame.items():
        if source_frame + 2 > last_frame:
            continue
        source_nodes = frames[source_frame]
        target_nodes = frames[source_frame + 1]
        source_tree = _tree(source_nodes)
        target_tree = _tree(target_nodes)
        for edge in sorted(edges, key=lambda item: (item.source_id, item.target_id)):
            source = nodes[edge.source_id]
            target = nodes[edge.target_id]
            predecessor = parent_by_node_id.get(source.node_id)
            predicted = _predicted_position(source, predecessor)
            prediction_error = float(np.linalg.norm(predicted - np.asarray(target.position_um)))
            edge_distance = float(np.linalg.norm(np.asarray(source.position_um) - np.asarray(target.position_um)))
            candidates.append(
                _Candidate(
                    edge=edge,
                    source=source,
                    target=target,
                    edge_distance_um=edge_distance,
                    prediction_error_um=prediction_error,
                    forward_margin_um=_selected_margin(target_tree, predicted, target_nodes, target.node_id),
                    reverse_margin_um=_selected_margin(
                        source_tree,
                        np.asarray(target.position_um, dtype=float),
                        source_nodes,
                        source.node_id,
                    ),
                    local_target_count=len(
                        target_tree.query_ball_point(
                            np.asarray(source.position_um, dtype=float),
                            r=max_link_distance_um,
                        )
                    ),
                    local_competing_source_count=max(
                        0,
                        len(
                            source_tree.query_ball_point(
                                np.asarray(target.position_um, dtype=float),
                                r=max_link_distance_um,
                            )
                        )
                        - 1,
                    ),
                )
            )

    selected = sorted(candidates, key=lambda candidate: candidate.ambiguity_key)[
        :max_counterfactual_edges
    ]
    records: list[CommitmentShadowRecord] = []
    for candidate in selected:
        changed_assignments, reconverged = _replay_without_predecessor(
            candidate,
            frames,
            baseline_by_frame,
            parent_by_node_id,
            max_link_distance_um,
            horizon_frames,
            last_frame,
        )
        records.append(
            CommitmentShadowRecord(
                source_id=candidate.source.node_id,
                target_id=candidate.target.node_id,
                source_frame=int(candidate.source.t),
                edge_distance_um=candidate.edge_distance_um,
                prediction_error_um=candidate.prediction_error_um,
                forward_margin_um=candidate.forward_margin_um,
                reverse_margin_um=candidate.reverse_margin_um,
                local_target_count=candidate.local_target_count,
                local_competing_source_count=candidate.local_competing_source_count,
                changed_assignment_count=changed_assignments,
                reconverged=reconverged,
            )
        )

    return CommitmentShadowSummary(
        sample_id=graph.sample_id,
        horizon_frames=horizon_frames,
        max_counterfactual_edges=max_counterfactual_edges,
        eligible_edge_count=len(candidates),
        counterfactual_edge_count=len(records),
        commitment_sensitive_edge_count=sum(
            record.changed_assignment_count > 0 and not record.reconverged
            for record in records
        ),
        records=tuple(records),
    )


def _replay_without_predecessor(
    candidate: _Candidate,
    frames: dict[int, list[Detection]],
    baseline_by_frame: dict[int, list[LineageEdge]],
    parent_by_node_id: dict[str, Detection],
    max_link_distance_um: float,
    horizon_frames: int,
    last_frame: int,
) -> tuple[int, bool]:
    counterfactual_parents = dict(parent_by_node_id)
    counterfactual_parents.pop(candidate.target.node_id, None)
    changed = 0
    final_equal = True
    first_replay_frame = int(candidate.target.t)
    final_replay_frame = min(last_frame - 1, first_replay_frame + horizon_frames - 1)

    for source_frame in range(first_replay_frame, final_replay_frame + 1):
        counterfactual_edges = link_adjacent_timepoints(
            frames.get(source_frame, []),
            frames.get(source_frame + 1, []),
            max_link_distance_um,
            strategy="motion_mutual",
            predecessor_by_node_id=counterfactual_parents,
        )
        baseline_assignments = {
            edge.source_id: edge.target_id for edge in baseline_by_frame.get(source_frame, [])
        }
        counterfactual_assignments = {
            edge.source_id: edge.target_id for edge in counterfactual_edges
        }
        changed += sum(
            baseline_assignments.get(source_id) != counterfactual_assignments.get(source_id)
            for source_id in set(baseline_assignments) | set(counterfactual_assignments)
        )
        final_equal = baseline_assignments == counterfactual_assignments

        for target in frames.get(source_frame + 1, []):
            counterfactual_parents.pop(target.node_id, None)
        source_lookup = {node.node_id: node for node in frames.get(source_frame, [])}
        for edge in counterfactual_edges:
            counterfactual_parents[edge.target_id] = source_lookup[edge.source_id]

    return changed, final_equal


def _tree(nodes: list[Detection]) -> cKDTree:
    return cKDTree(np.asarray([node.position_um for node in nodes], dtype=float))


def _predicted_position(source: Detection, predecessor: Detection | None) -> np.ndarray:
    source_position = np.asarray(source.position_um, dtype=float)
    if predecessor is None:
        return source_position
    return source_position + source_position - np.asarray(predecessor.position_um, dtype=float)


def _selected_margin(
    tree: cKDTree,
    position: np.ndarray,
    nodes: list[Detection],
    selected_node_id: str,
) -> float | None:
    neighbor_count = min(2, len(nodes))
    distances, indices = tree.query(position, k=neighbor_count)
    distance_values = np.atleast_1d(distances)
    index_values = np.atleast_1d(indices)
    selected_rank = next(
        (
            rank
            for rank, index in enumerate(index_values)
            if nodes[int(index)].node_id == selected_node_id
        ),
        None,
    )
    if selected_rank is None or neighbor_count < 2:
        return None
    alternative_rank = 1 if selected_rank == 0 else 0
    return float(distance_values[alternative_rank] - distance_values[selected_rank])