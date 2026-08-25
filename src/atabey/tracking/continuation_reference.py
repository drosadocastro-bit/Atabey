from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
from math import dist
from typing import Iterable, Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree

from atabey.types import Detection, LineageEdge, LineageGraph


@dataclass(frozen=True)
class ContinuationReference:
    reference_id: str
    sample_id: str
    anchor_id: str
    parent_id: str
    child_id: str
    anchor_t: int
    parent_t: int
    child_t: int
    anchor_parent_distance_um: float
    parent_child_distance_um: float
    prediction_error_um: float
    forward_margin_um: float | None
    reverse_margin_um: float | None
    local_target_count_14um: int
    alternative_target_count_14um: int
    local_competing_source_count_14um: int


@dataclass(frozen=True)
class ContinuationReferenceAudit:
    sample_id: str
    references: tuple[ContinuationReference, ...]
    funnel: Mapping[str, int]
    rejection_reasons: Mapping[str, int]


def extract_continuation_references(
    graph: LineageGraph,
    *,
    registered_division_times: Iterable[int],
    exclusion_radius_frames: int = 2,
    local_radius_um: float = 14.0,
    tie_tolerance_um: float = 1e-6,
) -> ContinuationReferenceAudit:
    """Extract high-confidence V19 continuation references without mutation.

    A retained reference is a consecutive three-frame continuation chain
    ``anchor -> parent -> child``. Ownership is exclusive in the source graph,
    and the central edge independently passes the motion-predicted forward /
    raw reverse mutual-nearest identity test used by V19 motion-mutual linking.
    """

    if exclusion_radius_frames < 0:
        raise ValueError("exclusion_radius_frames must be non-negative")
    if local_radius_um <= 0.0:
        raise ValueError("local_radius_um must be positive")
    if tie_tolerance_um < 0.0:
        raise ValueError("tie_tolerance_um must be non-negative")

    nodes = {node.node_id: node for node in graph.detections}
    if len(nodes) != len(graph.detections):
        raise ValueError("Detection node IDs must be unique")

    frames: dict[int, list[Detection]] = defaultdict(list)
    for node in graph.detections:
        frames[int(node.t)].append(node)
    for frame_nodes in frames.values():
        frame_nodes.sort(key=lambda node: node.node_id)

    incoming: dict[str, list[LineageEdge]] = defaultdict(list)
    outgoing: dict[str, list[LineageEdge]] = defaultdict(list)
    for edge in graph.edges:
        incoming[edge.target_id].append(edge)
        outgoing[edge.source_id].append(edge)
    for edges in incoming.values():
        edges.sort(key=lambda edge: (edge.source_id, edge.target_id))
    for edges in outgoing.values():
        edges.sort(key=lambda edge: (edge.source_id, edge.target_id))

    frame_trees = {
        t: cKDTree(np.asarray([node.position_um for node in frame_nodes], dtype=float))
        for t, frame_nodes in frames.items()
        if frame_nodes
    }
    division_times = tuple(sorted({int(t) for t in registered_division_times}))
    funnel: Counter[str] = Counter()
    rejections: Counter[str] = Counter()
    references: list[ContinuationReference] = []

    for edge in sorted(
        graph.edges,
        key=lambda item: (item.source_id, item.target_id, item.relation),
    ):
        funnel["graph_edges"] += 1
        parent = nodes.get(edge.source_id)
        child = nodes.get(edge.target_id)
        if parent is None or child is None:
            rejections["missing_edge_node"] += 1
            continue
        if int(child.t) != int(parent.t) + 1:
            rejections["nonconsecutive_edge"] += 1
            continue
        if edge.relation != "continuation":
            rejections["noncontinuation_edge"] += 1
            continue
        funnel["consecutive_continuation_edges"] += 1

        if len(outgoing[parent.node_id]) != 1 or len(incoming[child.node_id]) != 1:
            rejections["central_ownership_not_exclusive"] += 1
            continue
        funnel["central_single_ownership"] += 1

        parent_incoming = incoming[parent.node_id]
        if len(parent_incoming) != 1:
            rejections["missing_or_ambiguous_anchor"] += 1
            continue
        anchor_edge = parent_incoming[0]
        anchor = nodes.get(anchor_edge.source_id)
        if (
            anchor is None
            or int(anchor.t) != int(parent.t) - 1
            or anchor_edge.relation != "continuation"
        ):
            rejections["invalid_anchor_edge"] += 1
            continue
        if len(outgoing[anchor.node_id]) != 1:
            rejections["anchor_ownership_not_exclusive"] += 1
            continue
        funnel["three_frame_exclusive_chains"] += 1

        parent_child_distance = dist(parent.position_um, child.position_um)
        if parent_child_distance > local_radius_um:
            rejections["child_outside_local_radius"] += 1
            continue
        funnel["inside_local_radius"] += 1

        mutual = _motion_mutual_metrics(
            anchor=anchor,
            parent=parent,
            child=child,
            source_frame=frames[int(parent.t)],
            target_frame=frames[int(child.t)],
            source_tree=frame_trees[int(parent.t)],
            target_tree=frame_trees[int(child.t)],
            tie_tolerance_um=tie_tolerance_um,
        )
        if mutual is None:
            rejections["not_strict_motion_mutual"] += 1
            continue
        prediction_error, forward_margin, reverse_margin = mutual
        funnel["strict_motion_mutual"] += 1

        chain_times = (int(anchor.t), int(parent.t), int(child.t))
        if _within_division_exclusion(
            chain_times,
            division_times,
            exclusion_radius_frames,
        ):
            rejections["near_registered_division"] += 1
            continue
        funnel["outside_division_exclusion"] += 1

        target_neighbors = frame_trees[int(child.t)].query_ball_point(
            np.asarray(parent.position_um, dtype=float),
            r=float(local_radius_um),
        )
        local_target_count = len(target_neighbors)
        child_is_local = any(
            frames[int(child.t)][int(index)].node_id == child.node_id
            for index in target_neighbors
        )
        alternative_count = local_target_count - int(child_is_local)
        source_neighbors = frame_trees[int(parent.t)].query_ball_point(
            np.asarray(child.position_um, dtype=float),
            r=float(local_radius_um),
        )
        competing_source_count = max(0, len(source_neighbors) - 1)
        references.append(
            ContinuationReference(
                reference_id=_reference_id(graph.sample_id, anchor, parent, child),
                sample_id=graph.sample_id,
                anchor_id=anchor.node_id,
                parent_id=parent.node_id,
                child_id=child.node_id,
                anchor_t=int(anchor.t),
                parent_t=int(parent.t),
                child_t=int(child.t),
                anchor_parent_distance_um=dist(
                    anchor.position_um,
                    parent.position_um,
                ),
                parent_child_distance_um=parent_child_distance,
                prediction_error_um=prediction_error,
                forward_margin_um=forward_margin,
                reverse_margin_um=reverse_margin,
                local_target_count_14um=local_target_count,
                alternative_target_count_14um=alternative_count,
                local_competing_source_count_14um=competing_source_count,
            )
        )

    references.sort(key=lambda row: (row.parent_t, row.parent_id, row.child_id))
    funnel["eligible_references"] = len(references)
    return ContinuationReferenceAudit(
        sample_id=graph.sample_id,
        references=tuple(references),
        funnel=dict(sorted(funnel.items())),
        rejection_reasons=dict(sorted(rejections.items())),
    )


