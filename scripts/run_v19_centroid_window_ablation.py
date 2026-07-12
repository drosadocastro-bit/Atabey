import json
from pathlib import Path
import numpy as np
from scipy import ndimage
import copy
import zarr
import dataclasses

import atabey.evaluation.sparse_ground_truth_v19_experimental as exp
from atabey.io.geff_reader import read_geff_graph
from scripts.run_hybrid_submission import build_graph_cfar_sidelobe
from atabey.detection.adaptive import choose_settings_for_sample
from scripts.run_hybrid_train_evaluation import _should_use_cfar_route
from atabey.hybrid_config import DEFAULT_GUARDRAIL_SETTINGS, DEFAULT_HYBRID_FROZEN_DEFAULTS
from atabey.detection.baseline import DEFAULT_VOXEL_SCALE_UM
from atabey.io.zarr_reader import open_competition_array, read_timepoint
from scripts.run_v19_category_a_localization_bias import evaluate_category_a_bias

def refine_detections_com(detections, volume, window_size):
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
        
        if np.sum(crop) > 0:
            com_z, com_y, com_x = ndimage.center_of_mass(crop)
            new_z = z_start + com_z
            new_y = y_start + com_y
            new_x = x_start + com_x
        else:
            new_z, new_y, new_x = float(z0), float(y0), float(x0)
            
        z_um, y_um, x_um = DEFAULT_VOXEL_SCALE_UM.voxel_to_um(new_z, new_y, new_x)
        
        new_d = dataclasses.replace(
            d,
            z=new_z,
            y=new_y,
            x=new_x,
            z_um=z_um,
            y_um=y_um,
            x_um=x_um
        )
        refined_detections.append(new_d)
        
    return refined_detections

def evaluate_window(name: str, window_size, precomputed_graphs, ground_truths, arrays):
    all_offsets = []
    
    for sample_id, (graph, gt, array) in precomputed_graphs.items():
        if window_size is None:
            offsets = evaluate_category_a_bias(graph, gt)
        else:
            # refine graph
            test_graph = copy.deepcopy(graph)
            from collections import defaultdict
            dets_by_t = defaultdict(list)
            for d in test_graph.detections:
                dets_by_t[d.t].append(d)
                
            new_detections = []
            for t, t_dets in dets_by_t.items():
                volume = read_timepoint(array, t)
                refined_t_dets = refine_detections_com(t_dets, volume, window_size)
                new_detections.extend(refined_t_dets)
                
            test_graph.detections = new_detections
            offsets = evaluate_category_a_bias(test_graph, gt)
            
        all_offsets.extend(offsets)
        
    if not all_offsets:
        print(f"\n--- {name} ---")
        print("No Category A edges found.")
        return
        
    all_offsets = np.array(all_offsets)
    mean_offset = np.mean(all_offsets, axis=0)
    std_offset = np.std(all_offsets, axis=0)
    median_offset = np.median(all_offsets, axis=0)
    
    print(f"\n--- {name} ---")
    print(f"Total Nodes Analyzed: {len(all_offsets)}")
    print(f"Mean Offset (Z, Y, X) [um]: {mean_offset}")
    print(f"Median Offset (Z, Y, X) [um]: {median_offset}")


def main():
    print("Starting CFAR Centroid Refinement Window Ablation")
    train_dir = Path("train")
    sample_ids = ["44b6_0113de3b", "44b6_0b24845f", "44b6_0c582fdc", "6bba_05b6850b", "6bba_05db0fb1"]
    
    precomputed_graphs = {}
    
    for sample_id in sample_ids:
        print(f"Precomputing {sample_id}...")
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
            precomputed_graphs[sample_id] = (graph, ground_truth, array)
            
    print("Evaluating windows...")
    evaluate_window("Baseline (No refinement)", None, precomputed_graphs, None, None)
    evaluate_window("Refinement Window 3x3x3", (3, 3, 3), precomputed_graphs, None, None)
    evaluate_window("Refinement Window 5x3x3", (5, 3, 3), precomputed_graphs, None, None)
    evaluate_window("Refinement Window 7x5x5", (7, 5, 5), precomputed_graphs, None, None)
    evaluate_window("Refinement Window 9x5x5", (9, 5, 5), precomputed_graphs, None, None)
    evaluate_window("Refinement Window 11x5x5", (11, 5, 5), precomputed_graphs, None, None)

if __name__ == "__main__":
    main()
