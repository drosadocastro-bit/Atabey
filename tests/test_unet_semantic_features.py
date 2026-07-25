import json

from atabey.tracking.unet_action_availability import (
    AnchoredDivisionAction,
    UnetShadowPeak,
    enumerate_anchored_division_actions,
)
from atabey.tracking.unet_semantic_features import (
    build_event_feature_context,
    division_action_feature_row,
    semantic_action_id,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, y_um: float, x_um: float = 0.0) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id="sample",
        t=t,
        z=0.0,
        y=y_um,
        x=x_um,
        z_um=0.0,
        y_um=y_um,
        x_um=x_um,
    )


def _p(peak_id: str, t: int, y_um: float, x_um: float, confidence: float):
    return UnetShadowPeak(
        peak_id=peak_id,
        sample_id="sample",
        t=t,
        z_um=0.0,
        y_um=y_um,
        x_um=x_um,
        confidence=confidence,
    )


def test_division_action_features_are_parent_centered_and_explicitly_missing():
    graph = LineageGraph(
        "sample",
        [_d("history", 0, 0.0), _d("anchor", 1, 1.0)],
        [LineageEdge("history", "anchor")],
    )
    peaks = [
        _p("parent", 2, 2.0, 0.0, 0.99),
        _p("other_parent", 2, 2.0, 5.0, 0.98),
        _p("left", 3, 3.0, -1.0, 0.97),
        _p("right", 3, 3.0, 1.0, 0.96),
    ]
    enumeration = enumerate_anchored_division_actions(
        graph,
        peaks,
        parent_t=2,
        anchor_radius_um=6.0,
        formation_radius_um=3.0,
    )
    action = next(row for row in enumeration.actions if row.parent.peak_id == "parent")
    context = build_event_feature_context(graph, peaks, enumeration)

    row = division_action_feature_row(action, context)

    assert row["anchor_speed_um_per_frame"] == 1.0
    assert row["anchor_to_parent_distance_um"] == 1.0
    assert row["child_1_distance_um"] == 2 ** 0.5
    assert row["child_2_distance_um"] == 2 ** 0.5
    assert row["child_separation_um"] == 2.0
    assert row["child_distance_ratio"] == 1.0
    assert row["split_angle_deg"] == 90.0
    assert row["mean_detection_confidence"] == 0.9733333333333333
    assert row["minimum_detection_confidence"] == 0.96
    assert row["parent_density_10um"] == 2
    assert row["child_1_density_10um"] == 2
    missing = json.loads(row["missing_features"])
    assert missing["immediate_separation_growth_um"] == "future_unet_frames_not_exported"
    assert missing["volume_conservation_error"] == "unet_peak_has_no_component_volume"
    assert "split_angle_deg" in json.loads(row["available_features"])


def test_action_ids_are_order_stable_and_sensitive_to_ownership():
    parent = _p("parent", 2, 0.0, 0.0, 0.99)
    left = _p("left", 3, -1.0, 0.0, 0.99)
    right = _p("right", 3, 1.0, 0.0, 0.99)
    first = AnchoredDivisionAction("sample", 2, "anchor_a", parent, left, right, 0.0)
    same = AnchoredDivisionAction("sample", 2, "anchor_a", parent, left, right, 5.0)
    other_owner = AnchoredDivisionAction("sample", 2, "anchor_b", parent, left, right, 0.0)

    assert semantic_action_id(first) == semantic_action_id(same)
    assert semantic_action_id(first) != semantic_action_id(other_owner)
