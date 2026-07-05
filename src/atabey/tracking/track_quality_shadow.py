from __future__ import annotations

from dataclasses import dataclass

from atabey.types import Detection, LineageEdge, LineageGraph


@dataclass(frozen=True)
class TrackQualityShadowSummary:
    nodes: int
    edges: int
    roots: int
    mean_detection_confidence: float
    mean_link_confidence: float
    mean_persistence: float
    mean_track_quality: float
    beacon_count: int
    beacon_fraction: float
    beacon_quality_threshold: float
    min_track_length_for_beacon: int


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_mean(values: list[float], default: float = 0.0) -> float:
    if not values:
        return float(default)
    return float(sum(values) / len(values))


def _build_degree_maps(edges: list[LineageEdge], valid_node_ids: set[str]) -> tuple[dict[str, int], dict[str, int], dict[str, list[LineageEdge]]]:
    incoming_count = {node_id: 0 for node_id in valid_node_ids}
    outgoing_count = {node_id: 0 for node_id in valid_node_ids}
    incoming_edges_by_target = {node_id: [] for node_id in valid_node_ids}
    for edge in edges:
        if edge.source_id not in valid_node_ids or edge.target_id not in valid_node_ids:
            continue
        outgoing_count[edge.source_id] += 1
        incoming_count[edge.target_id] += 1
        incoming_edges_by_target[edge.target_id].append(edge)
    return incoming_count, outgoing_count, incoming_edges_by_target


def _compute_track_depths(
    detections: list[Detection],
    incoming_edges_by_target: dict[str, list[LineageEdge]],
) -> dict[str, int]:
    depth_by_node_id: dict[str, int] = {}
    ordered = sorted(detections, key=lambda detection: (int(detection.t), detection.node_id))
    for detection in ordered:
        incoming_edges = incoming_edges_by_target.get(detection.node_id, [])
        if not incoming_edges:
            depth_by_node_id[detection.node_id] = 1
            continue
        parent_depths = [int(depth_by_node_id.get(edge.source_id, 1)) for edge in incoming_edges]
        depth_by_node_id[detection.node_id] = 1 + max(parent_depths)
    return depth_by_node_id


def compute_track_quality_shadow(
    graph: LineageGraph,
    *,
    beacon_quality_threshold: float = 0.75,
    min_track_length_for_beacon: int = 3,
) -> TrackQualityShadowSummary:
    """Compute shadow-only track quality and beacon candidates without affecting linking.

    This function is diagnostics-only. It must never mutate graph state and must never
    change edge assignment decisions.
    """

    detections = list(graph.detections)
    edges = list(graph.edges)
    if not detections:
        return TrackQualityShadowSummary(
            nodes=0,
            edges=0,
            roots=0,
            mean_detection_confidence=0.0,
            mean_link_confidence=0.0,
            mean_persistence=0.0,
            mean_track_quality=0.0,
            beacon_count=0,
            beacon_fraction=0.0,
            beacon_quality_threshold=float(beacon_quality_threshold),
            min_track_length_for_beacon=int(min_track_length_for_beacon),
        )

    valid_node_ids = {detection.node_id for detection in detections}
    incoming_count, outgoing_count, incoming_edges_by_target = _build_degree_maps(edges, valid_node_ids)
    depth_by_node_id = _compute_track_depths(detections, incoming_edges_by_target)

    conf_values: list[float] = []
    link_values: list[float] = []
    persistence_values: list[float] = []
    quality_values: list[float] = []
    beacon_count = 0
    min_beacon_length = max(1, int(min_track_length_for_beacon))

    for detection in detections:
        detection_confidence = _clamp01(0.5 if detection.detection_confidence is None else detection.detection_confidence)
        incoming_edges = incoming_edges_by_target.get(detection.node_id, [])
        if incoming_edges:
            incoming_link_confidence = max(
                _clamp01(0.5 if edge.confidence is None else edge.confidence) for edge in incoming_edges
            )
            mutual_agreement = 1.0 if all(outgoing_count.get(edge.source_id, 0) <= 1 for edge in incoming_edges) else 0.5
        else:
            incoming_link_confidence = 0.5
            mutual_agreement = 1.0

        depth = int(depth_by_node_id.get(detection.node_id, 1))
        persistence = _clamp01(depth / float(min_beacon_length + 1))
        branching_penalty = 1.0 if (incoming_count.get(detection.node_id, 0) > 1 or outgoing_count.get(detection.node_id, 0) > 1) else 0.0

        quality = _clamp01(
            0.40 * detection_confidence
            + 0.35 * incoming_link_confidence
            + 0.20 * persistence
            + 0.10 * mutual_agreement
            - 0.20 * branching_penalty
        )

        conf_values.append(detection_confidence)
        link_values.append(incoming_link_confidence)
        persistence_values.append(persistence)
        quality_values.append(quality)

        if depth >= min_beacon_length and quality >= float(beacon_quality_threshold):
            beacon_count += 1

    roots = sum(1 for detection in detections if incoming_count.get(detection.node_id, 0) == 0)
    nodes = len(detections)
    return TrackQualityShadowSummary(
        nodes=nodes,
        edges=len(edges),
        roots=roots,
        mean_detection_confidence=_safe_mean(conf_values, default=0.0),
        mean_link_confidence=_safe_mean(link_values, default=0.0),
        mean_persistence=_safe_mean(persistence_values, default=0.0),
        mean_track_quality=_safe_mean(quality_values, default=0.0),
        beacon_count=int(beacon_count),
        beacon_fraction=float(beacon_count) / float(nodes),
        beacon_quality_threshold=float(beacon_quality_threshold),
        min_track_length_for_beacon=min_beacon_length,
    )
