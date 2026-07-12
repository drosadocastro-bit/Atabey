import json
from pathlib import Path
import numpy as np
from scipy import ndimage
import copy
import dataclasses
import warnings
from skimage.filters import threshold_otsu
from collections import defaultdict

from atabey.io.geff_reader import read_geff_graph
from scripts.run_hybrid_submission import build_graph_cfar_sidelobe
from atabey.detection.adaptive import choose_settings_for_sample
from scripts.run_hybrid_train_evaluation import _should_use_cfar_route
from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.detection.baseline import DEFAULT_VOXEL_SCALE_UM, robust_normalize
from atabey.io.zarr_reader import open_competition_array, read_timepoint

from atabey.evaluation.sparse_ground_truth_v19_experimental import match_sparse_centroids_global_greedy as match_sparse_centroids

def extract_match_sets(graph, ground_truth):
    # Same logic as evaluate_category_a_bias but we just want the node sets
    gt_nodes = ground_truth.nodes
    pred_nodes = graph.detections
    
    strict_matches = match_sparse_centroids(
        graph=graph,
        ground_truth=ground_truth,
        radius_um=7.0
    )
    
    relaxed_matches = match_sparse_centroids(
        graph=graph,
        ground_truth=ground_truth,
        radius_um=14.0
    )
    
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
    
    cat_a_pred_nodes = set()
    strict_pred_nodes = set(strict_gt_to_pred.values())
    
    for source_id, target_id in newly_evaluable:
        s_pred = relaxed_gt_to_pred[source_id]
        t_pred = relaxed_gt_to_pred[target_id]
        
        pos_s = np.array([d for d in graph.detections if d.node_id == s_pred][0].position_um, dtype=float)
        pos_t = np.array([d for d in graph.detections if d.node_id == t_pred][0].position_um, dtype=float)
        dist = float(np.linalg.norm(pos_s - pos_t))
        
        if dist <= 9.0:
            if (s_pred, t_pred) in predicted_edges:
                cat_a_pred_nodes.add(s_pred)
                cat_a_pred_nodes.add(t_pred)
                
    return strict_pred_nodes, cat_a_pred_nodes

def refine_detections_otsu(detections, volume, window_size=(7, 5, 5)):
    refined_detections = []
    wz, wy, wx = window_size
    rz, ry, rx = wz // 2, wy // 2, wx // 2
    Z_MAX, Y_MAX, X_MAX = volume.shape
    
    for d in detections:
        z0, y0, x0 = int(round(d.z)), int(round(d.y)), int(round(d.x))
        z_start, z_end = max(0, z0 - rz), min(Z_MAX, z0 + rz + 1)
        y_start, y_end = max(0, y0 - ry), min(Y_MAX, y0 + ry + 1)
        x_start, x_end = max(0, x0 - rx), min(X_MAX, x0 + rx + 1)
        
        crop = volume[z_start:z_end, y_start:y_end, x_start:x_end]
        
        if np.sum(crop) == 0:
            refined_detections.append(d)
            continue
            
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                thresh = threshold_otsu(crop)
                mask = crop >= thresh
            except ValueError:
                mask = crop >= crop.max()
                
        if mask is not None and np.sum(mask) > 0:
            com_z, com_y, com_x = ndimage.center_of_mass(mask)
            new_z = z_start + com_z
            new_y = y_start + com_y
            new_x = x_start + com_x
        else:
            new_z, new_y, new_x = float(z0), float(y0), float(x0)
            
        z_um, y_um, x_um = DEFAULT_VOXEL_SCALE_UM.voxel_to_um(new_z, new_y, new_x)
        
        new_d = dataclasses.replace(d, z=new_z, y=new_y, x=new_x, z_um=z_um, y_um=y_um, x_um=x_um)
        refined_detections.append(new_d)
    return refined_detections

