from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "scripts"))

from atabey.evaluation.sparse_ground_truth import match_sparse_centroids
from atabey.hybrid_config import DEFAULT_HYBRID_FROZEN_DEFAULTS as defaults
from atabey.io.geff_reader import SparseGroundTruthGraph, read_geff_graph
from atabey.tracking.division_firewall import _angle_between
from atabey.types import Detection, LineageGraph
from run_hybrid_train_evaluation import _build_hybrid_graph
from run_v20_quality_score_ablation import _build_v20_graph


@dataclass(frozen=True)
class CandidateTrace:
    sample_id: str
    gt_parent_id: int | None
    gt_child_1_id: int | None
    gt_child_2_id: int | None
    pred_parent_id: str
    pred_child_1_id: str
    pred_child_2_id: str
    v19_tp: bool
    v20_still_division: bool | None
    v20_parent_present: bool | None
    v20_child_1_present: bool | None
    v20_child_2_present: bool | None
    v20_parent_out_degree: int | None
    firewall_decision: str
    firewall_reason: str
    max_drift_deg: float | None
    v_sep_1_um_per_frame: float | None
    fallback_angle_deg: float | None
    fallback_distance_ratio: float | None
    t: int
    v19_edge_recall_context: str


def _nodes_by_id(graph: LineageGraph) -> dict[str, Detection]:
    return {d.node_id: d for d in graph.detections}


def _outgoing(graph: LineageGraph) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for edge in graph.edges:
        out.setdefault(edge.source_id, []).append(edge.target_id)
    return out


def _division_sources(graph: LineageGraph) -> list[str]:
    return [src for src, tgts in _outgoing(graph).items() if len(tgts) >= 2]


def _reachable(out: dict[str, list[str]], start_id: str, target_id: str, max_depth: int = 5) -> bool:
    if start_id == target_id:
        return True
    queue: deque[tuple[str, int]] = deque([(start_id, 0)])
    visited = {start_id}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for nxt in out.get(current, []):
            if nxt == target_id:
                return True
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, depth + 1))
    return False


def _gt_to_prediction(graph: LineageGraph, gt: SparseGroundTruthGraph) -> dict[int, str]:
    matches = match_sparse_centroids(graph, gt)
    return {
        match.ground_truth_node_id: match.prediction_node_id
        for match in matches
        if match.matched and match.prediction_node_id is not None
    }


def _gt_divisions(gt: SparseGroundTruthGraph) -> list[tuple[int, int, int]]:
    out: dict[int, list[int]] = {}
    for src, tgt in gt.edges:
        out.setdefault(int(src), []).append(int(tgt))
    return [(src, tgts[0], tgts[1]) for src, tgts in out.items() if len(tgts) >= 2]


def _match_v19_tp_candidates(graph: LineageGraph, gt: SparseGroundTruthGraph) -> list[tuple[int, int, int, str]]:
    gt_to_pred = _gt_to_prediction(graph, gt)
    out = _outgoing(graph)
    nodes = _nodes_by_id(graph)
    pred_divisions = _division_sources(graph)
    gt_nodes = {int(n.node_id): n for n in gt.nodes}

    matched: list[tuple[int, int, int, str]] = []
    used_pred: set[str] = set()
    for gt_parent, gt_child_1, gt_child_2 in _gt_divisions(gt):
        pred_parent = gt_to_pred.get(gt_parent)
        pred_child_1 = gt_to_pred.get(gt_child_1)
        pred_child_2 = gt_to_pred.get(gt_child_2)
        if not (pred_parent and pred_child_1 and pred_child_2):
            continue
        for pred_div in pred_divisions:
            if pred_div in used_pred:
                continue
            if pred_div not in nodes:
                continue
            if abs(nodes[pred_div].t - gt_nodes[gt_parent].t) > 2:
                continue
            if (
                _reachable(out, pred_parent, pred_div, max_depth=3)
                and _reachable(out, pred_div, pred_child_1, max_depth=3)
                and _reachable(out, pred_div, pred_child_2, max_depth=3)
            ):
                matched.append((gt_parent, gt_child_1, gt_child_2, pred_div))
                used_pred.add(pred_div)
                break
    return matched


def _descendant_at(out: dict[str, list[str]], nodes: dict[str, Detection], node_id: str, target_t: int) -> Detection | None:
    current = nodes[node_id]
    while current.t < target_t:
        next_ids = out.get(current.node_id, [])
        if not next_ids:
            return None
        current = nodes[next_ids[0]]
    return current


