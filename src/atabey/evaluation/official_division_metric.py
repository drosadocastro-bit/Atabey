from __future__ import annotations

from dataclasses import dataclass

from atabey.io.geff_reader import SparseGroundTruthGraph
from atabey.types import LineageGraph


OFFICIAL_METRIC_COMMIT = "075fc5f5a52d11077f9dc2b074644618f26939e2"
OFFICIAL_TRACKSDATA_COMMIT = "39dccf3a243e44274759468cb31b2ad9e7fc1d09"
OFFICIAL_MAX_DISTANCE_UM = 7.0


@dataclass(frozen=True)
class OfficialDivisionResult:
    tp: int
    fp: int
    fn: int
    jaccard: float | None
    gt_scores: dict[int, int]
    tp_fork_ids: frozenset[str]
    fp_fork_ids: frozenset[str]


def _official_modules():
    try:
        import polars as pl
        import tracksdata as td
        from tracking_cellmot.division_metrics import score_divisions
    except ImportError as exc:
        raise RuntimeError(
            "The patched official division metric is required. Install Atabey with "
            "the 'official-metrics' extra before running division evaluation."
        ) from exc
    return pl, td, score_divisions


def _new_tracksdata_graph(pl, td):
    graph = td.graph.InMemoryGraph()
    graph.add_node_attr_key("z", pl.Float64, 0.0)
    graph.add_node_attr_key("y", pl.Float64, 0.0)
    graph.add_node_attr_key("x", pl.Float64, 0.0)
    return graph


def _prediction_to_tracksdata(graph: LineageGraph, pl, td):
    converted = _new_tracksdata_graph(pl, td)
    id_map: dict[str, int] = {}
    for detection in graph.detections:
        id_map[detection.node_id] = converted.add_node(
            attrs={
                "t": int(detection.t),
                "z": float(detection.z_um),
                "y": float(detection.y_um),
                "x": float(detection.x_um),
            }
        )
    for edge in graph.edges:
        source = id_map.get(edge.source_id)
        target = id_map.get(edge.target_id)
        if source is not None and target is not None:
            converted.add_edge(source, target, {})
    return converted, id_map


def _ground_truth_to_tracksdata(ground_truth: SparseGroundTruthGraph, pl, td):
    converted = _new_tracksdata_graph(pl, td)
    id_map: dict[int, int] = {}
    for node in ground_truth.nodes:
        id_map[int(node.node_id)] = converted.add_node(
            attrs={
                "t": int(node.t),
                "z": float(node.z_um),
                "y": float(node.y_um),
                "x": float(node.x_um),
            }
        )
    for source_id, target_id in ground_truth.edges:
        source = id_map.get(int(source_id))
        target = id_map.get(int(target_id))
        if source is not None and target is not None:
            converted.add_edge(source, target, {})
    return converted, id_map


def evaluate_official_divisions(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    *,
    max_distance_um: float = OFFICIAL_MAX_DISTANCE_UM,
) -> OfficialDivisionResult:
    """Call the host's patched division scorer on converted Atabey graphs."""
    pl, td, score_divisions = _official_modules()
    prediction, prediction_id_map = _prediction_to_tracksdata(graph, pl, td)
    gt_graph, gt_id_map = _ground_truth_to_tracksdata(ground_truth, pl, td)
    official = score_divisions(
        prediction,
        gt_graph,
        scale=None,
        max_distance=float(max_distance_um),
    )
    reverse_gt_ids = {converted_id: original_id for original_id, converted_id in gt_id_map.items()}
    reverse_prediction_ids = {converted_id: original_id for original_id, converted_id in prediction_id_map.items()}
    gt_scores = {
        reverse_gt_ids[int(converted_id)]: int(score)
        for converted_id, score in official.scores.items()
    }
    tp = int(sum(official.scores.values()))
    fn = int(len(official.scores) - tp)
    fp = int(len(official.fp_forks))
    denominator = tp + fp + fn
    return OfficialDivisionResult(
        tp=tp,
        fp=fp,
        fn=fn,
        jaccard=(float(tp) / float(denominator) if denominator else None),
        gt_scores=gt_scores,
        tp_fork_ids=frozenset(reverse_prediction_ids[int(node_id)] for node_id in official.tp_forks),
        fp_fork_ids=frozenset(reverse_prediction_ids[int(node_id)] for node_id in official.fp_forks),
    )
