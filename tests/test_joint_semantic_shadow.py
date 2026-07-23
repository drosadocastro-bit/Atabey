from __future__ import annotations

import pytest

from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.tracking.joint_semantic_shadow import (
    evidence_as_row,
    extract_joint_semantic_evidence,
    label_division_action_official,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(
    node_id: str,
    t: int,
    x: float,
    y: float = 0.0,
    *,
    volume: int | None = None,
    intensity: float | None = None,
    confidence: float | None = None,
) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id="sample",
        t=t,
        z=0.0,
        y=y,
        x=x,
        z_um=0.0,
        y_um=y,
        x_um=x,
        component_volume=volume,
        intensity_mean=intensity,
        detection_confidence=confidence,
    )


def _feature_graph() -> LineageGraph:
    detections = [
        _d("pre", 0, 0.0, volume=90, intensity=45.0, confidence=0.8),
        _d("p", 1, 1.0, volume=100, intensity=50.0, confidence=0.9),
        _d("a1", 2, 2.0, -1.0, volume=45, intensity=20.0, confidence=0.7),
        _d("b1", 2, 2.0, 1.0, volume=55, intensity=30.0, confidence=0.6),
        _d("a2", 3, 3.0, -2.0),
        _d("b2", 3, 3.0, 2.0),
        _d("a3", 4, 4.0, -3.0),
        _d("b3", 4, 4.0, 3.0),
    ]
    edges = [
        LineageEdge("pre", "p"),
        LineageEdge("p", "a1", relation="division"),
        LineageEdge("p", "b1", relation="division"),
        LineageEdge("a1", "a2"),
        LineageEdge("b1", "b2"),
        LineageEdge("a2", "a3"),
        LineageEdge("b2", "b3"),
    ]
    return LineageGraph("sample", detections, edges)


def _signature(graph: LineageGraph):
    return (
        tuple(graph.detections),
        tuple((edge.source_id, edge.target_id, edge.confidence, edge.relation) for edge in graph.edges),
    )


def test_extracts_complete_action_space_and_raw_division_features_without_mutation():
    graph = _feature_graph()
    before = _signature(graph)

    summary = extract_joint_semantic_evidence(graph, parent_ids=["p"])

    assert _signature(graph) == before
    assert summary.parent_count == 1
    assert summary.action_count == 5
    assert summary.continue_count == 2
    assert summary.divide_count == 1
    assert summary.terminate_count == 1
    assert summary.abstain_count == 1

    division = next(row for row in summary.evidence if row.action_type == "divide")
    assert (division.child_1_id, division.child_2_id) == ("a1", "b1")
    assert division.candidate_set_complete is True
    assert division.parent_speed_um_per_frame == pytest.approx(1.0)
    assert division.child_distance_ratio == pytest.approx(1.0)
    assert division.child_separation_um == pytest.approx(2.0)
    assert division.split_angle_deg == pytest.approx(90.0)
    assert division.pair_midpoint_prediction_error_um == pytest.approx(0.0)
    assert division.split_axis_parent_velocity_alignment_deg == pytest.approx(90.0)
    assert division.immediate_separation_growth_um == pytest.approx(2.0)
    assert division.max_branch_axis_drift_deg == pytest.approx(0.0)
    assert division.child_1_continuity_coverage == pytest.approx(1.0)
    assert division.child_2_continuity_coverage == pytest.approx(1.0)
    assert division.volume_conservation_error == pytest.approx(0.0)
    assert division.intensity_conservation_error == pytest.approx(0.0)
    assert division.semantic_score is None
    assert division.calibrated_confidence is None
    assert division.decision == "abstain"
    assert division.decision_reason == "phase0_unscored_evidence"
    assert division.official_label == "not_evaluated"


