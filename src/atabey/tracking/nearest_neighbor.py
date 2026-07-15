from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

import numpy as np

from atabey.types import Detection, LineageEdge


LinkStrategy = Literal[
    "greedy",
    "mutual",
    "motion",
    "motion_division",
    "motion_mutual",
    "motion_crowding",
    "motion_mutual_latent",
    "bipartite",
]


def link_adjacent_timepoints(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    strategy: LinkStrategy = "greedy",
    predecessor_by_node_id: Mapping[str, Detection] | None = None,
) -> list[LineageEdge]:
    """Link detections from t to t+1 with a bounded nearest-neighbor strategy."""

    if strategy == "greedy":
        return link_adjacent_timepoints_greedy(previous, current, max_link_distance_um)
    if strategy == "mutual":
        return link_adjacent_timepoints_mutual(previous, current, max_link_distance_um)
    if strategy == "motion":
        return link_adjacent_timepoints_motion(
            previous,
            current,
            max_link_distance_um,
            predecessor_by_node_id=predecessor_by_node_id or {},
        )
    if strategy == "motion_division":
        return link_adjacent_timepoints_motion_division(
            previous,
            current,
            max_link_distance_um,
            predecessor_by_node_id=predecessor_by_node_id or {},
        )
    if strategy == "motion_mutual":
        return link_adjacent_timepoints_motion_mutual(
            previous,
            current,
            max_link_distance_um,
            predecessor_by_node_id=predecessor_by_node_id or {},
        )
    if strategy == "motion_mutual_latent":
        # Latent gap-bridging is orchestrated by the streaming baseline graph builder.
        # At adjacent-frame scope this strategy reduces to strict motion+mutual linking.
        return link_adjacent_timepoints_motion_mutual(
            previous,
            current,
            max_link_distance_um,
            predecessor_by_node_id=predecessor_by_node_id or {},
        )
    if strategy == "bipartite":
        return link_adjacent_timepoints_bipartite(
            previous,
            current,
            max_link_distance_um,
            predecessor_by_node_id=predecessor_by_node_id or {},
        )
    if strategy == "motion_crowding":
        return link_adjacent_timepoints_motion_crowding(
            previous,
            current,
            max_link_distance_um,
            predecessor_by_node_id=predecessor_by_node_id or {},
        )
    raise ValueError(f"Unknown link strategy: {strategy}")


def link_adjacent_timepoints_greedy(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
) -> list[LineageEdge]:
    """Link detections with one-way nearest-neighbor candidates and greedy assignment."""

    if not previous or not current:
        return []

    candidate_pairs: list[tuple[float, Detection, Detection]] = []
    current_positions = np.array([d.position_um for d in current], dtype=float)

    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(current_positions)
        for source in previous:
            distance, idx = tree.query(source.position_um, k=1)
            if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um:
                candidate_pairs.append((float(distance), source, current[int(idx)]))
    except ImportError:
        for source in previous:
            distances = np.linalg.norm(current_positions - np.array(source.position_um), axis=1)
            idx = int(np.argmin(distances))
            distance = float(distances[idx])
            if distance <= max_link_distance_um:
                candidate_pairs.append((distance, source, current[idx]))

    return _greedy_assign(candidate_pairs, max_link_distance_um)


def link_adjacent_timepoints_mutual(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
) -> list[LineageEdge]:
    """Link only pairs that are nearest neighbors in both temporal directions."""

    if not previous or not current:
        return []

    previous_positions = np.array([d.position_um for d in previous], dtype=float)
    current_positions = np.array([d.position_um for d in current], dtype=float)

    try:
        from scipy.spatial import cKDTree

        current_tree = cKDTree(current_positions)
        previous_tree = cKDTree(previous_positions)
        source_to_target: dict[int, tuple[int, float]] = {}
        for source_idx, source in enumerate(previous):
            distance, target_idx = current_tree.query(source.position_um, k=1)
            if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um:
                source_to_target[source_idx] = (int(target_idx), float(distance))

        target_to_source: dict[int, int] = {}
        for target_idx, target in enumerate(current):
            distance, source_idx = previous_tree.query(target.position_um, k=1)
            if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um:
                target_to_source[target_idx] = int(source_idx)
    except ImportError:
        distances = np.linalg.norm(previous_positions[:, None, :] - current_positions[None, :, :], axis=2)
        source_to_target = {}
        for source_idx in range(distances.shape[0]):
            target_idx = int(np.argmin(distances[source_idx]))
            distance = float(distances[source_idx, target_idx])
            if distance <= max_link_distance_um:
                source_to_target[source_idx] = (target_idx, distance)
        target_to_source = {}
        for target_idx in range(distances.shape[1]):
            source_idx = int(np.argmin(distances[:, target_idx]))
            distance = float(distances[source_idx, target_idx])
            if distance <= max_link_distance_um:
                target_to_source[target_idx] = source_idx

    edges: list[LineageEdge] = []
    for source_idx, (target_idx, distance) in sorted(source_to_target.items(), key=lambda item: item[1][1]):
        if target_to_source.get(target_idx) != source_idx:
            continue
        edges.append(_edge(previous[source_idx], current[target_idx], distance, max_link_distance_um))
    return edges


