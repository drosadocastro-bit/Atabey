from atabey.tracking.division_recovery_shadow import (
    TRACK_B_CONFIDENCE_THRESHOLD,
    compute_division_recovery_shadow,
    route_division_recovery_candidate,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id, t, y, x=0.0, volume=None, intensity=None):
    return Detection(
        node_id,
        "s",
        t,
        0.0,
        y,
        x,
        0.0,
        y,
        x,
        intensity_mean=intensity,
        component_volume=volume,
    )


def _add(graph, *detections):
    for detection in detections:
        graph.add_detection(detection)


def _edge_signature(graph):
    return [(edge.source_id, edge.target_id, edge.confidence, edge.relation) for edge in graph.edges]


def test_division_recovery_shadow_logs_candidate_features_without_mutating_graph():
    graph = LineageGraph("s")
    parent = _d("p", 0, 0.0, 0.0, volume=100, intensity=50.0)
    child_a = _d("a1", 1, -1.0, 0.0, volume=45, intensity=20.0)
    child_b = _d("b1", 1, 2.1, 0.0, volume=55, intensity=30.0)
    _add(graph, parent, child_a, child_b)
    graph.add_edge(LineageEdge("p", "a1", relation="division"))
    graph.add_edge(LineageEdge("p", "b1", relation="division"))
    before = _edge_signature(graph)

    summary = compute_division_recovery_shadow(graph)

    assert _edge_signature(graph) == before
    assert summary.nodes == 3
    assert summary.edges == 2
    assert summary.candidate_count == 1
    assert summary.accepted_count == 1
    assert summary.proposal_count == 0
    assert summary.flagged_count == 1
    candidate = summary.candidates[0]
    assert candidate.parent_id == "p"
    assert candidate.accepted is True
    assert candidate.reason == "fallback_broad_angle_balanced_split"
    assert candidate.angle_deg == 180.0
    assert candidate.distance_ratio == 2.1
    assert candidate.local_density_t1_10um == 2
    assert candidate.child_separation_um == 3.1
    assert candidate.volume_conservation_error == 0.0
    assert candidate.intensity_conservation_error == 0.0
    assert candidate.ranking_score > 0.0
    assert candidate.calibrated_confidence is None
    assert candidate.confidence_threshold == TRACK_B_CONFIDENCE_THRESHOLD
    assert candidate.decision_mode == "extractive_flagged"
    assert candidate.confidence_basis == "uncalibrated_feature_evidence"


def test_division_recovery_shadow_rejects_narrow_fallback_split():
    graph = LineageGraph("s")
    parent = _d("p", 0, 0.0, 0.0)
    child_a = _d("a1", 1, 1.0, 0.0)
    child_b = _d("b1", 1, 1.0, 1.0)
    _add(graph, parent, child_a, child_b)
    graph.add_edge(LineageEdge("p", "a1", relation="division"))
    graph.add_edge(LineageEdge("p", "b1", relation="division"))

    summary = compute_division_recovery_shadow(graph)

    assert summary.candidate_count == 1
    assert summary.accepted_count == 0
    assert summary.candidates[0].reason == "fallback_rejected"


def test_division_recovery_shadow_accepts_stable_positive_multiframe_divergence():
    graph = LineageGraph("s")
    detections = [
        _d("p", 0, 0.0, 0.0),
        _d("a1", 1, -1.0, 0.0),
        _d("b1", 1, 1.0, 0.0),
        _d("a2", 2, -2.0, 0.0),
        _d("b2", 2, 2.0, 0.0),
        _d("a3", 3, -3.0, 0.0),
        _d("b3", 3, 3.0, 0.0),
    ]
    _add(graph, *detections)
    for source, target in [
        ("p", "a1"),
        ("p", "b1"),
        ("a1", "a2"),
        ("b1", "b2"),
        ("a2", "a3"),
        ("b2", "b3"),
    ]:
        graph.add_edge(LineageEdge(source, target, relation="division" if source == "p" else "continuation"))

    summary = compute_division_recovery_shadow(graph)

    assert summary.candidate_count == 1
    assert summary.accepted_count == 1
    assert summary.candidates[0].reason == "multi_frame_positive_divergence"
    assert summary.candidates[0].max_drift_deg == 0.0
    assert summary.candidates[0].v_sep_1_um_per_frame == 2.0


def test_confidence_router_promotes_only_calibrated_candidates_at_threshold():
    graph = LineageGraph("s")
    parent = _d("p", 0, 0.0, 0.0)
    child_a = _d("a1", 1, -1.0, 0.0)
    child_b = _d("b1", 1, 1.0, 0.0)
    _add(graph, parent, child_a, child_b)
    graph.add_edge(LineageEdge("p", "a1", relation="division"))
    graph.add_edge(LineageEdge("p", "b1", relation="division"))
    candidate = compute_division_recovery_shadow(graph).candidates[0]

    below = route_division_recovery_candidate(candidate, calibrated_confidence=0.59)
    at_threshold = route_division_recovery_candidate(candidate, calibrated_confidence=0.60)

    assert below.decision_mode == "extractive_flagged"
    assert at_threshold.decision_mode == "division_proposal"
    assert at_threshold.confidence_basis == "external_calibrator"


def test_confidence_router_never_promotes_geometrically_rejected_candidate():
    graph = LineageGraph("s")
    parent = _d("p", 0, 0.0, 0.0)
    child_a = _d("a1", 1, 1.0, 0.0)
    child_b = _d("b1", 1, 1.0, 1.0)
    _add(graph, parent, child_a, child_b)
    graph.add_edge(LineageEdge("p", "a1", relation="division"))
    graph.add_edge(LineageEdge("p", "b1", relation="division"))
    candidate = compute_division_recovery_shadow(graph).candidates[0]

    routed = route_division_recovery_candidate(candidate, calibrated_confidence=0.99)

    assert routed.accepted is False
    assert routed.decision_mode == "rejected"
