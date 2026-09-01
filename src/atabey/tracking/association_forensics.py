from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Literal, Mapping, Sequence

import numpy as np

from atabey.types import Detection, LineageEdge, LineageGraph


FailureClass = Literal[
    "candidate_generation_failure",
    "candidate_selection_ranking_failure",
    "post_link_pruning_interaction",
    "metric_node_adjustment_only_effect",
    "unresolved_insufficient_telemetry",
]


@dataclass(frozen=True)
class AssociationCandidate:
    source_id: str
    target_id: str
    source_t: int
    target_t: int
    rank: int
    prediction_error_um: float
    edge_length_um: float
    reverse_nearest_source_id: str | None
    mutual: bool
    accepted: bool
    survives_pruning: bool | None


@dataclass(frozen=True)
class SourceAssociationTelemetry:
    source_id: str
    source_t: int
    candidate_count: int
    nearest_target_id: str | None
    nearest_distance_um: float | None
    second_nearest_distance_um: float | None
    nearest_second_margin_um: float | None
    mutuality_conflict: bool
    unmatched: bool
    accepted_target_id: str | None
    accepted_edge_length_um: float | None
    accepted_prediction_error_um: float | None
    velocity_um: tuple[float, float, float] | None
    local_source_density: int
    local_target_density: int
    crossing_competitor_count: int


@dataclass(frozen=True)
class AssociationFrameAudit:
    source_t: int
    candidates: tuple[AssociationCandidate, ...]
    sources: tuple[SourceAssociationTelemetry, ...]


@dataclass(frozen=True)
class AssociationGraphAudit:
    sample_id: str
    frames: tuple[AssociationFrameAudit, ...]
    graph_unchanged: bool


def classify_regression_mechanism(
    *,
    correct_source_detected: bool | None,
    correct_target_detected: bool | None,
    correct_candidate_present: bool | None,
    correct_candidate_accepted: bool | None,
    correct_edge_survives_pruning: bool | None,
    adjustment_only_effect: bool,
) -> FailureClass:
    if adjustment_only_effect:
        return "metric_node_adjustment_only_effect"
    if correct_source_detected is False or correct_target_detected is False:
        return "candidate_generation_failure"
    if correct_candidate_present is False:
        return "candidate_generation_failure"
    if correct_candidate_present is True and correct_candidate_accepted is False:
        return "candidate_selection_ranking_failure"
    if correct_candidate_accepted is True and correct_edge_survives_pruning is False:
        return "post_link_pruning_interaction"
    return "unresolved_insufficient_telemetry"


def audit_motion_mutual_graph(
    graph: LineageGraph,
    *,
    max_link_distance_um: float = 9.0,
    post_pruning_graph: LineageGraph | None = None,
) -> AssociationGraphAudit:
    """Reconstruct frame-level linker telemetry from a completed relink graph."""

    before = _graph_signature(graph)
    frames: dict[int, list[Detection]] = defaultdict(list)
    nodes = {node.node_id: node for node in graph.detections}
    for node in graph.detections:
        frames[int(node.t)].append(node)
    for frame_nodes in frames.values():
        frame_nodes.sort(key=lambda node: node.node_id)

    predecessor_by_node_id: dict[str, Detection] = {}
    edges_by_source_t: dict[int, list[LineageEdge]] = defaultdict(list)
    for edge in graph.edges:
        source = nodes.get(edge.source_id)
        target = nodes.get(edge.target_id)
        if source is None or target is None or edge.relation != "continuation":
            continue
        if int(target.t) != int(source.t) + 1:
            continue
        predecessor_by_node_id[target.node_id] = source
        edges_by_source_t[int(source.t)].append(edge)

    surviving_edges = (
        {
            (edge.source_id, edge.target_id)
            for edge in post_pruning_graph.edges
            if edge.relation == "continuation"
        }
        if post_pruning_graph is not None
        else None
    )
    audits = tuple(
        audit_motion_mutual_frame(
            frames.get(source_t, ()),
            frames.get(source_t + 1, ()),
            max_link_distance_um,
            predecessor_by_node_id,
            edges_by_source_t.get(source_t, ()),
            surviving_edges=surviving_edges,
        )
        for source_t in range(max(frames, default=0))
        if frames.get(source_t) and frames.get(source_t + 1)
    )
    return AssociationGraphAudit(
        sample_id=graph.sample_id,
        frames=audits,
        graph_unchanged=_graph_signature(graph) == before,
    )


