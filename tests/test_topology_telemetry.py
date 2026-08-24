from atabey.tracking.topology_telemetry import (
    compare_node_topology,
    summarize_node_topology,
)
from atabey.types import Detection, LineageEdge, LineageGraph


def _detection(node_id: str, frame: int) -> Detection:
    return Detection(node_id, "sample", frame, 0, 0, 0, 0, 0, 0)


def test_topology_telemetry_reports_frame_age_degree_and_support():
    graph = LineageGraph("sample")
    for node_id, frame in (("a", 0), ("b", 1), ("c", 2), ("orphan", 1)):
        graph.add_detection(_detection(node_id, frame))
    graph.add_edge(LineageEdge("a", "b"))
    graph.add_edge(LineageEdge("b", "c"))

    report = summarize_node_topology(graph)

    assert report["by_frame"] == {"0": 1, "1": 2, "2": 1}
    assert report["track_age_histogram"] == {"1": 2, "2": 1, "3": 1}
    assert report["degree_histogram"] == {"0": 1, "1": 2, "2": 1}
    assert report["continuation_support_histogram"] == {"0": 1, "1": 2, "2": 1}
    assert report["connectivity"] == {"connected": 3, "isolated": 1}
    assert report["joint_histogram"]["isolated|age=1|degree=0|support=0"] == 1
    assert len(report["bounded_node_records"]) == 4


def test_topology_telemetry_handles_empty_graph():
    report = summarize_node_topology(LineageGraph("empty"))

    assert report["node_count"] == 0
    assert report["edge_count"] == 0
    assert report["by_frame"] == {}


def test_topology_comparison_pairs_common_bounded_nodes_and_strata():
    left = LineageGraph("sample")
    right = LineageGraph("sample")
    for graph in (left, right):
        graph.add_detection(_detection("a", 0))
        graph.add_detection(_detection("b", 1))
    left.add_edge(LineageEdge("a", "b"))
    right.add_edge(LineageEdge("a", "b", relation="division"))

    comparison = compare_node_topology(
        summarize_node_topology(left), summarize_node_topology(right)
    )

    assert comparison["bounded_common_node_count"] == 2
    assert comparison["stratum_deltas_right_minus_left"]