def test_missing_features_keep_explicit_reason_codes_instead_of_favorable_defaults():
    graph = LineageGraph(
        "sample",
        [_d("p", 0, 0.0), _d("a", 1, 1.0, -1.0), _d("b", 1, 1.0, 1.0)],
        [],
    )

    division = next(
        row
        for row in extract_joint_semantic_evidence(graph, parent_ids=["p"]).evidence
        if row.action_type == "divide"
    )

    assert division.parent_speed_um_per_frame is None
    assert division.missing_reason("parent_speed_um_per_frame") == "no_parent_history"
    assert division.pair_midpoint_prediction_error_um is None
    assert division.missing_reason("pair_midpoint_prediction_error_um") == "no_parent_history"
    assert division.child_1_prediction_error_um is None
    assert division.missing_reason("child_1_prediction_error_um") == "daughter_track_ends"
    assert division.max_branch_axis_drift_deg is None
    assert division.missing_reason("max_branch_axis_drift_deg") == "daughter_track_ends"
    assert division.volume_conservation_error is None
    assert division.missing_reason("volume_conservation_error") == "no_parent_component_volume"
    assert division.intensity_conservation_error is None
    assert division.missing_reason("intensity_conservation_error") == "no_parent_detection_intensity"
    assert 0.0 not in {
        division.parent_speed_um_per_frame,
        division.pair_midpoint_prediction_error_um,
        division.volume_conservation_error,
        division.intensity_conservation_error,
    }


def test_formation_radius_is_observation_only_and_pair_order_is_deterministic():
    graph = LineageGraph(
        "sample",
        [
            _d("p", 0, 0.0),
            _d("z_near", 1, 2.0),
            _d("a_near", 1, 3.0),
            _d("outside", 1, 14.1),
        ],
        [],
    )
    before = _signature(graph)

    summary = extract_joint_semantic_evidence(
        graph,
        parent_ids=["p"],
        formation_radius_um=14.0,
    )

    assert _signature(graph) == before
    assert [row.child_1_id for row in summary.evidence if row.action_type == "continue"] == [
        "a_near",
        "z_near",
    ]
    division = next(row for row in summary.evidence if row.action_type == "divide")
    assert (division.child_1_id, division.child_2_id) == ("a_near", "z_near")
    assert "outside" not in {
        target
        for row in summary.evidence
        for target in (row.child_1_id, row.child_2_id)
    }


def test_partial_detection_confidence_is_missing_instead_of_partially_averaged():
    graph = LineageGraph(
        "sample",
        [
            _d("p", 0, 0.0, confidence=0.9),
            _d("a", 1, 1.0, -1.0),
            _d("b", 1, 1.0, 1.0),
        ],
        [],
    )
    division = next(
        row
        for row in extract_joint_semantic_evidence(graph, parent_ids=["p"]).evidence
        if row.action_type == "divide"
    )

    assert division.mean_detection_confidence is None
    assert division.missing_reason("mean_detection_confidence") == "partial_detection_confidence"


def test_csv_row_serializes_feature_availability_and_missingness():
    graph = LineageGraph("sample", [_d("p", 0, 0.0), _d("a", 1, 1.0)], [])
    continuation = next(
        row
        for row in extract_joint_semantic_evidence(graph, parent_ids=["p"]).evidence
        if row.action_type == "continue"
    )

    row = evidence_as_row(continuation)

    assert '"child_1_distance_um"' in row["available_features"]
    assert '"child_2_distance_um": "not_applicable_for_continue_action"' in row["missing_features"]


def test_official_projected_label_uses_graph_copy_and_patched_scorer():
    pytest.importorskip("tracking_cellmot")
    pytest.importorskip("tracksdata")
    graph = _feature_graph()
    before = _signature(graph)
    division = next(
        row
        for row in extract_joint_semantic_evidence(graph, parent_ids=["p"]).evidence
        if row.action_type == "divide"
    )

    def gt(node_id: int, t: int, x: int, y: int = 0) -> GroundTruthNode:
        return GroundTruthNode(node_id, t, 0, y, x, 0.0, float(y), float(x))

    ground_truth = SparseGroundTruthGraph(
        sample_id="sample",
        nodes=[
            gt(1, 0, 0),
            gt(2, 1, 1),
            gt(3, 2, 2, -1),
            gt(4, 2, 2, 1),
            gt(5, 3, 3, -2),
            gt(6, 3, 3, 2),
        ],
        edges=[(1, 2), (2, 3), (2, 4), (3, 5), (4, 6)],
        estimated_number_of_nodes=6,
    )

    labeled = label_division_action_official(division, graph, ground_truth)

    assert _signature(graph) == before
    assert labeled.official_label == "official_tp"
    assert labeled.official_label_basis == "patched_official_projected_graph"
