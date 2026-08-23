import json

import pytest

from atabey.tracking.continuation_features import (
    CONTINUATION_FEATURE_NAMES,
    continuation_candidate_id,
    iter_continuation_candidate_rows,
)
from atabey.tracking.continuation_reference import extract_continuation_references
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, y: float, x: float = 0.0) -> Detection:
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
    )


def test_builds_reference_and_unknown_alternative_without_mutation():
    graph = LineageGraph(
        "sample",
        [
            _d("anchor", 0, 0.0),
            _d("parent", 1, 1.0),
            _d("other_parent", 1, 12.0),
            _d("child", 2, 2.0),
            _d("alternative", 2, 4.0),
        ],
        [
            LineageEdge("anchor", "parent"),
            LineageEdge("parent", "child"),
        ],
    )
    before = tuple(graph.detections), tuple(graph.edges)
    audit = extract_continuation_references(
        graph,
        registered_division_times=[],
    )

    rows = list(
        iter_continuation_candidate_rows(
            graph,
            audit.references,
            fold=2,
            detector="components",
            link_strategy="greedy",
        )
    )

    assert (tuple(graph.detections), tuple(graph.edges)) == before
    assert len(rows) == 2
    reference = next(row for row in rows if row["weak_preference_target"] == 1)
    alternative = next(row for row in rows if row["weak_preference_target"] == 0)
    assert reference["candidate_role"] == "weak_reference_preferred"
    assert alternative["candidate_role"] == "weak_alternative_unknown"
    assert reference["biological_label"] == "unknown"
    assert alternative["alternative_is_negative"] is False
    assert reference["reference_is_ground_truth"] is False
    assert reference["prediction_error_um"] == pytest.approx(0.0)
    assert reference["forward_rank_local_14um"] == 1
    assert alternative["forward_rank_local_14um"] == 2
    assert reference["route"] == "components/greedy"
    assert sum(row["sample_hierarchical_weight"] for row in rows) == pytest.approx(
        1.0
    )
    assert set(json.loads(reference["available_features"])).issubset(
        CONTINUATION_FEATURE_NAMES
    )
    assert reference["semantic_score"] == ""
    assert reference["assignment_selected"] is False
    assert reference["graph_mutated"] is False


def test_missing_features_are_explicit_and_ids_are_stable():
    graph = LineageGraph(
        "sample",
        [_d("anchor", 0, 0.0), _d("parent", 1, 0.0), _d("child", 2, 0.0)],
        [LineageEdge("anchor", "parent"), LineageEdge("parent", "child")],
    )
    audit = extract_continuation_references(
        graph,
        registered_division_times=[],
    )
    row = next(
        iter_continuation_candidate_rows(
            graph,
            audit.references,
            fold=1,
            detector="components",
            link_strategy="greedy",
        )
    )
    missing = json.loads(row["missing_features"])

    assert missing["step_distance_ratio"] == "zero_anchor_parent_distance"
    assert missing["turn_angle_deg"] == "zero_motion_vector"
    assert missing["forward_competitor_margin_um"] == "no_other_local_target"
    assert missing["reverse_competitor_margin_um"] == "no_other_local_source"
    assert row["candidate_id"] == continuation_candidate_id(
        row["reference_id"], row["candidate_child_id"]
    )
