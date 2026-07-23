from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from atabey.types import LineageGraph


@dataclass(frozen=True)
class ComponentPruningEvidence:
    component_id: str
    node_ids: tuple[str, ...]
    node_count: int
    temporal_span: int
    edge_count: int
    mean_edge_confidence: float | None
    missing_edge_confidences: int
    contains_division: bool
    removed: bool


@dataclass(frozen=True)
class AdaptivePruningSummary:
    sample_id: str
    route_label: str | None
    activated: bool
    activation_reason: str
    keep_fraction: float
    fragment_size_threshold: int
    min_fragmented_node_fraction: float
    original_nodes: int
    shadow_nodes: int
    original_edges: int
    shadow_edges: int
    component_count: int
    fragmented_nodes: int
    fragmented_node_fraction: float
    protected_components: int
    removed_components: int
    removed_nodes: int
    removed_edges: int


@dataclass(frozen=True)
class AdaptivePruningShadowResult:
    graph: LineageGraph
    summary: AdaptivePruningSummary
    components: tuple[ComponentPruningEvidence, ...]


def _copy_graph(graph: LineageGraph) -> LineageGraph:
    return LineageGraph(
        sample_id=graph.sample_id,
        detections=list(graph.detections),
        edges=list(graph.edges),
    )


def compute_adaptive_pruning_shadow(
    graph: LineageGraph,
    *,
    keep_fraction: float = 0.95,
    fragment_size_threshold: int = 7,
    min_fragmented_node_fraction: float = 0.50,
    preserve_division_components: bool = True,
    route_label: str | None = None,
    allowed_routes: frozenset[str] | None = None,
) -> AdaptivePruningShadowResult:
    """Rank and remove weak whole components on a cloned graph only.

    Activation depends solely on prediction-side structure and optional route metadata.
    Ground-truth node counts and metric outcomes never participate in the pruning decision.
    """

    if not 0.0 < keep_fraction <= 1.0:
        raise ValueError("keep_fraction must be in (0, 1]")
    if fragment_size_threshold < 2:
        raise ValueError("fragment_size_threshold must be at least 2")
    if not 0.0 <= min_fragmented_node_fraction <= 1.0:
        raise ValueError("min_fragmented_node_fraction must be in [0, 1]")

    nodes_by_id = {detection.node_id: detection for detection in graph.detections}
    parent = {node_id: node_id for node_id in nodes_by_id}

    def find(node_id: str) -> str:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    def union(left: str, right: str) -> None:
        if left not in parent or right not in parent:
            return
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[left_root] = right_root

    outgoing_count: dict[str, int] = {}
    for edge in graph.edges:
        union(edge.source_id, edge.target_id)
        outgoing_count[edge.source_id] = outgoing_count.get(edge.source_id, 0) + 1

    members_by_root: dict[str, list[str]] = {}
    for node_id in nodes_by_id:
        members_by_root.setdefault(find(node_id), []).append(node_id)

    edges_by_root: dict[str, list] = {root: [] for root in members_by_root}
    for edge in graph.edges:
        if edge.source_id in parent:
            edges_by_root.setdefault(find(edge.source_id), []).append(edge)

    raw_components: list[dict[str, object]] = []
    for root, member_ids in members_by_root.items():
        member_ids = sorted(member_ids)
        component_edges = edges_by_root.get(root, [])
        confidence_values = [
            float(edge.confidence)
            for edge in component_edges
            if edge.confidence is not None
        ]
        contains_division = any(
            outgoing_count.get(node_id, 0) >= 2 for node_id in member_ids
        ) or any(edge.relation == "division" for edge in component_edges)
        times = [nodes_by_id[node_id].t for node_id in member_ids]
        raw_components.append(
            {
                "component_id": member_ids[0],
                "node_ids": tuple(member_ids),
                "node_count": len(member_ids),
                "temporal_span": max(times) - min(times) + 1,
                "edge_count": len(component_edges),
                "mean_edge_confidence": (
                    float(mean(confidence_values)) if confidence_values else None
                ),
                "missing_edge_confidences": len(component_edges) - len(confidence_values),
                "contains_division": contains_division,
            }
        )

    original_nodes = len(graph.detections)
    fragmented_nodes = sum(
        int(component["node_count"])
        for component in raw_components
        if int(component["node_count"]) < fragment_size_threshold
    )
    fragmented_fraction = fragmented_nodes / original_nodes if original_nodes else 0.0
    route_allowed = allowed_routes is None or route_label in allowed_routes
    if keep_fraction >= 1.0:
        activation_reason = "keep_fraction_is_noop"
    elif not original_nodes:
        activation_reason = "empty_graph"
    elif not route_allowed:
        activation_reason = "route_not_enabled"
    elif fragmented_fraction < min_fragmented_node_fraction:
        activation_reason = "fragmentation_below_gate"
    else:
        activation_reason = "fragmentation_gate_passed"
    activated = activation_reason == "fragmentation_gate_passed"

    keep_ids = set(nodes_by_id)
    removed_component_ids: set[str] = set()
    if activated:
        target_nodes = max(1, int(round(original_nodes * keep_fraction)))

        def rank_key(component: dict[str, object]) -> tuple[int, float, str]:
            confidence = component["mean_edge_confidence"]
            return (
                int(component["node_count"]),
                -1.0 if confidence is None else float(confidence),
                str(component["component_id"]),
            )

        for component in sorted(raw_components, key=rank_key):
            if len(keep_ids) <= target_nodes:
                break
            if preserve_division_components and bool(component["contains_division"]):
                continue
            member_ids = set(component["node_ids"])
            if len(keep_ids) - len(member_ids) < target_nodes:
                continue
            keep_ids.difference_update(member_ids)
            removed_component_ids.add(str(component["component_id"]))

    shadow = LineageGraph(
        sample_id=graph.sample_id,
        detections=[
            detection for detection in graph.detections if detection.node_id in keep_ids
        ],
        edges=[
            edge
            for edge in graph.edges
            if edge.source_id in keep_ids and edge.target_id in keep_ids
        ],
    )
    components = tuple(
        ComponentPruningEvidence(
            component_id=str(component["component_id"]),
            node_ids=tuple(component["node_ids"]),
            node_count=int(component["node_count"]),
            temporal_span=int(component["temporal_span"]),
            edge_count=int(component["edge_count"]),
            mean_edge_confidence=(
                None
                if component["mean_edge_confidence"] is None
                else float(component["mean_edge_confidence"])
            ),
            missing_edge_confidences=int(component["missing_edge_confidences"]),
            contains_division=bool(component["contains_division"]),
            removed=str(component["component_id"]) in removed_component_ids,
        )
        for component in sorted(raw_components, key=lambda item: str(item["component_id"]))
    )
    protected_components = sum(
        1 for component in raw_components if bool(component["contains_division"])
    ) if preserve_division_components else 0
    summary = AdaptivePruningSummary(
        sample_id=graph.sample_id,
        route_label=route_label,
        activated=activated,
        activation_reason=activation_reason,
        keep_fraction=float(keep_fraction),
        fragment_size_threshold=int(fragment_size_threshold),
        min_fragmented_node_fraction=float(min_fragmented_node_fraction),
        original_nodes=original_nodes,
        shadow_nodes=len(shadow.detections),
        original_edges=len(graph.edges),
        shadow_edges=len(shadow.edges),
        component_count=len(raw_components),
        fragmented_nodes=fragmented_nodes,
        fragmented_node_fraction=float(fragmented_fraction),
        protected_components=protected_components,
        removed_components=len(removed_component_ids),
        removed_nodes=original_nodes - len(shadow.detections),
        removed_edges=len(graph.edges) - len(shadow.edges),
    )
    return AdaptivePruningShadowResult(
        graph=shadow,
        summary=summary,
        components=components,
    )
