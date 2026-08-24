from __future__ import annotations

from atabey.types import LineageGraph


def prune_interior_isolated_detections(graph: LineageGraph) -> LineageGraph:
    """Clone a graph while removing only isolated detections in interior frames."""

    if not graph.detections:
        return LineageGraph(sample_id=graph.sample_id)

    incoming = {edge.target_id for edge in graph.edges}
    outgoing = {edge.source_id for edge in graph.edges}
    frame_counts: dict[int, int] = {}
    for detection in graph.detections:
        frame_counts[detection.t] = frame_counts.get(detection.t, 0) + 1
    first_frame = min(frame_counts)
    last_frame = max(frame_counts)
    keep_ids = {
        detection.node_id
        for detection in graph.detections
        if detection.node_id in incoming
        or detection.node_id in outgoing
        or detection.t in (first_frame, last_frame)
        or frame_counts.get(detection.t - 1, 0) == 0
        or frame_counts.get(detection.t + 1, 0) == 0
    }

    filtered = LineageGraph(sample_id=graph.sample_id)
    for detection in graph.detections:
        if detection.node_id in keep_ids:
            filtered.add_detection(detection)
    for edge in graph.edges:
        if edge.source_id in keep_ids and edge.target_id in keep_ids:
            filtered.add_edge(edge)
    return filtered