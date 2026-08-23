from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from math import dist
from typing import Any, Iterable, Iterator, Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree

from atabey.tracking.continuation_reference import ContinuationReference
from atabey.types import Detection, LineageGraph


CONTINUATION_FEATURE_NAMES = (
    "anchor_parent_distance_um",
    "parent_child_distance_um",
    "prediction_error_um",
    "step_distance_ratio",
    "radial_speed_change_um_per_frame",
    "turn_angle_deg",
    "forward_competitor_margin_um",
    "reverse_competitor_margin_um",
    "forward_rank_local_14um",
    "reverse_rank_local_14um",
    "parent_density_10um",
    "child_density_10um",
    "local_target_count_14um",
    "local_competing_source_count_14um",
)


def continuation_candidate_id(
    reference_id: str,
    candidate_child_id: str,
) -> str:
    payload = f"{reference_id}|{candidate_child_id}"
    return "v22cc:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def iter_continuation_candidate_rows(
    graph: LineageGraph,
    references: Sequence[ContinuationReference],
    *,
    fold: int,
    detector: str,
    link_strategy: str,
    local_radius_um: float = 14.0,
    density_radius_um: float = 10.0,
) -> Iterator[dict[str, Any]]:
    """Yield route-neutral continuation candidates without mutating ``graph``."""

    if local_radius_um <= 0.0:
        raise ValueError("local_radius_um must be positive")
    if density_radius_um <= 0.0:
        raise ValueError("density_radius_um must be positive")

    nodes = {node.node_id: node for node in graph.detections}
    if len(nodes) != len(graph.detections):
        raise ValueError("Detection node IDs must be unique")
    frames: dict[int, list[Detection]] = defaultdict(list)
    for node in graph.detections:
        frames[int(node.t)].append(node)
    for frame_nodes in frames.values():
        frame_nodes.sort(key=lambda node: node.node_id)
    trees = {
        t: cKDTree(np.asarray([node.position_um for node in frame_nodes], dtype=float))
        for t, frame_nodes in frames.items()
        if frame_nodes
    }

    references_by_frame = Counter(int(reference.parent_t) for reference in references)
    represented_frames = len(references_by_frame)
    if references and represented_frames == 0:
        raise RuntimeError("References do not contain a represented parent frame")

    for reference in references:
        anchor = nodes[reference.anchor_id]
        parent = nodes[reference.parent_id]
        reference_child = nodes[reference.child_id]
        source_nodes = frames[int(parent.t)]
        target_nodes = frames[int(reference_child.t)]
        source_tree = trees[int(parent.t)]
        target_tree = trees[int(reference_child.t)]
        candidate_indices = target_tree.query_ball_point(
            np.asarray(parent.position_um, dtype=float),
            r=float(local_radius_um),
        )
        candidates = sorted(
            (target_nodes[int(index)] for index in candidate_indices),
            key=lambda node: node.node_id,
        )
        if not any(node.node_id == reference.child_id for node in candidates):
            raise RuntimeError(
                f"{reference.reference_id}: reference child missing from local candidates"
            )

        predicted = 2.0 * np.asarray(parent.position_um) - np.asarray(
            anchor.position_um
        )
        prediction_errors = {
            child.node_id: float(
                np.linalg.norm(np.asarray(child.position_um) - predicted)
            )
            for child in candidates
        }
        forward_distances, forward_indices = target_tree.query(
            predicted,
            k=min(2, len(target_nodes)),
        )
        global_forward_nearest = tuple(
            (float(distance_um), target_nodes[int(index)].node_id)
            for distance_um, index in zip(
                np.atleast_1d(forward_distances),
                np.atleast_1d(forward_indices),
                strict=True,
            )
        )
        forward_order = sorted(
            candidates,
            key=lambda child: (prediction_errors[child.node_id], child.node_id),
        )
        forward_ranks = {
            child.node_id: rank for rank, child in enumerate(forward_order, start=1)
        }
        parent_density = len(
            source_tree.query_ball_point(
                np.asarray(parent.position_um),
                r=float(density_radius_um),
            )
        )
        candidate_count = len(candidates)
        frame_reference_count = references_by_frame[int(reference.parent_t)]
        hierarchical_weight = (
            1.0
            / float(represented_frames)
            / float(frame_reference_count)
            / float(candidate_count)
        )

        for child in candidates:
            row = _candidate_feature_row(
                anchor=anchor,
                parent=parent,
                child=child,
                source_nodes=source_nodes,
                source_tree=source_tree,
                target_nodes=target_nodes,
                target_tree=target_tree,
                prediction_errors=prediction_errors,
                global_forward_nearest=global_forward_nearest,
                forward_ranks=forward_ranks,
                local_radius_um=local_radius_um,
                density_radius_um=density_radius_um,
                parent_density=parent_density,
            )
            is_reference = child.node_id == reference.child_id
            yield {
                "candidate_id": continuation_candidate_id(
                    reference.reference_id, child.node_id
                ),
                "reference_id": reference.reference_id,
                "sample_id": graph.sample_id,
                "fold": int(fold),
                "family": graph.sample_id.split("_", 1)[0],
                "route": f"{detector}/{link_strategy}",
                "parent_t": int(reference.parent_t),
                "anchor_id": anchor.node_id,
                "parent_id": parent.node_id,
                "candidate_child_id": child.node_id,
                "reference_child_id": reference.child_id,
                "candidate_role": (
                    "weak_reference_preferred"
                    if is_reference
                    else "weak_alternative_unknown"
                ),
                "weak_preference_target": int(is_reference),
                "biological_label": "unknown",
                "reference_is_ground_truth": False,
                "alternative_is_negative": False,
                **row,
                "sample_hierarchical_weight": hierarchical_weight,
                "semantic_score": "",
                "assignment_selected": False,
                "graph_mutated": False,
            }


