from atabey.evaluation.sparse_ground_truth import (
    evaluate_sparse_ground_truth,
    match_sparse_centroids,
)
from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


def make_gt_node(node_id, t, z_um, y_um, x_um):
    return GroundTruthNode(
        node_id=node_id,
        t=t,
        z=0,
        y=0,
        x=0,
        z_um=z_um,
        y_um=y_um,
        x_um=x_um,
    )


def make_detection(node_id, t, z_um, y_um, x_um):
    return Detection(
        node_id=node_id,
        sample_id="sample",
        t=t,
        z=z_um,
        y=y_um,
        x=x_um,
        z_um=z_um,
        y_um=y_um,
        x_um=x_um,
    )


def test_match_sparse_centroids_requires_same_timepoint_and_radius():
    graph = LineageGraph(sample_id="sample")
    graph.add_detection(make_detection("p1", 0, 0.0, 0.0, 1.0))
    graph.add_detection(make_detection("wrong_time", 1, 0.0, 0.0, 0.0))
    gt = SparseGroundTruthGraph(
        sample_id="sample",
        nodes=[make_gt_node(10, 0, 0.0, 0.0, 0.0), make_gt_node(11, 0, 0.0, 0.0, 20.0)],
        edges=[],
        estimated_number_of_nodes=100,
    )

    matches = match_sparse_centroids(graph, gt, radius_um=7.0)

    assert matches[0].matched is True
    assert matches[0].prediction_node_id == "p1"
    assert matches[1].matched is False


def test_evaluate_sparse_ground_truth_reports_node_edge_and_count_calibration():
    graph = LineageGraph(sample_id="sample")
    graph.add_detection(make_detection("p1", 0, 0.0, 0.0, 0.0))
    graph.add_detection(make_detection("p2", 1, 0.0, 0.0, 1.0))
    graph.add_detection(make_detection("extra", 1, 20.0, 20.0, 20.0))
    graph.add_edge(LineageEdge("p1", "p2"))
    graph.add_edge(LineageEdge("p1", "extra"))
    gt = SparseGroundTruthGraph(
        sample_id="sample",
        nodes=[make_gt_node(10, 0, 0.0, 0.0, 0.0), make_gt_node(11, 1, 0.0, 0.0, 1.5)],
        edges=[(10, 11)],
        estimated_number_of_nodes=6,
    )

    report = evaluate_sparse_ground_truth(graph, gt, match_radius_um=7.0)

    assert report.predicted_nodes == 3
    assert report.predicted_edges == 2
    assert report.sparse_ground_truth_nodes == 2
    assert report.matched_sparse_nodes == 2
    assert report.sparse_recall == 1.0
    assert report.evaluable_sparse_edges == 1
    assert report.matched_sparse_edges == 1
    assert report.sparse_edge_recall == 1.0
    assert report.predicted_to_estimated_node_ratio == 0.5
    assert "not the official Kaggle metric" in report.caution
