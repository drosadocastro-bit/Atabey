from atabey.tracking.bounded_ilp_shadow import audit_bounded_ilp_window
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


def _crossing_graph() -> LineageGraph:
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


def test_joint_ilp_recommends_lower_cost_crossing_repair_without_mutation() -> None:
    graph = _crossing_graph()
    before = graph_signature(graph)

    result = audit_bounded_ilp_window(
        graph,
        trigger_source_id="s1",
        trigger_target_id="a",
        max_link_distance_um=9.0,
        baseline_change_penalty_um=0.25,
        minimum_improvement_um=0.5,
    )

    assert graph_signature(graph) == before
    assert result.solver_status == "optimal"
    assert result.recommendation == "shadow_alternative"
    assert result.objective_improvement_um > 0.5
    assert set(result.removed_edges) == {("a", "left"), ("b", "right")}
    assert set(result.added_edges) == {("a", "right"), ("b", "left")}


def test_joint_ilp_abstains_when_containment_penalty_blocks_small_change() -> None:
    graph = _crossing_graph()

    result = audit_bounded_ilp_window(
        graph,
        trigger_source_id="s1",
        trigger_target_id="a",
        max_link_distance_um=9.0,
        baseline_change_penalty_um=20.0,
        minimum_improvement_um=0.5,
    )

    assert result.solver_status == "optimal"
    assert result.recommendation == "keep_baseline"
    assert result.proposed_added_edges == ()
    assert result.proposed_removed_edges == ()
    assert result.added_edges == ()
    assert result.removed_edges == ()


def test_joint_ilp_refuses_window_above_variable_budget() -> None:
    graph = _crossing_graph()

    result = audit_bounded_ilp_window(
        graph,
        trigger_source_id="s1",
        trigger_target_id="a",
        max_variables=1,
    )

    assert result.solver_status == "budget_exceeded"
    assert result.recommendation == "keep_baseline"
    assert result.variable_count > 1