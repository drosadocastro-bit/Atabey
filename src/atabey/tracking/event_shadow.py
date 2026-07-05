from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from atabey.types import Detection, LineageEdge, LineageGraph


@dataclass(frozen=True)
class LineageEventShadowSummary:
    nodes: int
    edges: int
    latent_candidate_count: int
    latent_mean_prediction_error_um: float | None
    latent_window_frames: int
    latent_max_link_distance_um: float
    mitosis_candidate_count: int
    mitosis_distance_um: float
    mitosis_intensity_tolerance: float


def _detection_intensity(detection: Detection) -> float | None:
    if detection.intensity_mean is not None:
        return float(detection.intensity_mean)
    if detection.intensity_max is not None:
        return float(detection.intensity_max)
    return None


def _best_incoming_source_by_target(edges: list[LineageEdge]) -> dict[str, str]:
    best: dict[str, tuple[float, str]] = {}
    for edge in edges:
        confidence = float(edge.confidence if edge.confidence is not None else 0.0)
        existing = best.get(edge.target_id)
        if existing is None or confidence > existing[0]:
            best[edge.target_id] = (confidence, edge.source_id)
    return {target_id: source_id for target_id, (_confidence, source_id) in best.items()}


def _outgoing_target_ids_by_source(edges: list[LineageEdge]) -> dict[str, set[str]]:
    outgoing: dict[str, set[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source_id, set()).add(edge.target_id)
    return outgoing


def compute_lineage_event_shadow(
    graph: LineageGraph,
    *,
    latent_window_frames: int = 2,
    latent_max_link_distance_um: float = 9.0,
    mitosis_distance_um: float = 3.0,
    mitosis_intensity_tolerance: float = 0.40,
) -> LineageEventShadowSummary:
    """Compute latent-recovery and mitosis shadow signals without mutating the graph."""

    detections = list(graph.detections)
    edges = list(graph.edges)
    if not detections:
        return LineageEventShadowSummary(
            nodes=0,
            edges=len(edges),
            latent_candidate_count=0,
            latent_mean_prediction_error_um=None,
            latent_window_frames=int(latent_window_frames),
            latent_max_link_distance_um=float(latent_max_link_distance_um),
            mitosis_candidate_count=0,
            mitosis_distance_um=float(mitosis_distance_um),
            mitosis_intensity_tolerance=float(mitosis_intensity_tolerance),
        )

    by_id: dict[str, Detection] = {d.node_id: d for d in detections}
    by_t: dict[int, list[Detection]] = {}
    for detection in detections:
        by_t.setdefault(int(detection.t), []).append(detection)

    incoming_source_by_target = _best_incoming_source_by_target(edges)
    outgoing_target_ids_by_source = _outgoing_target_ids_by_source(edges)

    latent_count = 0
    latent_errors: list[float] = []
    used_latent_targets: set[str] = set()
    max_gap = max(1, int(latent_window_frames))

    ordered = sorted(detections, key=lambda detection: (int(detection.t), detection.node_id))
    for source in ordered:
        source_outgoing = outgoing_target_ids_by_source.get(source.node_id, set())
        has_adjacent_child = any(by_id[target_id].t == source.t + 1 for target_id in source_outgoing if target_id in by_id)
        if has_adjacent_child:
            continue

        predecessor_id = incoming_source_by_target.get(source.node_id)
        if predecessor_id is None:
            continue
        predecessor = by_id.get(predecessor_id)
        if predecessor is None:
            continue

        source_pos = np.array(source.position_um, dtype=float)
        predecessor_pos = np.array(predecessor.position_um, dtype=float)
        velocity = source_pos - predecessor_pos

        matched = False
        for gap in range(2, max_gap + 2):
            target_t = int(source.t) + gap
            candidates = [
                detection
                for detection in by_t.get(target_t, [])
                if detection.node_id not in used_latent_targets
                and detection.node_id not in incoming_source_by_target
            ]
            if not candidates:
                continue

            predicted_pos = source_pos + velocity * float(gap)
            candidate_positions = np.array([detection.position_um for detection in candidates], dtype=float)
            errors = np.linalg.norm(candidate_positions - predicted_pos, axis=1)
            best_idx = int(np.argmin(errors))
            best_error = float(errors[best_idx])
            if best_error > float(latent_max_link_distance_um) * float(gap):
                continue

            latent_count += 1
            latent_errors.append(best_error)
            used_latent_targets.add(candidates[best_idx].node_id)
            matched = True
            break
        if matched:
            continue

    mitosis_count = 0
    used_mitosis_children: set[str] = set()
    for source in ordered:
        parent_intensity = _detection_intensity(source)
        if parent_intensity is None or parent_intensity <= 0.0:
            continue

        next_candidates = [
            detection
            for detection in by_t.get(int(source.t) + 1, [])
            if detection.node_id not in used_mitosis_children
        ]
        if len(next_candidates) < 2:
            continue

        source_pos = np.array(source.position_um, dtype=float)
        nearby: list[tuple[float, Detection]] = []
        for detection in next_candidates:
            distance = float(np.linalg.norm(np.array(detection.position_um, dtype=float) - source_pos))
            if distance <= float(mitosis_distance_um):
                nearby.append((distance, detection))
        if len(nearby) < 2:
            continue

        nearby.sort(key=lambda item: item[0])
        child_a = nearby[0][1]
        child_b = nearby[1][1]
        intensity_a = _detection_intensity(child_a)
        intensity_b = _detection_intensity(child_b)
        if intensity_a is None or intensity_b is None:
            continue

        child_sum = float(intensity_a + intensity_b)
        relative_error = abs(child_sum - float(parent_intensity)) / max(float(parent_intensity), 1e-6)
        if relative_error > float(mitosis_intensity_tolerance):
            continue

        mitosis_count += 1
        used_mitosis_children.add(child_a.node_id)
        used_mitosis_children.add(child_b.node_id)

    return LineageEventShadowSummary(
        nodes=len(detections),
        edges=len(edges),
        latent_candidate_count=int(latent_count),
        latent_mean_prediction_error_um=(float(sum(latent_errors) / len(latent_errors)) if latent_errors else None),
        latent_window_frames=max_gap,
        latent_max_link_distance_um=float(latent_max_link_distance_um),
        mitosis_candidate_count=int(mitosis_count),
        mitosis_distance_um=float(mitosis_distance_um),
        mitosis_intensity_tolerance=float(mitosis_intensity_tolerance),
    )
