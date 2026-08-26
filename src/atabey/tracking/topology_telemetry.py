from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from typing import Any

from atabey.types import LineageGraph

DEFAULT_NODE_RECORD_LIMIT = 256
DEFAULT_COMPONENT_RECORD_LIMIT = 128


def _node_facts(
    graph: LineageGraph,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming_relations: dict[str, Counter[str]] = defaultdict(Counter)
    outgoing_relations: dict[str, Counter[str]] = defaultdict(Counter)
    degree: Counter[str] = Counter()
    continuation_support: Counter[str] = Counter()
    for edge in graph.edges:
        incoming[edge.target_id].append(edge.source_id)
        outgoing[edge.source_id].append(edge.target_id)
        incoming_relations[edge.target_id][edge.relation] += 1
        outgoing_relations[edge.source_id][edge.relation] += 1
        degree[edge.source_id] += 1
        degree[edge.target_id] += 1
        if edge.relation == "continuation":
            continuation_support[edge.source_id] += 1
            continuation_support[edge.target_id] += 1

    node_frames = {detection.node_id: detection.t for detection in graph.detections}
    component_stats: dict[str, tuple[int, int, int, int, str, str]] = {}
    component_records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for detection in graph.detections:
        node_id = detection.node_id
        if node_id in seen:
            continue
        stack = [node_id]
        visited: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(incoming.get(current, ()))
            stack.extend(outgoing.get(current, ()))
        seen.update(visited)
        frames = sorted(node_frames[member] for member in visited if member in node_frames)
        minimum = frames[0] if frames else detection.t
        maximum = frames[-1] if frames else detection.t
        gaps = [right - left for left, right in zip(frames, frames[1:])]
        max_gap = max(gaps, default=0)
        gap_count = sum(gap > 1 for gap in gaps)
        boundary = "single_frame" if minimum == maximum else "multi_frame"
        component_id = hashlib.sha256(
            f"{graph.sample_id}|{'|'.join(sorted(visited))}".encode("utf-8")
        ).hexdigest()[:16]
        members = [
            detection_member
            for detection_member in graph.detections
            if detection_member.node_id in visited
        ]
        component_records.append(
            {
                "component_id": component_id,
                "component_size": len(visited),
                "start_frame": minimum,
                "end_frame": maximum,
                "frame_span": maximum - minimum + 1,
                "component_span": boundary,
                "temporal_gap_count": gap_count,
                "max_temporal_gap": max_gap,
                "degree_histogram": dict(
                    sorted(Counter(degree[member.node_id] for member in members).items())
                ),
                "continuation_support_histogram": dict(
                    sorted(
                        Counter(continuation_support[member.node_id] for member in members).items()
                    )
                ),
                "incoming_relation_counts": dict(
                    sorted(
                        Counter(
                            relation
                            for member in members
                            for relation, count in incoming_relations[member.node_id].items()
                            for _ in range(count)
                        ).items()
                    )
                ),
                "outgoing_relation_counts": dict(
                    sorted(
                        Counter(
                            relation
                            for member in members
                            for relation, count in outgoing_relations[member.node_id].items()
                            for _ in range(count)
                        ).items()
                    )
                ),
            }
        )
        for member in visited:
            component_stats[member] = (len(visited), minimum, max_gap, gap_count, boundary, component_id)

    facts: list[dict[str, Any]] = []
    for detection in graph.detections:
        node_id = detection.node_id
        node_degree = degree[node_id]
        support = continuation_support[node_id]
        component_size, component_start, max_temporal_gap, temporal_gap_count, component_span, component_id = component_stats.get(
            node_id, (1, detection.t, 0, 0, "single_frame", "")
        )
        frame_boundary = (
            "first"
            if detection.t == min(node_frames.values())
            else "last"
            if detection.t == max(node_frames.values())
            else "interior"
        )
        facts.append(
            {
                "node_id": node_id,
                "frame": detection.t,
                "age": detection.t - component_start + 1,
                "degree": node_degree,
                "continuation_support": support,
                "connectivity": "connected" if node_degree else "isolated",
                "component_size": component_size,
                                "component_id": component_id,
                "component_age": detection.t - component_start + 1,
                "component_span": component_span,
                "max_temporal_gap": max_temporal_gap,
                "temporal_gap_count": temporal_gap_count,
                "frame_boundary": frame_boundary,
                "incoming_relations": dict(sorted(incoming_relations[node_id].items())),
                "outgoing_relations": dict(sorted(outgoing_relations[node_id].items())),
            }
        )
    return facts, component_records


def summarize_node_topology(
    graph: LineageGraph,
    node_record_limit: int = DEFAULT_NODE_RECORD_LIMIT,
    component_record_limit: int = DEFAULT_COMPONENT_RECORD_LIMIT,
) -> dict[str, Any]:
    """Return bounded node-topology distributions for an immutable graph."""
    facts, components = _node_facts(graph)

    by_frame: Counter[str] = Counter()
    track_age: Counter[str] = Counter()
    node_degree: Counter[str] = Counter()
    support: Counter[str] = Counter()
    by_connectivity: Counter[str] = Counter()
    joint: Counter[str] = Counter()
    for fact in facts:
        age = fact["age"]
        node_degree_value = fact["degree"]
        support_value = fact["continuation_support"]
        connected = fact["connectivity"]
        by_frame[str(fact["frame"])] += 1
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
        "bounded_node_record_limit": node_record_limit,
        "bounded_node_records": [
            fact
            for fact in sorted(
                facts,
                key=lambda item: hashlib.sha256(
                    f"{graph.sample_id}|{item['node_id']}".encode("utf-8")
                ).hexdigest(),
            )[: max(node_record_limit, 0)]
        ],
        "component_count": len(components),
        "component_size_histogram": dict(
            sorted(Counter(component["component_size"] for component in components).items())
        ),
        "component_span_histogram": dict(
            sorted(Counter(component["component_span"] for component in components).items())
        ),
        "bounded_component_record_limit": component_record_limit,
        "bounded_component_records": [
            component
            for component in sorted(
                components,
                key=lambda item: hashlib.sha256(
                    f"{graph.sample_id}|{item['component_id']}".encode("utf-8")
                ).hexdigest(),
            )[: max(component_record_limit, 0)]
        ],
    }