def association_frame_payload(
    audit: AssociationFrameAudit,
    previous: Sequence[Detection],
    current: Sequence[Detection],
    *,
    v19_edges: Sequence[LineageEdge] = (),
) -> dict[str, object]:
    """Return deterministic layers for a frame-by-frame visualization client."""

    source_rows = {row.source_id: row for row in audit.sources}
    return {
        "source_t": audit.source_t,
        "nodes": [
            {
                "node_id": node.node_id,
                "t": int(node.t),
                "position_um": [float(value) for value in node.position_um],
                "role": "source" if int(node.t) == audit.source_t else "target",
                "nearest_second_margin_um": (
                    source_rows[node.node_id].nearest_second_margin_um
                    if node.node_id in source_rows
                    else None
                ),
            }
            for node in sorted((*previous, *current), key=lambda item: (item.t, item.node_id))
        ],
        "candidate_edges": [
            {
                "source_id": candidate.source_id,
                "target_id": candidate.target_id,
                "rank": candidate.rank,
                "accepted": candidate.accepted,
                "mutual": candidate.mutual,
                "survives_pruning": candidate.survives_pruning,
                "prediction_error_um": candidate.prediction_error_um,
                "edge_length_um": candidate.edge_length_um,
            }
            for candidate in audit.candidates
        ],
        "v19_edges": [
            {"source_id": edge.source_id, "target_id": edge.target_id}
            for edge in sorted(v19_edges, key=lambda item: (item.source_id, item.target_id))
        ],
    }


def association_graph_payload(
    audit: AssociationGraphAudit,
    relink_graph: LineageGraph,
    post_pruning_graph: LineageGraph,
    v19_graph: LineageGraph,
) -> dict[str, object]:
    """Build deterministic frame layers for read-only V19/V24 inspection."""

    relink_frames: dict[int, list[Detection]] = defaultdict(list)
    v19_frames: dict[int, list[Detection]] = defaultdict(list)
    relink_nodes = {node.node_id: node for node in relink_graph.detections}
    v19_nodes = {node.node_id: node for node in v19_graph.detections}
    post_node_ids = {node.node_id for node in post_pruning_graph.detections}
    post_edge_ids = {
        (edge.source_id, edge.target_id) for edge in post_pruning_graph.edges
    }
    for node in relink_graph.detections:
        relink_frames[int(node.t)].append(node)
    for node in v19_graph.detections:
        v19_frames[int(node.t)].append(node)

    frames: list[dict[str, object]] = []
    for frame_audit in audit.frames:
        source_t = frame_audit.source_t
        v19_edges = [
            edge
            for edge in v19_graph.edges
            if edge.source_id in v19_nodes
            and int(v19_nodes[edge.source_id].t) == source_t
        ]
        payload = association_frame_payload(
            frame_audit,
            relink_frames.get(source_t, ()),
            relink_frames.get(source_t + 1, ()),
            v19_edges=v19_edges,
        )
        payload["v19_nodes"] = [
            {
                "node_id": node.node_id,
                "t": int(node.t),
                "position_um": [float(value) for value in node.position_um],
            }
            for node in sorted(
                (*v19_frames.get(source_t, ()), *v19_frames.get(source_t + 1, ())),
                key=lambda item: (item.t, item.node_id),
            )
        ]
        payload["v24_3_pruned_node_ids"] = sorted(
            node.node_id
            for node in (*relink_frames.get(source_t, ()), *relink_frames.get(source_t + 1, ()))
            if node.node_id not in post_node_ids
        )
        payload["v24_3_retained_edges"] = [
            {"source_id": source_id, "target_id": target_id}
            for source_id, target_id in sorted(post_edge_ids)
            if source_id in relink_nodes and int(relink_nodes[source_id].t) == source_t
        ]
        frames.append(payload)
    return {
        "sample_id": relink_graph.sample_id,
        "coordinate_system": "physical_microns_zyx",
        "frames": frames,
        "read_only": True,
    }


def _graph_signature(graph: LineageGraph) -> tuple[tuple[object, ...], tuple[object, ...]]:
    return (
        tuple(graph.detections),
        tuple(graph.edges),
    )


