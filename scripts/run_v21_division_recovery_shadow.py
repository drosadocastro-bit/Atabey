from __future__ import annotations

import argparse
import csv
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.sparse_ground_truth import evaluate_sparse_ground_truth, match_sparse_centroids
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import SparseGroundTruthGraph, read_geff_graph
from atabey.tracking.division_recovery_shadow import compute_division_recovery_shadow
from atabey.types import LineageGraph
from run_hybrid_train_evaluation import _build_hybrid_graph
from run_v20_quality_score_ablation import _build_v20_graph


@dataclass(frozen=True)
class V21ShadowRow:
    sample_id: str
    track_a_detector: str
    track_a_link_strategy: str
    track_a_edge_recall: float | None
    track_a_div_tp: int
    track_a_div_fp: int
    track_a_div_fn: int
    track_b_candidates: int
    track_b_accepted: int
    track_b_proposals: int
    track_b_flagged: int
    track_b_tp: int
    track_b_fp: int
    track_b_fn: int
    track_b_jaccard: float | None
    track_b_proposal_tp: int
    track_b_proposal_fp: int
    track_b_proposal_fn: int
    track_b_proposal_jaccard: float | None
    track_a_zero_perturbation: bool


def _build_v19_prefirewall_with_route(
    sample_path: Path,
    max_timepoints: int | None,
) -> tuple[LineageGraph, str, str]:
    graph, _profile, detector, link_strategy, _reason, _distance = _build_hybrid_graph(
        sample_path=sample_path,
        max_timepoints=max_timepoints,
        cfar_threshold=defaults.cfar_threshold,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
        cfar_threshold_mode=defaults.cfar_threshold_mode,
        cfar_k_sigma=defaults.cfar_k_sigma,
        cfar_pfa=defaults.cfar_pfa,
        sidelobe_mode=defaults.sidelobe_mode,
        sidelobe_radius_voxels=defaults.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=defaults.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=defaults.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=defaults.sidelobe_floor_ratio,
        max_detections_per_timepoint=defaults.max_detections_per_timepoint,
        cfar_link_strategy="bipartite",
        cfar_max_link_distance_um=defaults.cfar_max_link_distance_um,
        cfar_route_policy=defaults.cfar_route_policy,
        enable_watershed_refinement=True,
    )
    return graph, detector, link_strategy


def _build_v19_prefirewall(sample_path: Path, max_timepoints: int | None) -> LineageGraph:
    graph, _detector, _link_strategy = _build_v19_prefirewall_with_route(
        sample_path,
        max_timepoints,
    )
    return graph


def _build_track_a_v20(sample_path: Path, max_timepoints: int | None) -> tuple[LineageGraph, str, str]:
    graph, _profile, detector, link_strategy, _reason, _distance = _build_v20_graph(
        sample_path=sample_path,
        max_timepoints=max_timepoints,
        cfar_threshold=defaults.cfar_threshold,
        cfar_training_radius_voxels=defaults.cfar_training_radius_voxels,
        cfar_guard_radius_voxels=defaults.cfar_guard_radius_voxels,
        cfar_threshold_mode=defaults.cfar_threshold_mode,
        cfar_k_sigma=defaults.cfar_k_sigma,
        cfar_pfa=defaults.cfar_pfa,
        sidelobe_mode=defaults.sidelobe_mode,
        sidelobe_radius_voxels=defaults.sidelobe_radius_voxels,
        sidelobe_axial_z_radius_voxels=defaults.sidelobe_axial_z_radius_voxels,
        sidelobe_axial_xy_tolerance_voxels=defaults.sidelobe_axial_xy_tolerance_voxels,
        sidelobe_floor_ratio=defaults.sidelobe_floor_ratio,
        max_detections_per_timepoint=defaults.max_detections_per_timepoint,
        cfar_link_strategy="bipartite",
        cfar_max_link_distance_um=defaults.cfar_max_link_distance_um,
        cfar_route_policy=defaults.cfar_route_policy,
        cnn_weights_path=project_root / "weights" / "v20_cnn_best.pth",
    )
    return graph, detector, link_strategy


def _outgoing(graph: LineageGraph) -> dict[str, list[str]]:
    outgoing: dict[str, list[str]] = {}
    for edge in graph.edges:
        outgoing.setdefault(edge.source_id, []).append(edge.target_id)
    return outgoing


def _reaches(outgoing: dict[str, list[str]], start_id: str, target_id: str, max_depth: int = 5) -> bool:
    if start_id == target_id:
        return True
    queue: deque[tuple[str, int]] = deque([(start_id, 0)])
    visited = {start_id}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for nxt in outgoing.get(current, []):
            if nxt == target_id:
                return True
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, depth + 1))
    return False


def _gt_divisions(ground_truth: SparseGroundTruthGraph) -> list[tuple[int, int, int]]:
    outgoing: dict[int, list[int]] = {}
    for source_id, target_id in ground_truth.edges:
        outgoing.setdefault(int(source_id), []).append(int(target_id))
    return [(source_id, targets[0], targets[1]) for source_id, targets in outgoing.items() if len(targets) >= 2]


