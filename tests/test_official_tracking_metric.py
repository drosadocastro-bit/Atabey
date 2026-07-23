from __future__ import annotations

import pytest

pytest.importorskip("tracking_cellmot")
pytest.importorskip("tracksdata")

from atabey.evaluation.official_tracking_metric import evaluate_official_tracking
from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, y: float) -> Detection:
    return Detection(node_id, "sample", t, 0.0, y, 0.0, 0.0, y, 0.0)


def _g(node_id: int, t: int, y: float) -> GroundTruthNode:
    return GroundTruthNode(node_id, t, 0, 0, 0, 0.0, y, 0.0)


def _gt() -> SparseGroundTruthGraph:
    return SparseGroundTruthGraph(
        "sample",
        [_g(1, 0, 0.0), _g(2, 1, 0.0)],
        [(1, 2)],
        2,
    )


def test_official_tracking_adapter_scores_perfect_graph():
    graph = LineageGraph(
        "sample",
        [_d("a", 0, 0.0), _d("b", 1, 0.0)],
        [LineageEdge("a", "b")],
    )
    result = evaluate_official_tracking(graph, _gt())
    assert (result.edge_tp, result.edge_fp, result.edge_fn) == (1, 0, 0)
    assert result.edge_jaccard == pytest.approx(1.0)
    assert result.adjusted_edge_jaccard == pytest.approx(1.0)
    assert result.node_recall == pytest.approx(1.0)
    assert result.total_node_ratio == pytest.approx(0.0)


def test_official_tracking_adapter_applies_node_count_penalty_to_unsupported_component():
    graph = LineageGraph(
        "sample",
        [
            _d("a", 0, 0.0),
            _d("b", 1, 0.0),
            _d("noise-a", 0, 100.0),
            _d("noise-b", 1, 100.0),
        ],
        [LineageEdge("a", "b"), LineageEdge("noise-a", "noise-b")],
    )
    result = evaluate_official_tracking(graph, _gt())
    assert (result.edge_tp, result.edge_fp, result.edge_fn) == (1, 0, 0)
    assert result.edge_jaccard == pytest.approx(1.0)
    assert result.total_node_ratio == pytest.approx(1.0)
    assert result.adjusted_edge_jaccard == pytest.approx(0.9)


def test_official_tracking_adapter_uses_explicit_node_estimate_override():
    graph = LineageGraph(
        "sample",
        [_d("a", 0, 0.0), _d("b", 1, 0.0)],
        [LineageEdge("a", "b")],
    )
    result = evaluate_official_tracking(graph, _gt(), estimated_total_nodes=4)
    assert result.estimated_total_nodes == 4
    assert result.total_node_ratio == pytest.approx(-0.5)
    assert result.adjusted_edge_jaccard == pytest.approx(1.05)
