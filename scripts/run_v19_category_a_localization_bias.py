import json
from pathlib import Path
import numpy as np

import atabey.evaluation.sparse_ground_truth_v19_experimental as exp
from atabey.io.geff_reader import read_geff_graph
from scripts.run_hybrid_submission import build_graph_cfar_sidelobe
from atabey.detection.adaptive import choose_settings_for_sample
from scripts.run_hybrid_train_evaluation import _should_use_cfar_route
from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS

def evaluate_category_a_bias(graph, ground_truth):
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
        s_pred = strict_gt_to_pred.get(source_id)
        t_pred = strict_gt_to_pred.get(target_id)
        if s_pred is not None and t_pred is not None:
            strict_evaluable_edges.add((source_id, target_id))
            
        s_pred = relaxed_gt_to_pred.get(source_id)
        t_pred = relaxed_gt_to_pred.get(target_id)
        if s_pred is not None and t_pred is not None:
            relaxed_evaluable_edges.add((source_id, target_id))
            
    newly_evaluable = relaxed_evaluable_edges - strict_evaluable_edges
    
    pred_node_positions = {d.node_id: d.position_um for d in graph.detections}
    gt_node_positions = {n.node_id: n.position_um for n in ground_truth.nodes}
    
    offsets = []
    
    for source_id, target_id in newly_evaluable:
        s_pred = relaxed_gt_to_pred[source_id]
        t_pred = relaxed_gt_to_pred[target_id]
        
        pos_s = np.array(pred_node_positions[s_pred], dtype=float)
        pos_t = np.array(pred_node_positions[t_pred], dtype=float)
        dist = float(np.linalg.norm(pos_s - pos_t))
        
        if dist <= 9.0:
            if (s_pred, t_pred) in predicted_edges:
                # Category A edge! Both source and target missed by 7-14um but are correctly linked.
                # Let's record the 3D offset: Pred - GT
                gt_pos_s = np.array(gt_node_positions[source_id], dtype=float)
                gt_pos_t = np.array(gt_node_positions[target_id], dtype=float)
                
                offsets.append(pos_s - gt_pos_s)
                offsets.append(pos_t - gt_pos_t)
                
    return offsets

def main():
    train_dir = Path("train")
    sample_ids = ["44b6_0113de3b", "44b6_0b24845f", "44b6_0c582fdc", "6bba_05b6850b", "6bba_05db0fb1"]
    
    all_offsets = []
    
    for sample_id in sample_ids:
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
                max_timepoints=100,
            )
            offsets = evaluate_category_a_bias(graph, ground_truth)
            all_offsets.extend(offsets)
            
    if not all_offsets:
        print("No Category A edges found.")
        return
        
    all_offsets = np.array(all_offsets)
    mean_offset = np.mean(all_offsets, axis=0)
    std_offset = np.std(all_offsets, axis=0)
    median_offset = np.median(all_offsets, axis=0)
    abs_mean_offset = np.mean(np.abs(all_offsets), axis=0)
    
    print("\n--- Category A Localization Bias ---")
    print(f"Total Nodes Analyzed (Source + Target of Cat A Edges): {len(all_offsets)}")
    print(f"Mean Offset (Z, Y, X) [um]: {mean_offset}")
    print(f"Median Offset (Z, Y, X) [um]: {median_offset}")
    print(f"Std Dev (Z, Y, X) [um]: {std_offset}")
    print(f"Mean Absolute Error (Z, Y, X) [um]: {abs_mean_offset}")

if __name__ == "__main__":
    main()
