from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.tracking.v26_a_forward_ranking_shadow import (
    link_step_ranked_motion_mutual,
    relink_detections_step_ranked,
)
from atabey.types import Detection


def _detection(node_id: str, t: int, y: float) -> Detection:
    return Detection(node_id, "sample", t, 0, y, 0, 0, y, 0)


def _edge_ids(edges: list) -> list[tuple[str, str]]:
    return [(edge.source_id, edge.target_id) for edge in edges]


def test_step_ranking_changes_only_forward_candidate_order() -> None:
    predecessor = _detection("predecessor", 0, -4.0)
    source = _detection("source", 1, 0.0)
    step_nearest = _detection("step-nearest", 2, 1.0)
    prediction_nearest = _detection("prediction-nearest", 2, 4.0)
    predecessors = {source.node_id: predecessor}

    frozen = link_adjacent_timepoints(
        [source],
        [step_nearest, prediction_nearest],
        9.0,
        strategy="motion_mutual",
        predecessor_by_node_id=predecessors,
    )
    ablation = link_step_ranked_motion_mutual(
        [source],
        [step_nearest, prediction_nearest],
        9.0,
        predecessors,
    )

    assert _edge_ids(frozen) == [("source", "prediction-nearest")]
    assert _edge_ids(ablation) == [("source", "step-nearest")]


def test_step_ranking_preserves_both_candidate_generation_gates() -> None:
    predecessor = _detection("predecessor", 0, -9.0)
    source = _detection("source", 1, 0.0)
    prediction_gate_failure = _detection("prediction-gate-failure", 2, -0.5)
    feasible = _detection("feasible", 2, 1.0)

    edges = link_step_ranked_motion_mutual(
        [source],
        [prediction_gate_failure, feasible],
        9.0,
        {source.node_id: predecessor},
    )

    assert _edge_ids(edges) == [("source", "feasible")]


def test_step_ranking_preserves_reverse_mutuality() -> None:
    predecessor = _detection("predecessor", 0, -1.0)
    source = _detection("source", 1, 0.0)
    physical_owner = _detection("physical-owner", 1, 1.8)
    contested = _detection("contested", 2, 1.7)

    edges = link_step_ranked_motion_mutual(
        [source, physical_owner],
        [contested],
        9.0,
        {source.node_id: predecessor},
    )

    assert _edge_ids(edges) == [("physical-owner", "contested")]


def test_step_ranking_matches_frozen_linker_without_motion_history() -> None:
    previous = [_detection("source-a", 0, 0.0), _detection("source-b", 0, 5.0)]
    current = [_detection("target-a", 1, 1.0), _detection("target-b", 1, 6.0)]

    frozen = link_adjacent_timepoints(
        previous,
        current,
        9.0,
        strategy="motion_mutual",
        predecessor_by_node_id={},
    )
    ablation = link_step_ranked_motion_mutual(previous, current, 9.0, {})

    assert _edge_ids(ablation) == _edge_ids(frozen)


def test_relink_step_ranking_preserves_supplied_detections() -> None:
    detections = [
        _detection("predecessor", 0, -4.0),
        _detection("source", 1, 0.0),
        _detection("step-nearest", 2, 1.0),
        _detection("prediction-nearest", 2, 4.0),
    ]
    before = tuple(detections)

    graph = relink_detections_step_ranked("sample", detections)

    assert tuple(detections) == before
    assert tuple(graph.detections) == before
    assert _edge_ids(graph.edges) == [
        ("predecessor", "source"),
        ("source", "step-nearest"),
    ]