def compare_node_topology(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """Compare bounded node records and exact strata from two arm reports."""
    left_nodes = {record["node_id"]: record for record in left["bounded_node_records"]}
    right_nodes = {record["node_id"]: record for record in right["bounded_node_records"]}
    common = sorted(set(left_nodes) & set(right_nodes))
    left_components = {
        record["component_id"]: record for record in left["bounded_component_records"]
    }
    right_components = {
        record["component_id"]: record for record in right["bounded_component_records"]
    }
    common_components = sorted(set(left_components) & set(right_components))
    strata = sorted(set(left["joint_histogram"]) | set(right["joint_histogram"]))
    return {
        "bounded_node_record_limit": min(
            left["bounded_node_record_limit"], right["bounded_node_record_limit"]
        ),
        "bounded_common_node_count": len(common),
        "bounded_common_node_records": [
            {"node_id": node_id, "left": left_nodes[node_id], "right": right_nodes[node_id]}
            for node_id in common
        ],
        "component_count_left": left["component_count"],
        "component_count_right": right["component_count"],
        "bounded_component_record_limit": min(
            left["bounded_component_record_limit"],
            right["bounded_component_record_limit"],
        ),
        "bounded_common_component_count": len(common_components),
        "bounded_common_component_records": [
            {
                "component_id": component_id,
                "left": left_components[component_id],
                "right": right_components[component_id],
            }
            for component_id in common_components
        ],
        "stratum_deltas_right_minus_left": {
            stratum: right["joint_histogram"].get(stratum, 0)
            - left["joint_histogram"].get(stratum, 0)
            for stratum in strata
            if right["joint_histogram"].get(stratum, 0)
            != left["joint_histogram"].get(stratum, 0)
        },
    }