from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from statistics import mean

from atabey.tracking.adaptive_pruning_shadow import (
    AdaptivePruningSummary,
    compute_adaptive_pruning_shadow,
)
from atabey.types import LineageGraph


@dataclass(frozen=True)
class PredictionEvidenceComponent:
    component_id: str
    node_ids: tuple[str, ...]
    node_count: int
    contains_division: bool
    mean_detection_confidence: float | None
    temporal_support_sides: int
    nearest_linked_same_frame_um: float | None
    stable_tie_break: int
    removed: bool


@dataclass(frozen=True)
class PredictionEvidencePruningResult:
    graph: LineageGraph
    summary: AdaptivePruningSummary
    components: tuple[PredictionEvidenceComponent, ...]


def _stable_tie_break(sample_id: str, component_id: str) -> int:
    payload = f"{sample_id}\0{component_id}".encode("utf-8")
    return int.from_bytes(sha256(payload).digest()[:8], "big")


def compute_prediction_evidence_pruning_shadow(
    graph: LineageGraph,
    *,
    keep_fraction: float = 0.97,
    fragment_size_threshold: int = 7,
    min_fragmented_node_fraction: float = 0.50,
    preserve_division_components: bool = True,
    route_label: str | None = None,
    allowed_routes: frozenset[str] | None = None,
    temporal_support_radius_um: float = 14.0,
    same_frame_duplicate_radius_um: float = 7.0,
) -> PredictionEvidencePruningResult:
    """Prune on a clone using prediction evidence and a time-neutral tie-break.

    The existing adaptive-pruning shadow remains unchanged. This variant reuses
    only its component decomposition and activation gate.
    """
    if temporal_support_radius_um <= 0.0:
        raise ValueError("temporal_support_radius_um must be positive")
    if same_frame_duplicate_radius_um <= 0.0:
        raise ValueError("same_frame_duplicate_radius_um must be positive")

    base = compute_adaptive_pruning_shadow(
        graph,
        keep_fraction=keep_fraction,
        fragment_size_threshold=fragment_size_threshold,
        min_fragmented_node_fraction=min_fragmented_node_fraction,
        preserve_division_components=preserve_division_components,
        route_label=route_label,
        allowed_routes=allowed_routes,
    )
    nodes_by_id = {detection.node_id: detection for detection in graph.detections}
    linked_node_ids = {
        node_id for edge in graph.edges for node_id in (edge.source_id, edge.target_id)
    }

    from scipy.spatial import cKDTree

    detections_by_time: dict[int, list] = {}
    for detection in graph.detections:
        detections_by_time.setdefault(detection.t, []).append(detection)
    min_time = min(detections_by_time, default=0)
    max_time = max(detections_by_time, default=0)
    trees_by_time = {
        t: cKDTree([detection.position_um for detection in detections])
        for t, detections in detections_by_time.items()
    }
    linked_trees_by_time = {
        t: cKDTree(
            [
                detection.position_um
                for detection in detections
                if detection.node_id in linked_node_ids
            ]
        )
        for t, detections in detections_by_time.items()
        if any(detection.node_id in linked_node_ids for detection in detections)
    }

    evidence: list[dict[str, object]] = []
    for component in base.components:
        detections = [nodes_by_id[node_id] for node_id in component.node_ids]
        confidences = [
            float(detection.detection_confidence)
            for detection in detections
            if detection.detection_confidence is not None
        ]
        support_sides = 2
        nearest_linked: float | None = None
        if component.node_count == 1:
            detection = detections[0]
            support_sides = 0
            for adjacent_time in (detection.t - 1, detection.t + 1):
                if adjacent_time < min_time or adjacent_time > max_time:
                    support_sides += 1
                    continue
                tree = trees_by_time.get(adjacent_time)
                if tree is not None:
                    distance, _ = tree.query(detection.position_um, k=1)
                    if float(distance) <= temporal_support_radius_um:
                        support_sides += 1
            linked_tree = linked_trees_by_time.get(detection.t)
            if linked_tree is not None:
                distance, _ = linked_tree.query(detection.position_um, k=1)
                nearest_linked = float(distance)
        evidence.append(
            {
                "component_id": component.component_id,
                "node_ids": component.node_ids,
                "node_count": component.node_count,
                "contains_division": component.contains_division,
                "mean_detection_confidence": (
                    float(mean(confidences)) if confidences else None
                ),
                "temporal_support_sides": support_sides,
                "nearest_linked_same_frame_um": nearest_linked,
                "stable_tie_break": _stable_tie_break(
                    graph.sample_id, component.component_id
                ),
            }
        )

    keep_ids = set(nodes_by_id)
    removed_component_ids: set[str] = set()
    if base.summary.activated:
        target_nodes = max(1, int(round(len(keep_ids) * keep_fraction)))

        def rank_key(component: dict[str, object]) -> tuple:
            nearest_linked = component["nearest_linked_same_frame_um"]
            duplicate_priority = (
                0
                if nearest_linked is not None
                and float(nearest_linked) <= same_frame_duplicate_radius_um
                else 1
            )
            confidence = component["mean_detection_confidence"]
            return (
                int(component["node_count"]),
                int(component["temporal_support_sides"]),
                duplicate_priority,
                -1.0 if confidence is None else float(confidence),
                int(component["stable_tie_break"]),
            )

        for component in sorted(evidence, key=rank_key):
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
        PredictionEvidenceComponent(
            component_id=str(component["component_id"]),
            node_ids=tuple(component["node_ids"]),
            node_count=int(component["node_count"]),
            contains_division=bool(component["contains_division"]),
            mean_detection_confidence=(
                None
                if component["mean_detection_confidence"] is None
                else float(component["mean_detection_confidence"])
            ),
            temporal_support_sides=int(component["temporal_support_sides"]),
            nearest_linked_same_frame_um=(
                None
                if component["nearest_linked_same_frame_um"] is None
                else float(component["nearest_linked_same_frame_um"])
            ),
            stable_tie_break=int(component["stable_tie_break"]),
            removed=str(component["component_id"]) in removed_component_ids,
        )
        for component in evidence
    )
    summary = replace(
        base.summary,
        shadow_nodes=len(shadow.detections),
        shadow_edges=len(shadow.edges),
        removed_components=len(removed_component_ids),
        removed_nodes=len(graph.detections) - len(shadow.detections),
        removed_edges=len(graph.edges) - len(shadow.edges),
    )
    return PredictionEvidencePruningResult(
        graph=shadow,
        summary=summary,
        components=components,
    )
