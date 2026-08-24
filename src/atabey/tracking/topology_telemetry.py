from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from atabey.types import LineageGraph


def summarize_node_topology(graph: LineageGraph) -> dict[str, Any]:
    """Return bounded node-topology distributions for an immutable graph."""

    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    degree: Counter[str] = Counter()
    continuation_support: Counter[str] = Counter()
    for edge in graph.edges:
        incoming[edge.target_id].append(edge.source_id)
        outgoing[edge.source_id].append(edge.target_id)
        degree[edge.source_id] += 1
        degree[edge.target_id] += 1
        if edge.relation == "continuation":
            continuation_support[edge.source_id] += 1
            continuation_support[edge.target_id] += 1

    node_frames = {detection.node_id: detection.t for detection in graph.detections}
    earliest_frame: dict[str, int] = {}
    for detection in graph.detections:
        node_id = detection.node_id
        if node_id in earliest_frame:
            continue
        stack = [node_id]
        visited: set[str] = set()
        minimum = detection.t
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            minimum = min(minimum, node_frames.get(current, detection.t))
            stack.extend(incoming.get(current, ()))
            stack.extend(outgoing.get(current, ()))
        for member in visited:
            earliest_frame[member] = minimum

    by_frame: Counter[str] = Counter()
    track_age: Counter[str] = Counter()
    node_degree: Counter[str] = Counter()
    support: Counter[str] = Counter()
    by_connectivity: Counter[str] = Counter()
    joint: Counter[str] = Counter()
    for detection in graph.detections:
        node_id = detection.node_id
        age = detection.t - earliest_frame.get(node_id, detection.t) + 1
        node_degree_value = degree[node_id]
        support_value = continuation_support[node_id]
        connected = "connected" if node_degree_value else "isolated"
        by_frame[str(detection.t)] += 1
        track_age[str(age)] += 1
        node_degree[str(node_degree_value)] += 1
        support[str(support_value)] += 1
        by_connectivity[connected] += 1
        joint[f"{connected}|age={age}|degree={node_degree_value}|support={support_value}"] += 1

    return {
        "node_count": len(graph.detections),
        "edge_count": len(graph.edges),
        "by_frame": dict(sorted(by_frame.items(), key=lambda item: int(item[0]))),
        "track_age_histogram": dict(sorted(track_age.items(), key=lambda item: int(item[0]))),
        "degree_histogram": dict(sorted(node_degree.items(), key=lambda item: int(item[0]))),
        "continuation_support_histogram": dict(
            sorted(support.items(), key=lambda item: int(item[0]))
        ),
        "connectivity": dict(sorted(by_connectivity.items())),
        "joint_histogram": dict(sorted(joint.items())),
    }