def audit_motion_mutual_frame(
    previous: Sequence[Detection],
    current: Sequence[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
    accepted_edges: Sequence[LineageEdge],
    *,
    surviving_edges: set[tuple[str, str]] | None = None,
) -> AssociationFrameAudit:
    """Observe frozen motion-mutual inputs and outputs without changing them."""

    if max_link_distance_um <= 0.0:
        raise ValueError("max_link_distance_um must be positive")
    source_t = int(previous[0].t) if previous else -1
    if not previous or not current:
        return AssociationFrameAudit(source_t=source_t, candidates=(), sources=())

    previous_positions = np.asarray([node.position_um for node in previous], dtype=float)
    current_positions = np.asarray([node.position_um for node in current], dtype=float)
    accepted_by_source = {edge.source_id: edge.target_id for edge in accepted_edges}
    reverse_nearest: dict[int, int] = {}
    for target_index, target_position in enumerate(current_positions):
        distances = np.linalg.norm(previous_positions - target_position, axis=1)
        nearest_source = int(np.argmin(distances))
        if float(distances[nearest_source]) <= max_link_distance_um:
            reverse_nearest[target_index] = nearest_source

    preferred_target_counts: dict[int, int] = {}
    ranked_by_source: dict[int, list[tuple[int, float, float]]] = {}
    for source_index, source in enumerate(previous):
        source_position = previous_positions[source_index]
        predecessor = predecessor_by_node_id.get(source.node_id)
        if predecessor is None:
            predicted = source_position
        else:
            predicted = source_position + (
                source_position - np.asarray(predecessor.position_um, dtype=float)
            )
        prediction_errors = np.linalg.norm(current_positions - predicted, axis=1)
        step_distances = np.linalg.norm(current_positions - source_position, axis=1)
        ranked = sorted(
            (
                (target_index, float(prediction_errors[target_index]), float(step_distances[target_index]))
                for target_index in range(len(current))
                if float(prediction_errors[target_index]) <= max_link_distance_um
                and float(step_distances[target_index]) <= max_link_distance_um
            ),
            key=lambda item: (item[1], current[item[0]].node_id),
        )
        ranked_by_source[source_index] = ranked
        if ranked:
            preferred_target_counts[ranked[0][0]] = preferred_target_counts.get(ranked[0][0], 0) + 1

    candidates: list[AssociationCandidate] = []
    source_rows: list[SourceAssociationTelemetry] = []
    for source_index, source in enumerate(previous):
        ranked = ranked_by_source[source_index]
        accepted_target_id = accepted_by_source.get(source.node_id)
        for rank, (target_index, prediction_error, edge_length) in enumerate(ranked, start=1):
            target = current[target_index]
            reverse_source_index = reverse_nearest.get(target_index)
            candidates.append(
                AssociationCandidate(
                    source_id=source.node_id,
                    target_id=target.node_id,
                    source_t=int(source.t),
                    target_t=int(target.t),
                    rank=rank,
                    prediction_error_um=prediction_error,
                    edge_length_um=edge_length,
                    reverse_nearest_source_id=(
                        previous[reverse_source_index].node_id
                        if reverse_source_index is not None
                        else None
                    ),
                    mutual=reverse_source_index == source_index,
                    accepted=accepted_target_id == target.node_id,
                    survives_pruning=(
                        None
                        if surviving_edges is None
                        else (source.node_id, target.node_id) in surviving_edges
                    ),
                )
            )

        nearest = ranked[0] if ranked else None
        second = ranked[1] if len(ranked) > 1 else None
        accepted = next(
            (candidate for candidate in candidates if candidate.source_id == source.node_id and candidate.accepted),
            None,
        )
        predecessor = predecessor_by_node_id.get(source.node_id)
        velocity = (
            tuple(
                float(value)
                for value in np.asarray(source.position_um, dtype=float)
                - np.asarray(predecessor.position_um, dtype=float)
            )
            if predecessor is not None
            else None
        )
        source_rows.append(
            SourceAssociationTelemetry(
                source_id=source.node_id,
                source_t=int(source.t),
                candidate_count=len(ranked),
                nearest_target_id=current[nearest[0]].node_id if nearest else None,
                nearest_distance_um=nearest[1] if nearest else None,
                second_nearest_distance_um=second[1] if second else None,
                nearest_second_margin_um=(second[1] - nearest[1]) if second and nearest else None,
                mutuality_conflict=(
                    bool(nearest) and reverse_nearest.get(nearest[0]) != source_index
                ),
                unmatched=accepted_target_id is None,
                accepted_target_id=accepted_target_id,
                accepted_edge_length_um=accepted.edge_length_um if accepted else None,
                accepted_prediction_error_um=(
                    accepted.prediction_error_um if accepted else None
                ),
                velocity_um=velocity,
                local_source_density=int(
                    np.sum(np.linalg.norm(previous_positions - previous_positions[source_index], axis=1) <= max_link_distance_um)
                ) - 1,
                local_target_density=len(ranked),
                crossing_competitor_count=(
                    max(0, preferred_target_counts.get(nearest[0], 0) - 1)
                    if nearest
                    else 0
                ),
            )
        )

    if any(not math.isfinite(candidate.prediction_error_um) for candidate in candidates):
        raise ValueError("candidate telemetry contains a non-finite distance")
    return AssociationFrameAudit(
        source_t=source_t,
        candidates=tuple(candidates),
        sources=tuple(source_rows),
    )