def link_adjacent_timepoints_motion(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
) -> list[LineageEdge]:
    """Link by nearest candidate to a one-step motion prediction when available.

    For detections without an established predecessor, this falls back to ordinary
    nearest-neighbor distance. The motion prediction is a linking aid only; it is
    not treated as evidence that two detections are biologically identical.
    """

    if not previous or not current:
        return []

    current_positions = np.array([d.position_um for d in current], dtype=float)
    candidate_pairs: list[tuple[float, Detection, Detection]] = []

    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(current_positions)
        for source in previous:
            source_position = np.array(source.position_um, dtype=float)
            predecessor = predecessor_by_node_id.get(source.node_id)
            predicted_position = _predicted_position(source, predecessor)
            prediction_error, idx = tree.query(predicted_position, k=1)
            target = current[int(idx)]
            step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
            if (
                math.isfinite(float(prediction_error))
                and float(prediction_error) <= max_link_distance_um
                and step_distance <= max_link_distance_um
            ):
                candidate_pairs.append((float(prediction_error), source, target))
    except ImportError:
        for source in previous:
            source_position = np.array(source.position_um, dtype=float)
            predicted_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
            prediction_errors = np.linalg.norm(current_positions - predicted_position, axis=1)
            idx = int(np.argmin(prediction_errors))
            target = current[idx]
            prediction_error = float(prediction_errors[idx])
            step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
            if prediction_error <= max_link_distance_um and step_distance <= max_link_distance_um:
                candidate_pairs.append((prediction_error, source, target))

    return _greedy_assign(candidate_pairs, max_link_distance_um)

def link_adjacent_timepoints_motion_mutual(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
) -> list[LineageEdge]:
    """Link by motion prediction gated by mutual nearest-neighbor identity.

    A source keeps its motion-predicted nearest target only when that target's
    nearest previous detection in physical microns is the same source. The mutual
    identity gate rejects contested targets in dense fields, trading a little
    recall for fewer identity switches. It is a bounded linking aid, not a claim
    that two detections are biologically identical.
    """

    if not previous or not current:
        return []

    previous_positions = np.array([d.position_um for d in previous], dtype=float)
    current_positions = np.array([d.position_um for d in current], dtype=float)

    # Forward: motion-predicted nearest target per source (directional gate).
    source_to_target: dict[int, tuple[int, float]] = {}
    # Reverse: raw nearest previous source per target (identity anchor).
    target_to_source: dict[int, int] = {}

    try:
        from scipy.spatial import cKDTree

        current_tree = cKDTree(current_positions)
        previous_tree = cKDTree(previous_positions)
        for source_idx, source in enumerate(previous):
            source_position = np.array(source.position_um, dtype=float)
            predicted_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
            prediction_error, target_idx = current_tree.query(predicted_position, k=1)
            target = current[int(target_idx)]
            step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
            if (
                math.isfinite(float(prediction_error))
                and float(prediction_error) <= max_link_distance_um
                and step_distance <= max_link_distance_um
            ):
                source_to_target[source_idx] = (int(target_idx), float(prediction_error))
        for target_idx, target in enumerate(current):
            distance, source_idx = previous_tree.query(target.position_um, k=1)
            if math.isfinite(float(distance)) and float(distance) <= max_link_distance_um:
                target_to_source[target_idx] = int(source_idx)
    except ImportError:
        for source_idx, source in enumerate(previous):
            source_position = np.array(source.position_um, dtype=float)
            predicted_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
            prediction_errors = np.linalg.norm(current_positions - predicted_position, axis=1)
            target_idx = int(np.argmin(prediction_errors))
            target = current[target_idx]
            prediction_error = float(prediction_errors[target_idx])
            step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
            if prediction_error <= max_link_distance_um and step_distance <= max_link_distance_um:
                source_to_target[source_idx] = (target_idx, prediction_error)
        for target_idx in range(current_positions.shape[0]):
            distances = np.linalg.norm(previous_positions - current_positions[target_idx], axis=1)
            source_idx = int(np.argmin(distances))
            if float(distances[source_idx]) <= max_link_distance_um:
                target_to_source[target_idx] = source_idx

    candidate_pairs: list[tuple[float, Detection, Detection]] = []
    for source_idx, (target_idx, prediction_error) in source_to_target.items():
        if target_to_source.get(target_idx) != source_idx:
            continue
        candidate_pairs.append((prediction_error, previous[source_idx], current[target_idx]))
    return _greedy_assign(candidate_pairs, max_link_distance_um)


