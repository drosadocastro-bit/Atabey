from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from typing import Any

from atabey.types import LineageGraph

DEFAULT_NODE_RECORD_LIMIT = 256


def _node_facts(
    graph: LineageGraph,
) -> list[dict[str, Any]]:
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

    facts: list[dict[str, Any]] = []
    for detection in graph.detections:
        node_id = detection.node_id
        node_degree = degree[node_id]
        support = continuation_support[node_id]
        facts.append(
            {
                "node_id": node_id,
                "frame": detection.t,
                "age": detection.t - earliest_frame.get(node_id, detection.t) + 1,
                "degree": node_degree,
                "continuation_support": support,
                "connectivity": "connected" if node_degree else "isolated",
            }
        )
    return facts


def summarize_node_topology(
    graph: LineageGraph,
    node_record_limit: int = DEFAULT_NODE_RECORD_LIMIT,
) -> dict[str, Any]:
    """Return bounded node-topology distributions for an immutable graph."""
    facts = _node_facts(graph)

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
    }


def compare_node_topology(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    """Compare bounded node records and exact strata from two arm reports."""
    left_nodes = {record["node_id"]: record for record in left["bounded_node_records"]}
    right_nodes = {record["node_id"]: record for record in right["bounded_node_records"]}
    common = sorted(set(left_nodes) & set(right_nodes))
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
        "stratum_deltas_right_minus_left": {
            stratum: right["joint_histogram"].get(stratum, 0)
            - left["joint_histogram"].get(stratum, 0)
            for stratum in strata
            if right["joint_histogram"].get(stratum, 0)
            != left["joint_histogram"].get(stratum, 0)
        },
    }