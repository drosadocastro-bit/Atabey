from __future__ import annotations

from dataclasses import dataclass
import math

from atabey.evaluation.official_division_metric import (
    OFFICIAL_MAX_DISTANCE_UM,
    _ground_truth_to_tracksdata,
    _official_modules,
    _prediction_to_tracksdata,
)
from atabey.io.geff_reader import SparseGroundTruthGraph
from atabey.types import LineageGraph


@dataclass(frozen=True)
class OfficialTrackingResult:
    edge_tp: int
    edge_fp: int
    edge_fn: int
    edge_jaccard: float | None
    adjusted_edge_jaccard: float | None
    node_recall: float | None
    predicted_nodes: int
    estimated_total_nodes: int | None
    total_node_ratio: float | None
    division_tp: int
    division_fp: int
    division_fn: int
    division_jaccard: float | None
    score: float | None


@dataclass(frozen=True)
class OfficialTrackingSummary:
    sample_count: int
    edge_jaccard: float | None
    division_jaccard: float | None
    division_tp: int
    division_fp: int
    division_fn: int
    node_recall: float | None
    adjusted_edge_jaccard: float | None
    adjusted_sample_count: int
    score: float | None


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def evaluate_official_tracking(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    *,
    estimated_total_nodes: int | None = None,
    max_distance_um: float = OFFICIAL_MAX_DISTANCE_UM,
) -> OfficialTrackingResult:
    """Call the pinned host evaluator for edge, node, and division metrics."""

    pl, td, _score_divisions = _official_modules()
    try:
        from tracking_cellmot.metrics import evaluate, node_recall, per_sample_metrics
    except ImportError as exc:
        raise RuntimeError(
            "The official tracking metric is required. Install Atabey with the "
            "'official-metrics' extra before running adjusted-edge evaluation."
        ) from exc

    prediction, _ = _prediction_to_tracksdata(graph, pl, td)
    gt_graph, _ = _ground_truth_to_tracksdata(ground_truth, pl, td)
    official = evaluate(
        prediction,
        gt_graph,
        scale=None,
        max_distance=float(max_distance_um),
    )

    if prediction.num_edges() > 0 and prediction.num_nodes() > 0 and gt_graph.num_nodes() > 0:
        recall = float(node_recall(prediction, gt_graph))
    else:
        recall = float("nan")

    target_nodes = (
        ground_truth.estimated_number_of_nodes
        if estimated_total_nodes is None
        else estimated_total_nodes
    )
    metrics = per_sample_metrics(
        official,
        float(target_nodes) if target_nodes is not None else float("nan"),
        recall,
    )
    division_denominator = (
        int(official.division_tp)
        + int(official.division_fp)
        + int(official.division_fn)
    )
    division_jaccard = (
        float(official.division_tp) / float(division_denominator)
        if division_denominator
        else None
    )
    adjusted = _finite_or_none(metrics["adj_edge_jaccard"])
    score = (
        adjusted + 0.1 * division_jaccard
        if adjusted is not None and division_jaccard is not None
        else adjusted
    )
    return OfficialTrackingResult(
        edge_tp=int(official.edge_tp),
        edge_fp=int(official.edge_fp),
        edge_fn=int(official.edge_fn),
        edge_jaccard=_finite_or_none(metrics["edge_jaccard"]),
        adjusted_edge_jaccard=adjusted,
        node_recall=_finite_or_none(metrics["node_recall"]),
        predicted_nodes=int(official.num_pred_nodes),
        estimated_total_nodes=target_nodes,
        total_node_ratio=_finite_or_none(metrics["total_node_ratio"]),
        division_tp=int(official.division_tp),
        division_fp=int(official.division_fp),
        division_fn=int(official.division_fn),
        division_jaccard=division_jaccard,
        score=score,
    )


def summarize_official_tracking(
    results: list[OfficialTrackingResult],
) -> OfficialTrackingSummary:
    """Call the pinned host's run-level aggregation without local reweighting."""
    try:
        from tracking_cellmot.metrics import summarise
    except ImportError as exc:
        raise RuntimeError(
            "The official tracking metric is required. Install Atabey with the "
            "'official-metrics' extra before running tracking evaluation."
        ) from exc

    def value_or_nan(value: float | None) -> float:
        return float("nan") if value is None else float(value)

    rows = [
        {
            "edge_tp": result.edge_tp,
            "edge_fp": result.edge_fp,
            "edge_fn": result.edge_fn,
            "division_tp": result.division_tp,
            "division_fp": result.division_fp,
            "division_fn": result.division_fn,
            "num_pred_nodes": result.predicted_nodes,
            "node_recall": value_or_nan(result.node_recall),
            "total_node_ratio": value_or_nan(result.total_node_ratio),
            "edge_jaccard": value_or_nan(result.edge_jaccard),
            "adj_edge_jaccard": value_or_nan(result.adjusted_edge_jaccard),
        }
        for result in results
    ]
    summary = summarise(rows)
    return OfficialTrackingSummary(
        sample_count=int(summary["n"]),
        edge_jaccard=_finite_or_none(summary["edge_jaccard"]),
        division_jaccard=_finite_or_none(summary["division_jaccard"]),
        division_tp=int(summary["division_tp"]),
        division_fp=int(summary["division_fp"]),
        division_fn=int(summary["division_fn"]),
        node_recall=_finite_or_none(summary["node_recall"]),
        adjusted_edge_jaccard=_finite_or_none(summary["adj_edge_jaccard"]),
        adjusted_sample_count=int(summary["n_adj"]),
        score=_finite_or_none(summary["score"]),
    )
