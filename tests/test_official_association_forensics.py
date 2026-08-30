from atabey.evaluation.official_association_forensics import (
    extract_official_association_correspondence,
)
from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


def _prediction(node_id: str, t: int, y: float) -> Detection:
    return Detection(node_id, "sample", t, 0, y, 0, 0, y, 0)


def _ground_truth(node_id: int, t: int, y: float) -> GroundTruthNode:
    return GroundTruthNode(node_id, t, 0, int(y), 0, 0, y, 0)


def test_extracts_official_node_and_edge_correspondence_without_mutation() -> None:
    graph = LineageGraph(
        "sample",
        detections=[_prediction("source", 0, 0.0), _prediction("target", 1, 1.0)],
        edges=[LineageEdge("source", "target")],
    )
    ground_truth = SparseGroundTruthGraph(
        "sample",
        nodes=[_ground_truth(10, 0, 0.0), _ground_truth(11, 1, 1.0)],
        edges=[(10, 11)],
        estimated_number_of_nodes=2,
    )
    before = tuple(graph.detections), tuple(graph.edges)

    correspondence = extract_official_association_correspondence(graph, ground_truth)

    assert tuple(graph.detections), tuple(graph.edges) == before
    assert {
        row.prediction_node_id: row.ground_truth_node_id
        for row in correspondence.nodes
    } == {"source": 10, "target": 11}
    assert len(correspondence.edges) == 1
    edge = correspondence.edges[0]
    assert edge.ground_truth_source_id == 10
    assert edge.ground_truth_target_id == 11
    assert edge.officially_matched is True