def _candidate_feature_row(
    *,
    anchor: Detection,
    parent: Detection,
    child: Detection,
    source_nodes: Sequence[Detection],
    source_tree: cKDTree,
    target_nodes: Sequence[Detection],
    target_tree: cKDTree,
    prediction_errors: Mapping[str, float],
    global_forward_nearest: Sequence[tuple[float, str]],
    forward_ranks: Mapping[str, int],
    local_radius_um: float,
    density_radius_um: float,
    parent_density: int,
) -> dict[str, Any]:
    anchor_position = np.asarray(anchor.position_um, dtype=float)
    parent_position = np.asarray(parent.position_um, dtype=float)
    child_position = np.asarray(child.position_um, dtype=float)
    parent_step = parent_position - anchor_position
    child_step = child_position - parent_position
    parent_distance = float(np.linalg.norm(parent_step))
    child_distance = float(np.linalg.norm(child_step))
    prediction_error = float(prediction_errors[child.node_id])

    forward_other = [
        distance_um
        for distance_um, node_id in global_forward_nearest
        if node_id != child.node_id
    ]
    forward_margin = (
        min(forward_other) - prediction_error if forward_other else None
    )
    source_distances = sorted(
        (
            dist(source.position_um, child.position_um),
            source.node_id,
        )
        for source in source_nodes
        if dist(source.position_um, child.position_um) <= local_radius_um
    )
    reverse_rank = next(
        rank
        for rank, (_distance, node_id) in enumerate(source_distances, start=1)
        if node_id == parent.node_id
    )
    reverse_distances, reverse_indices = source_tree.query(
        child_position,
        k=min(2, len(source_nodes)),
    )
    reverse_other = [
        float(distance_um)
        for distance_um, index in zip(
            np.atleast_1d(reverse_distances),
            np.atleast_1d(reverse_indices),
            strict=True,
        )
        if source_nodes[int(index)].node_id != parent.node_id
    ]
    reverse_margin = (
        min(reverse_other) - child_distance if reverse_other else None
    )
    child_density = len(
        target_tree.query_ball_point(
            child_position,
            r=float(density_radius_um),
        )
    )
    local_competing_sources = max(0, len(source_distances) - 1)

    values: dict[str, float | int | None] = {
        "anchor_parent_distance_um": parent_distance,
        "parent_child_distance_um": child_distance,
        "prediction_error_um": prediction_error,
        "step_distance_ratio": (
            child_distance / parent_distance if parent_distance > 1e-9 else None
        ),
        "radial_speed_change_um_per_frame": child_distance - parent_distance,
        "turn_angle_deg": _angle(parent_step, child_step),
        "forward_competitor_margin_um": forward_margin,
        "reverse_competitor_margin_um": reverse_margin,
        "forward_rank_local_14um": int(forward_ranks[child.node_id]),
        "reverse_rank_local_14um": int(reverse_rank),
        "parent_density_10um": int(parent_density),
        "child_density_10um": int(child_density),
        "local_target_count_14um": len(prediction_errors),
        "local_competing_source_count_14um": int(local_competing_sources),
    }
    missing_reasons = {
        "step_distance_ratio": "zero_anchor_parent_distance",
        "turn_angle_deg": "zero_motion_vector",
        "forward_competitor_margin_um": "no_other_local_target",
        "reverse_competitor_margin_um": "no_other_local_source",
    }
    available = sorted(name for name, value in values.items() if value is not None)
    missing = {
        name: missing_reasons.get(name, "unavailable")
        for name, value in values.items()
        if value is None
    }
    return {
        **values,
        "available_features": json.dumps(available, separators=(",", ":")),
        "missing_features": json.dumps(
            missing, sort_keys=True, separators=(",", ":")
        ),
    }


def _angle(first: np.ndarray, second: np.ndarray) -> float | None:
    first_norm = float(np.linalg.norm(first))
    second_norm = float(np.linalg.norm(second))
    if first_norm <= 1e-9 or second_norm <= 1e-9:
        return None
    cosine = float(np.dot(first, second) / (first_norm * second_norm))
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