def _firewall_decision_for_branch(graph: LineageGraph, parent_id: str, child_ids: list[str]) -> tuple[str, str, float | None, float | None, float | None, float | None]:
    nodes = _nodes_by_id(graph)
    out = _outgoing(graph)
    parent = nodes[parent_id]
    child_1, child_2 = child_ids[0], child_ids[1]
    c1 = nodes[child_1]
    c2 = nodes[child_2]
    d1 = float(np.linalg.norm(np.array(c1.position_um) - np.array(parent.position_um)))
    d2 = float(np.linalg.norm(np.array(c2.position_um) - np.array(parent.position_um)))
    if d1 <= d2:
        primary_id, orphan_id = child_1, child_2
    else:
        primary_id, orphan_id = child_2, child_1

    d1_nodes: list[Detection | None] = [nodes[primary_id]]
    d2_nodes: list[Detection | None] = [nodes[orphan_id]]
    for offset in [2, 3]:
        if d1_nodes[-1] is None or d2_nodes[-1] is None:
            d1_nodes.append(None)
            d2_nodes.append(None)
            continue
        d1_nodes.append(_descendant_at(out, nodes, d1_nodes[-1].node_id, parent.t + offset))
        d2_nodes.append(_descendant_at(out, nodes, d2_nodes[-1].node_id, parent.t + offset))

    axes: list[np.ndarray] = []
    seps: list[float] = []
    for n1, n2 in zip(d1_nodes, d2_nodes):
        if n1 and n2:
            axis = np.array(n1.position_um) - np.array(n2.position_um)
            axes.append(axis)
            seps.append(float(np.linalg.norm(axis)))

    if len(axes) >= 3:
        angles = []
        for i in range(len(axes) - 1):
            angle = _angle_between(axes[i], axes[i + 1])
            angle = min(angle, 180.0 - angle)
            angles.append(angle)
        max_drift = max(angles)
        v_sep_1 = seps[1] - seps[0]
        if max_drift >= 15.0 or v_sep_1 <= 1.0:
            return "reject", f"multi_frame: drift={max_drift:.3f}, v_sep_1={v_sep_1:.3f}", max_drift, v_sep_1, None, None
        return "accept", f"multi_frame: drift={max_drift:.3f}, v_sep_1={v_sep_1:.3f}", max_drift, v_sep_1, None, None

    v1 = np.array(nodes[primary_id].position_um) - np.array(parent.position_um)
    v2 = np.array(nodes[orphan_id].position_um) - np.array(parent.position_um)
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    angle = _angle_between(v1, v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return "reject", "fallback: zero_vector", None, None, angle, None
    ratio = max(n1, n2) / min(n1, n2)
    if angle <= 90.0 or ratio >= 2.0:
        return "reject", f"fallback: angle={angle:.3f}, ratio={ratio:.3f}", None, None, angle, ratio
    return "accept", f"fallback: angle={angle:.3f}, ratio={ratio:.3f}", None, None, angle, ratio


def _build_v19(sample_path: Path, max_timepoints: int | None) -> LineageGraph:
    graph, *_ = _build_hybrid_graph(
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
    return graph


def _build_v20(sample_path: Path, max_timepoints: int | None) -> LineageGraph:
    graph, *_ = _build_v20_graph(
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
    return graph


def trace_sample(sample_id: str, max_timepoints: int | None, check_v20: bool = False) -> list[CandidateTrace]:
    sample_path = project_root / "train" / f"{sample_id}.zarr"
    gt = read_geff_graph(project_root / "train" / f"{sample_id}.geff")
    v19 = _build_v19(sample_path, max_timepoints=max_timepoints)
    v20 = _build_v20(sample_path, max_timepoints=max_timepoints) if check_v20 else None
    v19_out = _outgoing(v19)
    v20_out = _outgoing(v20) if v20 is not None else {}
    v19_nodes = _nodes_by_id(v19)
    traces: list[CandidateTrace] = []
    for gt_parent, gt_child_1, gt_child_2, pred_div in _match_v19_tp_candidates(v19, gt):
        child_ids = v19_out[pred_div][:2]
        decision, reason, drift, v_sep_1, fallback_angle, fallback_ratio = _firewall_decision_for_branch(v19, pred_div, child_ids)
        v20_nodes = _nodes_by_id(v20) if v20 is not None else {}
        v20_parent_present = (pred_div in v20_nodes) if check_v20 else None
        v20_child_1_present = (child_ids[0] in v20_nodes) if check_v20 else None
        v20_child_2_present = (child_ids[1] in v20_nodes) if check_v20 else None
        v20_parent_out_degree = len(v20_out.get(pred_div, [])) if check_v20 else None
        v20_still_division = (v20_parent_out_degree >= 2) if check_v20 else None
        traces.append(
            CandidateTrace(
                sample_id=sample_id,
                gt_parent_id=gt_parent,
                gt_child_1_id=gt_child_1,
                gt_child_2_id=gt_child_2,
                pred_parent_id=pred_div,
                pred_child_1_id=child_ids[0],
                pred_child_2_id=child_ids[1],
                v19_tp=True,
                v20_still_division=v20_still_division,
                v20_parent_present=v20_parent_present,
                v20_child_1_present=v20_child_1_present,
                v20_child_2_present=v20_child_2_present,
                v20_parent_out_degree=v20_parent_out_degree,
                firewall_decision=decision,
                firewall_reason=reason,
                max_drift_deg=drift,
                v_sep_1_um_per_frame=v_sep_1,
                fallback_angle_deg=fallback_angle,
                fallback_distance_ratio=fallback_ratio,
                t=v19_nodes[pred_div].t,
                v19_edge_recall_context="v19_tp_candidate",
            )
        )
    return traces


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace V19 division TPs lost by V20 firewall.")
    parser.add_argument("--sample-ids", nargs="+", default=["6bba_05db0fb1", "6bba_b329af44", "6bba_ebdf3b34"])
    parser.add_argument("--max-timepoints", type=int, default=100)
    parser.add_argument("--output", type=Path, default=project_root / "v21_lost_tp_trace.csv")
    parser.add_argument("--check-v20", action="store_true", help="Also build V20 and verify whether each branch remains a committed division.")
    args = parser.parse_args()

    rows: list[CandidateTrace] = []
    for sample_id in args.sample_ids:
        print(f"Tracing {sample_id}...", flush=True)
        rows.extend(trace_sample(sample_id, max_timepoints=args.max_timepoints, check_v20=args.check_v20))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(CandidateTrace.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)

    print(f"Wrote {args.output} ({len(rows)} traced V19 TP candidates)")
    for row in rows:
        print(
            f"{row.sample_id} gt={row.gt_parent_id} pred={row.pred_parent_id} "
            f"v20_still_division={row.v20_still_division} firewall={row.firewall_decision} {row.firewall_reason}",
            flush=True,
        )


if __name__ == "__main__":
    main()




