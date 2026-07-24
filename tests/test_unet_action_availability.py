from atabey.evaluation.detection_availability import DetectionPeak
from atabey.tracking.unet_action_availability import (
    UnetShadowPeak,
    action_matches_registered_division,
    enumerate_anchored_division_actions,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, y_um: float) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id="sample",
        t=t,
        z=0.0,
        y=y_um,
        x=0.0,
        z_um=0.0,
        y_um=y_um,
        x_um=0.0,
    )


def _peak(peak_id: str, t: int, y_um: float) -> UnetShadowPeak:
    return UnetShadowPeak(
        peak_id=peak_id,
        sample_id="sample",
        t=t,
        z_um=0.0,
        y_um=y_um,
        x_um=0.0,
        confidence=0.99,
    )


def _signature(graph: LineageGraph) -> tuple:
    return tuple(graph.detections), tuple(graph.edges)


def test_action_formation_uses_prior_track_prediction_without_mutating_graph():
    graph = LineageGraph(
        "sample",
        [_d("history", 0, 0.0), _d("anchor", 1, 1.0)],
        [LineageEdge("history", "anchor")],
    )
    peaks = [
        _peak("parent", 2, 2.0),
        _peak("daughter_a", 3, 1.0),
        _peak("daughter_b", 3, 3.0),
        _peak("unanchored_parent", 2, 30.0),
        _peak("unrelated_daughter", 3, 30.0),
    ]
    before = _signature(graph)

    result = enumerate_anchored_division_actions(
        graph,
        peaks,
        parent_t=2,
        anchor_radius_um=2.0,
        formation_radius_um=4.0,
    )

    assert _signature(graph) == before
    assert result.anchor_count == 1
    assert result.parent_peak_count == 2
    assert result.anchored_parent_count == 1
    assert result.division_action_count == 1
    assert result.actions[0].anchor_id == "anchor"
    assert result.actions[0].parent.peak_id == "parent"
    assert {
        result.actions[0].child_1.peak_id,
        result.actions[0].child_2.peak_id,
    } == {"daughter_a", "daughter_b"}


def test_registered_division_label_is_order_invariant_and_post_formation():
    action = enumerate_anchored_division_actions(
        LineageGraph("sample", [_d("anchor", 0, 0.0)], []),
        [
            _peak("parent", 1, 0.0),
            _peak("daughter_a", 2, -2.0),
            _peak("daughter_b", 2, 2.0),
        ],
        parent_t=1,
        anchor_radius_um=1.0,
        formation_radius_um=5.0,
    ).actions[0]

    assert action_matches_registered_division(
        action,
        parent_position_um=(0.0, 0.0, 0.0),
        daughter_positions_um=((0.0, 2.0, 0.0), (0.0, -2.0, 0.0)),
        match_radius_um=0.1,
    )


def test_detection_peak_conversion_keeps_the_type_boundary_explicit():
    peak = DetectionPeak(1, 0.0, 1.0, 2.0, 0.99)
    shadow = UnetShadowPeak(
        "peak",
        "sample",
        peak.t,
        peak.z_um,
        peak.y_um,
        peak.x_um,
        peak.confidence,
    )
    assert shadow.position_um == peak.position_um


def test_isolated_candidate_fork_matches_the_patched_official_metric():
    import pytest

    pytest.importorskip("tracking_cellmot")
    pytest.importorskip("tracksdata")
    from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
    from atabey.tracking.unet_action_availability import (
        AnchoredDivisionAction,
        evaluate_action_as_official_fork,
    )

    def gt(node_id: int, t: int, y: int) -> GroundTruthNode:
        return GroundTruthNode(node_id, t, 0, y, 0, 0.0, float(y), 0.0)

    action = AnchoredDivisionAction(
        sample_id="sample",
        t=1,
        anchor_id="anchor",
        parent=_peak("parent", 1, 0.0),
        child_1=_peak("daughter_a", 2, -1.0),
        child_2=_peak("daughter_b", 2, 1.0),
        anchor_prediction_distance_um=0.0,
    )
    ground_truth = SparseGroundTruthGraph(
        sample_id="sample",
        nodes=[
            gt(1, 0, 0),
            gt(2, 1, 0),
            gt(3, 2, -1),
            gt(4, 2, 1),
            gt(5, 3, -2),
            gt(6, 3, 2),
        ],
        edges=[(1, 2), (2, 3), (2, 4), (3, 5), (4, 6)],
        estimated_number_of_nodes=6,
    )

    assert evaluate_action_as_official_fork(
        action,
        ground_truth,
        gt_parent_id=2,
    )