def main():
    train_dir = Path("train")
    sample_ids = ["44b6_0113de3b", "44b6_0b24845f", "44b6_0c582fdc", "6bba_05b6850b", "6bba_05db0fb1"]
    
    # 1. Trace the 280 -> 300 Category A node increase
    baseline_strict_all = set()
    baseline_cata_all = set()
    otsu_strict_all = set()
    otsu_cata_all = set()
    
    # 2. Collision Check for Global Blob approach
    global_collision_counts = defaultdict(int)
    total_cfar_peaks_in_labels = 0
    total_cfar_peaks_no_labels = 0
    
    print("Investigating Ablation Side Effects on 5 Preview Samples...")
    
    for sample_id in sample_ids:
        sample_path = train_dir / f"{sample_id}.zarr"
        ground_truth = read_geff_graph(train_dir / f"{sample_id}.geff")
        profile, settings = choose_settings_for_sample(sample_path)
        array = open_competition_array(sample_path)
        
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
            
            # 1. TRACE NODES
            b_strict, b_cata = extract_match_sets(graph, ground_truth)
            baseline_strict_all.update(b_strict)
            baseline_cata_all.update(b_cata)
            
            test_graph = copy.deepcopy(graph)
            dets_by_t = defaultdict(list)
            for d in test_graph.detections:
                dets_by_t[d.t].append(d)
                
            new_detections = []
            for t, t_dets in dets_by_t.items():
                volume = read_timepoint(array, t)
                refined_t_dets = refine_detections_otsu(t_dets, volume, (7,5,5))
                new_detections.extend(refined_t_dets)
                
                # 2. COLLISION CHECK
                norm_vol = robust_normalize(volume)
                labels, _ = ndimage.label(norm_vol >= 0.65)
                
                for d in t_dets:
                    z, y, x = int(round(d.z)), int(round(d.y)), int(round(d.x))
                    z, y, x = min(z, labels.shape[0]-1), min(y, labels.shape[1]-1), min(x, labels.shape[2]-1)
                    z, y, x = max(z, 0), max(y, 0), max(x, 0)
                    
                    label_id = labels[z, y, x]
                    if label_id > 0:
                        # uniquely identify label across entire sample
                        global_label_id = f"{sample_id}_t{t}_L{label_id}"
                        global_collision_counts[global_label_id] += 1
                        total_cfar_peaks_in_labels += 1
                    else:
                        total_cfar_peaks_no_labels += 1
                        
            test_graph.detections = new_detections
            o_strict, o_cata = extract_match_sets(test_graph, ground_truth)
            otsu_strict_all.update(o_strict)
            otsu_cata_all.update(o_cata)

    print("\n--- 1. Node Tracing (Baseline vs Otsu) ---")
    print(f"Baseline Strict Nodes: {len(baseline_strict_all)}")
    print(f"Otsu Strict Nodes:     {len(otsu_strict_all)}")
    print(f"Baseline Cat A Nodes:  {len(baseline_cata_all)}")
    print(f"Otsu Cat A Nodes:      {len(otsu_cata_all)}")
    
    # Regression: Was in Baseline Strict, now in Otsu Cat A
    regression_nodes = baseline_strict_all.intersection(otsu_cata_all)
    # Improvement: Was NOT in Baseline Strict/Cat A, now in Otsu Cat A
    # (Or was in Baseline >14um, now in Otsu Cat A)
    baseline_all_matched = baseline_strict_all.union(baseline_cata_all)
    improvement_nodes = otsu_cata_all - baseline_all_matched
    
    print(f"\nScenario A (Regression): Nodes pushed OUT of strict into Cat A: {len(regression_nodes)}")
    print(f"Scenario B (Improvement): Nodes pulled IN from >14um to Cat A: {len(improvement_nodes)}")
    
    print("\n--- 2. Global Marker-Based Collision Check ---")
    print(f"Total CFAR peaks falling into a global label: {total_cfar_peaks_in_labels}")
    print(f"Total CFAR peaks NOT in any global label: {total_cfar_peaks_no_labels}")
    
    # Group counts
    distribution = defaultdict(int)
    for count in global_collision_counts.values():
        distribution[count] += 1
        
    print("\nCollision Distribution:")
    for count in sorted(distribution.keys()):
        print(f"Labels containing exactly {count} CFAR peaks: {distribution[count]}")

if __name__ == "__main__":
    main()
