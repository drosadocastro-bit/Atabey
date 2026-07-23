from __future__ import annotations

import pytest

from atabey.evaluation.semantic_positive_availability import (
    audit_gt_division_positive_availability,
    gt_division_parent_ids,
    gt_division_window,
)
from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, x: float, y: float = 0.0) -> Detection:
    return Detection(node_id, "sample", t, 0.0, y, x, 0.0, y, x)


def _gt_node(node_id: int, t: int, x: int, y: int = 0) -> GroundTruthNode:
    return GroundTruthNode(node_id, t, 0, y, x, 0.0, float(y), float(x))


def _ground_truth() -> SparseGroundTruthGraph:
    return SparseGroundTruthGraph(
        "sample",
        [
            _gt_node(1, 0, 0),
            _gt_node(2, 1, 1),
            _gt_node(3, 2, 2, -1),
            _gt_node(4, 2, 2, 1),
            _gt_node(5, 3, 3, -2),
            _gt_node(6, 3, 3, 2),
            _gt_node(99, 8, 20),
        ],
        [(1, 2), (2, 3), (2, 4), (3, 5), (4, 6)],
        7,
    )


def _graph() -> LineageGraph:
    return LineageGraph(
        "sample",
        [
            _d("pre", 0, 0.0),
            _d("p", 1, 1.0),
            _d("a", 2, 2.0, -1.0),
            _d("b", 2, 2.0, 1.0),
            _d("a2", 3, 3.0, -2.0),
            _d("b2", 3, 3.0, 2.0),
        ],
        [
            LineageEdge("pre", "p"),
            LineageEdge("p", "a", relation="division"),
            LineageEdge("p", "b", relation="division"),
            LineageEdge("a", "a2"),
            LineageEdge("b", "b2"),
        ],
    )


def _signature(graph: LineageGraph):
    return tuple(graph.detections), tuple(graph.edges)


def test_gt_division_window_matches_parent_children_and_one_step_context():
    gt = _ground_truth()

    window = gt_division_window(gt, 2)

    assert gt_division_parent_ids(gt) == (2,)
    assert {node.node_id for node in window.nodes} == {1, 2, 3, 4, 5, 6}
    assert set(window.edges) == {(1, 2), (2, 3), (2, 4), (3, 5), (4, 6)}


def test_availability_finds_one_canonical_official_positive_without_mutation():
    pytest.importorskip("tracking_cellmot")
    pytest.importorskip("tracksdata")
    graph = _graph()
    before = _signature(graph)

    result = audit_gt_division_positive_availability(graph, _ground_truth(), 2)

    assert _signature(graph) == before
    assert result.official_positive is True
    assert result.status == "official_positive"
    assert result.parent_candidate_count == 1
    assert result.daughter_1_candidate_count == 2
    assert result.daughter_2_candidate_count == 2
    assert result.candidate_action_count >= 1
    assert result.official_attempt_count >= 1
    assert result.canonical_parent_id == "p"
    assert {result.canonical_child_1_id, result.canonical_child_2_id} == {"a", "b"}
    assert result.canonical_evidence is not None
    assert result.canonical_evidence.decision == "abstain"
    assert result.canonical_evidence.official_label == "official_tp"


def test_availability_separates_missing_parent_from_missing_daughters():
    gt = _ground_truth()
    no_parent = LineageGraph(
        "sample",
        [_d("a", 2, 2.0, -1.0), _d("b", 2, 2.0, 1.0)],
        [],
    )
    no_daughters = LineageGraph("sample", [_d("p", 1, 1.0)], [])

    parent_result = audit_gt_division_positive_availability(no_parent, gt, 2)
    daughter_result = audit_gt_division_positive_availability(no_daughters, gt, 2)

    assert parent_result.status == "no_parent_detection_within_7um"
    assert daughter_result.status == "fewer_than_two_daughter_lineages_within_7um"


def test_availability_reports_formation_failure_without_scoring():
    gt = _ground_truth()
    graph = LineageGraph(
        "sample",
        [
            _d("p", 1, -5.9),
            _d("a", 2, 7.9, -1.0),
            _d("b", 2, 7.9, 1.0),
        ],
        [],
    )

    result = audit_gt_division_positive_availability(
        graph,
        gt,
        2,
        formation_radius_um=13.0,
    )

    assert result.status == "no_pair_inside_14um_formation_radius"
    assert result.candidate_action_count == 0
    assert result.official_attempt_count == 0
