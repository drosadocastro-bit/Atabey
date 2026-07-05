from __future__ import annotations

from atabey.tracking.track_quality_shadow import compute_track_quality_shadow
from atabey.types import Detection, LineageEdge, LineageGraph


def test_track_quality_shadow_reports_beacon_candidates_on_stable_chain() -> None:
    graph = LineageGraph(sample_id="sample")
    n1 = Detection("n1", "sample", 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, detection_confidence=0.95)
    n2 = Detection("n2", "sample", 1, 0.0, 0.2, 0.0, 0.0, 0.2, 0.0, detection_confidence=0.92)
    n3 = Detection("n3", "sample", 2, 0.0, 0.4, 0.0, 0.0, 0.4, 0.0, detection_confidence=0.91)
    graph.add_detection(n1)
    graph.add_detection(n2)
    graph.add_detection(n3)
    graph.add_edge(LineageEdge("n1", "n2", confidence=0.94))
    graph.add_edge(LineageEdge("n2", "n3", confidence=0.93))

    summary = compute_track_quality_shadow(
        graph,
        beacon_quality_threshold=0.70,
        min_track_length_for_beacon=2,
    )

    assert summary.nodes == 3
    assert summary.edges == 2
    assert summary.roots == 1
    assert summary.mean_track_quality > 0.70
    assert summary.beacon_count >= 1
    assert summary.beacon_fraction > 0.0


def test_track_quality_shadow_handles_empty_graph() -> None:
    summary = compute_track_quality_shadow(LineageGraph(sample_id="sample"))

    assert summary.nodes == 0
    assert summary.edges == 0
    assert summary.roots == 0
    assert summary.mean_track_quality == 0.0
    assert summary.beacon_count == 0
    assert summary.beacon_fraction == 0.0
