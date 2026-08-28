from atabey.tracking.commitment_ilp_shadow import audit_commitment_ilp_funnel
from atabey.tracking.commitment_shadow import (
    CommitmentShadowRecord,
    CommitmentShadowSummary,
)
from atabey.tracking.unet_graph import graph_signature
from atabey.types import Detection, LineageEdge, LineageGraph


def _node(node_id: str, t: int, x_um: float) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id="sample",
        t=t,
        z=0.0,
        y=0.0,
        x=x_um,
        z_um=0.0,
        y_um=0.0,
        x_um=x_um,
    )


def _graph() -> LineageGraph:
    graph = LineageGraph(sample_id="sample")
    for detection in (
        _node("p1", 0, -4.0),
        _node("p2", 0, 14.0),
        _node("s1", 1, 0.0),
        _node("s2", 1, 10.0),
        _node("a", 2, 4.0),
        _node("b", 2, 6.0),
        _node("left", 3, 2.0),
        _node("right", 3, 8.0),
    ):
        graph.add_detection(detection)
    for source_id, target_id in (
        ("p1", "s1"),
        ("p2", "s2"),
        ("s1", "a"),
        ("s2", "b"),
        ("a", "left"),
        ("b", "right"),
    ):
        graph.add_edge(LineageEdge(source_id=source_id, target_id=target_id))
    return graph


def _record(
    source_id: str,
    target_id: str,
    *,
    changed: int,
    reconverged: bool,
) -> CommitmentShadowRecord:
    return CommitmentShadowRecord(
        source_id=source_id,
        target_id=target_id,
        source_frame=1,
        edge_distance_um=4.0,
        prediction_error_um=0.0,
        forward_margin_um=2.0,
        reverse_margin_um=2.0,
        local_target_count=2,
        local_competing_source_count=1,
        changed_assignment_count=changed,
        reconverged=reconverged,
    )


def _commitment() -> CommitmentShadowSummary:
    return CommitmentShadowSummary(
        sample_id="sample",
        horizon_frames=2,
        max_counterfactual_edges=8,
        eligible_edge_count=2,
        counterfactual_edge_count=2,
        commitment_sensitive_edge_count=1,
        records=(
            _record("s1", "a", changed=1, reconverged=False),
            _record("s2", "b", changed=0, reconverged=True),
        ),
    )


def test_funnel_sends_only_root_changed_windows_to_ilp_without_mutation() -> None:
    graph = _graph()
    before = graph_signature(graph)

    summary = audit_commitment_ilp_funnel(
        graph,
        _commitment(),
        baseline_change_penalty_um=0.25,
        minimum_improvement_um=0.5,
    )

    assert graph_signature(graph) == before
    assert summary.root_changed_window_count == 1
    assert summary.root_persistent_window_count == 1
    assert summary.evaluated_window_count == 1
    assert summary.primary_alternative_count == 1
    assert summary.zero_penalty_alternative_count == 1
    assert summary.persistent_zero_penalty_overlap_count == 1
    assert summary.records[0].source_id == "s1"


def test_funnel_separates_contained_primary_from_mechanism_diagnostic() -> None:
    summary = audit_commitment_ilp_funnel(
        _graph(),
        _commitment(),
        baseline_change_penalty_um=20.0,
        minimum_improvement_um=0.5,
    )

    assert summary.primary_alternative_count == 0
    assert summary.zero_penalty_alternative_count == 1
    assert summary.records[0].primary.recommendation == "keep_baseline"
    assert summary.records[0].zero_penalty_diagnostic.recommendation == "shadow_alternative"