def link_adjacent_timepoints_motion_crowding(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
    *,
    crowding_ratio: float = 0.8,
) -> list[LineageEdge]:
    """Motion linking with a mutual-identity gate applied only to contested targets.

    Each source keeps its motion-predicted nearest target (permissive, like ``motion``).
    The stricter mutual-identity gate from ``motion_mutual`` is enforced only where the
    assignment is ambiguous: a target is "contested" when its nearest and second-nearest
    previous detections are within ``crowding_ratio`` of each other (a Lowe-style ratio
    test on physical distance). Uncontested targets stay permissive to preserve recall in
    sparse regions; contested targets require mutual agreement to suppress identity
    switches in crowded regions.

    Boundaries: ``crowding_ratio == 1.0`` reduces to ``motion`` (nothing is contested) and
    ``crowding_ratio == 0.0`` approaches ``motion_mutual`` (any real competitor is
    contested). The crowding ratio is a geometric ambiguity signal, not evidence of
    biological identity.
    """

    if not previous or not current:
        return []

    previous_positions = np.array([d.position_um for d in previous], dtype=float)
    current_positions = np.array([d.position_um for d in current], dtype=float)

    # Forward: motion-predicted nearest target per source (directional gate).
    source_to_target: dict[int, tuple[int, float]] = {}
    # Reverse: raw nearest previous source per target, plus a per-target contested flag.
    target_to_source: dict[int, int] = {}
    target_contested: dict[int, bool] = {}

    try:
        from scipy.spatial import cKDTree

        current_tree = cKDTree(current_positions)
        previous_tree = cKDTree(previous_positions)
        for source_idx, source in enumerate(previous):
            source_position = np.array(source.position_um, dtype=float)
            predicted_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
            prediction_error, target_idx = current_tree.query(predicted_position, k=1)
            target = current[int(target_idx)]
            step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
            if (
                math.isfinite(float(prediction_error))
                and float(prediction_error) <= max_link_distance_um
                and step_distance <= max_link_distance_um
            ):
                source_to_target[source_idx] = (int(target_idx), float(prediction_error))
        neighbor_count = min(2, len(previous))
        for target_idx, target in enumerate(current):
            distances, source_indices = previous_tree.query(target.position_um, k=neighbor_count)
            nearest_distance, nearest_source_idx = _first_neighbor(distances, source_indices)
            if not math.isfinite(nearest_distance) or nearest_distance > max_link_distance_um:
                continue
            second_distance = _second_neighbor_distance(distances, neighbor_count)
            target_to_source[target_idx] = nearest_source_idx
            target_contested[target_idx] = _is_contested(nearest_distance, second_distance, crowding_ratio)
    except ImportError:
        for source_idx, source in enumerate(previous):
            source_position = np.array(source.position_um, dtype=float)
            predicted_position = _predicted_position(source, predecessor_by_node_id.get(source.node_id))
            prediction_errors = np.linalg.norm(current_positions - predicted_position, axis=1)
            target_idx = int(np.argmin(prediction_errors))
            target = current[target_idx]
            prediction_error = float(prediction_errors[target_idx])
            step_distance = float(np.linalg.norm(np.array(target.position_um) - source_position))
            if prediction_error <= max_link_distance_um and step_distance <= max_link_distance_um:
                source_to_target[source_idx] = (target_idx, prediction_error)
        for target_idx in range(current_positions.shape[0]):
            distances = np.sort(np.linalg.norm(previous_positions - current_positions[target_idx], axis=1))
            nearest_distance = float(distances[0])
            if nearest_distance > max_link_distance_um:
                continue
            nearest_source_idx = int(np.argmin(np.linalg.norm(previous_positions - current_positions[target_idx], axis=1)))
            second_distance = float(distances[1]) if distances.size > 1 else math.inf
            target_to_source[target_idx] = nearest_source_idx
            target_contested[target_idx] = _is_contested(nearest_distance, second_distance, crowding_ratio)

    candidate_pairs: list[tuple[float, Detection, Detection]] = []
    for source_idx, (target_idx, prediction_error) in source_to_target.items():
        if target_contested.get(target_idx, False) and target_to_source.get(target_idx) != source_idx:
            continue
        candidate_pairs.append((prediction_error, previous[source_idx], current[target_idx]))
    return _greedy_assign(candidate_pairs, max_link_distance_um)


