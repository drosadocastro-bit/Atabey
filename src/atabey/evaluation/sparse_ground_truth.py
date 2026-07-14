from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median

import numpy as np

from atabey.io.geff_reader import SparseGroundTruthGraph
from atabey.types import Detection, LineageGraph


@dataclass(frozen=True)
class CentroidMatch:
    ground_truth_node_id: int
    prediction_node_id: str | None
    distance_um: float | None
    matched: bool


@dataclass(frozen=True)
class SparseEvaluationReport:
    sample_id: str
    predicted_nodes: int
    predicted_edges: int
    sparse_ground_truth_nodes: int
    sparse_ground_truth_edges: int
    estimated_total_nodes: int | None
    matched_sparse_nodes: int
    match_radius_um: float
    mean_matched_error_um: float | None
    median_matched_error_um: float | None
    sparse_recall: float | None
    matched_sparse_edges: int
    evaluable_sparse_edges: int
    sparse_edge_recall: float | None
    predicted_to_estimated_node_ratio: float | None
    division_tp: int = 0
    division_fp: int = 0
    division_fn: int = 0
    division_jaccard: float | None = None

    @property
    def caution(self) -> str:
        return (
            "Sparse labels are calibration context only: unmatched predictions are not "
            "automatically false positives, and this report is not the official Kaggle metric."
        )


def nearest_centroid_errors_um(
    predictions: list[Detection],
    ground_truth_positions_um: list[tuple[float, float, float]],
) -> list[float]:
    """Return nearest predicted centroid error for each sparse ground-truth point."""

    if not predictions or not ground_truth_positions_um:
        return []

    pred_positions = np.array([d.position_um for d in predictions], dtype=float)
    errors: list[float] = []
    for gt in ground_truth_positions_um:
        distances = np.linalg.norm(pred_positions - np.array(gt, dtype=float), axis=1)
        errors.append(float(distances.min()))
    return errors


def match_sparse_centroids(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    radius_um: float = 7.0,
) -> list[CentroidMatch]:
    """Greedily match sparse ground-truth centroids to predictions at the same timepoint."""

    predictions_by_t: dict[int, list[Detection]] = {}
    for detection in graph.detections:
        predictions_by_t.setdefault(detection.t, []).append(detection)

    matches: list[CentroidMatch] = []
    used_predictions: set[str] = set()
    for node in ground_truth.nodes:
        candidates = [
            prediction
            for prediction in predictions_by_t.get(node.t, [])
            if prediction.node_id not in used_predictions
        ]
        if not candidates:
            matches.append(CentroidMatch(node.node_id, None, None, False))
            continue

        candidate_positions = np.array([candidate.position_um for candidate in candidates], dtype=float)
        distances = np.linalg.norm(candidate_positions - np.array(node.position_um, dtype=float), axis=1)
        best_index = int(np.argmin(distances))
        best_distance = float(distances[best_index])
        if best_distance <= radius_um:
            prediction = candidates[best_index]
            used_predictions.add(prediction.node_id)
            matches.append(CentroidMatch(node.node_id, prediction.node_id, best_distance, True))
        else:
            matches.append(CentroidMatch(node.node_id, None, best_distance, False))
    return matches


