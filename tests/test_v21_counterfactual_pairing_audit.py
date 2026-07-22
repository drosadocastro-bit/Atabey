from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "scripts"))

from audit_v21_counterfactual_pairing import _add_scores_and_ranks, _pair_metrics
from atabey.types import Detection, LineageEdge, LineageGraph


def _d(node_id: str, t: int, x: float, y: float = 0.0) -> Detection:
    return Detection(
        node_id=node_id,
        sample_id="sample",
        t=t,
        z=0.0,
        y=y,
        x=x,
        z_um=0.0,
        y_um=y,
        x_um=x,
    )


def test_counterfactual_metrics_prefer_smooth_persistent_pair_without_mutation():
    parent = _d("p", 0, 0.0)
    good_1 = [_d(f"g1_{t}", t, float(t), 2.0) for t in range(1, 5)]
    good_2 = [_d(f"g2_{t}", t, float(t), -2.0) for t in range(1, 5)]
    wrong = [_d("w_1", 1, 0.5, 0.2), _d("w_2", 2, 5.0, 0.1)]
    graph = LineageGraph("sample", detections=[parent, *good_1, *good_2, *wrong])
    for branch in (good_1, good_2, wrong):
        for source, target in zip(branch, branch[1:]):
            graph.add_edge(LineageEdge(source.node_id, target.node_id))
    before = list(graph.edges)
    nodes = {node.node_id: node for node in graph.detections}
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_id, []).append(edge.target_id)

    good = _pair_metrics(parent, good_1[0], good_2[0], nodes=nodes, outgoing=outgoing, horizon=4)
    bad = _pair_metrics(parent, good_1[0], wrong[0], nodes=nodes, outgoing=outgoing, horizon=4)

    assert good["coverage_ratio"] == 1.0
    assert bad["coverage_ratio"] < good["coverage_ratio"]
    assert good["mean_prediction_error_um"] < bad["mean_prediction_error_um"]
    assert graph.edges == before


def test_profile_ranks_and_pareto_front_are_reported():
    rows = [
        {
            "child_1_id": "a",
            "child_2_id": "b",
            "coverage_ratio": 1.0,
            "mean_prediction_error_um": 0.1,
            "max_axis_drift_deg": 2.0,
            "minimum_separation_um": 4.0,
        },
        {
            "child_1_id": "a",
            "child_2_id": "c",
            "coverage_ratio": 0.5,
            "mean_prediction_error_um": 3.0,
            "max_axis_drift_deg": 40.0,
            "minimum_separation_um": 0.5,
        },
    ]

    _add_scores_and_ranks(rows)

    assert rows[0]["coverage_heavy_rank"] == 1
    assert rows[0]["balanced_rank"] == 1
    assert rows[0]["stability_heavy_rank"] == 1
    assert rows[0]["pareto_front"] is True
    assert rows[0]["pareto_dominates"] == 1
    assert rows[1]["pareto_dominated_by"] == 1
