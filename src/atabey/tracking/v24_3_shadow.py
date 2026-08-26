from __future__ import annotations

from collections import defaultdict

from atabey.types import LineageGraph


MAX_COMPONENT_SIZE = 2


def prune_interior_short_fragments(graph: LineageGraph) -> LineageGraph:
    """Clone a graph while removing only bounded, non-division short fragments."""

    if not graph.detections:
        return LineageGraph(sample_id=graph.sample_id)

    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    relations: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        incoming[edge.target_id].append(edge.source_id)
        outgoing[edge.source_id].append(edge.target_id)
        relations[edge.source_id].add(edge.relation)
        relations[edge.target_id].add(edge.relation)

    first_frame = min(detection.t for detection in graph.detections)
    last_frame = max(detection.t for detection in graph.detections)
    detections = {detection.node_id: detection for detection in graph.detections}
    seen: set[str] = set()
    remove_ids: set[str] = set()
    for node_id, detection in detections.items():
        if node_id in seen:
            continue
        stack = [node_id]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(incoming.get(current, ()))
            stack.extend(outgoing.get(current, ()))
        seen.update(component)
        frames = [detections[member].t for member in component if member in detections]
        if (
            1 < len(component) <= MAX_COMPONENT_SIZE
            and min(frames) > first_frame
            and max(frames) < last_frame
            and not any("division" in relations[member] for member in component)
        ):
            remove_ids.update(component)

    filtered = LineageGraph(sample_id=graph.sample_id)
    for detection in graph.detections:
        if detection.node_id not in remove_ids:
            filtered.add_detection(detection)
    for edge in graph.edges:
        if edge.source_id not in remove_ids and edge.target_id not in remove_ids:
            filtered.add_edge(edge)
    return filtered