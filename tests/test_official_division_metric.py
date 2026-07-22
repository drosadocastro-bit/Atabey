from __future__ import annotations

import pytest

pytest.importorskip("tracking_cellmot")
pytest.importorskip("tracksdata")

from atabey.evaluation.official_division_metric import evaluate_official_divisions
from atabey.io.geff_reader import GroundTruthNode, SparseGroundTruthGraph
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, y: float) -> Detection:
    return Detection(node_id, "sample", t, 0.0, y, 0.0, 0.0, y, 0.0)


def _g(node_id: int, t: int, y: float) -> GroundTruthNode:
    return GroundTruthNode(node_id, t, 0, 0, 0, 0.0, y, 0.0)


def _gt() -> SparseGroundTruthGraph:
    return SparseGroundTruthGraph(
        "sample",
        [_g(1, 0, 0.0), _g(2, 1, 0.0), _g(3, 2, 5.0), _g(4, 2, -5.0)],
        [(1, 2), (2, 3), (2, 4)],
        None,
    )


def test_official_adapter_scores_a_genuine_local_fork():
    graph = LineageGraph(
        "sample",
        [_d("p", 0, 0.0), _d("d", 1, 0.0), _d("c1", 2, 5.0), _d("c2", 2, -5.0)],
        [LineageEdge("p", "d"), LineageEdge("d", "c1"), LineageEdge("d", "c2")],
    )
    result = evaluate_official_divisions(graph, _gt())
    assert (result.tp, result.fp, result.fn) == (1, 0, 0)
    assert result.gt_scores == {2: 1}


def test_official_adapter_ignores_unsupported_sparse_region_fork():
    graph = LineageGraph(
        "sample",
        [_d("f", 0, 100.0), _d("a", 1, 95.0), _d("b", 1, 105.0)],
        [LineageEdge("f", "a"), LineageEdge("f", "b")],
    )
    empty_gt = SparseGroundTruthGraph("sample", [], [], None)
    result = evaluate_official_divisions(graph, empty_gt)
    assert (result.tp, result.fp, result.fn) == (0, 0, 0)


def test_official_adapter_rejects_shared_direct_child_branch():
    graph = LineageGraph(
        "sample",
        [
            _d("p", 0, 0.0),
            _d("d", 1, 0.0),
            _d("other", 1, 20.0),
            _d("c1", 2, 5.0),
            _d("c2", 2, -5.0),
        ],
        [
            LineageEdge("p", "d"),
            LineageEdge("d", "c1"),
            LineageEdge("d", "c2"),
            LineageEdge("other", "c1"),
        ],
    )
    result = evaluate_official_divisions(graph, _gt())
    assert (result.tp, result.fp, result.fn) == (0, 1, 1)
    assert result.gt_scores == {2: 0}
