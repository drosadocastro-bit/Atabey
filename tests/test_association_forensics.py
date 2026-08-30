from atabey.tracking.association_forensics import (
    association_frame_payload,
    association_graph_payload,
    audit_motion_mutual_frame,
    audit_motion_mutual_graph,
    classify_regression_mechanism,
)
from atabey.tracking.nearest_neighbor import link_adjacent_timepoints
from atabey.types import Detection, LineageEdge, LineageGraph


def _detection(node_id: str, t: int, y: float) -> Detection:
    return Detection(node_id, "sample", t, 0, y, 0, 0, y, 0)


def test_audit_reports_candidates_conflicts_and_pruning_survival_without_mutation() -> None:
    anchor = _detection("anchor", 0, -2.0)
    source = _detection("source", 1, 0.0)
    competitor = _detection("competitor", 1, 2.2)
    preferred = _detection("preferred", 2, 2.1)
    alternative = _detection("alternative", 2, 4.0)
    previous = [source, competitor]
    current = [preferred, alternative]
    predecessors = {source.node_id: anchor}
    before = tuple(previous), tuple(current), dict(predecessors)
    edges = link_adjacent_timepoints(
        previous,
        current,
        5.0,
        strategy="motion_mutual",
        predecessor_by_node_id=predecessors,
    )

    audit = audit_motion_mutual_frame(
        previous,
        current,
        5.0,
        predecessors,
        edges,
        surviving_edges={("competitor", "preferred")},
    )

    assert (tuple(previous), tuple(current), predecessors) == before
    rows = {row.source_id: row for row in audit.sources}
    assert rows["source"].candidate_count == 2
    assert rows["source"].nearest_target_id == "preferred"
    assert rows["source"].nearest_second_margin_um == 1.9
    assert rows["source"].mutuality_conflict is True
    assert rows["source"].unmatched is True
    assert rows["source"].velocity_um == (0.0, 2.0, 0.0)
    assert rows["source"].local_source_density == 1
    assert rows["source"].crossing_competitor_count == 1
    accepted = [candidate for candidate in audit.candidates if candidate.accepted]
    assert [(candidate.source_id, candidate.target_id) for candidate in accepted] == [
        ("competitor", "preferred")
    ]
    assert accepted[0].survives_pruning is True


def test_audit_handles_empty_frames_and_rejects_invalid_radius() -> None:
    assert audit_motion_mutual_frame([], [], 9.0, {}, []).sources == ()

    try:
        audit_motion_mutual_frame([], [], 0.0, {}, [])
    except ValueError as error:
        assert str(error) == "max_link_distance_um must be positive"
    else:
        raise AssertionError("invalid radius should fail closed")


def test_graph_audit_reports_pruning_and_preserves_both_graphs() -> None:
    graph = LineageGraph("sample")
    for node in (
        _detection("anchor", 0, -1.0),
        _detection("source", 1, 0.0),
        _detection("target", 2, 1.0),
    ):
        graph.add_detection(node)
    graph.add_edge(LineageEdge("anchor", "source"))
    graph.add_edge(LineageEdge("source", "target"))
    pruned = LineageGraph(
        "sample",
        detections=list(graph.detections),
        edges=[LineageEdge("anchor", "source")],
    )
    before = tuple(graph.detections), tuple(graph.edges), tuple(pruned.edges)

    audit = audit_motion_mutual_graph(graph, post_pruning_graph=pruned)

    assert audit.graph_unchanged is True
    target_candidate = next(
        candidate
        for frame in audit.frames
        for candidate in frame.candidates
        if candidate.target_id == "target"
    )
    assert target_candidate.accepted is True
    assert target_candidate.survives_pruning is False
    assert (tuple(graph.detections), tuple(graph.edges), tuple(pruned.edges)) == before


def test_failure_taxonomy_requires_direct_candidate_evidence() -> None:
    unknown = dict(
        correct_source_detected=None,
        correct_target_detected=None,
        correct_candidate_present=None,
        correct_candidate_accepted=None,
        correct_edge_survives_pruning=None,
        adjustment_only_effect=False,
    )
    assert classify_regression_mechanism(**unknown) == "unresolved_insufficient_telemetry"
    assert classify_regression_mechanism(
        **{**unknown, "correct_candidate_present": False}
    ) == "candidate_generation_failure"
    assert classify_regression_mechanism(
        **{
            **unknown,
            "correct_candidate_present": True,
            "correct_candidate_accepted": False,
        }
    ) == "candidate_selection_ranking_failure"
    assert classify_regression_mechanism(
        **{
            **unknown,
            "correct_candidate_present": True,
            "correct_candidate_accepted": True,
            "correct_edge_survives_pruning": False,
        }
    ) == "post_link_pruning_interaction"
    assert classify_regression_mechanism(
        **{**unknown, "adjustment_only_effect": True}
    ) == "metric_node_adjustment_only_effect"


def test_visualization_payload_separates_candidate_and_v19_layers() -> None:
    source = _detection("source", 1, 0.0)
    target = _detection("target", 2, 1.0)
    edge = LineageEdge("source", "target")
    audit = audit_motion_mutual_frame([source], [target], 9.0, {}, [edge])

    payload = association_frame_payload(
        audit,
        [source],
        [target],
        v19_edges=[LineageEdge("v19-source", "v19-target")],
    )

    assert payload["candidate_edges"] == [
        {
            "source_id": "source",
            "target_id": "target",
            "rank": 1,
            "accepted": True,
            "mutual": True,
            "survives_pruning": None,
            "prediction_error_um": 1.0,
            "edge_length_um": 1.0,
        }
    ]
    assert payload["v19_edges"] == [
        {"source_id": "v19-source", "target_id": "v19-target"}
    ]


def test_graph_visualization_payload_exposes_pruning_and_v19_nodes() -> None:
    source = _detection("source", 0, 0.0)
    target = _detection("target", 1, 1.0)
    edge = LineageEdge("source", "target")
    relink = LineageGraph("sample", [source, target], [edge])
    post_pruning = LineageGraph("sample", [source], [])
    v19_source = _detection("v19-source", 0, 0.2)
    v19_target = _detection("v19-target", 1, 1.2)
    v19 = LineageGraph(
        "sample",
        [v19_source, v19_target],
        [LineageEdge("v19-source", "v19-target")],
    )
    audit = audit_motion_mutual_graph(relink, post_pruning_graph=post_pruning)

    payload = association_graph_payload(audit, relink, post_pruning, v19)

    assert payload["read_only"] is True
    assert payload["coordinate_system"] == "physical_microns_zyx"
    frame = payload["frames"][0]
    assert frame["v24_3_pruned_node_ids"] == ["target"]
    assert frame["v24_3_retained_edges"] == []
    assert [node["node_id"] for node in frame["v19_nodes"]] == [
        "v19-source",
        "v19-target",
    ]