def evaluate_sparse_ground_truth(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    match_radius_um: float = 7.0,
) -> SparseEvaluationReport:
    """Evaluate a predicted graph against sparse GEFF labels as bounded calibration."""

    matches = match_sparse_centroids(graph, ground_truth, radius_um=match_radius_um)
    matched = [match for match in matches if match.matched and match.distance_um is not None]
    gt_to_prediction = {
        match.ground_truth_node_id: match.prediction_node_id
        for match in matched
        if match.prediction_node_id is not None
    }

    predicted_edges = {(edge.source_id, edge.target_id) for edge in graph.edges}
    evaluable_sparse_edges = 0
    matched_sparse_edges = 0
    for source_id, target_id in ground_truth.edges:
        source_prediction = gt_to_prediction.get(source_id)
        target_prediction = gt_to_prediction.get(target_id)
        if source_prediction is None or target_prediction is None:
            continue
        evaluable_sparse_edges += 1
        if (source_prediction, target_prediction) in predicted_edges:
            matched_sparse_edges += 1

    sparse_recall = _safe_ratio(len(matched), len(ground_truth.nodes))
    sparse_edge_recall = _safe_ratio(matched_sparse_edges, evaluable_sparse_edges)
    predicted_to_estimated = _safe_ratio(
        len(graph.detections), ground_truth.estimated_number_of_nodes
    )
    errors = [match.distance_um for match in matched if match.distance_um is not None]

    tp, fp, fn = compute_division_jaccard(graph, ground_truth, gt_to_prediction, time_tolerance=1)
    div_jaccard = _safe_ratio(tp, tp + fp + fn)

    return SparseEvaluationReport(
        sample_id=graph.sample_id,
        predicted_nodes=len(graph.detections),
        predicted_edges=len(graph.edges),
        sparse_ground_truth_nodes=len(ground_truth.nodes),
        sparse_ground_truth_edges=len(ground_truth.edges),
        estimated_total_nodes=ground_truth.estimated_number_of_nodes,
        matched_sparse_nodes=len(matched),
        match_radius_um=match_radius_um,
        mean_matched_error_um=float(mean(errors)) if errors else None,
        median_matched_error_um=float(median(errors)) if errors else None,
        sparse_recall=sparse_recall,
        matched_sparse_edges=matched_sparse_edges,
        evaluable_sparse_edges=evaluable_sparse_edges,
        sparse_edge_recall=sparse_edge_recall,
        predicted_to_estimated_node_ratio=predicted_to_estimated,
        division_tp=tp,
        division_fp=fp,
        division_fn=fn,
        division_jaccard=div_jaccard,
    )


def _safe_ratio(numerator: int | float, denominator: int | float | None) -> float | None:
    if denominator is None or denominator == 0:
        return None
    return float(numerator) / float(denominator)


def compute_division_jaccard(
    graph: LineageGraph,
    ground_truth: SparseGroundTruthGraph,
    gt_to_prediction: dict[int, str],
    time_tolerance: int = 1,
) -> tuple[int, int, int]:
    """Compute (TP, FP, FN) for divisions using the competition spec."""
    # 1. Find all GT divisions
    gt_edges_out: dict[int, list[int]] = {}
    for src, tgt in ground_truth.edges:
        gt_edges_out.setdefault(src, []).append(tgt)
    gt_divisions = [src for src, tgts in gt_edges_out.items() if len(tgts) >= 2]

    # 2. Find all Pred divisions
    pred_edges_out: dict[str, list[str]] = {}
    for edge in graph.edges:
        pred_edges_out.setdefault(edge.source_id, []).append(edge.target_id)
    pred_divisions = [src for src, tgts in pred_edges_out.items() if len(tgts) >= 2]

    # 3. Build reachability map for Pred graph
    pred_nodes_by_id = {d.node_id: d for d in graph.detections}
    gt_nodes_by_id = {n.node_id: n for n in ground_truth.nodes}

    def reaches(start_id: str, target_id: str, max_depth: int = 5) -> bool:
        if start_id == target_id:
            return True
        queue = [(start_id, 0)]
        visited = {start_id}
        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for nxt in pred_edges_out.get(curr, []):
                if nxt == target_id:
                    return True
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, depth + 1))
        return False

    tp_gt = set()
    tp_pred = set()

    for gt_p in gt_divisions:
        gt_targets = gt_edges_out[gt_p]
        gt_d1, gt_d2 = gt_targets[0], gt_targets[1]

        pred_p = gt_to_prediction.get(gt_p)
        pred_d1 = gt_to_prediction.get(gt_d1)
        pred_d2 = gt_to_prediction.get(gt_d2)

        if not (pred_p and pred_d1 and pred_d2):
            continue

        matched_pred_div = None
        for pdiv in pred_divisions:
            if pdiv in tp_pred:
                continue
            
            pdiv_t = pred_nodes_by_id[pdiv].t
            gt_t = gt_nodes_by_id[gt_p].t
            if abs(pdiv_t - gt_t) > time_tolerance + 1:
                continue

            if reaches(pred_p, pdiv, max_depth=3) and reaches(pdiv, pred_d1, max_depth=3) and reaches(pdiv, pred_d2, max_depth=3):
                matched_pred_div = pdiv
                break

        if matched_pred_div:
            tp_gt.add(gt_p)
            tp_pred.add(matched_pred_div)

    tp = len(tp_gt)
    fp = len(pred_divisions) - len(tp_pred)
    fn = len(gt_divisions) - len(tp_gt)
    return tp, fp, fn

