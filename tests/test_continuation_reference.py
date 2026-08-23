from atabey.tracking.continuation_reference import (
    extract_continuation_references,
    reference_as_row,
)
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


def _chain(
    *,
    child_y: float = 2.0,
    distractors: list[Detection] | None = None,
    extra_edges: list[LineageEdge] | None = None,
) -> LineageGraph:
    detections = [
        _d("anchor", 0, 0.0),
        _d("parent", 1, 1.0),
        _d("child", 2, child_y),
        *(distractors or []),
    ]
    edges = [
        LineageEdge("anchor", "parent"),
        LineageEdge("parent", "child"),
        *(extra_edges or []),
    ]
    return LineageGraph("sample", detections, edges)


def test_extracts_route_neutral_three_frame_motion_mutual_reference():
    graph = _chain(
        distractors=[
            _d("other_parent", 1, 20.0),
            _d("other_child", 2, 5.0),
        ]
    )
    before = tuple(graph.detections), tuple(graph.edges)

    audit = extract_continuation_references(
        graph,
        registered_division_times=[],
    )

    assert (tuple(graph.detections), tuple(graph.edges)) == before
    assert len(audit.references) == 1
    row = reference_as_row(audit.references[0])
    assert row["anchor_id"] == "anchor"
    assert row["parent_id"] == "parent"
    assert row["child_id"] == "child"
    assert row["prediction_error_um"] == 0.0
    assert row["alternative_target_count_14um"] == 1
    assert row["local_competing_source_count_14um"] == 0
    assert row["reference_is_ground_truth"] is False
    assert row["graph_mutated"] is False


def test_excludes_any_chain_frame_within_division_radius():
    graph = _chain()

    near = extract_continuation_references(
        graph,
        registered_division_times=[4],
        exclusion_radius_frames=2,
    )
    far = extract_continuation_references(
        graph,
        registered_division_times=[5],
        exclusion_radius_frames=2,
    )

    assert len(near.references) == 0
    assert near.rejection_reasons["near_registered_division"] == 1
    assert len(far.references) == 1


def test_rejects_nonexclusive_central_ownership():
    graph = _chain(
        distractors=[_d("other_child", 2, 3.0)],
        extra_edges=[LineageEdge("parent", "other_child")],
    )

    audit = extract_continuation_references(
        graph,
        registered_division_times=[],
    )

    assert len(audit.references) == 0
    assert audit.rejection_reasons["central_ownership_not_exclusive"] >= 1


def test_rejects_wrong_or_tied_motion_mutual_target():
    wrong = _chain(
        child_y=2.5,
        distractors=[_d("predicted", 2, 2.0)],
    )
    tied = _chain(
        child_y=2.0,
        distractors=[_d("tied", 2, 2.0)],
    )

    wrong_audit = extract_continuation_references(
        wrong,
        registered_division_times=[],
    )
    tied_audit = extract_continuation_references(
        tied,
        registered_division_times=[],
    )

    assert len(wrong_audit.references) == 0
    assert len(tied_audit.references) == 0
    assert wrong_audit.rejection_reasons["not_strict_motion_mutual"] == 1
    assert tied_audit.rejection_reasons["not_strict_motion_mutual"] == 1


def test_rejects_child_outside_local_action_radius():
    graph = _chain(child_y=20.0)

    audit = extract_continuation_references(
        graph,
        registered_division_times=[],
        local_radius_um=14.0,
    )

    assert len(audit.references) == 0
    assert audit.rejection_reasons["child_outside_local_radius"] == 1


def test_requires_continuation_relation_for_both_chain_edges():
    parent_division = LineageGraph(
        "sample",
        [_d("anchor", 0, 0.0), _d("parent", 1, 1.0), _d("child", 2, 2.0)],
        [
            LineageEdge("anchor", "parent", relation="division"),
            LineageEdge("parent", "child"),
        ],
    )
    child_division = LineageGraph(
        "sample",
        [_d("anchor", 0, 0.0), _d("parent", 1, 1.0), _d("child", 2, 2.0)],
        [
            LineageEdge("anchor", "parent"),
            LineageEdge("parent", "child", relation="division"),
        ],
    )

    first = extract_continuation_references(
        parent_division,
        registered_division_times=[],
    )
    second = extract_continuation_references(
        child_division,
        registered_division_times=[],
    )

    assert len(first.references) == 0
    assert len(second.references) == 0