def _first_neighbor(distances: object, source_indices: object) -> tuple[float, int]:
    distances_array = np.atleast_1d(distances)
    indices_array = np.atleast_1d(source_indices)
    return float(distances_array[0]), int(indices_array[0])


def _second_neighbor_distance(distances: object, neighbor_count: int) -> float:
    distances_array = np.atleast_1d(distances)
    if neighbor_count < 2 or distances_array.size < 2:
        return math.inf
    return float(distances_array[1])


def _is_contested(nearest_distance: float, second_distance: float, crowding_ratio: float) -> bool:
    if not math.isfinite(second_distance) or second_distance <= 0.0:
        return False
    return (nearest_distance / second_distance) > crowding_ratio


def link_adjacent_timepoints_motion_division(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
    *,
    daughter_distance_ratio: float = 1.75,
    max_daughter_separation_um: float | None = None,
) -> list[LineageEdge]:
    """Add conservative split edges on top of motion-predicted links.

    The one-to-one motion linker remains the main path. A second outgoing edge is
    added only for an unused current detection whose nearest previous detection
    is the same source. This is a bounded candidate for mitosis, not a claim that
    a biological division occurred.
    """

    if not previous or not current:
        return []

    continuation_edges = link_adjacent_timepoints_motion(
        previous,
        current,
        max_link_distance_um,
        predecessor_by_node_id=predecessor_by_node_id,
    )
    if not continuation_edges:
        return []

    previous_by_id = {detection.node_id: detection for detection in previous}
    current_by_id = {detection.node_id: detection for detection in current}
    source_to_primary_target = {edge.source_id: edge.target_id for edge in continuation_edges}
    used_targets = {edge.target_id for edge in continuation_edges}
    source_to_primary_distance = {
        edge.source_id: _distance_um(previous_by_id[edge.source_id], current_by_id[edge.target_id])
        for edge in continuation_edges
    }
    separation_limit = max_daughter_separation_um or max_link_distance_um

    candidate_pairs: list[tuple[float, Detection, Detection]] = []
    previous_positions = np.array([detection.position_um for detection in previous], dtype=float)
    try:
        from scipy.spatial import cKDTree

        previous_tree = cKDTree(previous_positions)
        for target in current:
            if target.node_id in used_targets:
                continue
            distance, source_idx = previous_tree.query(target.position_um, k=1)
            if not math.isfinite(float(distance)) or float(distance) > max_link_distance_um:
                continue
            source = previous[int(source_idx)]
            _append_division_candidate(
                candidate_pairs,
                source,
                target,
                float(distance),
                source_to_primary_target,
                source_to_primary_distance,
                current_by_id,
                daughter_distance_ratio,
                separation_limit,
            )
    except ImportError:
        for target in current:
            if target.node_id in used_targets:
                continue
            distances = np.linalg.norm(previous_positions - np.array(target.position_um), axis=1)
            source_idx = int(np.argmin(distances))
            distance = float(distances[source_idx])
            if distance > max_link_distance_um:
                continue
            source = previous[source_idx]
            _append_division_candidate(
                candidate_pairs,
                source,
                target,
                distance,
                source_to_primary_target,
                source_to_primary_distance,
                current_by_id,
                daughter_distance_ratio,
                separation_limit,
            )

    division_edges = _division_assign(candidate_pairs, max_link_distance_um, used_targets)
    return continuation_edges + division_edges

