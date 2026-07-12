import json
import time
from pathlib import Path
from dataclasses import asdict, dataclass
import numpy as np

# Patch the evaluation module *before* any imports
import atabey.evaluation.sparse_ground_truth
import atabey.evaluation.sparse_ground_truth_v19_experimental as exp

atabey.evaluation.sparse_ground_truth.match_sparse_centroids = exp.match_sparse_centroids_global_greedy
atabey.evaluation.sparse_ground_truth.evaluate_sparse_ground_truth = exp.evaluate_sparse_ground_truth

from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.io.geff_reader import read_geff_graph
from scripts.run_hybrid_submission import build_graph_cfar_sidelobe
from atabey.detection.adaptive import choose_settings_for_sample
from scripts.run_hybrid_train_evaluation import _should_use_cfar_route, _build_v9_style_graph

@dataclass
class BreakdownReport:
    sample_id: str
    strict_evaluable_edges: int
    relaxed_evaluable_edges: int
    newly_evaluable_edges: int
    actionable_edges: int
    theoretical_edges: int
    strict_matched_nodes: int
    relaxed_matched_nodes: int

def evaluate_breakdown(graph, ground_truth):
    strict_matches = exp.match_sparse_centroids_global_greedy(graph, ground_truth, radius_um=7.0)
    relaxed_matches = exp.match_sparse_centroids_global_greedy(graph, ground_truth, radius_um=14.0)
    
    strict_matched = [m for m in strict_matches if m.matched and m.distance_um is not None]
    relaxed_matched = [m for m in relaxed_matches if m.matched and m.distance_um is not None]
    
    strict_gt_to_pred = {m.ground_truth_node_id: m.prediction_node_id for m in strict_matched if m.prediction_node_id is not None}
    relaxed_gt_to_pred = {m.ground_truth_node_id: m.prediction_node_id for m in relaxed_matched if m.prediction_node_id is not None}
    
    predicted_edges = {(e.source_id, e.target_id) for e in graph.edges}
    
    strict_evaluable_edges = set()
    relaxed_evaluable_edges = set()
    
    for source_id, target_id in ground_truth.edges:
        # Strict
        s_pred = strict_gt_to_pred.get(source_id)
        t_pred = strict_gt_to_pred.get(target_id)
        if s_pred is not None and t_pred is not None:
            strict_evaluable_edges.add((source_id, target_id))
            
        # Relaxed
        s_pred = relaxed_gt_to_pred.get(source_id)
        t_pred = relaxed_gt_to_pred.get(target_id)
        if s_pred is not None and t_pred is not None:
            relaxed_evaluable_edges.add((source_id, target_id))
            
    newly_evaluable = relaxed_evaluable_edges - strict_evaluable_edges
    
    pred_node_positions = {d.node_id: d.position_um for d in graph.detections}
    
    actionable_count = 0
    theoretical_count = 0
    
    for source_id, target_id in newly_evaluable:
        s_pred = relaxed_gt_to_pred[source_id]
        t_pred = relaxed_gt_to_pred[target_id]
        
        pos_s = np.array(pred_node_positions[s_pred], dtype=float)
        pos_t = np.array(pred_node_positions[t_pred], dtype=float)
        dist = float(np.linalg.norm(pos_s - pos_t))
        
        # cfar_max_link_distance_um is 9.0 in V13
        if dist <= 9.0:
            actionable_count += 1
        else:
            theoretical_count += 1
            
    return BreakdownReport(
        sample_id=graph.sample_id,
        strict_evaluable_edges=len(strict_evaluable_edges),
        relaxed_evaluable_edges=len(relaxed_evaluable_edges),
        newly_evaluable_edges=len(newly_evaluable),
        actionable_edges=actionable_count,
        theoretical_edges=theoretical_count,
        strict_matched_nodes=len(strict_matched),
        relaxed_matched_nodes=len(relaxed_matched)
    )

def main():
    train_dir = Path("train")
    sample_ids = [f.stem for f in train_dir.glob("*.geff")]
    
    reports = []
    
    for sample_id in sample_ids:
        # Skip the hang sample
        if sample_id == "6bba_6ca87370":
            print(f"Skipping known hang sample {sample_id}...")
            continue
            
        print(f"Evaluating {sample_id}...")
        sample_path = train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")
        
        profile, settings = choose_settings_for_sample(sample_path)
        
        if _should_use_cfar_route(profile=profile, adaptive_detector=settings.detector, cfar_route_policy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_route_policy):
            graph, _ = build_graph_cfar_sidelobe(
                sample_path=sample_path,
                threshold=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold,
                cfar_training_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_training_radius_voxels,
                cfar_guard_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_guard_radius_voxels,
                cfar_threshold_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_threshold_mode,
                cfar_k_sigma=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_k_sigma,
                cfar_pfa=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_pfa,
                sidelobe_mode=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_mode,
                sidelobe_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_radius_voxels,
                sidelobe_axial_z_radius_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_z_radius_voxels,
                sidelobe_axial_xy_tolerance_voxels=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_axial_xy_tolerance_voxels,
                sidelobe_floor_ratio=DEFAULT_HYBRID_FROZEN_DEFAULTS.sidelobe_floor_ratio,
                max_detections_per_timepoint=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
                guardrail_spike_multiplier=DEFAULT_GUARDRAIL_SETTINGS.spike_multiplier,
                guardrail_min_history=DEFAULT_GUARDRAIL_SETTINGS.min_history,
                guardrail_history_window=DEFAULT_GUARDRAIL_SETTINGS.history_window,
                guardrail_min_absolute_count=DEFAULT_GUARDRAIL_SETTINGS.min_absolute_count,
                guardrail_fallback_threshold=DEFAULT_GUARDRAIL_SETTINGS.fallback_threshold,
                guardrail_fallback_max_detections=DEFAULT_HYBRID_FROZEN_DEFAULTS.max_detections_per_timepoint,
                link_strategy=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_link_strategy,
                max_link_distance_um=DEFAULT_HYBRID_FROZEN_DEFAULTS.cfar_max_link_distance_um,
                max_timepoints=None,
            )
        else:
            graph, _, _, _, _, _ = _build_v9_style_graph(sample_path, max_timepoints=None)
            
        report = evaluate_breakdown(graph, ground_truth)
        reports.append(asdict(report))
        
        # Save incrementally
        with open("submissions/v19_evaluation_breakdown.json", "w") as f:
            json.dump(reports, f, indent=2)
            
    # Compute summary
    summary = {
        "samples_run": len(reports),
        "total_strict_matched_nodes": sum(r["strict_matched_nodes"] for r in reports),
        "total_relaxed_matched_nodes": sum(r["relaxed_matched_nodes"] for r in reports),
        "total_strict_evaluable_edges": sum(r["strict_evaluable_edges"] for r in reports),
        "total_relaxed_evaluable_edges": sum(r["relaxed_evaluable_edges"] for r in reports),
        "total_newly_evaluable_edges": sum(r["newly_evaluable_edges"] for r in reports),
        "total_actionable_edges": sum(r["actionable_edges"] for r in reports),
        "total_theoretical_edges": sum(r["theoretical_edges"] for r in reports),
    }
    
    with open("submissions/v19_evaluation_breakdown_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
        
    print("V19 Audit complete. Wrote submissions/v19_evaluation_breakdown_summary.json")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