def reference_as_row(reference: ContinuationReference) -> dict[str, object]:
    return {
        "reference_id": reference.reference_id,
        "sample_id": reference.sample_id,
        "anchor_id": reference.anchor_id,
        "parent_id": reference.parent_id,
        "child_id": reference.child_id,
        "anchor_t": reference.anchor_t,
        "parent_t": reference.parent_t,
        "child_t": reference.child_t,
        "anchor_parent_distance_um": reference.anchor_parent_distance_um,
        "parent_child_distance_um": reference.parent_child_distance_um,
        "prediction_error_um": reference.prediction_error_um,
        "forward_margin_um": reference.forward_margin_um,
        "reverse_margin_um": reference.reverse_margin_um,
        "local_target_count_14um": reference.local_target_count_14um,
        "alternative_target_count_14um": reference.alternative_target_count_14um,
        "local_competing_source_count_14um": (
            reference.local_competing_source_count_14um
        ),
        "reference_is_ground_truth": False,
        "graph_mutated": False,
    }


def _motion_mutual_metrics(
    *,
    anchor: Detection,
    parent: Detection,
    child: Detection,
    source_frame: Sequence[Detection],
    target_frame: Sequence[Detection],
    source_tree: cKDTree,
    target_tree: cKDTree,
    tie_tolerance_um: float,
) -> tuple[float, float | None, float | None] | None:
    predicted = np.asarray(
        [
            2.0 * current - previous
            for current, previous in zip(
                parent.position_um,
                anchor.position_um,
                strict=True,
            )
        ],
        dtype=float,
    )
    forward = _strict_nearest(
        target_tree,
        target_frame,
        predicted,
        expected_node_id=child.node_id,
        tie_tolerance_um=tie_tolerance_um,
    )
    if forward is None:
        return None
    reverse = _strict_nearest(
        source_tree,
        source_frame,
        np.asarray(child.position_um, dtype=float),
        expected_node_id=parent.node_id,
        tie_tolerance_um=tie_tolerance_um,
    )
    if reverse is None:
        return None
    return forward[0], forward[1], reverse[1]


def _strict_nearest(
    tree: cKDTree,
    nodes: Sequence[Detection],
    query: np.ndarray,
    *,
    expected_node_id: str,
    tie_tolerance_um: float,
) -> tuple[float, float | None] | None:
    k = min(2, len(nodes))
    distances, indices = tree.query(query, k=k)
    distance_values = np.atleast_1d(distances).astype(float)
    index_values = np.atleast_1d(indices).astype(int)
    if not np.isfinite(distance_values[0]):
        return None
    if nodes[int(index_values[0])].node_id != expected_node_id:
        return None
    if len(distance_values) == 1:
        return float(distance_values[0]), None
    margin = float(distance_values[1] - distance_values[0])
    if margin <= tie_tolerance_um:
        return None
    return float(distance_values[0]), margin


def _within_division_exclusion(
    chain_times: Sequence[int],
    division_times: Sequence[int],
    radius: int,
) -> bool:
    return any(
        abs(int(chain_t) - int(division_t)) <= radius
        for chain_t in chain_times
        for division_t in division_times
    )


def _reference_id(
    sample_id: str,
    anchor: Detection,
    parent: Detection,
    child: Detection,
) -> str:
    payload = "|".join(
        (sample_id, anchor.node_id, parent.node_id, child.node_id)
    )
    return "v22c:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
