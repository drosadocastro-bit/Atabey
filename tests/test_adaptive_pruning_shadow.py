from __future__ import annotations

from atabey.tracking.adaptive_pruning_shadow import compute_adaptive_pruning_shadow
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int) -> Detection:
    return Detection(node_id, "sample", t, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def _signature(graph: LineageGraph) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    return (
        tuple(detection.node_id for detection in graph.detections),
        tuple((edge.source_id, edge.target_id) for edge in graph.edges),
    )


def test_shadow_pruning_activates_on_fragmented_graph_without_mutating_source():
    graph = LineageGraph(
        "sample",
        [_d(f"long-{i}", i) for i in range(4)]
        + [_d(f"fragment-{i}", 0) for i in range(4)],
        [
            LineageEdge("long-0", "long-1", 0.9),
            LineageEdge("long-1", "long-2", 0.9),
            LineageEdge("long-2", "long-3", 0.9),
        ],
    )
    before = _signature(graph)
    result = compute_adaptive_pruning_shadow(
        graph,
        keep_fraction=0.75,
        fragment_size_threshold=3,
        min_fragmented_node_fraction=0.50,
        route_label="components/greedy",
    )
    assert result.summary.activated
    assert result.summary.removed_nodes == 2
    assert result.summary.shadow_nodes == 6
    assert result.summary.route_label == "components/greedy"
    assert _signature(graph) == before
    assert result.graph is not graph


def test_shadow_pruning_preserves_division_component():
    graph = LineageGraph(
        "sample",
        [_d("p", 0), _d("c1", 1), _d("c2", 1)]
        + [_d(f"noise-{i}", 0) for i in range(5)],
        [
            LineageEdge("p", "c1", 0.2, "division"),
            LineageEdge("p", "c2", 0.2, "division"),
        ],
    )
    result = compute_adaptive_pruning_shadow(
        graph,
        keep_fraction=0.50,
        fragment_size_threshold=4,
        min_fragmented_node_fraction=0.0,
        preserve_division_components=True,
    )
    kept = {detection.node_id for detection in result.graph.detections}
    assert {"p", "c1", "c2"}.issubset(kept)
    assert result.summary.protected_components == 1


def test_shadow_pruning_stays_inactive_below_fragmentation_gate():
    graph = LineageGraph(
        "sample",
        [_d(f"track-{i}", i) for i in range(5)],
        [LineageEdge(f"track-{i}", f"track-{i + 1}", 0.8) for i in range(4)],
    )
    result = compute_adaptive_pruning_shadow(
        graph,
        keep_fraction=0.50,
        fragment_size_threshold=3,
        min_fragmented_node_fraction=0.50,
    )
    assert not result.summary.activated
    assert result.summary.activation_reason == "fragmentation_below_gate"
    assert _signature(result.graph) == _signature(graph)


def test_shadow_pruning_can_restrict_activation_by_route():
    graph = LineageGraph("sample", [_d(f"noise-{i}", 0) for i in range(4)], [])
    result = compute_adaptive_pruning_shadow(
        graph,
        keep_fraction=0.50,
        fragment_size_threshold=3,
        min_fragmented_node_fraction=0.0,
        route_label="components/greedy",
        allowed_routes=frozenset({"cfar_sidelobe/bipartite"}),
    )
    assert not result.summary.activated
    assert result.summary.activation_reason == "route_not_enabled"