def _predicted_position(source: Detection, predecessor: Detection | None) -> np.ndarray:
    source_position = np.array(source.position_um, dtype=float)
    if predecessor is None:
        return source_position
    predecessor_position = np.array(predecessor.position_um, dtype=float)
    return source_position + (source_position - predecessor_position)


def _greedy_assign(
    candidate_pairs: list[tuple[float, Detection, Detection]],
    max_link_distance_um: float,
) -> list[LineageEdge]:
    candidate_pairs.sort(key=lambda item: item[0])
    used_sources: set[str] = set()
    used_targets: set[str] = set()
    edges: list[LineageEdge] = []

    for distance, source, target in candidate_pairs:
        if source.node_id in used_sources or target.node_id in used_targets:
            continue
        used_sources.add(source.node_id)
        used_targets.add(target.node_id)
        edges.append(_edge(source, target, distance, max_link_distance_um))

    return edges


def _edge(source: Detection, target: Detection, distance: float, max_link_distance_um: float) -> LineageEdge:
    confidence = max(0.0, 1.0 - distance / max_link_distance_um)
    return LineageEdge(source.node_id, target.node_id, confidence=confidence)


def _append_division_candidate(
    candidate_pairs: list[tuple[float, Detection, Detection]],
    source: Detection,
    target: Detection,
    distance: float,
    source_to_primary_target: Mapping[str, str],
    source_to_primary_distance: Mapping[str, float],
    current_by_id: Mapping[str, Detection],
    daughter_distance_ratio: float,
    separation_limit: float,
) -> None:
    primary_target_id = source_to_primary_target.get(source.node_id)
    if primary_target_id is None:
        return
    primary_target = current_by_id[primary_target_id]
    primary_distance = source_to_primary_distance[source.node_id]
    if distance > max(primary_distance, 1e-6) * daughter_distance_ratio:
        return
    if _distance_um(primary_target, target) > separation_limit:
        return
    candidate_pairs.append((distance, source, target))


def _division_assign(
    candidate_pairs: list[tuple[float, Detection, Detection]],
    max_link_distance_um: float,
    used_targets: set[str],
) -> list[LineageEdge]:
    candidate_pairs.sort(key=lambda item: item[0])
    used_sources: set[str] = set()
    edges: list[LineageEdge] = []
    for distance, source, target in candidate_pairs:
        if source.node_id in used_sources or target.node_id in used_targets:
            continue
        used_sources.add(source.node_id)
        used_targets.add(target.node_id)
        confidence = max(0.0, 1.0 - distance / max_link_distance_um)
        edges.append(LineageEdge(source.node_id, target.node_id, confidence=confidence, relation="division"))
    return edges


def _distance_um(source: Detection, target: Detection) -> float:
    return float(np.linalg.norm(np.array(source.position_um) - np.array(target.position_um)))



