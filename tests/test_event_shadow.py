from __future__ import annotations

from atabey.tracking.event_shadow import compute_lineage_event_shadow
from atabey.types import Detection, LineageEdge, LineageGraph


def test_event_shadow_detects_latent_and_mitosis_candidates() -> None:
    graph = LineageGraph(sample_id="sample")

    d0 = Detection("d0", "sample", 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, intensity_mean=90.0)
    d1 = Detection("d1", "sample", 1, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, intensity_mean=92.0)
    d3 = Detection("d3", "sample", 3, 0.0, 3.0, 0.0, 0.0, 3.0, 0.0, intensity_mean=96.0)
    parent = Detection("parent", "sample", 4, 0.0, 4.0, 0.0, 0.0, 4.0, 0.0, intensity_mean=100.0)
    c1 = Detection("c1", "sample", 5, 0.0, 4.3, 0.0, 0.0, 4.3, 0.0, intensity_mean=49.0)
    c2 = Detection("c2", "sample", 5, 0.0, 3.7, 0.0, 0.0, 3.7, 0.0, intensity_mean=51.0)

    for detection in (d0, d1, d3, parent, c1, c2):
        graph.add_detection(detection)

    graph.add_edge(LineageEdge("d0", "d1", confidence=0.95))
    graph.add_edge(LineageEdge("d3", "parent", confidence=0.90))

    summary = compute_lineage_event_shadow(
        graph,
        latent_window_frames=2,
        latent_max_link_distance_um=1.5,
        mitosis_distance_um=1.0,
        mitosis_intensity_tolerance=0.15,
    )

    assert summary.latent_candidate_count >= 1
    assert summary.latent_mean_prediction_error_um is not None
    assert summary.mitosis_candidate_count >= 1


def test_event_shadow_handles_empty_graph() -> None:
    summary = compute_lineage_event_shadow(LineageGraph(sample_id="sample"))

    assert summary.nodes == 0
    assert summary.edges == 0
    assert summary.latent_candidate_count == 0
    assert summary.latent_mean_prediction_error_um is None
    assert summary.mitosis_candidate_count == 0