def _evaluate_track_b(graph: LineageGraph, ground_truth: SparseGroundTruthGraph, accepted_parent_ids: set[str]) -> tuple[int, int, int, float | None]:
    matches = match_sparse_centroids(graph, ground_truth)
    gt_to_prediction = {
        match.ground_truth_node_id: match.prediction_node_id
        for match in matches
        if match.matched and match.prediction_node_id is not None
    }
    gt_nodes_by_id = {int(node.node_id): node for node in ground_truth.nodes}
    pred_nodes_by_id = {node.node_id: node for node in graph.detections}
    outgoing = _outgoing(graph)

    tp_gt: set[int] = set()
    tp_pred: set[str] = set()
    for gt_parent, gt_child_1, gt_child_2 in _gt_divisions(ground_truth):
        pred_parent = gt_to_prediction.get(gt_parent)
        pred_child_1 = gt_to_prediction.get(gt_child_1)
        pred_child_2 = gt_to_prediction.get(gt_child_2)
        if not (pred_parent and pred_child_1 and pred_child_2):
            continue
        for candidate_parent in accepted_parent_ids:
            if candidate_parent in tp_pred or candidate_parent not in pred_nodes_by_id:
                continue
            if abs(pred_nodes_by_id[candidate_parent].t - gt_nodes_by_id[gt_parent].t) > 2:
                continue
            if (
                _reaches(outgoing, pred_parent, candidate_parent, max_depth=3)
                and _reaches(outgoing, candidate_parent, pred_child_1, max_depth=3)
                and _reaches(outgoing, candidate_parent, pred_child_2, max_depth=3)
            ):
                tp_gt.add(gt_parent)
                tp_pred.add(candidate_parent)
                break

    tp = len(tp_gt)
    fp = max(0, len(accepted_parent_ids) - len(tp_pred))
    fn = max(0, len(_gt_divisions(ground_truth)) - tp)
    denom = tp + fp + fn
    return tp, fp, fn, (float(tp) / float(denom) if denom else None)


def _edge_signature(graph: LineageGraph) -> tuple[tuple[str, str, float | None, str], ...]:
    return tuple((edge.source_id, edge.target_id, edge.confidence, edge.relation) for edge in graph.edges)


def evaluate_sample(sample_id: str, max_timepoints: int | None) -> V21ShadowRow:
    train_dir = project_root / "train"
    sample_path = train_dir / f"{sample_id}.zarr"
    ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")

    track_a, detector, link_strategy = _build_track_a_v20(sample_path, max_timepoints=max_timepoints)
    before_edges = _edge_signature(track_a)
    track_a_report = evaluate_sparse_ground_truth(track_a, ground_truth)
    after_edges = _edge_signature(track_a)

    prefirewall = _build_v19_prefirewall(sample_path, max_timepoints=max_timepoints)
    shadow = compute_division_recovery_shadow(prefirewall)
    accepted_parent_ids = {candidate.parent_id for candidate in shadow.candidates if candidate.accepted}
    track_b_tp, track_b_fp, track_b_fn, track_b_jaccard = _evaluate_track_b(prefirewall, ground_truth, accepted_parent_ids)
    proposal_parent_ids = {
        candidate.parent_id for candidate in shadow.candidates if candidate.decision_mode == "division_proposal"
    }
    proposal_tp, proposal_fp, proposal_fn, proposal_jaccard = _evaluate_track_b(
        prefirewall, ground_truth, proposal_parent_ids
    )

    return V21ShadowRow(
        sample_id=sample_id,
        track_a_detector=detector,
        track_a_link_strategy=link_strategy,
        track_a_edge_recall=track_a_report.sparse_edge_recall,
        track_a_div_tp=track_a_report.division_tp,
        track_a_div_fp=track_a_report.division_fp,
        track_a_div_fn=track_a_report.division_fn,
        track_b_candidates=shadow.candidate_count,
        track_b_accepted=shadow.accepted_count,
        track_b_proposals=shadow.proposal_count,
        track_b_flagged=shadow.flagged_count,
        track_b_tp=track_b_tp,
        track_b_fp=track_b_fp,
        track_b_fn=track_b_fn,
        track_b_jaccard=track_b_jaccard,
        track_b_proposal_tp=proposal_tp,
        track_b_proposal_fp=proposal_fp,
        track_b_proposal_fn=proposal_fn,
        track_b_proposal_jaccard=proposal_jaccard,
        track_a_zero_perturbation=(before_edges == after_edges),
    )


def _sample_ids_from_args(sample_ids: list[str]) -> list[str]:
    if sample_ids == ["all"]:
        return sorted(path.stem for path in (project_root / "train").glob("*.zarr"))
    return sample_ids


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate V21 shadow-only division recovery candidates.")
    parser.add_argument("--sample-ids", nargs="+", default=["6bba_05db0fb1", "6bba_b329af44", "6bba_ebdf3b34"])
    parser.add_argument("--max-timepoints", type=int, default=100)
    parser.add_argument("--output", type=Path, default=project_root / "v21_division_recovery_shadow.csv")
    args = parser.parse_args()

    sample_ids = _sample_ids_from_args(args.sample_ids)
    rows: list[V21ShadowRow] = []
    for index, sample_id in enumerate(sample_ids, start=1):
        print(f"[{index}/{len(sample_ids)}] {sample_id}", flush=True)
        row = evaluate_sample(sample_id, max_timepoints=args.max_timepoints)
        rows.append(row)
        print(
            f"  TrackA={row.track_a_detector}/{row.track_a_link_strategy} "
            f"EdgeRecall={row.track_a_edge_recall} DivTP={row.track_a_div_tp} FP={row.track_a_div_fp} "
            f"| TrackB accepted={row.track_b_accepted} TP={row.track_b_tp} FP={row.track_b_fp} FN={row.track_b_fn} "
            f"proposals={row.track_b_proposals} flagged={row.track_b_flagged} "
            f"zero_perturb={row.track_a_zero_perturbation}",
            flush=True,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(V21ShadowRow.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)
    print(f"Wrote {args.output} ({len(rows)} samples)")


if __name__ == "__main__":
    main()
