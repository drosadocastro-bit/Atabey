from __future__ import annotations

from atabey.tracking.adaptive_pruning_evidence_shadow import (
    compute_prediction_evidence_pruning_shadow,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(
    node_id: str,
    t: int,
    *,
    x_um: float = 0.0,
    confidence: float | None = None,
) -> Detection:
    return Detection(
        node_id,
        "sample",
        t,
        0.0,
        0.0,
        x_um,
        0.0,
        0.0,
        x_um,
        detection_confidence=confidence,
    )


def _signature(graph: LineageGraph) -> tuple:
    return (
        tuple(detection.node_id for detection in graph.detections),
        tuple((edge.source_id, edge.target_id) for edge in graph.edges),
    )


def test_evidence_rank_removes_unsupported_low_confidence_singleton():
    graph = LineageGraph(
        "sample",
        [
            _d("track-0", 0, confidence=0.9),
            _d("track-1", 1, confidence=0.9),
            _d("track-2", 2, confidence=0.9),
            _d("z-unsupported", 20, x_um=100.0, confidence=0.1),
            _d("a-supported", 1, x_um=1.0, confidence=0.8),
        ],
        [
            LineageEdge("track-0", "track-1", 0.9),
            LineageEdge("track-1", "track-2", 0.9),
        ],
    )
    before = _signature(graph)
    result = compute_prediction_evidence_pruning_shadow(
        graph,
        keep_fraction=0.80,
        fragment_size_threshold=3,
        min_fragmented_node_fraction=0.0,
    )
    kept = {detection.node_id for detection in result.graph.detections}
    assert "z-unsupported" not in kept
    assert "a-supported" in kept
    evidence = {component.component_id: component for component in result.components}
    assert evidence["z-unsupported"].temporal_support_sides == 1
    assert evidence["a-supported"].temporal_support_sides == 2
    assert _signature(graph) == before


def test_exact_ties_do_not_follow_lexicographic_time_order():
    graph = LineageGraph(
        "sample",
        [
            _d(f"sample:t{t}:p0", t, x_um=float(t * 100), confidence=0.5)
            for t in range(20)
        ],
        [],
    )
    result = compute_prediction_evidence_pruning_shadow(
        graph,
        keep_fraction=0.50,
        fragment_size_threshold=3,
        min_fragmented_node_fraction=0.0,
        temporal_support_radius_um=1.0,
    )
    kept_ids = {detection.node_id for detection in result.graph.detections}
    removed_times = {
        detection.t for detection in graph.detections if detection.node_id not in kept_ids
    }
    assert len(removed_times) == 10
    assert removed_times != set(range(10))
    assert min(removed_times) < 10 < max(removed_times)