def link_adjacent_timepoints_bipartite(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
    *,
    debug: bool = False,
    divergence_angle_max_cos: float = 0.0,
    daughter_distance_ratio: float = 2.0,
) -> list[LineageEdge]:
    """Link detections using a bipartite solver to natively support 1-to-2 divisions.
    
    Uses an exclusion gate principle:
    Pass 1: Run standard motion_mutual assignment to lock in normal continuations.
    Pass 2: Identify unassigned 'orphan' targets and 'candidate parents' at T0.
    Pass 3: Use local assignments to resolve potential 1-to-2 division topologies,
            enforcing geometric and kinematic guardrails.
    """
    
    if not previous or not current:
        return []

    # Pass 1: Standard strict 1-to-1 baseline
    baseline_edges = link_adjacent_timepoints_motion_mutual(
        previous, current, max_link_distance_um, predecessor_by_node_id
    )
    
    # Pass 2: Candidate Gating
    assigned_targets = {edge.target_id for edge in baseline_edges}
    
    orphans = [t for t in current if t.node_id not in assigned_targets]
    if not orphans:
        # Strict regression guarantee: no orphans = zero perturbation.
        return baseline_edges
        
    sources_by_id = {s.node_id: s for s in previous}
    targets_by_id = {t.node_id: t for t in current}
    
    candidate_parents = set()
    current_positions = np.array([d.position_um for d in orphans], dtype=float)
    if current_positions.size > 0:
        for edge in baseline_edges:
            source = sources_by_id[edge.source_id]
            source_pos = np.array(source.position_um)
            dists = np.linalg.norm(current_positions - source_pos, axis=1)
            if np.any(dists <= max_link_distance_um):
                candidate_parents.add(source.node_id)
                
    if not candidate_parents:
        return baseline_edges

    # Pass 3: Local 1-to-2 Resolution
    final_edges = []
    
    for edge in baseline_edges:
        source_id = edge.source_id
        if source_id not in candidate_parents:
            final_edges.append(edge)
            continue
            
        source = sources_by_id[source_id]
        t_primary = targets_by_id[edge.target_id]
        
        # Find all orphans within distance
        local_orphans = []
        source_pos = np.array(source.position_um)
        for o in orphans:
            if np.linalg.norm(np.array(o.position_um) - source_pos) <= max_link_distance_um:
                local_orphans.append(o)
                
        if not local_orphans:
            final_edges.append(edge)
            continue
            
        # Kinematic evidence for division: anti-parallel divergence.
        v1 = np.array(t_primary.position_um) - source_pos
        norm_v1 = np.linalg.norm(v1)
        
        best_orphan = None
        best_orphan_cost = float('inf')
        
        for o in local_orphans:
            v2 = np.array(o.position_um) - source_pos
            norm_v2 = np.linalg.norm(v2)
            dist_primary_to_orphan = np.linalg.norm(np.array(t_primary.position_um) - np.array(o.position_um))
            
            rejection_reason = None
            cos_theta = None
            
            if norm_v1 < 1e-6 or norm_v2 < 1e-6:
                rejection_reason = "Zero-length vector"
            else:
                cos_theta = np.dot(v1, v2) / (norm_v1 * norm_v2)
                if cos_theta > divergence_angle_max_cos:
                    rejection_reason = f"Angle constraint (cos={cos_theta:.3f} > {divergence_angle_max_cos})"
                elif norm_v2 > max(norm_v1, 1e-6) * daughter_distance_ratio:
                    rejection_reason = f"Distance ratio ({norm_v2:.2f}/{norm_v1:.2f} > {daughter_distance_ratio})"
                elif dist_primary_to_orphan > max_link_distance_um:
                    rejection_reason = f"Daughter separation ({dist_primary_to_orphan:.2f} > {max_link_distance_um})"
            
            if debug:
                angle_deg = math.degrees(math.acos(np.clip(cos_theta, -1.0, 1.0))) if cos_theta is not None else 0.0
                print(f"[DEBUG Bipartite] Source {source.node_id[:6]} -> Orphan {o.node_id[:6]}: "
                      f"dist={norm_v2:.2f}um, angle={angle_deg:.1f}deg (cos={cos_theta if cos_theta else 0.0:.3f}), "
                      f"separation={dist_primary_to_orphan:.2f}um. "
                      f"Rejected: {rejection_reason or 'No'}")
            
            if rejection_reason is None:
                if norm_v2 < best_orphan_cost:
                    best_orphan = o
                    best_orphan_cost = norm_v2
                        
        if best_orphan is not None:
            # Found a valid 1-to-2 branch!
            # Edge to primary (keep original, but change relation to 'division')
            final_edges.append(LineageEdge(source.node_id, t_primary.node_id, edge.confidence, "division"))
            
            # Edge to orphan (compute proper confidence)
            orphan_conf = max(0.0, 1.0 - best_orphan_cost / max_link_distance_um)
            final_edges.append(LineageEdge(source.node_id, best_orphan.node_id, orphan_conf, "division"))
            
            # Remove orphan from global orphans pool
            orphans.remove(best_orphan)
        else:
            final_edges.append(edge)

    if len(final_edges) > len(baseline_edges):
        if debug:
            print(f"BIPARTITE: found {len(final_edges) - len(baseline_edges)} new division edges!")
    return final_edges

