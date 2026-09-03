from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

from atabey.tracking.nearest_neighbor import _greedy_assign, _predicted_position
from atabey.tracking.unet_graph import (
    DEFAULT_VOXEL_SCALE_UM,
    VoxelScale,
    detections_from_predictor_coordinates,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def link_step_ranked_motion_mutual(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
) -> list[LineageEdge]:
    """Replace only forward motion ranking with physical-step ranking."""

    if max_link_distance_um <= 0:
        raise ValueError("max_link_distance_um must be positive")
    if not previous or not current:
        return []

    previous_positions = np.array([node.position_um for node in previous], dtype=float)
    current_positions = np.array([node.position_um for node in current], dtype=float)

    try:
        from scipy.spatial import cKDTree
    except ImportError as exc:
        raise RuntimeError("V26A requires the pinned SciPy cKDTree runtime") from exc

    previous_tree = cKDTree(previous_positions)
    target_to_source: dict[int, int] = {}
    for target_idx, target in enumerate(current):
        distance, source_idx = previous_tree.query(target.position_um, k=1)
        if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um:
            target_to_source[target_idx] = int(source_idx)

    candidate_pairs: list[tuple[float, Detection, Detection]] = []
    for source_idx, source in enumerate(previous):
        source_position = previous_positions[source_idx]
        predicted_position = _predicted_position(
            source, predecessor_by_node_id.get(source.node_id)
        )
        prediction_errors = np.linalg.norm(current_positions - predicted_position, axis=1)
        step_distances = np.linalg.norm(current_positions - source_position, axis=1)
        feasible_indices = np.flatnonzero(
            np.isfinite(prediction_errors)
            & (prediction_errors <= max_link_distance_um)
            & np.isfinite(step_distances)
            & (step_distances <= max_link_distance_um)
        )
        if feasible_indices.size == 0:
            continue
        target_idx = min(
            (int(index) for index in feasible_indices),
            key=lambda index: (float(step_distances[index]), index),
        )
        if target_to_source.get(target_idx) != source_idx:
            continue
        candidate_pairs.append(
            (float(prediction_errors[target_idx]), source, current[target_idx])
        )

    return _greedy_assign(candidate_pairs, max_link_distance_um)


def relink_predictor_detections_step_ranked(
    sample_id: str,
    coordinates: Sequence[Sequence[float]],
    *,
    max_link_distance_um: float = 9.0,
    voxel_scale: VoxelScale = DEFAULT_VOXEL_SCALE_UM,
) -> LineageGraph:
    """Build a new graph with the V26A shadow linker and frozen detections."""

    if max_link_distance_um <= 0:
        raise ValueError("max_link_distance_um must be positive")
    detections = detections_from_predictor_coordinates(
        sample_id,
        coordinates,
        voxel_scale=voxel_scale,
    )
    return relink_detections_step_ranked(
        sample_id,
        detections,
        max_link_distance_um=max_link_distance_um,
    )


def relink_detections_step_ranked(
    sample_id: str,
    detections: Sequence[Detection],
    *,
    max_link_distance_um: float = 9.0,
) -> LineageGraph:
    """Build a new V26A graph over an immutable frozen detection sequence."""

    if max_link_distance_um <= 0:
        raise ValueError("max_link_distance_um must be positive")
    graph = LineageGraph(sample_id=sample_id)
    by_time: dict[int, list[Detection]] = {}
    for detection in detections:
        if detection.sample_id != sample_id:
            raise ValueError("Detection sample_id does not match graph sample_id")
        graph.add_detection(detection)
        by_time.setdefault(detection.t, []).append(detection)

    predecessor_by_node_id: dict[str, Detection] = {}
    previous: list[Detection] = []
    for t in range(max(by_time, default=-1) + 1):
        current = by_time.get(t, [])
        edges = link_step_ranked_motion_mutual(
            previous,
            current,
            max_link_distance_um,
            predecessor_by_node_id,
        )
        previous_by_id = {node.node_id: node for node in previous}
        for edge in edges:
            graph.add_edge(edge)
            predecessor_by_node_id[edge.target_id] = previous_by_id[edge.source_id]
        previous = current
    return graph